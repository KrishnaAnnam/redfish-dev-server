"""Contoso CPU-core CPER section analyzer."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

import contoso_catalog


CPU_SECTION_NAME = "CPU Core - First Generation"
_SEVERITY_NAMES = {
    value: name for name, value in contoso_catalog.SEVERITY_VALUES.items()
}


class CpuCoreAnalyzer:
    """Analyze every decoded CPU-core section from the newest CPER."""

    def analyze(self, sections: Iterable[Dict[str, Any]],
                prior_cper_count: int = 0) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        section_indexes: List[int] = []

        for section in sections:
            if section.get("section_name") != CPU_SECTION_NAME:
                continue
            decoded = section["decoded"]
            status = decoded["error_status"]
            error_name = contoso_catalog.error_name_from_id(
                CPU_SECTION_NAME, decoded["bank_name"], status["error_id"])
            source = copy.deepcopy(section["source"])
            section_indexes.append(source["section_index"])
            findings.append({
                "subcomponent": "cpu_core",
                "source": source,
                "section_type": CPU_SECTION_NAME,
                "fru": copy.deepcopy(section.get("fru", {})),
                "error": {
                    "bank": decoded["bank_name"],
                    "id": status["error_id"],
                    "name": error_name,
                    "severity": {
                        "code": status["severity_value"],
                        "name": _SEVERITY_NAMES.get(
                            status["severity_value"], "Unknown"),
                    },
                    "address_valid": status["addressValid"],
                    "overflow": status["overflow"],
                    "address": decoded["error_address"],
                    "injected": decoded["misc0"]["injected"],
                    "corrected_error_count": decoded["misc0"]["ce_count"],
                    "subcomponent": copy.deepcopy(decoded["subcomponent"]),
                    "additional": copy.deepcopy(decoded["additional"]),
                },
            })

        return {
            "subcomponent": "cpu_core",
            "section_indexes": section_indexes,
            "findings": findings,
            "cpads": [],
            "history_summary": {
                "heading": "CPU-core analysis",
                "messages": [
                    "This error does not require historical analysis; "
                    f"{prior_cper_count} prior CPER candidate(s) were not used."
                ],
            },
        }
