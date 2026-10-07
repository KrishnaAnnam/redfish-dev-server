"""Adapter between canonical Contoso memory events and Micron MERC."""

from __future__ import annotations

import csv
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

from contoso_action_parameters import (
    PAGE_OFFLINE_ACTION_ID,
    POWER_CYCLE_ACTION_ID,
    PPR_ACTION_ID,
    PPR_TYPE_SOFT_RUNTIME,
    REBOOT_WITH_RETRAINING_ACTION_ID,
    REPLACE_PART_ACTION_ID,
    RESEAT_PART_ACTION_ID,
)
from memory_address_translation import (
    MemoryAddressConfiguration,
    MemoryChannelAddress,
    MemoryOrganization,
    memory_address_to_physical_address,
)


SHIM_INFO = {
    "api_version": 5,
    "name": "Micron MERC Memory Analyzer Shim",
    "version": "1.0.0",
    "dram_manufacturer_ids": [[0x80, 0x2C]],
}

MERC_INPUT_ENV = "MICRON_MERC_INPUT_FILE"
MERC_EXECUTABLE = (
    Path(__file__).resolve().parent
    / "vendor_tools"
    / "micron"
    / "merc3_1_1"
    / "merc3"
)
RETRY_READ_FIELDS = (
    "msn",
    "mpn",
    "rr_log",
    "rr_addr1",
    "rr_addr2",
    "rr_parity",
    "intel_hw_gen",
)

_NO_ACTION_CLASSES = {
    "correctable",
    "low_severity",
    "system_transient",
}


