"""Encode and decode Contoso proprietary CPAD action parameters."""

from __future__ import annotations

import hashlib
import struct
from typing import Any, Dict, Iterable, List, Tuple


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
PAGE_SIZE_BYTES = 1 << PAGE_SHIFT
PFN_BITS = PHYSICAL_ADDRESS_BITS - PAGE_SHIFT
PFN_BYTES = PFN_BITS // 8
MAX_PFN = 1 << PFN_BITS
MAX_PAGE_COUNT = (1 << 32) - 1
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


def _require_int(
        value: Any, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in the range {minimum}..{maximum}")
    return value


def _memory_error(event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get("event_type") != "memory_error":
        raise ValueError("Contoso action requires a memory-error source event")
    return event["memory_error"]


def _pack_header(payload: bytes) -> bytes:
    return struct.pack(
        _HEADER_FORMAT,
        *_FORMAT_VERSION,
        len(payload),
        _PARAMETER_VERSION,
        0,
        0,
    ) + payload


def _encode_pfn(pfn: int) -> bytes:
    if not 0 <= pfn < MAX_PFN:
        raise ValueError("page frame number exceeds the 52-bit address space")
    return pfn.to_bytes(PFN_BYTES, "little")


def _decode_pfn(data: bytes) -> int:
    if len(data) != PFN_BYTES:
        raise ValueError("40-bit page frame number is truncated")
    return int.from_bytes(data, "little")


def _normalized_page_ranges(
        parameters: Dict[str, Any]) -> List[Tuple[int, int]]:
    if set(parameters) != {"page_ranges"}:
        raise ValueError(
            "Page Offline parameters must contain only page_ranges")
    raw_ranges = parameters["page_ranges"]
    if not isinstance(raw_ranges, list) or not raw_ranges:
        raise ValueError("page_ranges must be a non-empty list")

    ranges = []
    for index, item in enumerate(raw_ranges):
        if not isinstance(item, dict) or set(item) != {
                "start_address", "page_count"}:
            raise ValueError(
                f"page_ranges[{index}] must contain start_address and page_count")
        address = _require_int(
            item["start_address"], "start_address", 0,
            (1 << PHYSICAL_ADDRESS_BITS) - 1)
        if address % PAGE_SIZE_BYTES:
            raise ValueError(
                "Page Offline physical addresses must be 4 KiB aligned")
        count = _require_int(
            item["page_count"], "page_count", 1, MAX_PAGE_COUNT)
        start_pfn = address >> PAGE_SHIFT
        end_pfn = start_pfn + count
        if end_pfn > MAX_PFN:
            raise ValueError(
                "Page Offline range exceeds the 52-bit address space")
        ranges.append((start_pfn, count))

    merged = []
    for start, count in sorted(ranges):
        end = start + count
        if merged and start <= merged[-1][0] + merged[-1][1]:
            previous_start, previous_count = merged[-1]
            merged[-1] = (
                previous_start,
                max(previous_start + previous_count, end) - previous_start,
            )
        else:
            merged.append((start, count))
    return merged


def _split_large_ranges(
        ranges: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    split = []
    for start, count in ranges:
        limit = min(MAX_PAGE_COUNT, MAX_PAGE_OFFLINE_PAGES_PER_CPAD)
        while count > limit:
            split.append((start, limit))
            start += limit
            count -= limit
        split.append((start, count))
    return split


def _candidate_encoding(
        ranges: List[Tuple[int, int]], chunked: bool):
    page_count = sum(count for _start, count in ranges)
    if (not ranges or page_count > MAX_PAGE_COUNT
            or page_count > MAX_PAGE_OFFLINE_PAGES_PER_CPAD):
        return None
    fixed = _HEADER_SIZE + _PAGE_HEADER_SIZE
    if chunked:
        fixed += _CHUNK_HEADER_SIZE

    candidates = []
    if page_count <= 0xFFFF:
        candidates.append((
            fixed + PFN_BYTES * page_count,
            PAGE_ENCODING_PFN_LIST,
        ))
    if len(ranges) <= 0xFFFF:
        candidates.append((
            fixed + (PFN_BYTES + _RANGE_COUNT_SIZE) * len(ranges),
            PAGE_ENCODING_RANGES,
        ))
    span = ranges[-1][0] + ranges[-1][1] - ranges[0][0]
    bitmap_bytes = (span + 7) // 8
    if (bitmap_bytes <= 0xFFFF
            and ranges[0][0] + bitmap_bytes * 8 <= MAX_PFN):
        candidates.append((
            fixed + PFN_BYTES + bitmap_bytes,
            PAGE_ENCODING_BITMAP,
        ))
    candidates = [
        candidate for candidate in candidates
        if candidate[0] <= MAX_PAGE_OFFLINE_BODY_BYTES
    ]
    return min(candidates, default=None)


def _batch_id(event: Dict[str, Any], ranges: List[Tuple[int, int]]) -> int:
    digest = hashlib.sha256()
    header = event.get("header", {})
    for field in ("creatorID", "platformID", "partitionID", "recordID"):
        digest.update(str(header.get(field, "")).encode("utf-8"))
        digest.update(b"\0")
    digest.update(str(event.get("section_index", 0)).encode("ascii"))
    for start, count in ranges:
        digest.update(start.to_bytes(PFN_BYTES, "little"))
        digest.update(struct.pack("<Q", count))
    return int.from_bytes(digest.digest()[:8], "little")


def _encode_page_chunk(
        ranges: List[Tuple[int, int]],
        encoding: int,
        batch_id: int = 0,
        chunk_index: int = 0,
        chunk_count: int = 1) -> bytes:
    page_count = sum(count for _start, count in ranges)
    flags = PAGE_FLAG_CHUNKED if chunk_count > 1 else 0
    data = bytearray()

    if encoding == PAGE_ENCODING_PFN_LIST:
        for start, count in ranges:
            for pfn in range(start, start + count):
                data += _encode_pfn(pfn)
        item_count = page_count
    elif encoding == PAGE_ENCODING_RANGES:
        for start, count in ranges:
            data += _encode_pfn(start)
            data += struct.pack(_RANGE_COUNT_FORMAT, count)
        item_count = len(ranges)
    elif encoding == PAGE_ENCODING_BITMAP:
        base = ranges[0][0]
        span = ranges[-1][0] + ranges[-1][1] - base
        bitmap = bytearray((span + 7) // 8)
        for start, count in ranges:
            for pfn in range(start, start + count):
                bit = pfn - base
                bitmap[bit // 8] |= 1 << (bit % 8)
        data += _encode_pfn(base)
        data += bitmap
        item_count = len(bitmap)
    else:
        raise ValueError(f"unsupported Page Offline encoding {encoding}")

    payload = bytearray(struct.pack(
        _PAGE_HEADER_FORMAT,
        encoding,
        flags,
        item_count,
        page_count,
    ))
    if flags:
        payload += struct.pack(
            _CHUNK_HEADER_FORMAT, batch_id, chunk_index, chunk_count)
    payload += data
    body = _pack_header(bytes(payload))
    if len(body) > MAX_PAGE_OFFLINE_BODY_BYTES:
        raise ValueError("Page Offline action body exceeds the size limit")
    return body


def _page_offline_bodies(
        event: Dict[str, Any],
        parameters: Dict[str, Any]) -> List[bytes]:
    ranges = _split_large_ranges(_normalized_page_ranges(parameters))
    whole = _candidate_encoding(ranges, chunked=False)
    if whole is not None:
        return [_encode_page_chunk(ranges, whole[1])]

    chunks = []
    current = []
    for page_range in ranges:
        candidate = _candidate_encoding(
            [*current, page_range], chunked=True)
        if candidate is not None:
            current.append(page_range)
            continue
        if not current:
            raise ValueError("Page Offline range cannot fit in one CPAD")
        chunks.append(current)
        current = [page_range]
        if _candidate_encoding(current, chunked=True) is None:
            raise ValueError("Page Offline range cannot fit in one CPAD")
    if current:
        chunks.append(current)
    if len(chunks) > 0xFFFF:
        raise ValueError("Page Offline request requires too many CPAD chunks")

    batch_id = _batch_id(event, ranges)
    bodies = []
    for index, chunk in enumerate(chunks):
        candidate = _candidate_encoding(chunk, chunked=True)
        bodies.append(_encode_page_chunk(
            chunk,
            candidate[1],
            batch_id=batch_id,
            chunk_index=index,
            chunk_count=len(chunks),
        ))
    return bodies


def encode_action_parameters(
        action_id: str,
        event: Dict[str, Any],
        parameters: Dict[str, Any]) -> bytes:
    """Build one action-specific payload from a referenced decoded CPER event."""
    bodies = encode_action_parameter_bodies(action_id, event, parameters)
    if len(bodies) != 1:
        raise ValueError(
            "action requires multiple CPADs; use encode_action_parameter_bodies")
    return bodies[0]


def encode_action_parameter_bodies(
        action_id: str,
        event: Dict[str, Any],
        parameters: Dict[str, Any]) -> List[bytes]:
    """Build one or more action bodies from a referenced decoded CPER event."""
    if not isinstance(parameters, dict):
        raise ValueError("action parameters must be an object")
    error = _memory_error(event)
    additional = error["additional"]
    subcomponent = error["subcomponent"]

    if action_id == PPR_ACTION_ID:
        if set(parameters) != {"ppr_type"}:
            raise ValueError("PPR parameters must contain only ppr_type")
        ppr_type = _require_int(parameters["ppr_type"], "ppr_type", 1, 4)
        if ppr_type not in PPR_TYPES:
            raise ValueError("ppr_type must be one of 0x01, 0x02, or 0x04")
        payload = struct.pack(
            _PPR_FORMAT,
            ppr_type,
            _require_int(subcomponent.get("chiplet"), "chiplet", 0, 0xFFFF),
            _require_int(
                subcomponent.get("controller"), "controller", 0, 0xFFFF),
            _require_int(additional.get("channel"), "channel", 0, 0xFF),
            _require_int(additional.get("dimm"), "dimm", 0, 0xFF),
            _require_int(
                additional.get("subchannel"), "subchannel", 0, 0xFF),
            _require_int(additional.get("rank"), "rank", 0, 0xFF),
            _require_int(additional.get("device"), "device", 0, 0xFF),
            _require_int(
                additional.get("bank_group"), "bank_group", 0, 0xFF),
            _require_int(additional.get("bank"), "bank", 0, 0xFF),
            _require_int(additional.get("row"), "row", 0, 0xFFFFFFFF),
        )
        return [_pack_header(payload)]

    if action_id == PAGE_OFFLINE_ACTION_ID:
        return _page_offline_bodies(event, parameters)

    if action_id == REBOOT_WITH_RETRAINING_ACTION_ID:
        if parameters:
            raise ValueError(
                "Reboot with Memory Retraining parameters must be empty")
        return [_pack_header(b"")]

    raise ValueError(f"unsupported Contoso action {action_id}")


def decode_action_parameters(action_id: str, body: bytes) -> Dict[str, int]:
    """Decode a body for tests and analyzer-side validation."""
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
        values = struct.unpack(_PPR_FORMAT, payload)
        names = (
            "ppr_type", "chiplet", "controller", "channel", "dimm",
            "subchannel", "rank", "device", "bank_group", "bank", "row",
        )
        result = dict(zip(names, values))
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
        for offset in range(0, len(data), entry_size):
            start = _decode_pfn(data[offset:offset + PFN_BYTES])
            count = struct.unpack_from(
                _RANGE_COUNT_FORMAT, data, offset + PFN_BYTES)[0]
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
