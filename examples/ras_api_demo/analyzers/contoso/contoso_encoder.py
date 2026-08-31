"""
Contoso Section Body Encoder / Decoder
======================================

Packs and unpacks the *proprietary* Contoso CPER section body — the part that
libcper does not understand.  Everything here follows the "Contoso Standard
Section Layout" in ``contoso-cper-sections.md`` and is little-endian / packed.

Body layout (single error per CPAD — one section, all of the section type's
banks are present, but only the selected bank carries the error):

    [ Section Header            8 bytes ]
    [ Error Bank 0             40 bytes ]
    [ Error Bank 1 ...         40 bytes each (if the section type has more) ]
    [ Additional registers for Bank 0 ]
    [ Additional registers for Bank 1 ... ]

Only libcper-agnostic ``struct`` packing lives here; the CPAD envelope is built
elsewhere (``cpad_builder.py``).
"""

import struct

from contoso_catalog import (
    CONTOSO_SECTION_MAJOR,
    CONTOSO_SECTION_MINOR,
    SEVERITY_VALUES,
    resolve_section,
    get_bank,
)

# Fixed structure sizes from the sections doc.
SECTION_HEADER_SIZE = 8   # major, minor, num_banks, subcomponent instance ID
ERROR_BANK_SIZE = 40      # status, address, misc0, misc1, addl_offset, reserved

_SCALAR_SIZES = {"B": 1, "H": 2, "I": 4, "Q": 8}


# ── Register bitfield helpers (one per Error Status / Misc table) ────────────

def pack_error_status(addr_valid, overflow, severity_value, error_id):
    """Assemble the 64-bit Error Status Register.

    Layout (bit 0 = LSB), per the sections doc:
        bit  63     Address Valid
        bit  62     Overflow
        bits 61:59  Severity (3 bits)
        bits 58:16  Reserved
        bits 15:0   errorID
    """
    value = 0
    if addr_valid:
        value |= 1 << 63
    if overflow:
        value |= 1 << 62
    value |= (severity_value & 0x7) << 59
    value |= error_id & 0xFFFF
    return value


def unpack_error_status(value):
    """Inverse of :func:`pack_error_status`."""
    return {
        "addressValid": bool(value >> 63 & 0x1),
        "overflow": bool(value >> 62 & 0x1),
        "severity_value": value >> 59 & 0x7,
        "error_id": value & 0xFFFF,
    }


def pack_misc0(injected, ce_count, impl=0):
    """Assemble the 64-bit Misc 0 register.

    Layout:
        bit  63     Injected (set if injected/spoofed, not natural)
        bits 62:16  Implementation specific (47 bits)
        bits 15:0   ce_count (corrected-error count)
    """
    value = 0
    if injected:
        value |= 1 << 63
    value |= (impl & ((1 << 47) - 1)) << 16
    value |= ce_count & 0xFFFF
    return value


def unpack_misc0(value):
    """Inverse of :func:`pack_misc0`."""
    return {
        "injected": bool(value >> 63 & 0x1),
        "impl": value >> 16 & ((1 << 47) - 1),
        "ce_count": value & 0xFFFF,
    }


# ── Additional-register block pack/unpack ───────────────────────────────────

def additional_block_size(fields):
    """Byte size of an additional-register layout from the catalog."""
    size = 0
    for _name, code in fields:
        if isinstance(code, tuple):            # ("array", elem_code, (rows, cols))
            _, elem, (rows, cols) = code
            size += _SCALAR_SIZES[elem] * rows * cols
        else:
            size += _SCALAR_SIZES[code]
    return size


def pack_additional(fields, values):
    """Pack an additional-register block from a dict of field values."""
    out = bytearray()
    for name, code in fields:
        if isinstance(code, tuple):            # array field, e.g. beat_mask[10][4]
            _, elem, (rows, cols) = code
            grid = values.get(name) or []
            for r in range(rows):
                row = grid[r] if r < len(grid) else []
                for c in range(cols):
                    cell = row[c] if isinstance(row, (list, tuple)) and c < len(row) else 0
                    out += struct.pack("<" + elem, cell & _mask(elem))
        else:
            out += struct.pack("<" + code, int(values.get(name, 0)) & _mask(code))
    return bytes(out)


def unpack_additional(fields, data):
    """Inverse of :func:`pack_additional` → dict of field values."""
    values = {}
    offset = 0
    for name, code in fields:
        if isinstance(code, tuple):
            _, elem, (rows, cols) = code
            size = _SCALAR_SIZES[elem]
            grid = []
            for _r in range(rows):
                row = []
                for _c in range(cols):
                    (cell,) = struct.unpack_from("<" + elem, data, offset)
                    row.append(cell)
                    offset += size
                grid.append(row)
            values[name] = grid
        else:
            size = _SCALAR_SIZES[code]
            (val,) = struct.unpack_from("<" + code, data, offset)
            values[name] = val
            offset += size
    return values


