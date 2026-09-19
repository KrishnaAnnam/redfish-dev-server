"""Build memory-vendor shim events from decoded Contoso CPER windows."""

from __future__ import annotations

import base64
import copy
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contoso_catalog
import contoso_encoder


CONTOSO_MEMORY_SECTION = "Memory Controller - First Generation"
CONTOSO_MEMORY_GUID = contoso_catalog.SECTION_TYPES[
    CONTOSO_MEMORY_SECTION]["guid"].lower()

_RETURN_NAMES = {
    "0x00": "Success",
    "0x01": "Failed",
    "0x02": "Deferred",
    "0x03": "Policy rejected or not supported",
}


def _guid(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("guid", value.get("data", ""))
    return str(value or "").strip().strip("{}").lower()


def _fru_text(value: Any) -> str:
    return str(value or "").strip()


def _hex_code(value: Any, width: int = 2) -> str:
    if isinstance(value, int):
        return f"0x{value:0{width}x}"
    text = str(value or "").strip().lower()
    try:
        number = int(text, 16) if text.startswith("0x") else int(text)
    except ValueError:
        return text
    return f"0x{number:0{width}x}"


def _source(record: Dict[str, Any], window_index: int, section_index: int):
    return {
        "cper_file": str(record.get("cper_file", "")),
        "window_index": window_index,
        "section_index": section_index,
        "is_newest": bool(record.get("is_newest", window_index == 0)),
    }


def _fru(descriptor: Dict[str, Any]):
    return {
        "id": _guid(descriptor.get("fruID")),
        "text": _fru_text(descriptor.get("fruText")),
    }


def _decode_memory_error(record: Dict[str, Any], window_index: int,
                         section_index: int) -> Optional[Dict[str, Any]]:
    cper_data = record["cper_data"]
    descriptors = cper_data.get("sectionDescriptors", [])
    sections = cper_data.get("sections", [])
    if section_index >= len(descriptors) or section_index >= len(sections):
        return None
    descriptor = descriptors[section_index]
    section_type = descriptor.get("sectionType", {})
    guid = section_type.get("data") if isinstance(section_type, dict) else None
    if _guid(guid) != CONTOSO_MEMORY_GUID:
        return None
    encoded = sections[section_index].get("Unknown", {}).get("data")
    if not encoded:
        return None
    try:
        body = base64.b64decode(encoded, validate=True)
        decoded = contoso_encoder.unpack_section_body(
            CONTOSO_MEMORY_SECTION, body)
    except Exception:
        return None

    error_id = decoded["error_status"]["error_id"]
    error_name = contoso_catalog.error_name_from_id(
        CONTOSO_MEMORY_SECTION, decoded["bank_name"], error_id)
    additional = copy.deepcopy(decoded["additional"])
    manufacturer_id = additional.get("dram_manufacturer_id")
    return {
        "event_type": "memory_error",
        "source": _source(record, window_index, section_index),
        "header": copy.deepcopy(cper_data.get("header", {})),
        "section_descriptor": copy.deepcopy(descriptor),
        "section_type": CONTOSO_MEMORY_SECTION,
        "fru": _fru(descriptor),
        "dram_manufacturer_id": copy.deepcopy(manufacturer_id),
        "spd_temperature": additional.get("spd_temperature"),
        "memory_error": {
            "bank": decoded["bank_name"],
            "id": error_id,
            "name": error_name,
            "subcomponent": copy.deepcopy(decoded["subcomponent"]),
            "error_status": copy.deepcopy(decoded["error_status"]),
            "error_address": decoded["error_address"],
            "misc0": copy.deepcopy(decoded["misc0"]),
            "misc1": decoded["misc1"],
            "additional": additional,
        },
    }


def _matching_memory_errors(action_fru: Dict[str, str],
                            action_window_index: int,
                            memory_errors: Iterable[Dict[str, Any]]):
    if not action_fru["id"] or not action_fru["text"]:
        return []
    return [
        event for event in memory_errors
        if event["source"]["window_index"] > action_window_index
        and event["fru"] == action_fru
    ]


def _decode_action_event(record: Dict[str, Any], window_index: int,
                         section_index: int,
                         memory_errors: List[Dict[str, Any]]):
    cper_data = record["cper_data"]
    descriptors = cper_data.get("sectionDescriptors", [])
    sections = cper_data.get("sections", [])
    if section_index >= len(descriptors) or section_index >= len(sections):
        return None
    action = sections[section_index].get("PlatformActionEvent")
    if not isinstance(action, dict):
        return None

    descriptor = descriptors[section_index]
    action_fru = _fru(descriptor)
    matches = _matching_memory_errors(
        action_fru, window_index, memory_errors)
    manufacturer_ids = {
        tuple(event["dram_manufacturer_id"])
        for event in matches
        if isinstance(event.get("dram_manufacturer_id"), list)
        and len(event["dram_manufacturer_id"]) == 2
    }
    correlated = len(manufacturer_ids) == 1
    matched_error = min(
        matches, key=lambda event: (
            event["source"]["window_index"],
            event["source"]["section_index"]),
        default=None,
    ) if correlated else None
    return_code = _hex_code(action.get("actionReturnCode"), 2)
    correlation = {
        "method": "fru_id_and_text",
        "matched": correlated,
        "ambiguous": len(manufacturer_ids) > 1,
    }
    memory_target = None
    manufacturer_id = None
    if matched_error is not None:
        correlation.update({
            "source_error_cper": matched_error["source"]["cper_file"],
            "source_error_section_index": matched_error["source"]["section_index"],
        })
        manufacturer_id = list(next(iter(manufacturer_ids)))
        memory_target = copy.deepcopy(
            matched_error["memory_error"]["additional"])
        memory_target["subcomponent"] = copy.deepcopy(
            matched_error["memory_error"]["subcomponent"])

    return {
        "event_type": "platform_action",
        "source": _source(record, window_index, section_index),
        "header": copy.deepcopy(cper_data.get("header", {})),
        "section_descriptor": copy.deepcopy(descriptor),
        "fru": action_fru,
        "dram_manufacturer_id": manufacturer_id,
        "platform_action": {
            "action_id": _hex_code(action.get("cpadActionId"), 4),
            "return_code": return_code,
            "return_name": _RETURN_NAMES.get(return_code, "Unknown"),
            "reason_code": _hex_code(
                action.get("actionReturnReasonCode", "0x00"), 2),
            "cpad_record_id": _hex_code(action.get("cpadRecordId"), 16),
            "cpad_section_index": action.get("cpadSectionIndex"),
            "successful": return_code == "0x00",
            "additional_context": action.get("additionalContext"),
            "raw": copy.deepcopy(action),
        },
        "correlation": correlation,
        "memory_target": memory_target,
    }


def decode_memory_events(records: List[Dict[str, Any]]):
    """Decode memory errors and FRU-correlated actions, newest first."""
    memory_errors = []
    for window_index, record in enumerate(records):
        cper_data = record.get("cper_data", {})
        section_count = max(
            len(cper_data.get("sectionDescriptors", [])),
            len(cper_data.get("sections", [])),
        )
        for section_index in range(section_count):
            event = _decode_memory_error(
                record, window_index, section_index)
            if event is not None:
                memory_errors.append(event)

    action_events = []
    for window_index, record in enumerate(records):
        cper_data = record.get("cper_data", {})
        section_count = min(
            len(cper_data.get("sectionDescriptors", [])),
            len(cper_data.get("sections", [])),
        )
        for section_index in range(section_count):
            event = _decode_action_event(
                record, window_index, section_index, memory_errors)
            if event is not None:
                action_events.append(event)

    return sorted(
        [*memory_errors, *action_events],
        key=lambda event: (
            event["source"]["window_index"],
            event["source"]["section_index"],
        ),
    )


def manufacturer_id(event: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    value = event.get("dram_manufacturer_id")
    if (not isinstance(value, list) or len(value) != 2 or
            any(not isinstance(byte, int) for byte in value)):
        return None
    return value[0], value[1]


def events_for_manufacturer(events: Iterable[Dict[str, Any]],
                            vendor_id: Tuple[int, int]):
    return [event for event in events if manufacturer_id(event) == vendor_id]


def newest_manufacturer_ids(events: Iterable[Dict[str, Any]]):
    return sorted({
        vendor_id for event in events
        if event["source"]["is_newest"]
        for vendor_id in [manufacturer_id(event)]
        if vendor_id is not None
    })
