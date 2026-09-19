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
    SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT,
    SUPPORTED_SECTION_VERSIONS,
    SEVERITY_VALUES,
    resolve_section,
    get_bank,
)

# Fixed structure sizes from the sections doc.
SECTION_HEADER_SIZE = 8   # major, minor, num_banks, subcomponent instance ID
ERROR_BANK_SIZE = 40      # status, address, misc0, misc1, addl_offset, reserved

_SCALAR_SIZES = {"b": 1, "B": 1, "H": 2, "I": 4, "Q": 8}


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

def additional_block_size(fields, values=None):
    """Byte size of an additional-register layout from the catalog."""
    values = values or {}
    size = 0
    for name, code in fields:
        if isinstance(code, tuple) and code[0] == "array":
            _, elem, (rows, cols) = code
            size += _SCALAR_SIZES[elem] * rows * cols
        elif isinstance(code, tuple) and code[0] == "vector":
            _, elem, length = code
            size += _SCALAR_SIZES[elem] * length
        elif isinstance(code, tuple) and code[0] == "string":
            _, capacity = code
            size += capacity
        elif isinstance(code, tuple) and code[0] == "bytes":
            _, length = code
            size += length
        elif isinstance(code, tuple) and code[0] == "repairs":
            size += 1 + 6 * len(values.get(name, []))
        else:
            size += _SCALAR_SIZES[code]
    return size


def pack_additional(fields, values):
    """Pack an additional-register block from a dict of field values."""
    out = bytearray()
    for name, code in fields:
        if isinstance(code, tuple) and code[0] == "array":
            _, elem, (rows, cols) = code
            grid = values.get(name) or []
            for r in range(rows):
                row = grid[r] if r < len(grid) else []
                for c in range(cols):
                    cell = row[c] if isinstance(row, (list, tuple)) and c < len(row) else 0
                    out += struct.pack("<" + elem, cell & _mask(elem))
        elif isinstance(code, tuple) and code[0] == "vector":
            _, elem, length = code
            vector = values.get(name) or []
            for index in range(length):
                cell = vector[index] if index < len(vector) else 0
                out += struct.pack("<" + elem, int(cell) & _mask(elem))
        elif isinstance(code, tuple) and code[0] == "string":
            _, capacity = code
            value = values.get(name, "")
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            if "\x00" in value:
                raise ValueError(f"{name} must not contain NUL characters")
            try:
                encoded = value.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{name} must contain only ASCII characters") from exc
            if len(encoded) >= capacity:
                raise ValueError(
                    f"{name} must be at most {capacity - 1} characters")
            out += encoded + b"\x00" * (capacity - len(encoded))
        elif isinstance(code, tuple) and code[0] == "bytes":
            _, length = code
            value = values.get(name, [0] * length)
            if not isinstance(value, (list, tuple)) or len(value) != length:
                raise ValueError(f"{name} must contain exactly {length} bytes")
            if any(not isinstance(byte, int) or isinstance(byte, bool) or
                   not 0 <= byte <= 0xFF for byte in value):
                raise ValueError(f"{name} values must be bytes (0..255)")
            out += bytes(value)
        elif isinstance(code, tuple) and code[0] == "repairs":
            entries = values.get(name) or []
            if len(entries) > 0xFF:
                raise ValueError(f"{name} must contain at most 255 entries")
            out += struct.pack("<B", len(entries))
            for entry in entries:
                out += struct.pack(
                    "<BBBBBB",
                    int(entry["subchannel"]), int(entry["rank"]),
                    int(entry["device"]), int(entry["bank_group"]),
                    int(entry["bank"]), int(entry["count"]),
                )
        else:
            value = values.get(name, 0)
            if name == "spd_temperature" and value is None:
                value = SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT
            value = int(value)
            if code == "b":
                if not -128 <= value <= 127:
                    raise ValueError(f"{name} must be in the range -128..127")
                out += struct.pack("<b", value)
            else:
                out += struct.pack("<" + code, value & _mask(code))
    return bytes(out)


