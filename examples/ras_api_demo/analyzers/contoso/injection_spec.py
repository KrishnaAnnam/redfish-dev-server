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
import copy
import uuid
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.plugins.ras.memory_address_translation import (  # noqa: E402
    MemoryAddressConfiguration,
    MemoryChannelAddress,
    MemoryOrganization,
    memory_address_to_physical_address,
    physical_address_to_memory_address,
)

from contoso_catalog import (
    SECTION_TYPES,
    SEVERITY_VALUES,
    resolve_section,
    resolve_error,
    get_bank,
    is_valid_spd_manufacturer_id,
    SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT,
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
# The DRAM error bank logs an explicit device plus beat_mask[DQ], where each
# element is a 16-bit mask (one bit per beat). Rather than hand-editing it, users describe
# failing beats declaratively with a ``beatErrors`` list, e.g.:
#
#   "beatErrors": [ { "dram": 3, "dq": 2, "beats": "0,5,15" } ]
#
# Each of dram / dq / beats accepts an int, a list, "all", a comma list, or a
# "lo-hi" range (or a combination like "0,3-5").  Entries OR together onto the
# zero-initialised vector. All entries must select the same DRAM device.
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
    additional = section.get("additional", {})
    masks = additional.get("beat_mask")
    if not isinstance(masks, list) or len(masks) != 4:
        raise ValueError("beatErrors given but this section has no beat_mask vector")

    selected_device = None
    for entry in entries:
        drams = parse_index_set(entry.get("dram"), 0, 9)
        if len(drams) != 1:
            raise ValueError("each beatErrors entry must select exactly one DRAM")
        device = drams[0]
        if selected_device is not None and device != selected_device:
            raise ValueError("all beatErrors entries must select the same DRAM")
        selected_device = device
        dqs = parse_index_set(entry.get("dq", "all"), 0, len(masks) - 1)
        beats = parse_index_set(entry.get("beats", "all"), 0, _NUM_BEATS - 1)
        bits = 0
        for b in beats:
            bits |= (1 << b)
        for q in dqs:
            masks[q] = as_int(masks[q]) | bits
    additional["device"] = selected_device


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
        if name == "spd_temperature":
            out[name] = None
        elif isinstance(code, tuple) and code[0] == "array":
            _, _elem, (rows, cols) = code
            out[name] = [[0] * cols for _ in range(rows)]
        elif isinstance(code, tuple) and code[0] == "vector":
            _, _elem, length = code
            out[name] = [0] * length
        elif isinstance(code, tuple) and code[0] == "repairs":
            out[name] = []
        elif isinstance(code, tuple) and code[0] == "memory_organization":
            out[name] = {
                "version": 1,
                "address_translation": "contoso-simple-v1",
                "dimm_size_gib": 64,
            }
        elif isinstance(code, tuple) and code[0] == "string":
            out[name] = ""
        elif isinstance(code, tuple) and code[0] == "bytes":
            _, length = code
            out[name] = ["0x00"] * length
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
        "addressSource": "memory",
        "socket": 0,
        "byteInColumn": 0,
        "subcomponent": {name: 0 for name, _ in section["subcomponent"]},
        "errorStatus": {"addressValid": True, "overflow": False},
        "errorAddress": "0x0",
        "misc0": {"injected": True, "ce_count": 0},
        "misc1": "0x0",
        "additional": _default_additional(bank["additional"]),
    }
    for name in ("dram_manufacturer_id", "module_manufacturer_id"):
        if name in section_block["additional"]:
            section_block["additional"][name] = ["0x04", "0xD5"]
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


def _memory_address_configuration(spec):
    organization = spec["section"]["additional"].get("memory_organization")
    if not isinstance(organization, dict):
        raise ValueError(
            "section.additional.memory_organization must be an object")
    return MemoryAddressConfiguration(MemoryOrganization(
        version=as_int(organization.get("version")),
        address_translation=organization.get("address_translation"),
        dimm_size_gib=as_int(organization.get("dimm_size_gib")),
    ))


