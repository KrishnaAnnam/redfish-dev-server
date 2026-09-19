"""Contoso memory-controller orchestration for decoded CPER windows."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Tuple

import contoso_catalog
from memory_events import decode_memory_events, manufacturer_id
from memory_shims import discover_memory_shims


MEMORY_SECTION_NAME = "Memory Controller - First Generation"
DRAM_ERRORS = "DRAM Errors"
OTHER_ERRORS = "Other Errors"
CORRECTED = contoso_catalog.SEVERITY_VALUES["Corrected"]


def _identity(header: Dict[str, Any]) -> Tuple[str, str, str]:
    def identifier(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("guid", value.get("data", ""))
        return str(value or "").strip().strip("{}").lower()

    return (
        identifier(header.get("creatorID")),
        identifier(header.get("platformID")),
        identifier(header.get("partitionID")),
    )


class MemoryControllerAnalyzer:
    """Own memory history, vendor-shim, row, and SPPR orchestration."""

    def __init__(self, host: Any, shim_dir: Any):
        self.host = host
        self.shims, self.shim_errors = discover_memory_shims(shim_dir)
        # Keep the pre-refactor API usable for callers and focused tests.
        host.memory_shims = self.shims
        host.memory_shim_errors = self.shim_errors

    @staticmethod
    def _newest_dram_vendor(
            newest_sections: Iterable[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
        vendors = {
            tuple(section["decoded"]["additional"]["dram_manufacturer_id"])
            for section in newest_sections
            if section["decoded"]["bank_name"] == DRAM_ERRORS
        }
        if len(vendors) > 1:
            formatted = ", ".join(
                f"{vendor[0]:02X} {vendor[1]:02X}" for vendor in sorted(vendors))
            raise ValueError(
                "newest memory-controller DRAM sections must identify one "
                f"manufacturer; found {formatted}")
        return next(iter(vendors), None)

    @staticmethod
    def _filtered_events(records: List[Dict[str, Any]],
                         newest_vendor: Optional[Tuple[int, int]]):
        if not records:
            return []
        newest_identity = _identity(records[0]["cper_data"].get("header", {}))
        matching_records = [
            record
            if _identity(record["cper_data"].get("header", {})) == newest_identity
            else {
                "cper_data": {},
                "cper_file": record.get("cper_file", ""),
                "is_newest": record.get("is_newest", False),
            }
            for record in records
        ]
        events = decode_memory_events(matching_records)
        if newest_vendor is None:
            action_vendors = {
                manufacturer_id(event)
                for event in events
                if event["source"]["is_newest"]
                and event["event_type"] == "platform_action"
                and manufacturer_id(event) is not None
            }
            if len(action_vendors) == 1:
                newest_vendor = next(iter(action_vendors))
        filtered = []
        for event in events:
            if event["source"]["is_newest"]:
                filtered.append(event)
                continue
            if (event["event_type"] == "memory_error"
                    and event["memory_error"]["bank"] == DRAM_ERRORS
                    and manufacturer_id(event) == newest_vendor):
                filtered.append(event)
        return filtered

    def _analysis_route(
            self, newest_vendor: Optional[Tuple[int, int]],
            shim_result: Dict[str, Any]) -> Dict[str, Any]:
        """Describe which analyzer owns the newest memory-controller errors."""
        if newest_vendor is None:
            return {
                "heading": "Memory analysis routing",
                "messages": [
                    "Using the default Contoso memory-controller analyzer.",
                    "Reason: No DRAM vendor applies to this error.",
                ],
            }

        vendor_text = f"{newest_vendor[0]:02X} {newest_vendor[1]:02X}"
        if newest_vendor in shim_result["handled_manufacturers"]:
            shim = self.shims[newest_vendor]
            return {
                "heading": "Memory analysis routing",
                "messages": [
                    f"Using memory-vendor analyzer: {shim.name}",
                    f"DRAM manufacturer: {vendor_text}",
                ],
            }

        if newest_vendor in shim_result["failed_manufacturers"]:
            return {
                "heading": "Memory analysis routing",
                "messages": [
                    "Using the default Contoso memory analyzer.",
                    "Reason: The matching memory-vendor analyzer failed.",
                ],
            }

        if not self.shims:
            reason = "No memory-vendor analyzers are available."
        else:
            reason = (
                "No memory-vendor analyzer is registered for DRAM "
                f"manufacturer {vendor_text}."
            )
        return {
            "heading": "Memory analysis routing",
            "messages": [
                "Using the default Contoso memory analyzer.",
                f"Reason: {reason}",
            ],
        }

    def analyze(self, newest_sections: List[Dict[str, Any]],
                records: List[Dict[str, Any]], source_stem: str,
                prior_cper_count: int = 0) -> Dict[str, Any]:
        newest_vendor = self._newest_dram_vendor(newest_sections)
        events = self._filtered_events(records, newest_vendor)
        selected_history = {
            event["source"]["cper_file"]
            for event in events
            if not event["source"]["is_newest"]
            and event["event_type"] == "memory_error"
            and event["memory_error"]["bank"] == DRAM_ERRORS
        }
        for event in events:
            if (event["event_type"] == "memory_error"
                    and not event["source"]["is_newest"]
                    and event["memory_error"]["bank"] == DRAM_ERRORS):
                self.host._add_to_seen_locations(
                    self.host._memory_location_from_event(event))
        shim_result = self.host.analyze_memory_events(
            events, self.shims, newest_vendor)
        shim_cpad_paths, emission_errors = self.host.emit_shim_cpad_groups(
            shim_result, source_stem)

        newest_dram_events = [
            event for event in events
            if event["event_type"] == "memory_error"
            and event["source"]["is_newest"]
            and event["memory_error"]["bank"] == DRAM_ERRORS
            and self.host._memory_location_from_event(event) is not None
        ]
        other_findings = [
            self._memory_error_finding(event, "contoso")
            for event in events
            if event["event_type"] == "memory_error"
            and event["source"]["is_newest"]
            and event["memory_error"]["bank"] == OTHER_ERRORS
        ]
        default_events = self.host.default_memory_events(shim_result)
        default_locations = [
            self.host._memory_location_from_event(event)
            for event in default_events
        ]
        failure_locations = [
            location
            for event, location in zip(default_events, default_locations)
            if event["memory_error"]["error_status"]["severity_value"] == CORRECTED
            and self.host._has_prior_error_on_same_dram_device_row_at_different_column(
                location)
        ]
        default_cpad_paths = []
        generation_failures = []
        newest_record = records[0]
        for event, location in zip(default_events, default_locations):
            section_index = event["source"]["section_index"]
            output_stem = source_stem
            if len(default_events) > 1:
                output_stem = f"{source_stem}_section{section_index + 1}"
            path = self.host.create_sppr_cpad_from_memory_event(
                event,
                newest_record["cper_data"],
                newest_record["cper_file"],
                output_stem,
                record_location=False,
            )
            if path:
                default_cpad_paths.append(path)
            elif location in failure_locations:
                generation_failures.append(location)
        for location in default_locations:
            self.host._add_to_seen_locations(location)

        memory_location = (
            self.host._memory_location_from_event(newest_dram_events[0])
            if newest_dram_events else None
        )
        recommendation_location = (
            failure_locations[0] if failure_locations else memory_location)
        dram_findings = [
            self._memory_error_finding(
                event,
                ("vendor_shim"
                 if tuple(event["dram_manufacturer_id"])
                 in shim_result["handled_manufacturers"]
                 else "contoso"),
            )
            for event in newest_dram_events
        ]

        return {
            "subcomponent": "memory_controller",
            "section_indexes": [
                section["source"]["section_index"] for section in newest_sections
            ],
            "newest_vendor": list(newest_vendor) if newest_vendor else None,
            "events": events,
            "newest_dram_events": newest_dram_events,
            "default_events": default_events,
            "findings": [*dram_findings, *other_findings],
            "cpads": [*shim_cpad_paths, *default_cpad_paths],
            "shim_cpads": shim_cpad_paths,
            "default_cpads": default_cpad_paths,
            "failure_locations": failure_locations,
            "recommendation_location": recommendation_location,
            "dram_row_failure_detected": bool(failure_locations),
            "cpad_generation_failed": bool(generation_failures),
            "all_newest_dram_errors_handled": (
                bool(newest_dram_events) and not default_events),
            "shim_result": shim_result,
            "emission_errors": emission_errors,
            "analysis_route": self._analysis_route(
                newest_vendor, shim_result),
            "history_summary": {
                "heading": "Memory-controller history",
                "messages": [
                    f"Evaluated {prior_cper_count} prior CPER candidate(s) "
                    "for matching memory-controller errors.",
                    f"Selected {len(selected_history)} same-vendor memory "
                    "record(s).",
                ],
            },
        }

    @staticmethod
    def _memory_error_finding(
            event: Dict[str, Any], analysis_owner: str) -> Dict[str, Any]:
        error = event["memory_error"]
        return {
            "subcomponent": "memory_controller",
            "source": copy.deepcopy(event["source"]),
            "section_type": MEMORY_SECTION_NAME,
            "fru": copy.deepcopy(event["fru"]),
            "error": {
                "bank": error["bank"],
                "id": error["id"],
                "name": error["name"],
                "severity": error["error_status"]["severity_value"],
                "address": error["error_address"],
                "subcomponent": copy.deepcopy(error["subcomponent"]),
                "additional": copy.deepcopy(error["additional"]),
            },
            "analysis_owner": analysis_owner,
        }