def unpack_additional(fields, data):
    """Inverse of :func:`pack_additional`; return values and bytes consumed."""
    values = {}
    offset = 0
    for name, code in fields:
        if isinstance(code, tuple) and code[0] == "array":
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
        elif isinstance(code, tuple) and code[0] == "vector":
            _, elem, length = code
            size = _SCALAR_SIZES[elem]
            vector = []
            for _index in range(length):
                (cell,) = struct.unpack_from("<" + elem, data, offset)
                vector.append(cell)
                offset += size
            values[name] = vector
        elif isinstance(code, tuple) and code[0] == "string":
            _, capacity = code
            raw = data[offset:offset + capacity]
            if len(raw) != capacity:
                raise ValueError(f"{name} is truncated")
            terminator = raw.find(b"\x00")
            if terminator < 0:
                raise ValueError(f"{name} is not NUL-terminated")
            if any(raw[terminator + 1:]):
                raise ValueError(f"{name} has non-NUL padding")
            try:
                values[name] = raw[:terminator].decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError(f"{name} contains non-ASCII data") from exc
            offset += capacity
        elif isinstance(code, tuple) and code[0] == "bytes":
            _, length = code
            raw = data[offset:offset + length]
            if len(raw) != length:
                raise ValueError(f"{name} is truncated")
            values[name] = list(raw)
            offset += length
        elif isinstance(code, tuple) and code[0] == "repairs":
            (count,) = struct.unpack_from("<B", data, offset)
            offset += 1
            entries = []
            for _index in range(count):
                fields = struct.unpack_from("<BBBBBB", data, offset)
                entries.append(dict(zip(
                    ("subchannel", "rank", "device", "bank_group", "bank", "count"),
                    fields,
                )))
                offset += 6
            values[name] = entries
        else:
            size = _SCALAR_SIZES[code]
            (val,) = struct.unpack_from("<" + code, data, offset)
            if name == "memory_repair_capabilities" and val & ~0x07:
                raise ValueError(
                    "memory_repair_capabilities has reserved bits set")
            if name == "reserved" and val != 0:
                raise ValueError("reserved field must be zero")
            if (name == "spd_temperature" and
                    val == SPD_TEMPERATURE_USE_ENDPOINT_DEFAULT):
                val = None
            values[name] = val
            offset += size
    return values, offset


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

    # 1. Pack each additional block first because repair entries make the
    #    selected DRAM block variable-length.
    addl_start = SECTION_HEADER_SIZE + ERROR_BANK_SIZE * len(banks)
    packed_additional = []
    for bank in banks:
        values = fields["additional"] if bank["name"] == bank_name else {}
        packed_additional.append(pack_additional(bank["additional"], values))

    addl_offsets = []
    running = addl_start
    for block in packed_additional:
        addl_offsets.append(running)
        running += len(block)

    # 2. Section header: version, bank count, subcomponent instance ID.
    subcomp = fields.get("subcomponent", {})
    header = struct.pack("<BBH", CONTOSO_SECTION_MAJOR, CONTOSO_SECTION_MINOR, len(banks))
    for name, code in section["subcomponent"]:
        header += struct.pack("<" + code, int(subcomp.get(name, 0)) & _mask(code))

    # 3. Error banks — selected bank gets the error, others are zeroed.
    bank_records = bytearray()
    addl_blocks = bytearray()
    for bank, addl_offset, addl_block in zip(
            banks, addl_offsets, packed_additional):
        if bank["name"] == bank_name:
            addr_valid, overflow, sev_value, error_id = fields["error_status"]
            injected, ce_count = fields["misc0"]
            status = pack_error_status(addr_valid, overflow, sev_value, error_id)
            address = fields["error_address"]
            misc0 = pack_misc0(injected, ce_count)
            misc1 = fields["misc1"]
            addl_blocks += addl_block
        else:
            status = address = misc0 = misc1 = 0
            addl_blocks += addl_block
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
    version = major, minor
    if version not in SUPPORTED_SECTION_VERSIONS:
        raise ValueError(
            f"Unsupported Contoso section format {major}.{minor}; "
            f"expected one of {sorted(SUPPORTED_SECTION_VERSIONS)}")
    if num_banks != len(banks):
        raise ValueError(
            f"Contoso section declares {num_banks} banks; expected {len(banks)}")
    offset = 4
    subcomp = {}
    for name, code in section["subcomponent"]:
        (val,) = struct.unpack_from("<" + code, body, offset)
        subcomp[name] = val
        offset += _SCALAR_SIZES[code]

    # Parse every Error Bank before decoding additional blocks so each block is
    # bounded by the next bank's recorded offset.
    bank_records = []
    bank_offset = SECTION_HEADER_SIZE
    for bank in banks:
        status, address, misc0, misc1, addl_offset, reserved = struct.unpack_from(
            "<QQQQII", body, bank_offset)
        if reserved != 0:
            raise ValueError(f"{bank['name']} Error Bank reserved field must be zero")
        bank_records.append((bank, status, address, misc0, misc1, addl_offset))
        bank_offset += ERROR_BANK_SIZE

    addl_start = SECTION_HEADER_SIZE + ERROR_BANK_SIZE * len(banks)
    offsets = [record[5] for record in bank_records]
    if not offsets or offsets[0] != addl_start:
        raise ValueError("first additional-register offset is invalid")
    if any(start >= end for start, end in zip(offsets, offsets[1:])):
        raise ValueError("additional-register offsets must be increasing")
    if offsets[-1] >= len(body):
        raise ValueError("additional-register offset is outside the section")

    active_records = []
    for index, record in enumerate(bank_records):
        bank, status, address, misc0, misc1, addl_offset = record
        addl_end = offsets[index + 1] if index + 1 < len(offsets) else len(body)
        addl_fields = get_bank(section, bank["name"])["additional"]
        legacy_temperature = (
            version == (1, 4)
            and section_name == "Memory Controller - First Generation"
            and bank["name"] == "DRAM Errors"
        )
        if legacy_temperature:
            addl_fields = [
                field for field in addl_fields
                if field[0] != "spd_temperature"
            ]
        try:
            addl, consumed = unpack_additional(
                addl_fields, body[addl_offset:addl_end])
        except struct.error as exc:
            raise ValueError(
                f"{bank['name']} additional registers are truncated") from exc
        if consumed != addl_end - addl_offset:
            raise ValueError(
                f"{bank['name']} additional-register size does not match its boundary")
        st = unpack_error_status(status)
        if st["error_id"] != 0:
            if legacy_temperature:
                addl["spd_temperature"] = None
            active_records.append({
                "bank_name": bank["name"],
                "subcomponent": subcomp,
                "error_status": st,
                "error_address": address,
                "misc0": unpack_misc0(misc0),
                "misc1": misc1,
                "additional": addl,
            })

    if len(active_records) != 1:
        raise ValueError("Contoso section must have exactly one active Error Bank")
    return active_records[0]
