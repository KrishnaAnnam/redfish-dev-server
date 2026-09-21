"""
Contoso CPER/CPAD Catalog
========================

This module is the shared, data-driven protocol description used by the
Contoso error injector, CPER analyzer, and subcomponent analyzers. It is
defined by ``contoso-cper-sections.md`` and contains:

- The fixed Contoso SoC CreatorID (never a user input).
- The Contoso severity encoding (Error Status Register severity field ↔ name).
- Every Contoso CPER section type: its GUID, its subcomponent-instance
  coordinate fields, and its ordered list of error banks.
- For each error bank: the ErrorID ↔ name ↔ typical severity table and the
  layout of that bank's "additional registers".

The encoder, injector, analyzer, and subcomponent analyzers read from this
catalog. Adding a future Contoso generation means adding one entry here rather
than duplicating the protocol definition across those components.

Field-layout codes used by the additional-register tables:
    "b" = int8    "B" = uint8   "H" = uint16   "I" = uint32   "Q" = uint64
    ("array", <code>, (rows, cols)) = a packed array (row-major)
    ("vector", <code>, length) = a packed one-dimensional array
    ("string", <capacity>) = fixed-capacity, NUL-terminated ASCII string
    ("bytes", <length>) = fixed-length byte sequence in wire order
    ("repairs",) = uint8 count followed by sparse six-byte repair entries

All Contoso structures are little-endian and packed (see the sections doc).
"""

# ── Fixed identity ──────────────────────────────────────────────────────────
# The CreatorID identifies the analyzer/endpoint a CPAD is routed to.  Because
# this tool is specific to the Contoso SoC it ALWAYS stamps this CreatorID and
# never exposes it as an input.
CONTOSO_CREATOR_ID = "11111111-2222-3333-4444-555555555555"

# Contoso CPER section format version emitted by this tool. The decoder also
# accepts 1.4 records created before spd_temperature was added.
CONTOSO_SECTION_MAJOR = 1
CONTOSO_SECTION_MINOR = 5
SUPPORTED_SECTION_VERSIONS = frozenset({(1, 4), (1, 5)})

# The RAS API "Inject Error" action (Action Id 0x06).
INJECT_ACTION = {"code": "0x0006", "name": "Inject Error"}
PPR_ACTION = {"code": "0x8001", "name": "Post Package Repair"}
# Compatibility name for callers that specifically request runtime soft PPR.
SPPR_ACTION = PPR_ACTION
PAGE_OFFLINE_ACTION = {"code": "0x8002", "name": "Page Offline"}
REBOOT_WITH_RETRAINING_ACTION = {
    "code": "0x8003",
    "name": "Reboot with Memory Retraining",
}
PAGE_SIZE_BYTES = 4096
SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT = -128


# ── Severity encoding (Error Status Register bits 61:59) ────────────────────
# Maps the Contoso severity name to its 3-bit value in the Error Status
# Register.  The per-error severity in the tables below is the *typical*
# severity; the value packed into the register is authoritative.
SEVERITY_VALUES = {
    "No error logged": 0,
    "Fatal": 1,
    "Uncorrected": 2,
    "Recoverable": 3,
    "Deferred": 4,
    "Corrected": 5,
}


# ── JEP106 manufacturer IDs in DDR5 SPD format ─────────────────────────────
# SPD stores a manufacturer ID as two bytes: the first contains the JEP106
# continuation count in bits 6:0 plus odd parity in bit 7; the second is the
# final JEP106 manufacturer byte, including its odd parity bit.
JEP106_MANUFACTURERS = {
    (0x80, 0x2C): "Micron",
    (0x80, 0xAD): "SK Hynix",
    (0x80, 0xCE): "Samsung",
    (0x04, 0xD5): "Microsoft",
}


