"""Adapter between canonical Contoso memory events and Samsung analysis."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

import contoso_catalog
from contoso_action_parameters import (
    PAGE_OFFLINE_ACTION_ID,
    POWER_CYCLE_ACTION_ID,
    PPR_ACTION_ID,
    REBOOT_WITH_RETRAINING_ACTION_ID,
    REPLACE_PART_ACTION_ID,
    RESEAT_PART_ACTION_ID,
    SHUFFLE_PART_ACTION_ID,
)


SHIM_INFO = {
    "api_version": 5,
    "name": "Samsung Memory Analyzer Shim",
    "version": "0.5.0",
    "dram_manufacturer_ids": [[0x80, 0xCE]],
}

_ACTION_IDS = {
    "cold_reboot": POWER_CYCLE_ACTION_ID,
    "reseat_dimm": RESEAT_PART_ACTION_ID,
    "dance_dimm": SHUFFLE_PART_ACTION_ID,
    "replace_dimm": REPLACE_PART_ACTION_ID,
    "ppr": PPR_ACTION_ID,
    "page_offline": PAGE_OFFLINE_ACTION_ID,
    "reboot_with_training": REBOOT_WITH_RETRAINING_ACTION_ID,
}
_EMPTY_BODY_ACTIONS = {
    "cold_reboot",
    "reseat_dimm",
    "dance_dimm",
    "replace_dimm",
    "reboot_with_training",
}
_FRU_TARGET_ACTIONS = {
    "reseat_dimm",
    "dance_dimm",
    "replace_dimm",
    "ppr",
    "page_offline",
}
_FRU_PARAMETER_FIELDS = {"fru_id", "fru_text"}
_SEVERITY_NAMES = {
    value: name for name, value in contoso_catalog.SEVERITY_VALUES.items()
}


def _header_id(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("guid", value.get("data", ""))
    return str(value or "").strip().strip("{}")


def _target_bank_repair_count(additional: Dict[str, Any]) -> int:
    target = tuple(additional.get(name) for name in (
        "subchannel", "rank", "device", "bank_group", "bank"))
    for entry in additional.get("repairs", []):
        if tuple(entry.get(name) for name in (
                "subchannel", "rank", "device", "bank_group", "bank")) == target:
            return int(entry.get("count", 0))
    return 0


def _beat_data(additional: Dict[str, Any]) -> Dict[str, Any]:
    masks = [int(mask) for mask in additional.get("beat_mask", [])]
    mask_64 = sum((mask & 0xFFFF) << (16 * dq)
                  for dq, mask in enumerate(masks))
    failing_beats = {
        dq: [beat for beat in range(16) if mask & (1 << beat)]
        for dq, mask in enumerate(masks)
        if mask
    }
    return {
        "mask_by_dq": masks,
        "mask_64": mask_64,
        "failing_dqs": list(failing_beats),
        "failing_dq_count": len(failing_beats),
        "failing_beats_by_dq": failing_beats,
        "failing_beat_count": sum(
            len(beats) for beats in failing_beats.values()),
    }


def _ppr_data(additional: Dict[str, Any]) -> Dict[str, Any]:
    capabilities = int(additional.get("memory_repair_capabilities", 0))
    consumed = _target_bank_repair_count(additional)
    return {
        "capability_bits": capabilities,
        "soft_runtime": bool(capabilities & 0x01),
        "soft_boot_time": bool(capabilities & 0x02),
        "hard_boot_time": bool(capabilities & 0x04),
        "target_bank_repair_count": consumed,
        "repair_history": copy.deepcopy(additional.get("repairs", [])),
    }


def _source(event: Dict[str, Any]) -> Dict[str, Any]:
    source = event.get("source", {})
    return {
        "cper_file": event["cper_file"],
        "section_index": event["section_index"],
        "is_newest": bool(source.get("is_newest")),
        "window_index": source.get("window_index"),
    }


def _common_record(event: Dict[str, Any]) -> Dict[str, Any]:
    header = event.get("header", {})
    severity = header.get("severity", {})
    if isinstance(severity, dict):
        severity = severity.get("name", severity.get("code"))
    return {
        "source": _source(event),
        "timestamp": header.get("timestamp"),
        "record_id": header.get("recordID"),
        "cper_severity": severity,
        "platform_id": _header_id(header.get("platformID")),
        "partition_id": _header_id(header.get("partitionID")),
        "creator_id": _header_id(header.get("creatorID")),
        "fru_id": event.get("fru_id", ""),
        "fru_text": event.get("fru_text", ""),
    }


def _to_samsung_memory_error(event: Dict[str, Any]) -> Dict[str, Any]:
    error = event["memory_error"]
    status = error.get("error_status", {})
    misc0 = error.get("misc0", {})
    subcomponent = error.get("subcomponent", {})
    additional = error.get("additional", {})
    manufacturer = additional.get("dram_manufacturer_id")
    if manufacturer != [0x80, 0xCE]:
        raise ValueError(
            "Samsung shim received a non-Samsung DRAM manufacturer ID")
    return {
        "record_type": "memory_error",
        **_common_record(event),
        "error": {
            "bank": error.get("bank"),
            "id": error.get("id"),
            "name": error.get("name"),
            "severity": _SEVERITY_NAMES.get(
                status.get("severity_value"), "Unknown"),
            "address_valid": bool(status.get("addressValid")),
            "overflow": bool(status.get("overflow")),
            "injected": bool(misc0.get("injected")),
            "ce_count": int(misc0.get("ce_count", 0)),
            "physical_address": error.get("error_address"),
        },
        "location": {
            "chiplet": subcomponent.get("chiplet"),
            "controller": subcomponent.get("controller"),
            "channel": additional.get("channel"),
            "dimm": additional.get("dimm"),
            "subchannel": additional.get("subchannel"),
            "rank": additional.get("rank"),
            "dram_device": additional.get("device"),
            "bank_group": additional.get("bank_group"),
            "bank": additional.get("bank"),
            "row": additional.get("row"),
            "column": additional.get("column"),
        },
        "dimm": {
            "serial_number": additional.get("serial_number"),
            "part_number": additional.get("part_number"),
            "module_manufacturer_id": copy.deepcopy(
                additional.get("module_manufacturer_id")),
            "dram_manufacturer_id": copy.deepcopy(manufacturer),
            "spd_temperature_c": additional.get("spd_temperature"),
        },
        "ppr": _ppr_data(additional),
        "system": {
            "total_memory_bytes": additional.get("total_memory_bytes"),
        },
        "beats": _beat_data(additional),
    }


def _to_samsung_platform_action(event: Dict[str, Any]) -> Dict[str, Any]:
    action = event["platform_action"]
    correlation = event.get("correlation", {})
    return {
        "record_type": "platform_action",
        **_common_record(event),
        "action": {
            "action_id": action.get("action_id"),
            "return_code": action.get("return_code"),
            "return_name": action.get("return_name"),
            "reason_code": action.get("reason_code"),
            "successful": bool(action.get("successful")),
            "additional_context": action.get("additional_context"),
            "cpad_record_id": action.get("cpad_record_id"),
            "cpad_section_index": action.get("cpad_section_index"),
        },
        "correlation": copy.deepcopy(correlation),
        "memory_target": copy.deepcopy(event.get("memory_target")),
    }


def _to_samsung_record(event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get("event_type") == "memory_error":
        return _to_samsung_memory_error(event)
    if event.get("event_type") == "platform_action":
        return _to_samsung_platform_action(event)
    raise ValueError(f"unsupported Samsung event type {event.get('event_type')}")


def analyze(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Samsung analysis seam.

    Proprietary Samsung diagnosis can replace this conservative default
    without changing the Contoso shim contract.
    """
    spare_rows_per_bank = 16
    for record in records:
        if record.get("record_type") != "memory_error":
            continue
        ppr = record["ppr"]
        ppr["repairs_per_bank"] = max(
            0, spare_rows_per_bank - ppr["target_bank_repair_count"])
    return {
        "fault": None,
        "cpads": [],
        "advisories": [],
    }


