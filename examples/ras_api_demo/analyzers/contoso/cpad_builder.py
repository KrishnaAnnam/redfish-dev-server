"""
CPAD Builder
============

Turns a resolved injection into a binary ``.cpad`` file, and reads one back.

Division of labor (see the plan in ``error-injector-contoso.md``):
- We build the *standard* CPAD JSON envelope here (header + one section
  descriptor), carrying the Contoso section body as an opaque, base64-encoded
  "Unknown" section.
- libcper's ``cpad-convert`` assembles/parses the binary envelope (signature,
  layout).  It treats the Contoso section-type GUID as opaque and copies our
  body bytes verbatim.

Single error per CPAD: exactly one section.  For a single section the fixed
header + one descriptor occupy 202 bytes, so:
    sectionOffset = 202
    sectionLength = len(body)
    recordLength  = 202 + len(body)
(verified empirically against the bundled libcper build).
"""

import os
import json
import base64
import struct
import subprocess
import tempfile
from pathlib import Path

from contoso_catalog import CONTOSO_CREATOR_ID, INJECT_ACTION

# Fixed envelope geometry for a single-section CPAD.
SINGLE_SECTION_OFFSET = 202

# Confidence for an injected error is always 100: the operator explicitly ran
# the inject command, so we are certain the action is intended.  (Confidence is
# a section-descriptor field per the CPAD standard; cpad-convert sets its
# validation bit automatically when the "confidence" key is present.)
INJECTION_CONFIDENCE = 100

# Project root: Demos/RasApi/analyzers/contoso/ → up 4 → repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
LIBCPER_BUILD = PROJECT_ROOT / "src" / "plugins" / "ras" / "libcper" / "build"
CPAD_CONVERT = LIBCPER_BUILD / "cpad-convert"


# ── libcper invocation ──────────────────────────────────────────────────────

def _run_cpad_convert(args):
    """Run cpad-convert from its build dir with LD_LIBRARY_PATH set."""
    if not CPAD_CONVERT.exists():
        raise FileNotFoundError(
            f"cpad-convert not found at {CPAD_CONVERT}. Build it with build_libcper.sh.")
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{LIBCPER_BUILD}:{env.get('LD_LIBRARY_PATH', '')}"
    proc = subprocess.run(
        [str(CPAD_CONVERT), *args],
        cwd=str(LIBCPER_BUILD), env=env,
        capture_output=True, text=True, timeout=15)
    return proc


# ── Build (inject) ──────────────────────────────────────────────────────────

def build_cpad_json(spec, section_guid, body):
    """Compose the standard CPAD JSON for one Contoso section body.

    The CreatorID is ALWAYS the Contoso CreatorID, regardless of the spec.
    """
    cpad = spec.get("cpad", {})
    body_len = len(body)
    # Revision is set by the injector and copied into the CPER by the endpoint.
    revision = cpad.get("revision") or {"major": 1, "minor": 0}
    return {
        "header": {
            "revision": revision,
            "sectionCount": 1,
            "urgency": 1 if cpad.get("urgency") else 0,
            # The timestamp is assigned by the RAS API endpoint (here, the BMC)
            # when it logs the resulting CPER — not by the injector.  Emit an
            # "unassigned" epoch sentinel so the CPAD binary stays valid.
            "timestamp": "1970-01-01T00:00:00+00:00",
            "timestampIsPrecise": False,
            "recordLength": SINGLE_SECTION_OFFSET + body_len,
            "platformID": cpad.get("platformID"),
            "partitionID": cpad.get("partitionID"),
            "creatorID": CONTOSO_CREATOR_ID,          # forced — never a user input
            # recordID is assigned by the RAS API endpoint (here, the BMC) when
            # it logs the resulting CPER — not by the injector.  0 = unassigned.
            "recordID": 0,
            "flags": 0,
        },
        "sectionDescriptors": [
            {
                "sectionOffset": SINGLE_SECTION_OFFSET,
                "sectionLength": body_len,
                "revision": revision,
                "flags": 0,
                "confidence": INJECTION_CONFIDENCE,
                "sectionType": {"data": section_guid, "type": "Unknown"},
                "fruID": cpad.get("fruID", "00000000-0000-0000-0000-000000000000"),
                "fruText": cpad.get("fruText", ""),
                "actionID": dict(INJECT_ACTION),
            }
        ],
        "sections": [
            {"Unknown": {"data": base64.b64encode(body).decode("ascii")}}
        ],
    }


def write_cpad(cpad_json, out_path):
    """Write a binary .cpad from a CPAD JSON via libcper's cpad-convert."""
    out_path = str(Path(out_path).resolve())
    with tempfile.NamedTemporaryFile("w", suffix=".cpad.json", delete=False) as tmp:
        json.dump(cpad_json, tmp)
        tmp_path = tmp.name
    try:
        proc = _run_cpad_convert(["to-cpad", tmp_path, "--out", out_path, "--no-validate"])
        if proc.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(f"cpad-convert failed: {proc.stderr.strip()}")
    finally:
        os.unlink(tmp_path)
    return out_path


# ── Read (decode) ───────────────────────────────────────────────────────────

def read_cpad(cpad_path):
    """Parse a binary .cpad into CPAD JSON via libcper's cpad-convert."""
    cpad_path = str(Path(cpad_path).resolve())
    proc = _run_cpad_convert(["to-json", cpad_path])
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"cpad-convert to-json failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def extract_section_body(cpad_json):
    """Return (section_guid, body_bytes) from a parsed CPAD JSON."""
    descriptor = cpad_json["sectionDescriptors"][0]
    guid = descriptor["sectionType"]["data"]
    b64 = cpad_json["sections"][0]["Unknown"]["data"]
    return guid, base64.b64decode(b64)