def _mask(code):
    return (1 << (_SCALAR_SIZES[code] * 8)) - 1


# ── Whole-section-body pack/unpack ──────────────────────────────────────────

def pack_section_body(section_name, bank_name, fields):
    """Build the full Contoso section body bytes for a single injected error.

    Args:
        section_name: exact section-type name (selects layout + subcomponent).
        bank_name:    exact bank name that carries the injected error.
        fields:       dict with the resolved section values:
            subcomponent : {field: int, ...}  (e.g. {"chiplet":0,"core":3})
            error_status : (addr_valid, overflow, severity_value, error_id)
            error_address: int
            misc0        : (injected, ce_count)
            misc1        : int
            additional   : {field: value, ...} for the selected bank

    Returns:
        bytes: the packed section body.
    """
    section = resolve_section(section_name)
    banks = section["banks"]

    # 1. Precompute where each bank's additional block will live (offset from
    #    the start of the section body).  Every bank's block is present; only
    #    the selected bank's block holds real data.
    addl_start = SECTION_HEADER_SIZE + ERROR_BANK_SIZE * len(banks)
    addl_offsets = []
    running = addl_start
    for bank in banks:
        addl_offsets.append(running)
        running += additional_block_size(bank["additional"])

    # 2. Section header: version, bank count, subcomponent instance ID.
    subcomp = fields.get("subcomponent", {})
    header = struct.pack("<BBH", CONTOSO_SECTION_MAJOR, CONTOSO_SECTION_MINOR, len(banks))
    for name, code in section["subcomponent"]:
        header += struct.pack("<" + code, int(subcomp.get(name, 0)) & _mask(code))

    # 3. Error banks — selected bank gets the error, others are zeroed.
    bank_records = bytearray()
    addl_blocks = bytearray()
    for bank, addl_offset in zip(banks, addl_offsets):
        if bank["name"] == bank_name:
            addr_valid, overflow, sev_value, error_id = fields["error_status"]
            injected, ce_count = fields["misc0"]
            status = pack_error_status(addr_valid, overflow, sev_value, error_id)
            address = fields["error_address"]
            misc0 = pack_misc0(injected, ce_count)
            misc1 = fields["misc1"]
            addl_blocks += pack_additional(bank["additional"], fields["additional"])
        else:
            status = address = misc0 = misc1 = 0
            addl_blocks += b"\x00" * additional_block_size(bank["additional"])
        bank_records += struct.pack("<QQQQII", status, address, misc0, misc1, addl_offset, 0)

    return bytes(header + bank_records + addl_blocks)


def unpack_section_body(section_name, body):
    """Inverse of :func:`pack_section_body`.

    Finds the one bank whose errorID is non-zero (the injected error) and
    returns its decoded fields plus the identified bank name.
    """
    section = resolve_section(section_name)
    banks = section["banks"]

    # Section header.
    major, minor, num_banks = struct.unpack_from("<BBH", body, 0)
    if (major, minor) != (CONTOSO_SECTION_MAJOR, CONTOSO_SECTION_MINOR):
        raise ValueError(
            f"Unsupported Contoso section format {major}.{minor}; "
            f"expected {CONTOSO_SECTION_MAJOR}.{CONTOSO_SECTION_MINOR}")
    offset = 4
    subcomp = {}
    for name, code in section["subcomponent"]:
        (val,) = struct.unpack_from("<" + code, body, offset)
        subcomp[name] = val
        offset += _SCALAR_SIZES[code]

    # Error banks.
    result = None
    bank_offset = SECTION_HEADER_SIZE
    for bank in banks:
        status, address, misc0, misc1, addl_offset, _reserved = struct.unpack_from(
            "<QQQQII", body, bank_offset)
        st = unpack_error_status(status)
        if st["error_id"] != 0:                # this is the injected bank
            m0 = unpack_misc0(misc0)
            addl_fields = get_bank(section, bank["name"])["additional"]
            addl = unpack_additional(addl_fields, body[addl_offset:])
            result = {
                "bank_name": bank["name"],
                "subcomponent": subcomp,
                "error_status": st,
                "error_address": address,
                "misc0": m0,
                "misc1": misc1,
                "additional": addl,
            }
        bank_offset += ERROR_BANK_SIZE

    return result