def synchronize_memory_address(spec):
    """Reconcile physical and hierarchy addresses for a DRAM error spec."""
    error = spec.get("error", {})
    if (error.get("sectionType") != "Memory Controller - First Generation"
            or error.get("errorBank") != "DRAM Errors"):
        return spec
    section = spec["section"]
    source = section.get("addressSource", "memory")
    if source not in {"memory", "physical", "both"}:
        raise ValueError(
            "section.addressSource must be memory, physical, or both")
    configuration = _memory_address_configuration(spec)
    subcomponent = section["subcomponent"]
    additional = section["additional"]
    hierarchy = MemoryChannelAddress(
        socket=as_int(section.get("socket", 0)),
        chiplet=as_int(subcomponent.get("chiplet", 0)),
        memory_controller=as_int(subcomponent.get("controller", 0)),
        channel=as_int(additional.get("channel", 0)),
        dimm=as_int(additional.get("dimm", 0)),
        subchannel=as_int(additional.get("subchannel", 0)),
        rank=as_int(additional.get("rank", 0)),
        bank_group=as_int(additional.get("bank_group", 0)),
        bank=as_int(additional.get("bank", 0)),
        row=as_int(additional.get("row", 0)),
        column=as_int(additional.get("column", 0)),
        byte_in_column=as_int(section.get("byteInColumn", 0)),
    )
    physical = as_int(section.get("errorAddress", 0))
    if source in {"memory", "both"}:
        encoded = memory_address_to_physical_address(
            hierarchy, configuration)
        if source == "both" and physical != encoded:
            raise ValueError(
                f"physical address {physical:#x} does not match hierarchy "
                f"address {encoded:#x}")
        section["errorAddress"] = hex(encoded)
    else:
        decoded = physical_address_to_memory_address(
            physical, configuration)
        section["socket"] = decoded.socket
        section["byteInColumn"] = decoded.byte_in_column
        subcomponent.update({
            "chiplet": decoded.chiplet,
            "controller": decoded.memory_controller,
        })
        additional.update({
            "channel": decoded.channel,
            "dimm": decoded.dimm,
            "subchannel": decoded.subchannel,
            "rank": decoded.rank,
            "bank_group": decoded.bank_group,
            "bank": decoded.bank,
            "row": decoded.row,
            "column": decoded.column,
        })
    return spec


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
    try:
        synchronize_memory_address(copy.deepcopy(spec))
    except (KeyError, ValueError, TypeError) as exc:
        problems.append(str(exc))
    cpad = spec["cpad"]
    fru_id = cpad.get("fruID")
    fru_text = cpad.get("fruText")
    try:
        parsed_fru = uuid.UUID(str(fru_id).strip().strip("{}"))
        if parsed_fru.int == 0:
            problems.append("cpad.fruID must not be the zero GUID.")
    except (ValueError, AttributeError):
        problems.append("cpad.fruID must be a valid GUID.")
    if not isinstance(fru_text, str) or not fru_text.strip():
        problems.append("cpad.fruText must be a non-empty string.")
    elif len(fru_text.strip().encode("utf-8")) > 19:
        problems.append("cpad.fruText must fit in 19 UTF-8 bytes.")

    section_name = error.get("sectionType")
    bank_name = error.get("errorBank")
    error_name = error.get("errorName")

    bank = None
    try:
        error_id, _severity = resolve_error(section_name, bank_name, error_name)
        bank = get_bank(resolve_section(section_name), bank_name)
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

    reserved = spec.get("section", {}).get("additional", {}).get("reserved", 0)
    try:
        if as_int(reserved) != 0:
            problems.append("section.additional.reserved must be zero.")
    except (ValueError, TypeError):
        problems.append("section.additional.reserved must be zero.")

    capabilities = spec.get("section", {}).get("additional", {}).get(
        "memory_repair_capabilities", 0)
    try:
        if as_int(capabilities) & ~0x07:
            problems.append(
                "section.additional.memory_repair_capabilities has reserved bits set.")
    except (ValueError, TypeError):
        problems.append(
            "section.additional.memory_repair_capabilities must be a byte.")

    spd_temperature = spec.get("section", {}).get("additional", {}).get(
        "spd_temperature")
    if spd_temperature is not None:
        try:
            parsed_temperature = as_int(spd_temperature)
            if not SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT < parsed_temperature <= 127:
                problems.append(
                    "section.additional.spd_temperature must be null or in "
                    "the range -127..127 degrees Celsius.")
        except (ValueError, TypeError):
            problems.append(
                "section.additional.spd_temperature must be null or an integer.")

    if bank:
        additional = spec.get("section", {}).get("additional", {})
        for name, code in bank["additional"]:
            if not (isinstance(code, tuple) and code[0] == "string"):
                continue
            _, capacity = code
            value = additional.get(name, "")
            if not isinstance(value, str):
                problems.append(f"section.additional.{name} must be a string.")
                continue
            if "\x00" in value:
                problems.append(
                    f"section.additional.{name} must not contain NUL characters.")
                continue
            try:
                encoded = value.encode("ascii")
            except UnicodeEncodeError:
                problems.append(
                    f"section.additional.{name} must contain only ASCII characters.")
                continue
            if len(encoded) >= capacity:
                problems.append(
                    f"section.additional.{name} must be at most "
                    f"{capacity - 1} characters.")

        for name, code in bank["additional"]:
            if not (isinstance(code, tuple) and code[0] == "bytes"):
                continue
            _, length = code
            value = additional.get(name)
            if not isinstance(value, (list, tuple)) or len(value) != length:
                problems.append(
                    f"section.additional.{name} must contain exactly "
                    f"{length} bytes.")
                continue
            try:
                parsed = [as_int(byte) for byte in value]
            except (ValueError, TypeError):
                problems.append(
                    f"section.additional.{name} values must be bytes (0..255).")
                continue
            if any(isinstance(byte, bool) for byte in value) or \
                    any(not 0 <= byte <= 0xFF for byte in parsed):
                problems.append(
                    f"section.additional.{name} values must be bytes (0..255).")
            elif name in ("dram_manufacturer_id", "module_manufacturer_id") and \
                    not is_valid_spd_manufacturer_id(parsed):
                problems.append(
                    f"section.additional.{name} must be a valid odd-parity "
                    "JEP106 ID in SPD byte order.")

    # Validate beat-error authoring entries (one DRAM 0-9, DQ 0-3, beat 0-15).
    selected_devices = set()
    for entry in spec.get("section", {}).get("beatErrors", []) or []:
        try:
            devices = parse_index_set(entry.get("dram"), 0, 9)
            if len(devices) != 1:
                raise ValueError("exactly one DRAM must be selected")
            selected_devices.update(devices)
            parse_index_set(entry.get("dq", "all"), 0, 3)
            parse_index_set(entry.get("beats", "all"), 0, _NUM_BEATS - 1)
        except (ValueError, TypeError) as exc:
            problems.append(f"Invalid beatErrors entry {entry}: {exc}")
    if len(selected_devices) > 1:
        problems.append("All beatErrors entries must select the same DRAM.")

    repairs = spec.get("section", {}).get("additional", {}).get("repairs", [])
    if not isinstance(repairs, list):
        problems.append("section.additional.repairs must be a list.")
    else:
        seen_repairs = set()
        required = ("subchannel", "rank", "device", "bank_group", "bank", "count")
        for index, repair in enumerate(repairs):
            try:
                values = tuple(as_int(repair[name]) for name in required)
            except (KeyError, ValueError, TypeError):
                problems.append(
                    f"section.additional.repairs[{index}] must contain byte values "
                    f"for {', '.join(required)}.")
                continue
            if any(not 0 <= value <= 0xFF for value in values):
                problems.append(
                    f"section.additional.repairs[{index}] values must be bytes (0..255).")
                continue
            key = values[:-1]
            if values[-1] == 0:
                problems.append(
                    f"section.additional.repairs[{index}].count must be 1..255.")
            if key in seen_repairs:
                problems.append(
                    f"section.additional.repairs[{index}] duplicates a bank address.")
            seen_repairs.add(key)

    return problems