def _validate_source(source: Dict[str, Any]) -> None:
    if not isinstance(source, dict) or set(source) != {
            "cper_file", "section_index"}:
        raise ValueError(
            "Samsung action source must contain cper_file and section_index")
    if not isinstance(source["cper_file"], str) or not source["cper_file"]:
        raise ValueError("Samsung action cper_file must be a non-empty string")
    if (not isinstance(source["section_index"], int)
            or isinstance(source["section_index"], bool)
            or source["section_index"] < 0):
        raise ValueError(
            "Samsung action section_index must be a non-negative integer")


def _to_contoso_action_request(action: Dict[str, Any]) -> Dict[str, Any]:
    required = {
        "source", "action", "confidence", "urgency", "parameters", "reason"}
    if not isinstance(action, dict) or set(action) != required:
        raise ValueError(
            "Samsung action must contain source, action, confidence, "
            "urgency, parameters, and reason")
    _validate_source(action["source"])
    action_name = action["action"]
    try:
        action_id = _ACTION_IDS[action_name]
    except KeyError as exc:
        raise ValueError(f"unsupported Samsung action {action_name}") from exc
    confidence = action["confidence"]
    if (not isinstance(confidence, int) or isinstance(confidence, bool)
            or not 0 <= confidence <= 100):
        raise ValueError("Samsung action confidence must be an integer 0..100")
    urgency = action["urgency"]
    if not isinstance(urgency, bool):
        raise ValueError("Samsung action urgency must be a boolean")
    parameters = action["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("Samsung action parameters must be an object")
    if (action_name in _FRU_TARGET_ACTIONS
            and not _FRU_PARAMETER_FIELDS.issubset(parameters)):
        raise ValueError(
            f"{action_name} parameters must contain fru_id and fru_text")
    if action_name in _EMPTY_BODY_ACTIONS:
        allowed = (
            _FRU_PARAMETER_FIELDS
            if action_name in _FRU_TARGET_ACTIONS
            else set()
        )
        if set(parameters) != allowed:
            raise ValueError(
                f"{action_name} parameters may contain only "
                f"{', '.join(sorted(allowed)) or 'no fields'}")
    if not isinstance(action["reason"], str) or not action["reason"].strip():
        raise ValueError("Samsung action reason must be a non-empty string")
    return {
        **action["source"],
        "action_id": action_id,
        "confidence": confidence,
        "urgency": urgency,
        "parameters": copy.deepcopy(parameters),
    }


def _to_contoso_cpad_requests(
        result: Dict[str, Any],
        events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(result, dict) or set(result) != {
            "fault", "cpads", "advisories"}:
        raise ValueError(
            "Samsung result must contain fault, cpads, and advisories")
    if not isinstance(result["cpads"], list):
        raise ValueError("Samsung result cpads must be a list")
    if not isinstance(result["advisories"], list):
        raise ValueError("Samsung result advisories must be a list")
    available = {
        (event.get("cper_file"), event.get("section_index"))
        for event in events
        if event.get("event_type") == "memory_error"
    }
    proposals = []
    for cpad in result["cpads"]:
        if not isinstance(cpad, dict) or set(cpad) != {"actions"}:
            raise ValueError(
                "Samsung CPAD proposal must contain exactly actions")
        actions = cpad["actions"]
        if not isinstance(actions, list) or not actions:
            raise ValueError(
                "Samsung CPAD proposal actions must be a non-empty list")
        requests = []
        for action in actions:
            request = _to_contoso_action_request(action)
            source = request["cper_file"], request["section_index"]
            if source not in available:
                raise ValueError(
                    "Samsung action source must identify an input memory error")
            requests.append(request)
        proposals.append({"sections": requests})
    return proposals


def analyze_memory_events(events):
    """Adapt canonical events to Samsung analysis and return action requests."""
    records = [_to_samsung_record(event) for event in events]
    result = analyze(records)
    return _to_contoso_cpad_requests(result, events)
