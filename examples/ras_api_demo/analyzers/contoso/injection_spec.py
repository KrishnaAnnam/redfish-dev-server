"""
Injection Spec Model
====================

The injection spec is the editable JSON document a user works with.  It has
three blocks (see ``error-injector-contoso.md``):

    cpad     — CPAD targeting / header fields (platformID, partitionID, ...).
               CreatorID is NOT here — it is always the Contoso CreatorID.
    error    — the human-friendly selector (section type, bank, error name).
    section  — every register logged in the CPER section body.

This module builds a fully-defaulted template for a chosen error, loads/validates
an edited spec, and resolves a spec into the low-level values the encoder needs.
"""

import json

from contoso_catalog import (
    SECTION_TYPES,
    SEVERITY_VALUES,
    resolve_section,
    resolve_error,
)

# Sensible defaults for the demo platform (user edits these).
DEFAULT_PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"
DEFAULT_PARTITION_ID = "22222222-3333-4444-5555-666666666666"
DEFAULT_FRU_ID = "75824856-bd36-2cc8-61f4-39bb3276da2a"


# ── Value parsing ───────────────────────────────────────────────────────────

def as_int(value):
    """Accept an int or a decimal/hex ("0x..") string and return an int."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return int(str(value), 0)


# ── Beat-mask authoring (beatErrors → beat_mask grid) ────────────────────────
#
# The DRAM error bank logs a beat_mask[DRAM][DQ] where each element is a 16-bit
# mask (one bit per beat).  Rather than hand-editing that grid, users describe
# failing beats declaratively with a ``beatErrors`` list, e.g.:
#
#   "beatErrors": [ { "dram": 3, "dq": 2, "beats": "0,5,15" } ]
#
# Each of dram / dq / beats accepts an int, a list, "all", a comma list, or a
# "lo-hi" range (or a combination like "0,3-5").  Entries OR together onto the
# zero-initialised grid.
_NUM_BEATS = 16   # bits per DQ beat_mask element (uint16), one per beat


def parse_index_set(value, lo, hi):
    """Expand an index spec into a sorted list of ints within [lo, hi].

    Accepts an int, a list of ints, or a string: "all", "N", "N,M", a "lo-hi"
    range, or a combination such as "0,3-5,9".  Raises ValueError if any value
    falls outside [lo, hi].
    """
    result = set()

    def add_token(tok):
        tok = str(tok).strip().lower()
        if tok == "all":
            result.update(range(lo, hi + 1))
        elif "-" in tok:
            a, b = tok.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        elif tok != "":
            result.add(int(tok))

    if isinstance(value, bool):
        raise ValueError(f"invalid index value: {value!r}")
    elif isinstance(value, int):
        result.add(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            add_token(item)
    else:
        for token in str(value).split(","):
            add_token(token)

    for v in result:
        if not (lo <= v <= hi):
            raise ValueError(f"index {v} is out of range [{lo}..{hi}]")
    return sorted(result)


def compile_beat_errors(section):
    """Overlay a section's ``beatErrors`` list onto its ``beat_mask`` grid.

    Mutates ``section['additional']['beat_mask']`` in place (OR-ing bits).  A
    no-op if the section has no beatErrors or no beat_mask (non-DRAM sections).
    """
    entries = section.get("beatErrors")
    if not entries:
        return
    grid = section.get("additional", {}).get("beat_mask")
    if not isinstance(grid, list) or not grid or not isinstance(grid[0], list):
        raise ValueError("beatErrors given but this section has no beat_mask grid")

    num_drams = len(grid)
    num_dqs = len(grid[0])
    for entry in entries:
        drams = parse_index_set(entry.get("dram", "all"), 0, num_drams - 1)
        dqs = parse_index_set(entry.get("dq", "all"), 0, num_dqs - 1)
        beats = parse_index_set(entry.get("beats", "all"), 0, _NUM_BEATS - 1)
        bits = 0
        for b in beats:
            bits |= (1 << b)
        for d in drams:
            for q in dqs:
                grid[d][q] = as_int(grid[d][q]) | bits


# ── Template generation ─────────────────────────────────────────────────────

def _find_bank_for_error(section, error_name):
    """Return the bank in ``section`` that defines ``error_name``."""
    for bank in section["banks"]:
        if error_name in bank["errors"]:
            return bank
    known = ", ".join(
        e for b in section["banks"] for e in b["errors"] if b["errors"][e][0] != 0)
    raise KeyError(f"Unknown error '{error_name}'. Known: {known}")


def _default_additional(fields):
    """Build a defaulted additional-register dict that shows each field's shape."""
    out = {}
    for name, code in fields:
        if isinstance(code, tuple):            # array, e.g. beat_mask[10][4]
            _, _elem, (rows, cols) = code
            out[name] = [[0] * cols for _ in range(rows)]
        elif code == "Q":                      # 64-bit → hex string for readability
            out[name] = "0x0"
        else:
            out[name] = 0
    return out


