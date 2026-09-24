#!/usr/bin/env python3
"""Focused tests for the Samsung memory-vendor analyzer adapter."""

import base64
import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTOSO_DIR = (
    ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso")
SHIM_DIR = CONTOSO_DIR / "memory_shims"
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
for path in (ROOT, CONTOSO_DIR, SHIM_DIR, RAS_DEMO_DIR):
    sys.path.insert(0, str(path))

import analyzer_samsung as samsung  # noqa: E402
import contoso_action_parameters as actions  # noqa: E402

HELPERS_SPEC = importlib.util.spec_from_file_location(
    "samsung_test_helpers", ROOT / "tests" / "test_contoso_memory_shims.py")
assert HELPERS_SPEC and HELPERS_SPEC.loader
helpers = importlib.util.module_from_spec(HELPERS_SPEC)
HELPERS_SPEC.loader.exec_module(helpers)


def _samsung_event():
    return helpers.decode_memory_events(
        helpers._records(helpers._memory_cper(helpers.SAMSUNG)))[0]


def _ppr_parameters(event):
    error = event["memory_error"]
    subcomponent = error["subcomponent"]
    additional = error["additional"]
    return {
        "fru_id": event["fru_id"],
        "fru_text": event["fru_text"],
        "ppr_type": actions.PPR_TYPE_SOFT_RUNTIME,
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


def test_samsung_memory_record_maps_complete_event_and_fru_text():
    event = _samsung_event()
    additional = event["memory_error"]["additional"]
    additional["memory_repair_capabilities"] = 0x07
    additional["repairs"] = [{
        "subchannel": 0,
        "rank": 0,
        "device": 3,
        "bank_group": 2,
        "bank": 3,
        "count": 2,
    }]
    additional["beat_mask"] = [0, 0, 0x0021, 0]
    additional["spd_temperature"] = 40

    record = samsung._to_samsung_memory_error(event)

    assert record["record_type"] == "memory_error"
    assert record["source"]["cper_file"] == "record-0.cper"
    assert record["source"]["section_index"] == 0
    assert record["fru_id"] == helpers.FRU_ID
    assert record["fru_text"] == helpers.FRU_TEXT
    assert record["dimm"]["dram_manufacturer_id"] == helpers.SAMSUNG
    assert record["dimm"]["spd_temperature_c"] == 40
    assert record["ppr"]["capability_bits"] == 0x07
    assert record["ppr"]["target_bank_repair_count"] == 2
    assert "repairs_per_bank" not in record["ppr"]
    assert record["beats"] == {
        "mask_by_dq": [0, 0, 0x0021, 0],
        "mask_64": 0x0000002100000000,
        "failing_dqs": [2],
        "failing_dq_count": 1,
        "failing_beats_by_dq": {2: [0, 5]},
        "failing_beat_count": 2,
    }
    assert "page_offline" not in record


def test_samsung_platform_action_record_preserves_result_and_correlation():
    events = helpers.decode_memory_events(helpers._records(
        helpers._action_cper(action_id="0x8001", return_code="0x01"),
        helpers._memory_cper(helpers.SAMSUNG),
    ))

    record = samsung._to_samsung_platform_action(events[0])

    assert record["record_type"] == "platform_action"
    assert record["fru_text"] == helpers.FRU_TEXT
    assert record["action"]["action_id"] == "0x8001"
    assert record["action"]["successful"] is False
    assert record["correlation"]["matched"] is True
    assert record["correlation"]["source_error_cper"] == "record-1.cper"


def test_samsung_translates_all_supported_actions():
    event = _samsung_event()
    source = {
        "cper_file": event["cper_file"],
        "section_index": event["section_index"],
    }
    page_parameters = {
        "fru_id": event["fru_id"],
        "fru_text": event["fru_text"],
        "pages": [0x12345000, 0x12347000],
        "page_ranges": [{
            "start_address": 0x20000000,
            "page_count": 32,
        }],
    }
    result = {
        "fault": {"mode": "Row"},
        "cpads": [
            {"actions": [{
                "source": source,
                "action": "cold_reboot",
                "confidence": 80,
                "urgency": True,
                "parameters": {},
                "reason": "Power cycle requested",
            }]},
            {"actions": [{
                "source": source,
                "action": "reseat_dimm",
                "confidence": 81,
                "urgency": False,
                "parameters": {
                    "fru_id": event["fru_id"],
                    "fru_text": event["fru_text"],
                },
                "reason": "Reseat the DIMM",
            }]},
            {"actions": [{
                "source": source,
                "action": "dance_dimm",
                "confidence": 82,
                "urgency": True,
                "parameters": {
                    "fru_id": event["fru_id"],
                    "fru_text": event["fru_text"],
                },
                "reason": "Shuffle the DIMM",
            }]},
            {"actions": [{
                "source": source,
                "action": "replace_dimm",
                "confidence": 83,
                "urgency": False,
                "parameters": {
                    "fru_id": event["fru_id"],
                    "fru_text": event["fru_text"],
                },
                "reason": "Replace the DIMM",
            }]},
            {"actions": [{
                "source": source,
                "action": "ppr",
                "confidence": 84,
                "urgency": True,
                "parameters": _ppr_parameters(event),
                "reason": "Repair the failing row",
            }]},
            {"actions": [{
                "source": source,
                "action": "page_offline",
                "confidence": 85,
                "urgency": False,
                "parameters": page_parameters,
                "reason": "Offline affected pages",
            }]},
            {"actions": [{
                "source": source,
                "action": "reboot_with_training",
                "confidence": 86,
                "urgency": True,
                "parameters": {},
                "reason": "Retrain memory",
            }]},
        ],
        "advisories": [],
    }

    proposals = samsung._to_contoso_cpad_requests(result, [event])
    requests = [proposal["sections"][0] for proposal in proposals]

    assert [request["action_id"] for request in requests] == [
        actions.POWER_CYCLE_ACTION_ID,
        actions.RESEAT_PART_ACTION_ID,
        actions.SHUFFLE_PART_ACTION_ID,
        actions.REPLACE_PART_ACTION_ID,
        actions.PPR_ACTION_ID,
        actions.PAGE_OFFLINE_ACTION_ID,
        actions.REBOOT_WITH_RETRAINING_ACTION_ID,
    ]
    assert [request["urgency"] for request in requests] == [
        True, False, True, False, True, False, True]
    assert requests[4]["parameters"] == _ppr_parameters(event)
    assert requests[5]["parameters"] == page_parameters


def test_samsung_entry_point_adapts_records_and_returns_requests():
    event = _samsung_event()
    captured = {}
    original_analyze = samsung.analyze

    def fake_analyze(records):
        captured["records"] = records
        record = records[0]
        return {
            "fault": {"mode": "Row"},
            "cpads": [{"actions": [{
                    "source": {
                        "cper_file": record["source"]["cper_file"],
                        "section_index": record["source"]["section_index"],
                    },
                    "action": "replace_dimm",
                    "confidence": 95,
                    "urgency": True,
                    "parameters": {
                        "fru_id": record["fru_id"],
                        "fru_text": record["fru_text"],
                    },
                    "reason": "Repair budget exhausted",
                }]}],
            "advisories": [],
        }

    samsung.analyze = fake_analyze
    try:
        requests = samsung.analyze_memory_events([event])
    finally:
        samsung.analyze = original_analyze

    assert captured["records"][0]["fru_text"] == helpers.FRU_TEXT
    assert "repairs_per_bank" not in captured["records"][0]["ppr"]
    assert requests == [{"sections": [{
        "cper_file": "record-0.cper",
        "section_index": 0,
        "action_id": actions.REPLACE_PART_ACTION_ID,
        "confidence": 95,
        "urgency": True,
        "parameters": {
            "fru_id": helpers.FRU_ID,
            "fru_text": helpers.FRU_TEXT,
        },
    }]}]


def test_samsung_rejects_non_boolean_action_urgency():
    event = _samsung_event()
    result = {
        "fault": None,
        "cpads": [{"actions": [{
            "source": {
                "cper_file": event["cper_file"],
                "section_index": event["section_index"],
            },
            "action": "replace_dimm",
            "confidence": 95,
            "urgency": 1,
            "parameters": {},
            "reason": "Replace the DIMM",
        }]}],
        "advisories": [],
    }

    try:
        samsung._to_contoso_cpad_requests(result, [event])
    except ValueError as exc:
        assert "urgency must be a boolean" in str(exc)
    else:
        raise AssertionError("integer Samsung urgency was accepted")


def test_samsung_analyzer_owns_spare_row_budget():
    record = {
        "record_type": "memory_error",
        "ppr": {"target_bank_repair_count": 2},
    }

    samsung.analyze([record])

    assert record["ppr"]["repairs_per_bank"] == 14


def test_replace_request_builds_cpad_with_source_fru_text():
    event = _samsung_event()
    request = {
        "cper_file": event["cper_file"],
        "section_index": event["section_index"],
        "action_id": actions.REPLACE_PART_ACTION_ID,
        "confidence": 95,
        "urgency": True,
        "parameters": {
            "fru_id": event["fru_id"],
            "fru_text": event["fru_text"],
        },
    }
    analyzer = helpers.ContosoAnalyzer()

    cpad = analyzer._build_shim_action_cpad(request, [event])

    descriptor = cpad["sectionDescriptors"][0]
    body = base64.b64decode(
        cpad["sections"][0]["Unknown"]["data"], validate=True)
    assert descriptor["actionID"]["code"] == actions.REPLACE_PART_ACTION_ID
    assert descriptor["fruText"] == helpers.FRU_TEXT
    assert len(body) == 8


def test_control_plane_actions_are_not_submitted_to_endpoint():
    class AllowedDecision:
        reason = None
        action_id = actions.REPLACE_PART_ACTION_ID
        fru_text = "DIMM A1"

        def __bool__(self):
            return True

    class Policy:
        @staticmethod
        def evaluate_cpad(_path):
            return AllowedDecision()

    class Submitter:
        def __init__(self):
            self.calls = []

        def submit(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        cpad_binary = directory / "replace.cpad"
        cpad_binary.write_bytes(b"CPAD")
        orchestrator = helpers.AnalysisOrchestrator.__new__(
            helpers.AnalysisOrchestrator)
        orchestrator.policy_engine = Policy()
        orchestrator.submitter = Submitter()
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            orchestrator._policy_and_submit(cpad_binary=cpad_binary)

        assert orchestrator.submitter.calls == []
        assert "Replace Part approved for DIMM A1" in output.getvalue()
        assert "will not be submitted to the Contoso endpoint" in (
            output.getvalue())


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"  [PASS] {name}")
            except Exception as exc:
                failures += 1
                print(f"  [FAIL] {name}: {exc}")
    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILURE(S)'}")
    raise SystemExit(1 if failures else 0)
