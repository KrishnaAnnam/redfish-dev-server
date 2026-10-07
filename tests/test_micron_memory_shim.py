#!/usr/bin/env python3
"""Focused tests for the Micron MERC memory-vendor adapter."""

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTOSO_DIR = ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso"
SHIM_DIR = CONTOSO_DIR / "memory_shims"
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
for path in (ROOT, CONTOSO_DIR, SHIM_DIR, RAS_DEMO_DIR):
    sys.path.insert(0, str(path))

import analyzer_micron as micron  # noqa: E402
import contoso_action_parameters as actions  # noqa: E402

HELPERS_SPEC = importlib.util.spec_from_file_location(
    "micron_test_helpers", ROOT / "tests" / "test_contoso_memory_shims.py")
assert HELPERS_SPEC and HELPERS_SPEC.loader
helpers = importlib.util.module_from_spec(HELPERS_SPEC)
HELPERS_SPEC.loader.exec_module(helpers)


def _micron_event():
    return helpers.decode_memory_events(
        helpers._records(helpers._memory_cper(helpers.MICRON)))[0]


def test_micron_is_inactive_without_a_selected_input(monkeypatch):
    monkeypatch.delenv(micron.MERC_INPUT_ENV, raising=False)
    assert micron.analyze_memory_events([_micron_event()]) == []


def test_micron_action_only_event_does_not_rerun_merc(
        monkeypatch, tmp_path):
    input_path = tmp_path / "retry.csv"
    input_path.write_text(
        "msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen\n"
        "SERIAL,PART,1,2,3,4,2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(micron.MERC_INPUT_ENV, str(input_path))
    monkeypatch.setattr(
        micron, "_run_merc",
        lambda _rows: (_ for _ in ()).throw(
            AssertionError("MERC must not run for an action-only event")))
    action_event = helpers.decode_memory_events(helpers._records(
        helpers._action_cper(),
        helpers._memory_cper(helpers.MICRON),
    ))[0]

    assert action_event["event_type"] == "platform_action"
    assert micron.analyze_memory_events([action_event]) == []


def test_micron_maps_merc_classes_to_supported_actions(
        monkeypatch, tmp_path):
    input_path = tmp_path / "retry.csv"
    input_path.write_text(
        "msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen\n"
        "SERIAL,PART,1,2,3,4,2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(micron.MERC_INPUT_ENV, str(input_path))
    monkeypatch.setattr(micron, "_run_merc", lambda _rows: [
        {"predicted_class": "high_severity"},
        {"predicted_class": "dram_transient"},
        {"predicted_class": "ppr_eligible"},
        {"predicted_class": "system_general"},
        {"predicted_class": "system_socketing"},
        {"predicted_class": "correctable"},
    ])

    proposals = micron.analyze_memory_events([_micron_event()])
    requests = [proposal["sections"][0] for proposal in proposals]

    assert [request["action_id"] for request in requests] == [
        actions.REPLACE_PART_ACTION_ID,
        actions.POWER_CYCLE_ACTION_ID,
        actions.PPR_ACTION_ID,
        actions.REBOOT_WITH_RETRAINING_ACTION_ID,
        actions.RESEAT_PART_ACTION_ID,
    ]
    assert requests[0]["parameters"]["fru_text"] == helpers.FRU_TEXT
    assert requests[2]["parameters"]["row"] == 1234


def test_micron_block_of_rows_becomes_page_offline(monkeypatch, tmp_path):
    input_path = tmp_path / "retry.csv"
    input_path.write_text(
        "msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen\n"
        "SERIAL,PART,1,2,3,4,2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(micron.MERC_INPUT_ENV, str(input_path))
    monkeypatch.setattr(micron, "_run_merc", lambda _rows: [{
        "predicted_class": "block_of_rows",
        "bank": "11",
        "offline_range_1_min": "100",
        "offline_range_1_max": "101",
    }])

    request = micron.analyze_memory_events(
        [_micron_event()])[0]["sections"][0]

    assert request["action_id"] == actions.PAGE_OFFLINE_ACTION_ID
    assert request["parameters"]["page_ranges"][0]["page_count"] == 2
    assert request["parameters"]["page_ranges"][0]["start_address"] % 4096 == 0


def test_micron_block_without_ranges_replaces_dimm(monkeypatch, tmp_path):
    input_path = tmp_path / "retry.csv"
    input_path.write_text(
        "msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen\n"
        "SERIAL,PART,1,2,3,4,2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(micron.MERC_INPUT_ENV, str(input_path))
    monkeypatch.setattr(micron, "_run_merc", lambda _rows: [{
        "predicted_class": "block_of_rows",
    }])

    request = micron.analyze_memory_events(
        [_micron_event()])[0]["sections"][0]

    assert request["action_id"] == actions.REPLACE_PART_ACTION_ID
    assert request["parameters"] == {
        "fru_id": helpers.FRU_ID,
        "fru_text": helpers.FRU_TEXT,
    }
