"""Contoso-owned interpretation of Error Injection CPAD section bodies."""

from __future__ import annotations

import base64
import copy
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .action_provider import GeneratedCper
from .contoso_memory import (
    is_contoso_memory_cpad,
    overlay_cpad_memory_state,
)
from .memory_config import MemoryRepairState


CONTOSO_CPU_SECTION_GUID = "f63f509b-8995-4efd-9144-4b7fed6c4fd3"
CONTOSO_MEMORY_SECTION_GUID = "e01ce992-d080-43f4-8a2c-df8a9d81eb4e"
CONTOSO_ERROR_SECTION_GUIDS = frozenset({
    CONTOSO_CPU_SECTION_GUID,
    CONTOSO_MEMORY_SECTION_GUID,
})

_SECTION_HEADER_SIZE = 8
_ERROR_BANK_SIZE = 40
_SEVERITY_TO_CPER = {
    1: {"code": 1, "name": "Fatal"},
    2: {"code": 1, "name": "Fatal"},
    3: {"code": 0, "name": "Recoverable"},
    4: {"code": 3, "name": "Informational"},
    5: {"code": 2, "name": "Corrected"},
}
_SEVERITY_RANK = {
    "Fatal": 3,
    "Recoverable": 2,
    "Corrected": 1,
    "Informational": 0,
}
_NOTIFICATION_BY_SEVERITY = {
    "Corrected": {
        "guid": "2dce8bb1-bdd7-450e-b9ad-9cf4ebd4f890",
        "type": "Corrected Machine Check (CMC)",
    },
    "Informational": {
        "guid": "2dce8bb1-bdd7-450e-b9ad-9cf4ebd4f890",
        "type": "Corrected Machine Check (CMC)",
    },
    "Recoverable": {
        "guid": "e8f56ffe-919c-4cc5-ba88-65abe14913bb",
        "type": "Machine Check Exception (MCE)",
    },
    "Fatal": {
        "guid": "e8f56ffe-919c-4cc5-ba88-65abe14913bb",
        "type": "Machine Check Exception (MCE)",
    },
}


def _body_severity(body: bytes) -> Dict[str, Any]:
    """Decode the highest logged Contoso error severity."""
    if len(body) < _SECTION_HEADER_SIZE:
        raise ValueError("Contoso error section body is truncated")
    bank_count = struct.unpack_from("<H", body, 2)[0]
    if bank_count == 0:
        raise ValueError("Contoso error section contains no error banks")
    if len(body) < _SECTION_HEADER_SIZE + bank_count * _ERROR_BANK_SIZE:
        raise ValueError("Contoso error-bank table is truncated")

    best = None
    for index in range(bank_count):
        offset = _SECTION_HEADER_SIZE + _ERROR_BANK_SIZE * index
        status = struct.unpack_from("<Q", body, offset)[0]
        if status & 0xFFFF == 0:
            continue
        severity = _SEVERITY_TO_CPER.get((status >> 59) & 0x7)
        if severity is None:
            raise ValueError("Contoso error section has an invalid severity")
        if (best is None
                or _SEVERITY_RANK[severity["name"]]
                > _SEVERITY_RANK[best["name"]]):
            best = severity
    if best is None:
        raise ValueError("Contoso error injection contains no logged error")
    return dict(best)


def build_contoso_injected_error(
        cpad_data: Dict[str, Any],
        metadata: Dict[str, Any],
        memory_states: Dict[str, MemoryRepairState]) -> GeneratedCper:
    """Build the error CPER requested by one Contoso Error Injection section."""
    section_index = metadata.get("section_index", 0)
    descriptors = cpad_data.get("sectionDescriptors", [])
    sections = cpad_data.get("sections", [])
    if (not 0 <= section_index < len(descriptors)
            or not 0 <= section_index < len(sections)):
        raise ValueError("Error Injection section index is out of range")
    descriptor = descriptors[section_index]
    section_type = descriptor.get("sectionType", {})
    guid = (
        section_type.get("data", "").lower()
        if isinstance(section_type, dict)
        else ""
    )
    if guid not in CONTOSO_ERROR_SECTION_GUIDS:
        raise ValueError(
            f"unsupported Contoso Error Injection section type {guid}")

    encoded = sections[section_index].get("Unknown", {}).get("data")
    if not encoded:
        raise ValueError("Contoso Error Injection section has no body")
    try:
        body = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError(
            "Contoso Error Injection section body is not valid base64") from exc

    if is_contoso_memory_cpad(cpad_data, section_index):
        try:
            state = memory_states[metadata["partition_id"]]
        except KeyError as exc:
            raise ValueError(
                f"no memory configuration for partition "
                f"{metadata['partition_id']}") from exc
        body = overlay_cpad_memory_state(
            cpad_data,
            state,
            allow_spd_temperature_override=True,
            section_index=section_index,
        )

    severity = _body_severity(body)
    template = (
        Path(__file__).resolve().parent
        / "templates"
        / "contosoErrorCperTemplate.json"
    )
    with template.open(encoding="utf-8") as stream:
        cper = json.load(stream)
    cper = copy.deepcopy(cper)

    cpad_header = cpad_data.get("header", {})
    cper["header"].update({
        "recordID": 0,
        "creatorID": cpad_header.get("creatorID"),
        "platformID": cpad_header.get("platformID"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "timestampIsPrecise": True,
        "severity": severity,
        "notificationType": dict(
            _NOTIFICATION_BY_SEVERITY[severity["name"]]),
    })
    if "partitionID" in cpad_header:
        cper["header"]["partitionID"] = cpad_header["partitionID"]
    if isinstance(cpad_header.get("revision"), dict):
        cper["header"]["revision"] = cpad_header["revision"]

    cper_descriptor = cper["sectionDescriptors"][0]
    cper_descriptor.update({
        "fruID": descriptor.get("fruID"),
        "fruText": descriptor.get("fruText"),
        "sectionType": {
            "data": guid,
            "type": section_type.get("type", "Unknown"),
        },
        "severity": severity,
        "sectionOffset": 200,
        "sectionLength": len(body),
    })
    if isinstance(descriptor.get("revision"), dict):
        cper_descriptor["revision"] = descriptor["revision"]
    cper["sections"] = [{
        "Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        },
    }]
    cper["header"]["recordLength"] = 200 + len(body)

    return GeneratedCper(
        cper_data=cper,
        description=f"{severity['name']} Contoso error",
    )