def _read_retry_rows(path: Path) -> List[Dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = [field for field in RETRY_READ_FIELDS
                       if field not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(
                    f"Micron MERC input is missing columns: {', '.join(missing)}")
            rows = []
            for line_number, row in enumerate(reader, start=2):
                normalized = {
                    field: str(row.get(field, "")).strip()
                    for field in RETRY_READ_FIELDS
                }
                empty = [field for field, value in normalized.items() if not value]
                if empty:
                    raise ValueError(
                        f"Micron MERC input line {line_number} has empty fields: "
                        f"{', '.join(empty)}")
                rows.append(normalized)
    except OSError as exc:
        raise ValueError(f"cannot read Micron MERC input {path}: {exc}") from exc
    if not rows:
        raise ValueError("Micron MERC input contains no error rows")
    return rows


def _run_merc(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not MERC_EXECUTABLE.is_file():
        raise ValueError(f"Micron MERC executable not found: {MERC_EXECUTABLE}")
    with tempfile.TemporaryDirectory(prefix="ras-micron-merc-") as temp_dir:
        input_path = Path(temp_dir) / "retry-read.csv"
        output_path = Path(temp_dir) / "merc-results.csv"
        with input_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=RETRY_READ_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        result = subprocess.run(
            [
                str(MERC_EXECUTABLE),
                "-i", str(input_path),
                "-o", str(output_path),
                "-n", "1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"Micron MERC exited with status {result.returncode}: {details}")
        if not output_path.is_file():
            raise RuntimeError("Micron MERC did not create its output CSV")
        with output_path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            required = {"msn", "mpn", "predicted_class", "recommended_action"}
            missing = sorted(required.difference(reader.fieldnames or []))
            if missing:
                raise RuntimeError(
                    f"Micron MERC output is missing columns: {', '.join(missing)}")
            return [dict(row) for row in reader]


def _source(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "cper_file": event["cper_file"],
        "section_index": event["section_index"],
    }


def _fru_parameters(event: Dict[str, Any]) -> Dict[str, str]:
    return {
        "fru_id": event["fru_id"],
        "fru_text": event["fru_text"],
    }


def _ppr_parameters(event: Dict[str, Any]) -> Dict[str, Any]:
    error = event["memory_error"]
    subcomponent = error["subcomponent"]
    additional = error["additional"]
    return {
        **_fru_parameters(event),
        "ppr_type": PPR_TYPE_SOFT_RUNTIME,
        "chiplet": subcomponent["chiplet"],
        "controller": subcomponent["controller"],
        "channel": additional["channel"],
        "dimm": additional["dimm"],
        "subchannel": additional["subchannel"],
        "rank": additional["rank"],
        "device": additional["device"],
        "bank_group": additional["bank_group"],
        "bank": additional["bank"],
        "row": additional["row"],
    }


def _required_int(row: Dict[str, str], field: str) -> int:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(
            f"Micron MERC {row.get('predicted_class')} result has no {field}")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"Micron MERC {field} is not numeric: {value}") from exc
    if not parsed.is_integer():
        raise ValueError(f"Micron MERC {field} is not an integer: {value}")
    return int(parsed)


def _page_offline_parameters(
        event: Dict[str, Any],
        result: Dict[str, str]) -> Dict[str, Any]:
    error = event["memory_error"]
    additional = error["additional"]
    subcomponent = error["subcomponent"]
    organization_data = event.get("memory_organization")
    translated = event.get("address_translation")
    if not isinstance(organization_data, dict) or not isinstance(translated, dict):
        raise ValueError(
            "Micron block_of_rows requires valid memory address translation")

    organization = MemoryOrganization(
        version=organization_data["version"],
        address_translation=organization_data["address_translation"],
        dimm_size_gib=organization_data["dimm_size_gib"],
    )
    configuration = MemoryAddressConfiguration(organization)
    dimm_geometry = organization.dimm
    memory_address = translated["memory_address"]
    dimm_base = memory_address_to_physical_address(
        MemoryChannelAddress(
            socket=memory_address["socket"],
            chiplet=subcomponent["chiplet"],
            memory_controller=subcomponent["controller"],
            channel=additional["channel"],
            dimm=additional["dimm"],
            subchannel=0,
            rank=0,
            bank_group=0,
            bank=0,
            row=0,
            column=0,
            byte_in_column=0,
        ),
        configuration,
    )
    pages_per_dimm = dimm_geometry.dimm_size_bytes // 4096

    ranges = []
    for index in range(1, 5):
        minimum = str(result.get(f"offline_range_{index}_min", "")).strip()
        maximum = str(result.get(f"offline_range_{index}_max", "")).strip()
        if not minimum and not maximum:
            continue
        page_min = _required_int(result, f"offline_range_{index}_min")
        page_max = _required_int(result, f"offline_range_{index}_max")
        if not 0 <= page_min <= page_max < pages_per_dimm:
            raise ValueError(
                f"Micron MERC offline page range {page_min}..{page_max} "
                f"does not fit the configured DIMM")
        ranges.append({
            "start_address": dimm_base + page_min * 4096,
            "page_count": page_max - page_min + 1,
        })
    if not ranges:
        raise ValueError(
            "Micron block_of_rows result contains no offline row ranges")
    return {**_fru_parameters(event), "page_ranges": ranges}


def _action_request(
        event: Dict[str, Any],
        result: Dict[str, str]) -> Dict[str, Any] | None:
    classification = str(result.get("predicted_class", "")).strip().lower()
    if classification in _NO_ACTION_CLASSES:
        return None

    parameters: Dict[str, Any]
    urgency = False
    if classification == "block_of_rows":
        has_ranges = any(
            str(result.get(f"offline_range_{index}_min", "")).strip()
            and str(result.get(f"offline_range_{index}_max", "")).strip()
            for index in range(1, 5)
        )
        if has_ranges:
            action_id = PAGE_OFFLINE_ACTION_ID
            confidence = 90
            urgency = True
            parameters = _page_offline_parameters(event, result)
        else:
            print(
                "Micron MERC classified block_of_rows without actionable "
                "offline ranges; falling back to Replace Part.")
            action_id = REPLACE_PART_ACTION_ID
            confidence = 90
            urgency = True
            parameters = _fru_parameters(event)
    elif classification == "high_severity":
        action_id = REPLACE_PART_ACTION_ID
        confidence = 95
        urgency = True
        parameters = _fru_parameters(event)
    elif classification == "dram_transient":
        action_id = POWER_CYCLE_ACTION_ID
        confidence = 85
        parameters = {}
    elif classification == "ppr_eligible":
        action_id = PPR_ACTION_ID
        confidence = 85
        parameters = _ppr_parameters(event)
    elif classification == "system_general":
        action_id = REBOOT_WITH_RETRAINING_ACTION_ID
        confidence = 80
        parameters = {}
    elif classification == "system_socketing":
        action_id = RESEAT_PART_ACTION_ID
        confidence = 95
        parameters = _fru_parameters(event)
    else:
        raise ValueError(
            f"Micron MERC returned unsupported classification: {classification}")

    return {
        **_source(event),
        "action_id": action_id,
        "confidence": confidence,
        "urgency": urgency,
        "parameters": parameters,
    }


def _newest_memory_error(
        events: Iterable[Dict[str, Any]]) -> Dict[str, Any] | None:
    matches = [
        event for event in events
        if event.get("event_type") == "memory_error"
        and event.get("source", {}).get("is_newest")
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Micron MERC requires one newest memory-error section")
    return matches[0]


def analyze_memory_events(events):
    """Run MERC for the newest Micron DIMM and return grouped CPAD requests."""
    input_value = os.environ.get(MERC_INPUT_ENV)
    if not input_value:
        return []
    event = _newest_memory_error(events)
    if event is None:
        return []

    additional = event["memory_error"]["additional"]
    serial_number = str(additional.get("serial_number", "")).strip()
    part_number = str(additional.get("part_number", "")).strip()
    rows = [
        row for row in _read_retry_rows(Path(input_value).expanduser())
        if row["msn"] == serial_number and row["mpn"] == part_number
    ]
    if not rows:
        raise ValueError(
            f"Micron MERC input has no rows for DIMM "
            f"{serial_number}/{part_number}")

    proposals = []
    seen = set()
    for result in _run_merc(rows):
        request = _action_request(event, result)
        if request is None:
            continue
        key = repr(request)
        if key in seen:
            continue
        seen.add(key)
        proposals.append({"sections": [request]})
    return proposals
