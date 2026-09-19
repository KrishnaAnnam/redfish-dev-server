"""Endpoint-side helpers for Contoso v1.4 memory section bodies."""

from __future__ import annotations

import base64
import struct
from typing import Any, Dict

from .memory_config import MemoryRepairState


CONTOSO_MEMORY_SECTION_GUID = "e01ce992-d080-43f4-8a2c-df8a9d81eb4e"
_SECTION_VERSION = (1, 4)
_SECTION_HEADER_SIZE = 8
_ERROR_BANK_SIZE = 40
_LOCATION_AND_BEATS_SIZE = 21
_BANK_COUNT = 2
_DRAM_ADDITIONAL_OFFSET = _SECTION_HEADER_SIZE + _BANK_COUNT * _ERROR_BANK_SIZE
_DRAM_FIXED_SIZE = 81
_OTHER_ADDITIONAL_SIZE = 8


def is_contoso_memory_cpad(cpad_data: Dict[str, Any]) -> bool:
    descriptors = cpad_data.get("sectionDescriptors", [])
    if not descriptors:
        return False
    section_type = descriptors[0].get("sectionType", {})
    guid = section_type.get("data") if isinstance(section_type, dict) else None
    return (isinstance(guid, str) and
            guid.lower() == CONTOSO_MEMORY_SECTION_GUID)


def _section_body(cpad_data: Dict[str, Any]) -> bytes:
    descriptors = cpad_data.get("sectionDescriptors", [])
    sections = cpad_data.get("sections", [])
    if not descriptors or not sections:
        raise ValueError("CPAD has no section")
    if not is_contoso_memory_cpad(cpad_data):
        raise ValueError("SPPR CPAD does not contain a Contoso memory section")
    encoded = sections[0].get("Unknown", {}).get("data")
    if not encoded:
        raise ValueError("Contoso memory section has no body")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Contoso memory section body is not valid base64") from exc


def active_memory_bank(body: bytes) -> str:
    """Validate the common v1.4 header and return ``dram`` or ``other``."""
    if len(body) < _DRAM_ADDITIONAL_OFFSET + _DRAM_FIXED_SIZE + _OTHER_ADDITIONAL_SIZE:
        raise ValueError("Contoso memory section body is truncated")
    major, minor, bank_count = struct.unpack_from("<BBH", body, 0)
    if (major, minor) != _SECTION_VERSION or bank_count != _BANK_COUNT:
        raise ValueError(
            f"unsupported Contoso memory section {major}.{minor} with {bank_count} banks")
    for index in range(_BANK_COUNT):
        reserved = struct.unpack_from(
            "<I", body,
            _SECTION_HEADER_SIZE + index * _ERROR_BANK_SIZE + 36)[0]
        if reserved != 0:
            raise ValueError("Contoso memory Error Bank reserved field must be zero")
    dram_status = struct.unpack_from("<Q", body, _SECTION_HEADER_SIZE)[0]
    other_status = struct.unpack_from(
        "<Q", body, _SECTION_HEADER_SIZE + _ERROR_BANK_SIZE)[0]
    dram_active = dram_status & 0xFFFF != 0
    other_active = other_status & 0xFFFF != 0
    if dram_active == other_active:
        raise ValueError("Contoso memory section must have exactly one active error bank")
    dram_offset = struct.unpack_from(
        "<I", body, _SECTION_HEADER_SIZE + 32)[0]
    other_offset = struct.unpack_from(
        "<I", body, _SECTION_HEADER_SIZE + _ERROR_BANK_SIZE + 32)[0]
    if dram_offset != _DRAM_ADDITIONAL_OFFSET:
        raise ValueError("Contoso DRAM additional-register offset is invalid")
    repair_count = body[dram_offset + _DRAM_FIXED_SIZE - 1]
    if other_offset != dram_offset + _DRAM_FIXED_SIZE + repair_count * 6:
        raise ValueError("Contoso sparse repair table length is invalid")
    if len(body) != other_offset + _OTHER_ADDITIONAL_SIZE:
        raise ValueError("Contoso memory section length is invalid")
    if body[dram_offset + 77] & ~0x07:
        raise ValueError("Contoso memory repair capabilities have reserved bits set")
    if any(body[dram_offset + 78:dram_offset + 80]):
        raise ValueError("Contoso memory reserved field must be zero")
    return "dram" if dram_active else "other"


def active_cpad_memory_bank(cpad_data: Dict[str, Any]) -> str:
    return active_memory_bank(_section_body(cpad_data))


