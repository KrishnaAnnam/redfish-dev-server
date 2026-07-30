#!/usr/bin/env python3
"""Focused tests for Contoso analyzer SPPR row-failure detection."""

import base64
import importlib.util
from pathlib import Path


ANALYZER_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "ras_api_demo"
    / "analyzers"
    / "contoso"
    / "analyzer-contoso.py"
)
SPEC = importlib.util.spec_from_file_location("analyzer_contoso", ANALYZER_PATH)
assert SPEC and SPEC.loader
ANALYZER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER_MODULE)
ContosoAnalyzer = ANALYZER_MODULE.ContosoAnalyzer
contoso_encoder = ANALYZER_MODULE.contoso_encoder
contoso_catalog = ANALYZER_MODULE.contoso_catalog


def _location(column: int, device: int):
    return {
        "chiplet": 0,
        "controller": 0,
        "channel": 1,
        "subchannel": 0,
        "dimm": 0,
        "rank": 2,
        "bank_group": 3,
        "bank": 1,
        "row": 42,
        "column": column,
        "device": device,
    }


def _analyzer_with_seen(*locations):
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    analyzer.seen_locations = list(locations)
    return analyzer


def test_memory_location_uses_single_failing_dram_as_device():
    beat_mask = [[0] * 4 for _ in range(10)]
    beat_mask[3][2] = 1 << 5
    fields = {
        "subcomponent": {"chiplet": 0, "controller": 0},
        "error_status": (True, False, 0, 1),
        "error_address": 0,
        "misc0": (False, 1),
        "misc1": 0,
        "additional": {
            "channel": 1,
            "subchannel": 0,
            "dimm": 0,
            "rank": 2,
            "bank_group": 3,
            "bank": 1,
            "row": 42,
            "column": 10,
            "syndrome": 0,
            "beat_mask": beat_mask,
        },
    }
    body = contoso_encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    cper_data = {
        "sectionDescriptors": [{"sectionType": {
            "data": contoso_catalog.SECTION_TYPES[
                "Memory Controller - First Generation"]["guid"]
        }}],
        "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii")
        }}],
    }

    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    location = analyzer._extract_memory_location(cper_data)

    assert location is not None
    assert location["device"] == 3


def test_sppr_matches_different_columns_on_same_row_and_device():
    analyzer = _analyzer_with_seen(_location(column=10, device=3))
    current = _location(column=20, device=3)

    assert analyzer._has_prior_error_on_same_dram_device_row_at_different_column(
        current)
    assert analyzer._distinct_columns_on_row(current) == 2


def test_sppr_does_not_match_same_row_on_different_device():
    analyzer = _analyzer_with_seen(_location(column=10, device=3))
    current = _location(column=20, device=7)

    assert not analyzer._has_prior_error_on_same_dram_device_row_at_different_column(
        current)
    assert analyzer._distinct_columns_on_row(current) == 1


def test_sppr_requires_an_identifiable_device():
    prior = _location(column=10, device=3)
    current = _location(column=20, device=3)
    prior["device"] = None
    current["device"] = None
    analyzer = _analyzer_with_seen(prior)

    assert not analyzer._has_prior_error_on_same_dram_device_row_at_different_column(
        current)
    assert analyzer._distinct_columns_on_row(current) == 0


def test_failing_row_report_does_not_count_recorded_current_error_twice():
    prior = _location(column=567, device=3)
    current = _location(column=891, device=3)
    analyzer = _analyzer_with_seen(prior, current)

    lines = analyzer._failing_row_lines(current)

    error_lines = [line for line in lines if line.strip().startswith("Error ")]
    assert len(error_lines) == 2
    assert sum("Column 567" in line for line in error_lines) == 1
    assert sum("Column 891" in line for line in error_lines) == 1


def test_beat_mask_format_names_device_dq_and_beat():
    beat_mask = [[0] * 4 for _ in range(10)]
    beat_mask[3][1] = 0x80

    formatted = ContosoAnalyzer._fmt_register(
        "beat_mask", ("array", "H", (10, 4)), beat_mask)

    assert formatted == "Device 3, DQ 1, beat 7 (mask 0x80)"