def is_valid_spd_manufacturer_id(value):
    """Return whether ``value`` is a valid two-byte SPD manufacturer ID."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    if any(not isinstance(byte, int) or isinstance(byte, bool) or
           not 0 <= byte <= 0xFF for byte in value):
        return False
    continuation, manufacturer = value
    return (continuation.bit_count() % 2 == 1 and
            manufacturer.bit_count() % 2 == 1 and
            manufacturer & 0x7F not in (0, 0x7F))


def decode_spd_manufacturer_id(value):
    """Decode a supported JEP106 ID, or return ``Unknown``/``Invalid``."""
    if not is_valid_spd_manufacturer_id(value):
        return "Invalid"
    return JEP106_MANUFACTURERS.get(tuple(value), "Unknown")


# ── Section-type definitions ────────────────────────────────────────────────
# Each entry mirrors a "CPER Section Type Definition" from the sections doc.
#   guid          : proprietary section-type GUID
#   category       : short error class used by the `list` table
#   subcomponent   : ordered (name, code) fields of the Subcomponent Instance ID
#   banks          : ordered list of error banks (order defines the body layout)
#       name        : exact Error Bank name (used as an input)
#       errors      : { exact error name : (errorID, typical severity name) }
#       additional  : ordered (name, code) additional-register fields
SECTION_TYPES = {
    "CPU Core - First Generation": {
        "guid": "f63f509b-8995-4efd-9144-4b7fed6c4fd3",
        "category": "core",
        "subcomponent": [("chiplet", "H"), ("core", "H")],
        "banks": [
            {
                "name": "Core Errors",
                "errors": {
                    "No Error Logged": (0x00, "No error logged"),
                    "Poison Consumption": (0x01, "Recoverable"),
                    "Transaction Timeout": (0x02, "Fatal"),
                    "Register Parity Error": (0x03, "Fatal"),
                    "Cache Corrected ECC Error": (0x04, "Corrected"),
                    "Cache Uncorrected ECC Error": (0x05, "Deferred"),
                    "Hardware Assert": (0x06, "Fatal"),
                },
                "additional": [
                    ("timeout_transaction_details", "Q"),
                    ("register_parity_details", "Q"),
                    ("cache_location", "Q"),
                    ("assert_details", "Q"),
                    ("core_debug_details", "Q"),
                ],
            },
        ],
    },
    "Memory Controller - First Generation": {
        "guid": "e01ce992-d080-43f4-8a2c-df8a9d81eb4e",
        "category": "memory",
        "subcomponent": [("chiplet", "H"), ("controller", "H")],
        "banks": [
            {
                "name": "DRAM Errors",
                "errors": {
                    "No Error Logged": (0x00, "No error logged"),
                    "Corrected Memory ECC Error": (0x01, "Corrected"),
                    "Uncorrected Memory ECC Error": (0x02, "Deferred"),
                    "Command/Address Parity Error": (0x03, "Uncorrected"),
                },
                # DDR5 x4: explicit device plus 4 DQs, 16 beats per DQ.
                "additional": [
                    ("channel", "B"),
                    ("dimm", "B"),
                    ("subchannel", "B"),
                    ("rank", "B"),
                    ("device", "B"),
                    ("bank_group", "B"),
                    ("bank", "B"),
                    ("row", "I"),
                    ("column", "H"),
                    ("beat_mask", ("vector", "H", 4)),
                    ("serial_number", ("string", 19)),
                    ("part_number", ("string", 25)),
                    ("module_manufacturer_id", ("bytes", 2)),
                    ("dram_manufacturer_id", ("bytes", 2)),
                    ("spd_temperature", "b"),
                    ("total_memory_bytes", "Q"),
                    ("memory_repair_capabilities", "B"),
                    ("reserved", "H"),
                    ("repairs", ("repairs",)),
                ],
            },
            {
                "name": "Other Errors",
                "errors": {
                    "No Error Logged": (0x00, "No error logged"),
                    "DLL Lock Error": (0x01, "Fatal"),
                    "Internal Corrected Error": (0x02, "Corrected"),
                    "Internal Uncorrected Error": (0x03, "Fatal"),
                    "Mesh Error": (0x04, "Fatal"),
                },
                "additional": [
                    ("DllLockLossInfo", "I"),
                    ("ErrorStructure", "H"),
                    ("OtherMeshEntity", "H"),
                ],
            },
        ],
    },
}


# ── Lookup helpers ──────────────────────────────────────────────────────────

def resolve_section(section_name):
    """Return the section-type definition for an exact section name."""
    try:
        return SECTION_TYPES[section_name]
    except KeyError:
        raise KeyError(
            f"Unknown section type '{section_name}'. "
            f"Known: {', '.join(SECTION_TYPES)}")


def get_bank(section, bank_name):
    """Return the bank definition for an exact bank name within a section."""
    for bank in section["banks"]:
        if bank["name"] == bank_name:
            return bank
    known = ", ".join(b["name"] for b in section["banks"])
    raise KeyError(f"Unknown error bank '{bank_name}'. Known: {known}")


def resolve_error(section_name, bank_name, error_name):
    """Map (section, bank, error name) → (errorID, typical severity name)."""
    section = resolve_section(section_name)
    bank = get_bank(section, bank_name)
    try:
        return bank["errors"][error_name]
    except KeyError:
        known = ", ".join(bank["errors"])
        raise KeyError(f"Unknown error '{error_name}'. Known: {known}")


def error_name_from_id(section_name, bank_name, error_id):
    """Reverse lookup: errorID → error name (used by `decode`)."""
    section = resolve_section(section_name)
    bank = get_bank(section, bank_name)
    for name, (eid, _sev) in bank["errors"].items():
        if eid == error_id:
            return name
    return None


def section_name_from_guid(guid):
    """Reverse lookup: section-type GUID → section name (used by `decode`)."""
    guid = guid.lower()
    for name, section in SECTION_TYPES.items():
        if section["guid"].lower() == guid:
            return name
    return None


def iter_all_errors():
    """Yield one record per injectable error, for the `list` table.

    Skips the "No Error Logged" placeholder (errorID 0), which is not an
    injectable error.
    """
    for section_name, section in SECTION_TYPES.items():
        for bank in section["banks"]:
            for error_name, (error_id, severity) in bank["errors"].items():
                if error_id == 0:
                    continue
                yield {
                    "category": section["category"],
                    "section_type": section_name,
                    "bank": bank["name"],
                    "error_name": error_name,
                    "error_id": error_id,
                    "severity": severity,
                }