def decode_memory_coordinates(body: bytes) -> Dict[str, int]:
    """Decode the v1.4 DIMM and bank target from a Contoso memory body."""
    if len(body) < _DRAM_ADDITIONAL_OFFSET + _DRAM_FIXED_SIZE + _OTHER_ADDITIONAL_SIZE:
        raise ValueError("Contoso memory section body is truncated")
    if active_memory_bank(body) != "dram":
        raise ValueError("SPPR requires the DRAM Errors bank to be active")
    chiplet, controller = struct.unpack_from("<HH", body, 4)
    additional_offset = _DRAM_ADDITIONAL_OFFSET
    channel, dimm, subchannel, rank, device, bank_group, bank = struct.unpack_from(
        "<BBBBBBB", body, additional_offset)
    row = struct.unpack_from("<I", body, additional_offset + 7)[0]
    column = struct.unpack_from("<H", body, additional_offset + 11)[0]
    return {
        "chiplet": chiplet,
        "controller": controller,
        "channel": channel,
        "dimm": dimm,
        "subchannel": subchannel,
        "rank": rank,
        "device": device,
        "bank_group": bank_group,
        "bank": bank,
        "row": row,
        "column": column,
    }


def decode_cpad_memory_coordinates(cpad_data: Dict[str, Any]) -> Dict[str, int]:
    return decode_memory_coordinates(_section_body(cpad_data))


def decode_memory_error_address(body: bytes) -> int:
    """Decode the active DRAM bank's valid 64-bit physical address."""
    if active_memory_bank(body) != "dram":
        raise ValueError("Page Offline requires the DRAM Errors bank to be active")
    status = struct.unpack_from("<Q", body, _SECTION_HEADER_SIZE)[0]
    if not status >> 63 & 0x1:
        raise ValueError("Page Offline requires a valid physical address")
    return struct.unpack_from("<Q", body, _SECTION_HEADER_SIZE + 8)[0]


def decode_cpad_memory_error_address(cpad_data: Dict[str, Any]) -> int:
    return decode_memory_error_address(_section_body(cpad_data))


def _fixed_ascii(value: str, capacity: int) -> bytes:
    encoded = value.encode("ascii")
    return encoded + b"\x00" * (capacity - len(encoded))


def overlay_memory_state(body: bytes, state: MemoryRepairState) -> bytes:
    """Overlay authoritative DIMM SPD and repair counters into a memory body."""
    active_bank = active_memory_bank(body)
    if active_bank == "other":
        other_offset = struct.unpack_from(
            "<I", body, _SECTION_HEADER_SIZE + _ERROR_BANK_SIZE + 32)[0]
        dram = bytearray(_LOCATION_AND_BEATS_SIZE + 19 + 25 + 2 + 2)
        dram += struct.pack("<Q", state.config.total_memory_bytes)
        dram += struct.pack("<B", state.capabilities.bitfield)
        dram += b"\x00\x00\x00"
        prefix = bytearray(body[:_DRAM_ADDITIONAL_OFFSET])
        struct.pack_into(
            "<I", prefix, _SECTION_HEADER_SIZE + _ERROR_BANK_SIZE + 32,
            _DRAM_ADDITIONAL_OFFSET + len(dram))
        return bytes(prefix + dram + body[other_offset:])

    coordinates = decode_memory_coordinates(body)
    dimm = state.config.get_dimm(
        coordinates["chiplet"], coordinates["controller"],
        coordinates["channel"], coordinates["dimm"])
    entries = state.entries_for_dimm(*dimm.key)
    dram_offset = _DRAM_ADDITIONAL_OFFSET
    other_bank_offset_field = _SECTION_HEADER_SIZE + _ERROR_BANK_SIZE + 32
    old_other_offset = struct.unpack_from("<I", body, other_bank_offset_field)[0]
    if old_other_offset < dram_offset + _LOCATION_AND_BEATS_SIZE or old_other_offset > len(body):
        raise ValueError("Contoso memory additional-register offsets are invalid")

    dram = bytearray(body[dram_offset:dram_offset + _LOCATION_AND_BEATS_SIZE])
    dram += _fixed_ascii(dimm.serial_number, 19)
    dram += _fixed_ascii(dimm.part_number, 25)
    dram += bytes(dimm.module_manufacturer_id)
    dram += bytes(dimm.dram_manufacturer_id)
    dram += struct.pack("<Q", state.config.total_memory_bytes)
    dram += struct.pack("<B", state.capabilities.bitfield)
    dram += b"\x00\x00"
    dram += struct.pack("<B", len(entries))
    for entry in entries:
        dram += struct.pack(
            "<BBBBBB", entry["subchannel"], entry["rank"], entry["device"],
            entry["bank_group"], entry["bank"], entry["count"])

    prefix = bytearray(body[:dram_offset])
    struct.pack_into("<I", prefix, other_bank_offset_field, dram_offset + len(dram))
    return bytes(prefix + dram + body[old_other_offset:])


def overlay_cpad_memory_state(cpad_data: Dict[str, Any], state: MemoryRepairState) -> bytes:
    return overlay_memory_state(_section_body(cpad_data), state)