# ── Resolve to encoder inputs ───────────────────────────────────────────────

def to_encoder_fields(spec):
    """Resolve a validated spec into the low-level ``fields`` dict the encoder
    needs, plus the resolved errorID/severity."""
    synchronize_memory_address(spec)
    error = spec["error"]
    section = spec["section"]

    error_id, typical_severity = resolve_error(
        error["sectionType"], error["errorBank"], error["errorName"])
    severity_name = error.get("severityOverride") or typical_severity
    severity_value = SEVERITY_VALUES[severity_name]

    # Expand any declarative beat errors onto the beat_mask vector first.
    compile_beat_errors(section)

    status = section.get("errorStatus", {})
    misc0 = section.get("misc0", {})

    # Resolve additional register values (arrays stay nested int lists).
    additional = {}
    bank = get_bank(resolve_section(error["sectionType"]), error["errorBank"])
    supplied = section.get("additional", {})
    for name, code in bank["additional"]:
        if name == "spd_temperature":
            default = None
        elif isinstance(code, tuple) and code[0] in ("vector", "repairs"):
            default = []
        elif isinstance(code, tuple) and code[0] == "string":
            default = ""
        else:
            default = 0
        value = supplied.get(name, default)
        if isinstance(code, tuple) and code[0] == "string":
            additional[name] = value
        elif isinstance(code, tuple) and code[0] == "bytes":
            additional[name] = [as_int(byte) for byte in value]
        elif isinstance(code, tuple) and code[0] == "repairs":
            additional[name] = [
                {key: as_int(entry[key]) for key in
                 ("subchannel", "rank", "device", "bank_group", "bank", "count")}
                for entry in value
            ]
        elif isinstance(code, tuple) and code[0] == "vector":
            additional[name] = [as_int(cell) for cell in value]
        elif isinstance(code, tuple) and code[0] == "memory_organization":
            additional[name] = value
        elif isinstance(value, list):
            additional[name] = [[as_int(c) for c in row] for row in value]
        elif name == "spd_temperature" and value is None:
            additional[name] = SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT
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
