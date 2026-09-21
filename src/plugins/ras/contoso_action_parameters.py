"""Decode Contoso proprietary CPAD action parameters."""

from __future__ import annotations

import base64
import struct
from typing import Any, Dict


CONTOSO_ACTION_PARAMETER_GUID = "a813b17b-db08-416b-810c-172668affb28"

PPR_ACTION_ID = "0x8001"
PAGE_OFFLINE_ACTION_ID = "0x8002"
REBOOT_WITH_RETRAINING_ACTION_ID = "0x8003"

PPR_TYPE_SOFT_RUNTIME = 0x01
PPR_TYPE_SOFT_BOOT_TIME = 0x02
PPR_TYPE_HARD_BOOT_TIME = 0x04
PPR_TYPES = frozenset({
    PPR_TYPE_SOFT_RUNTIME,
    PPR_TYPE_SOFT_BOOT_TIME,
    PPR_TYPE_HARD_BOOT_TIME,
})

_FORMAT_VERSION = (1, 0)
_PARAMETER_VERSION = 1
_HEADER_FORMAT = "<BBHBBH"
_HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)
_PPR_FORMAT = "<BHHBBBBBBBI"

PHYSICAL_ADDRESS_BITS = 52
PAGE_SHIFT = 12
PFN_BITS = PHYSICAL_ADDRESS_BITS - PAGE_SHIFT
PFN_BYTES = PFN_BITS // 8
MAX_PFN = 1 << PFN_BITS
MAX_PAGE_OFFLINE_PAGES_PER_CPAD = 1_000_000
MAX_PAGE_OFFLINE_BODY_BYTES = 16 * 1024

PAGE_ENCODING_PFN_LIST = 0
PAGE_ENCODING_RANGES = 1
PAGE_ENCODING_BITMAP = 2
PAGE_FLAG_CHUNKED = 1 << 0

_PAGE_HEADER_FORMAT = "<BBHI"
_PAGE_HEADER_SIZE = struct.calcsize(_PAGE_HEADER_FORMAT)
_CHUNK_HEADER_FORMAT = "<QHH"
_CHUNK_HEADER_SIZE = struct.calcsize(_CHUNK_HEADER_FORMAT)
_RANGE_COUNT_FORMAT = "<I"
_RANGE_COUNT_SIZE = struct.calcsize(_RANGE_COUNT_FORMAT)


def is_contoso_action_cpad(cpad_data: Dict[str, Any]) -> bool:
    descriptors = cpad_data.get("sectionDescriptors", [])
    if not descriptors:
        return False
    section_type = descriptors[0].get("sectionType", {})
    guid = section_type.get("data") if isinstance(section_type, dict) else None
    return (
        isinstance(guid, str)
        and guid.lower() == CONTOSO_ACTION_PARAMETER_GUID
    )


def _body(cpad_data: Dict[str, Any]) -> bytes:
    if not is_contoso_action_cpad(cpad_data):
        raise ValueError(
            "CPAD does not contain Contoso action parameters")
    sections = cpad_data.get("sections", [])
    encoded = (
        sections[0].get("Unknown", {}).get("data")
        if sections else None
    )
    if not encoded:
        raise ValueError("Contoso action-parameter section has no body")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError(
            "Contoso action-parameter body is not valid base64") from exc


def _decode_pfn(data: bytes) -> int:
    if len(data) != PFN_BYTES:
        raise ValueError("40-bit page frame number is truncated")
    return int.from_bytes(data, "little")


def decode_cpad_action_parameters(
        cpad_data: Dict[str, Any], action_id: str) -> Dict[str, int]:
    body = _body(cpad_data)
    if len(body) < _HEADER_SIZE:
        raise ValueError("Contoso action-parameter body is truncated")
    major, minor, length, parameter_version, flags, reserved = \
        struct.unpack_from(_HEADER_FORMAT, body)
    if (major, minor) != _FORMAT_VERSION:
        raise ValueError(
            f"unsupported Contoso action-parameter format {major}.{minor}")
    if parameter_version != _PARAMETER_VERSION:
        raise ValueError(
            f"unsupported Contoso action parameter version {parameter_version}")
    if flags != 0 or reserved != 0:
        raise ValueError("Contoso action-parameter reserved fields must be zero")
    payload = body[_HEADER_SIZE:]
    if len(payload) != length:
        raise ValueError("Contoso action-parameter length is invalid")

    if action_id == PPR_ACTION_ID:
        if len(payload) != struct.calcsize(_PPR_FORMAT):
            raise ValueError("Contoso PPR parameters have an invalid length")
        names = (
            "ppr_type", "chiplet", "controller", "channel", "dimm",
            "subchannel", "rank", "device", "bank_group", "bank", "row",
        )
        result = dict(zip(names, struct.unpack(_PPR_FORMAT, payload)))
        if result["ppr_type"] not in PPR_TYPES:
            raise ValueError("Contoso PPR type is invalid")
        return result

    if action_id == PAGE_OFFLINE_ACTION_ID:
        return _decode_page_offline_payload(payload)

    if action_id == REBOOT_WITH_RETRAINING_ACTION_ID:
        if payload:
            raise ValueError(
                "Contoso retraining parameters must not contain a payload")
        return {}

    raise ValueError(f"unsupported Contoso action {action_id}")