def build_template(section_name, error_name):
    """Return a fully-populated injection spec for the chosen error."""
    section = resolve_section(section_name)
    bank = _find_bank_for_error(section, error_name)
    fru_text = "CPU Core 3" if section["category"] == "core" else "DIMM A1"

    section_block = {
        "subcomponent": {name: 0 for name, _ in section["subcomponent"]},
        "errorStatus": {"addressValid": True, "overflow": False},
        "errorAddress": "0x0",
        "misc0": {"injected": True, "ce_count": 0},
        "misc1": "0x0",
        "additional": _default_additional(bank["additional"]),
    }
    # DRAM sections can author beat errors declaratively (see compile_beat_errors).
    if any(name == "beat_mask" for name, _ in bank["additional"]):
        section_block["beatErrors"] = []

    return {
        "cpad": {
            "platformID": DEFAULT_PLATFORM_ID,
            "partitionID": DEFAULT_PARTITION_ID,
            "revision": {"major": 1, "minor": 0},
            "urgency": False,
            "fruID": DEFAULT_FRU_ID,
            "fruText": fru_text,
        },
        "error": {
            "sectionType": section_name,
            "errorBank": bank["name"],
            "errorName": error_name,
            "severityOverride": None,
            "injected": True,
            "occurrence": "immediate",
        },
        "section": section_block,
    }


# ── Load / validate ─────────────────────────────────────────────────────────

def load_spec(path):
    """Read and parse an injection spec JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def validate_spec(spec):
    """Validate a spec against the catalog and the demo rules.

    Returns a list of human-readable problems (empty list means valid).
    Any user-supplied ``creatorID`` is ignored, not honored.
    """
    problems = []
    for block in ("cpad", "error", "section"):
        if block not in spec:
            problems.append(f"Missing '{block}' block.")
    if problems:
        return problems

    error = spec["error"]
    section_name = error.get("sectionType")
    bank_name = error.get("errorBank")
    error_name = error.get("errorName")

    try:
        error_id, _severity = resolve_error(section_name, bank_name, error_name)
        if error_id == 0:
            problems.append("'No Error Logged' is not an injectable error.")
    except KeyError as exc:
        problems.append(str(exc))

    if error.get("occurrence", "immediate") != "immediate":
        problems.append("Only 'immediate' occurrence is supported in this demo.")
    if not error.get("injected", True):
        problems.append("This demo only injects/spoofs errors ('injected' must be true).")

    override = error.get("severityOverride")
    if override is not None and override not in SEVERITY_VALUES:
        problems.append(
            f"Unknown severityOverride '{override}'. "
            f"Known: {', '.join(SEVERITY_VALUES)}")

    # Validate beat-error authoring entries (DRAM 0-9, DQ 0-3, beat 0-15).
    for entry in spec.get("section", {}).get("beatErrors", []) or []:
        try:
            parse_index_set(entry.get("dram", "all"), 0, 9)
            parse_index_set(entry.get("dq", "all"), 0, 3)
            parse_index_set(entry.get("beats", "all"), 0, _NUM_BEATS - 1)
        except (ValueError, TypeError) as exc:
            problems.append(f"Invalid beatErrors entry {entry}: {exc}")

    return problems


# ── Resolve to encoder inputs ───────────────────────────────────────────────

def to_encoder_fields(spec):
    """Resolve a validated spec into the low-level ``fields`` dict the encoder
    needs, plus the resolved errorID/severity."""
    error = spec["error"]
    section = spec["section"]

    error_id, typical_severity = resolve_error(
        error["sectionType"], error["errorBank"], error["errorName"])
    severity_name = error.get("severityOverride") or typical_severity
    severity_value = SEVERITY_VALUES[severity_name]

    # Expand any declarative beat errors onto the beat_mask grid first.
    compile_beat_errors(section)

    status = section.get("errorStatus", {})
    misc0 = section.get("misc0", {})

    # Resolve additional register values (ints; arrays stay nested int lists).
    additional = {}
    for name, value in section.get("additional", {}).items():
        if isinstance(value, list):
            additional[name] = [[as_int(c) for c in row] for row in value]
        else:
            additional[name] = as_int(value)

    fields = {
        "subcomponent": {k: as_int(v) for k, v in section.get("subcomponent", {}).items()},
        "error_status": (
            bool(status.get("addressValid", False)),
            bool(status.get("overflow", False)),
            severity_value,
            error_id,
        ),
        "error_address": as_int(section.get("errorAddress", 0)),
        "misc0": (bool(misc0.get("injected", True)), as_int(misc0.get("ce_count", 0))),
        "misc1": as_int(section.get("misc1", 0)),
        "additional": additional,
    }
    return fields