def _decode_page_offline_payload(payload: bytes) -> Dict[str, Any]:
    if _HEADER_SIZE + len(payload) > MAX_PAGE_OFFLINE_BODY_BYTES:
        raise ValueError("Contoso Page Offline action body exceeds the size limit")
    if len(payload) < _PAGE_HEADER_SIZE:
        raise ValueError("Contoso Page Offline parameters are truncated")
    encoding, flags, item_count, page_count = struct.unpack_from(
        _PAGE_HEADER_FORMAT, payload)
    if page_count == 0 or page_count > MAX_PAGE_OFFLINE_PAGES_PER_CPAD:
        raise ValueError("Contoso Page Offline page count is outside the limit")
    if flags & ~PAGE_FLAG_CHUNKED:
        raise ValueError("Contoso Page Offline flags are invalid")
    offset = _PAGE_HEADER_SIZE
    batch_id = None
    chunk_index = 0
    chunk_count = 1
    if flags:
        if len(payload) < offset + _CHUNK_HEADER_SIZE:
            raise ValueError("Contoso Page Offline chunk header is truncated")
        batch_id, chunk_index, chunk_count = struct.unpack_from(
            _CHUNK_HEADER_FORMAT, payload, offset)
        offset += _CHUNK_HEADER_SIZE
        if chunk_count < 2 or chunk_index >= chunk_count:
            raise ValueError("Contoso Page Offline chunk metadata is invalid")

    data = payload[offset:]
    ranges = []
    if encoding == PAGE_ENCODING_PFN_LIST:
        if len(data) != item_count * PFN_BYTES or page_count != item_count:
            raise ValueError("Contoso Page Offline PFN-list length is invalid")
        pfns = [
            _decode_pfn(data[index:index + PFN_BYTES])
            for index in range(0, len(data), PFN_BYTES)
        ]
        if pfns != sorted(set(pfns)):
            raise ValueError(
                "Contoso Page Offline PFNs must be sorted and unique")
        ranges = [(pfn, 1) for pfn in pfns]
    elif encoding == PAGE_ENCODING_RANGES:
        entry_size = PFN_BYTES + _RANGE_COUNT_SIZE
        if len(data) != item_count * entry_size:
            raise ValueError("Contoso Page Offline range length is invalid")
        previous_end = -1
        for entry_offset in range(0, len(data), entry_size):
            start = _decode_pfn(
                data[entry_offset:entry_offset + PFN_BYTES])
            count = struct.unpack_from(
                _RANGE_COUNT_FORMAT,
                data,
                entry_offset + PFN_BYTES,
            )[0]
            if count == 0 or start + count > MAX_PFN:
                raise ValueError("Contoso Page Offline range is invalid")
            if start <= previous_end:
                raise ValueError(
                    "Contoso Page Offline ranges must be sorted and nonadjacent")
            previous_end = start + count
            ranges.append((start, count))
        if sum(count for _start, count in ranges) != page_count:
            raise ValueError("Contoso Page Offline page count is invalid")
    elif encoding == PAGE_ENCODING_BITMAP:
        if item_count == 0 or len(data) != PFN_BYTES + item_count:
            raise ValueError("Contoso Page Offline bitmap length is invalid")
        base = _decode_pfn(data[:PFN_BYTES])
        bitmap = data[PFN_BYTES:]
        if bitmap[0] == 0 or bitmap[-1] == 0:
            raise ValueError("Contoso Page Offline bitmap is not canonical")
        if base + len(bitmap) * 8 > MAX_PFN:
            raise ValueError(
                "Contoso Page Offline bitmap exceeds the address space")
        pfns = [
            base + bit
            for bit in range(len(bitmap) * 8)
            if bitmap[bit // 8] & (1 << (bit % 8))
        ]
        if not pfns or pfns[-1] >= MAX_PFN or len(pfns) != page_count:
            raise ValueError("Contoso Page Offline bitmap page count is invalid")
        range_start = range_end = pfns[0]
        for pfn in pfns[1:]:
            if pfn == range_end + 1:
                range_end = pfn
            else:
                ranges.append((range_start, range_end - range_start + 1))
                range_start = range_end = pfn
        ranges.append((range_start, range_end - range_start + 1))
    else:
        raise ValueError(f"unsupported Page Offline encoding {encoding}")

    return {
        "encoding": encoding,
        "page_count": page_count,
        "page_ranges": [
            {
                "start_address": start << PAGE_SHIFT,
                "page_count": count,
            }
            for start, count in ranges
        ],
        "batch_id": batch_id,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
    }
