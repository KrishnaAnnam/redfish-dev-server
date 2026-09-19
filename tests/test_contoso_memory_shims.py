#!/usr/bin/env python3
"""Focused tests for Contoso memory-vendor shim integration."""

import base64
import copy
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTOSO_DIR = ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso"
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
sys.path.insert(0, str(CONTOSO_DIR))
sys.path.insert(0, str(RAS_DEMO_DIR))
sys.path.insert(0, str(ROOT))

import contoso_catalog as catalog  # noqa: E402
import contoso_encoder as encoder  # noqa: E402
import injection_spec as spec_model  # noqa: E402
from memory_events import decode_memory_events  # noqa: E402
from memory_controller_analyzer import MemoryControllerAnalyzer  # noqa: E402
from memory_shims.contract import discover_memory_shims  # noqa: E402
from analysis_orchestrator import AnalysisOrchestrator  # noqa: E402


ANALYZER_PATH = CONTOSO_DIR / "analyzer-contoso.py"
SPEC = importlib.util.spec_from_file_location("analyzer_contoso_shims", ANALYZER_PATH)
assert SPEC and SPEC.loader
ANALYZER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER_MODULE)
ContosoAnalyzer = ANALYZER_MODULE.ContosoAnalyzer

PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"
PARTITION_ID = "22222222-3333-4444-5555-666666666666"
CREATOR_ID = "11111111-2222-3333-4444-555555555555"
FRU_ID = "75824856-bd36-2cc8-61f4-39bb3276da2a"
FRU_TEXT = "DIMM A1"
MICRON = [0x80, 0x2C]
SAMSUNG = [0x80, 0xCE]


def _memory_cper(vendor=MICRON, record_id=1, fru_id=FRU_ID,
                 fru_text=FRU_TEXT, error_name="Corrected Memory ECC Error",
                 column=567):
    spec = spec_model.build_template(
        "Memory Controller - First Generation", error_name)
    spec["section"]["subcomponent"] = {"chiplet": 0, "controller": 0}
    spec["section"]["additional"].update({
        "channel": 0,
        "dimm": 1,
        "subchannel": 0,
        "rank": 0,
        "device": 3,
        "bank_group": 2,
        "bank": 3,
        "row": 1234,
        "column": column,
        "dram_manufacturer_id": vendor,
        "serial_number": "SERIAL",
        "part_number": "PART",
    })
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors",
        spec_model.to_encoder_fields(spec))
    return {
        "header": {
            "platformID": PLATFORM_ID,
            "partitionID": PARTITION_ID,
            "creatorID": CREATOR_ID,
            "recordID": record_id,
            "severity": {"name": "Corrected", "code": 2},
        },
        "sectionDescriptors": [{
            "sectionType": {
                "data": catalog.SECTION_TYPES[
                    "Memory Controller - First Generation"]["guid"],
                "type": "Unknown",
            },
            "fruID": fru_id,
            "fruText": fru_text,
        }],
        "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        }}],
    }


def _action_cper(action_id="0x9001", return_code="0x01",
                 fru_id=FRU_ID, fru_text=FRU_TEXT):
    return {
        "header": {
            "platformID": PLATFORM_ID,
            "partitionID": PARTITION_ID,
            "creatorID": CREATOR_ID,
            "recordID": 2,
            "severity": {"name": "Platform Action Event", "code": 4},
        },
        "sectionDescriptors": [{
            "sectionType": {"type": "Platform Action Event"},
            "fruID": fru_id,
            "fruText": fru_text,
        }],
        "sections": [{"PlatformActionEvent": {
            "cpadActionId": action_id,
            "actionReturnCode": return_code,
            "actionReturnReasonCode": "0x55",
            "cpadRecordId": "0x1234",
            "cpadSectionIndex": 0,
        }}],
    }


def _cpu_section():
    fields = {
        "subcomponent": {"chiplet": 0, "core": 1},
        "error_status": (True, False, 3, 2),
        "error_address": 0x1234,
        "misc0": (False, 0),
        "misc1": 0,
        "additional": {
            "timeout_transaction_details": 0,
            "register_parity_details": 0,
            "cache_location": 0,
            "assert_details": 0,
            "core_debug_details": 0,
        },
    }
    body = encoder.pack_section_body(
        "CPU Core - First Generation", "Core Errors", fields)
    return (
        {"sectionType": {
            "data": catalog.SECTION_TYPES[
                "CPU Core - First Generation"]["guid"],
            "type": "Unknown",
        }},
        {"Unknown": {"data": base64.b64encode(body).decode("ascii")}},
    )


def _other_memory_cper():
    fields = {
        "subcomponent": {"chiplet": 0, "controller": 2},
        "error_status": (True, False, 3, 1),
        "error_address": 0,
        "misc0": (False, 1),
        "misc1": 0,
        "additional": {
            "DllLockLossInfo": 7,
            "ErrorStructure": 8,
            "OtherMeshEntity": 9,
        },
    }
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "Other Errors", fields)
    cper = _memory_cper()
    cper["sectionDescriptors"] = [cper["sectionDescriptors"][0]]
    cper["sections"] = [{"Unknown": {
        "data": base64.b64encode(body).decode("ascii"),
    }}]
    return cper


def _records(*cpers):
    return [
        {
            "cper_data": cper,
            "cper_file": f"record-{index}.cper",
            "is_newest": index == 0,
        }
        for index, cper in enumerate(cpers)
    ]


def _cpad_for_event(event, action_id="0x9001"):
    return {
        "header": {
            "platformID": event["header"]["platformID"],
            "partitionID": event["header"]["partitionID"],
            "creatorID": event["header"]["creatorID"],
            "sectionCount": 1,
        },
        "sectionDescriptors": [{
            "actionID": {"code": action_id, "name": "Vendor action"},
            "confidence": 90,
            "fruID": event["section_descriptor"]["fruID"],
            "fruText": event["section_descriptor"]["fruText"],
        }],
        "sections": [{"Unknown": {"data": ""}}],
    }


class FakeShim:
    def __init__(self, result=None, error=None, vendor="micron"):
        self.name = f"{vendor.title()} Fake Shim"
        self.path = Path(f"analyzer_{vendor}.py")
        self.result = result
        self.error = error
        self.received = None

    def analyze(self, events):
        self.received = copy.deepcopy(events)
        if self.error:
            raise RuntimeError(self.error)
        if callable(self.result):
            return self.result(events)
        return copy.deepcopy(self.result or [])


def test_discovers_three_stub_shims():
    shims, errors = discover_memory_shims(CONTOSO_DIR / "memory_shims")

    assert errors == []
    assert set(shims) == {(0x80, 0x2C), (0x80, 0xCE), (0x80, 0xAD)}
    assert all(shim.analyze([{"event_type": "memory_error"}]) == []
               for shim in shims.values())


def test_multi_id_shim_registration_is_atomic_on_conflict():
    with tempfile.TemporaryDirectory() as directory:
        shim_dir = Path(directory)
        (shim_dir / "analyzer_a.py").write_text(
            "SHIM_INFO = {'api_version': 1, 'name': 'A', 'version': '1', "
            "'dram_manufacturer_ids': [[128, 206]]}\n"
            "def analyze_memory_events(events): return []\n")
        (shim_dir / "analyzer_b.py").write_text(
            "SHIM_INFO = {'api_version': 1, 'name': 'B', 'version': '1', "
            "'dram_manufacturer_ids': [[128, 44], [128, 206]]}\n"
            "def analyze_memory_events(events): return []\n")

        shims, errors = discover_memory_shims(shim_dir)

        assert set(shims) == {tuple(SAMSUNG)}
        assert len(errors) == 1
        assert "duplicates manufacturer ID" in errors[0]


def test_decodes_complete_memory_error():
    events = decode_memory_events(_records(_memory_cper()))

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "memory_error"
    assert event["source"] == {
        "cper_file": "record-0.cper",
        "window_index": 0,
        "section_index": 0,
        "is_newest": True,
    }
    assert event["fru"] == {"id": FRU_ID, "text": FRU_TEXT}
    assert event["dram_manufacturer_id"] == MICRON
    assert event["memory_error"]["bank"] == "DRAM Errors"
    assert event["memory_error"]["name"] == "Corrected Memory ECC Error"
    assert event["memory_error"]["subcomponent"] == {
        "chiplet": 0, "controller": 0}
    additional = event["memory_error"]["additional"]
    assert additional["serial_number"] == "SERIAL"
    assert event["spd_temperature"] is None
    assert additional["spd_temperature"] is None
    assert additional["device"] == 3
    assert additional["row"] == 1234
    assert "beat_mask" in additional
    assert "repairs" in additional


def test_decodes_every_memory_section_in_source_order():
    first = _memory_cper(MICRON)
    second = _memory_cper(MICRON)
    combined = copy.deepcopy(first)
    combined["sectionDescriptors"].append(second["sectionDescriptors"][0])
    combined["sections"].append(second["sections"][0])

    events = decode_memory_events(_records(combined))

    assert len(events) == 2
    assert [event["source"]["section_index"] for event in events] == [0, 1]


def test_memory_history_keeps_only_same_identity_and_newest_dram_vendor():
    newest = _memory_cper(MICRON)
    mixed_history = _memory_cper(MICRON, record_id=2)
    cpu_descriptor, cpu_body = _cpu_section()
    mixed_history["sectionDescriptors"].insert(0, cpu_descriptor)
    mixed_history["sections"].insert(0, cpu_body)
    other_vendor = _memory_cper(SAMSUNG, record_id=3)
    other_platform = _memory_cper(MICRON, record_id=4)
    other_platform["header"]["platformID"] = (
        "00000000-0000-0000-0000-000000000001")

    events = MemoryControllerAnalyzer._filtered_events(
        _records(newest, mixed_history, other_vendor, other_platform),
        tuple(MICRON),
    )

    assert [(event["source"]["cper_file"],
             event["source"]["section_index"])
            for event in events] == [
        ("record-0.cper", 0),
        ("record-1.cper", 1),
    ]
    assert all(event["dram_manufacturer_id"] == MICRON for event in events)


def test_newest_dram_sections_require_one_manufacturer():
    sections = [
        {"decoded": {
            "bank_name": "DRAM Errors",
            "additional": {"dram_manufacturer_id": MICRON},
        }},
        {"decoded": {
            "bank_name": "DRAM Errors",
            "additional": {"dram_manufacturer_id": SAMSUNG},
        }},
    ]

    try:
        MemoryControllerAnalyzer._newest_dram_vendor(sections)
    except ValueError as exc:
        assert "must identify one manufacturer" in str(exc)
    else:
        raise AssertionError("mixed newest DRAM manufacturers were accepted")


def test_memory_other_errors_are_contoso_owned_and_skip_vendor_shims():
    analyzer = ContosoAnalyzer()
    shim = FakeShim()
    memory = MemoryControllerAnalyzer.__new__(MemoryControllerAnalyzer)
    memory.host = analyzer
    memory.shims = {tuple(MICRON): shim}
    memory.shim_errors = []
    cper = _other_memory_cper()
    records = _records(cper)
    grouped = ANALYZER_MODULE.decode_newest_sections(
        analyzer, cper, "other.cper")

    result = memory.analyze(
        grouped["memory_controller"], records, "other")

    assert shim.received is None
    assert result["shim_result"]["invocations"] == []
    assert len(result["findings"]) == 1
    assert result["findings"][0]["analysis_owner"] == "contoso"
    assert result["findings"][0]["error"]["bank"] == "Other Errors"
    assert result["history_summary"]["messages"] == [
        "Evaluated 0 prior CPER candidate(s) for matching "
        "memory-controller errors.",
        "Selected 0 same-vendor memory record(s).",
    ]
    assert result["analysis_route"]["messages"] == [
        "Using the default Contoso memory-controller analyzer.",
        "Reason: No DRAM vendor applies to this error.",
    ]


def test_memory_routing_uses_default_when_no_vendor_analyzers_are_available():
    analyzer = ContosoAnalyzer()
    memory = MemoryControllerAnalyzer.__new__(MemoryControllerAnalyzer)
    memory.host = analyzer
    memory.shims = {}
    memory.shim_errors = []
    cper = _memory_cper()
    records = _records(cper)
    grouped = ANALYZER_MODULE.decode_newest_sections(
        analyzer, cper, "memory.cper")

    result = memory.analyze(
        grouped["memory_controller"], records, "memory")

    assert result["analysis_route"]["messages"] == [
        "Using the default Contoso memory analyzer.",
        "Reason: No memory-vendor analyzers are available.",
    ]


def test_memory_routing_identifies_selected_vendor_analyzer():
    analyzer = ContosoAnalyzer()
    shim = FakeShim()
    memory = MemoryControllerAnalyzer.__new__(MemoryControllerAnalyzer)
    memory.host = analyzer
    memory.shims = {tuple(MICRON): shim}
    memory.shim_errors = []
    cper = _memory_cper()
    records = _records(cper)
    grouped = ANALYZER_MODULE.decode_newest_sections(
        analyzer, cper, "memory.cper")

    result = memory.analyze(
        grouped["memory_controller"], records, "memory")

    assert result["analysis_route"]["messages"] == [
        "Using memory-vendor analyzer: Micron Fake Shim",
        "DRAM manufacturer: 80 2C",
    ]


def test_uncorrected_memory_error_does_not_report_failed_sppr_generation():
    analyzer = ContosoAnalyzer()
    memory = MemoryControllerAnalyzer.__new__(MemoryControllerAnalyzer)
    memory.host = analyzer
    memory.shims = {}
    memory.shim_errors = []
    newest = _memory_cper(
        record_id=2,
        error_name="Uncorrected Memory ECC Error",
        column=891,
    )
    prior = _memory_cper(record_id=1, column=567)
    records = _records(newest, prior)
    grouped = ANALYZER_MODULE.decode_newest_sections(
        analyzer, newest, "uncorrected.cper")

    result = memory.analyze(
        grouped["memory_controller"], records, "uncorrected")

    assert result["dram_row_failure_detected"] is False
    assert result["cpad_generation_failed"] is False
    assert result["default_cpads"] == []


def test_correlates_arbitrary_action_to_prior_memory_error_by_fru():
    events = decode_memory_events(_records(
        _action_cper(action_id="0x9123", return_code="0x01",
                     fru_id=FRU_ID.upper(), fru_text=f" {FRU_TEXT} "),
        _memory_cper(),
    ))

    assert [event["event_type"] for event in events] == [
        "platform_action", "memory_error"]
    action = events[0]
    assert action["dram_manufacturer_id"] == MICRON
    assert action["correlation"] == {
        "method": "fru_id_and_text",
        "matched": True,
        "ambiguous": False,
        "source_error_cper": "record-1.cper",
        "source_error_section_index": 0,
    }
    assert action["platform_action"]["action_id"] == "0x9123"
    assert action["platform_action"]["return_code"] == "0x01"
    assert action["platform_action"]["reason_code"] == "0x55"
    assert action["platform_action"]["successful"] is False
    assert action["memory_target"]["serial_number"] == "SERIAL"


def test_action_requires_both_fru_fields_and_unambiguous_vendor():
    mismatched = decode_memory_events(_records(
        _action_cper(fru_text="Another DIMM"), _memory_cper()))[0]
    assert mismatched["correlation"]["matched"] is False
    assert mismatched["dram_manufacturer_id"] is None

    ambiguous = decode_memory_events(_records(
        _action_cper(),
        _memory_cper(MICRON, record_id=2),
        _memory_cper(SAMSUNG, record_id=1),
    ))[0]
    assert ambiguous["correlation"]["matched"] is False
    assert ambiguous["correlation"]["ambiguous"] is True
    assert ambiguous["dram_manufacturer_id"] is None


def test_same_cper_memory_error_does_not_correlate_action():
    action = _action_cper()
    memory = _memory_cper()
    action["sectionDescriptors"].append(memory["sectionDescriptors"][0])
    action["sections"].append(memory["sections"][0])

    events = decode_memory_events(_records(action))
    action_event = next(event for event in events
                        if event["event_type"] == "platform_action")

    assert action_event["correlation"]["matched"] is False
    assert action_event["dram_manufacturer_id"] is None


def test_valid_empty_stub_owns_newest_vendor_events():
    analyzer = ContosoAnalyzer()
    shim = FakeShim()
    analyzer.memory_shims = {tuple(MICRON): shim}

    result = analyzer.analyze_memory_event_window(_records(
        _action_cper(), _memory_cper()))

    assert result["cpads"] == []
    assert result["handled_manufacturers"] == {tuple(MICRON)}
    assert result["failed_manufacturers"] == set()
    assert [event["event_type"] for event in shim.received] == [
        "platform_action", "memory_error"]
    assert result["invocations"][0]["event_count"] == 2
    assert analyzer.default_memory_events(result) == []


def test_mixed_newest_vendors_fall_back_only_for_unhandled_sections():
    analyzer = ContosoAnalyzer()
    analyzer.memory_shims = {tuple(MICRON): FakeShim()}
    micron = _memory_cper(MICRON)
    samsung = _memory_cper(SAMSUNG)
    combined = copy.deepcopy(micron)
    combined["sectionDescriptors"].append(samsung["sectionDescriptors"][0])
    combined["sections"].append(samsung["sections"][0])

    result = analyzer.analyze_memory_event_window(_records(combined))
    fallback = analyzer.default_memory_events(result)

    assert result["handled_manufacturers"] == {tuple(MICRON)}
    assert len(fallback) == 1
    assert fallback[0]["dram_manufacturer_id"] == SAMSUNG


def test_shim_failure_is_reported_for_default_fallback():
    analyzer = ContosoAnalyzer()
    analyzer.memory_shims = {tuple(MICRON): FakeShim(error="vendor failed")}

    result = analyzer.analyze_memory_event_window(_records(_memory_cper()))

    assert result["handled_manufacturers"] == set()
    assert result["failed_manufacturers"] == {tuple(MICRON)}
    assert result["invocations"][0]["status"] == "failed"
    assert "vendor failed" in result["invocations"][0]["error"]


def test_action_only_window_never_enters_default_analysis():
    analyzer = ContosoAnalyzer()

    result = analyzer.analyze_memory_event_window(_records(_action_cper()))

    assert analyzer.default_memory_events(result) == []


def test_missing_and_failed_shims_can_create_default_sppr():
    with tempfile.TemporaryDirectory() as directory:
        analyzer = ContosoAnalyzer(output_dir=directory)
        current_cper = _memory_cper(MICRON)
        event = decode_memory_events(_records(current_cper))[0]
        current_location = analyzer._memory_location_from_event(event)
        prior_location = copy.deepcopy(current_location)
        prior_location["column"] = current_location["column"] - 1
        analyzer.seen_locations = [prior_location]

        class Decoder:
            @staticmethod
            def _convert_json_to_binary_cpad(json_path, binary_path):
                Path(binary_path).write_bytes(b"CPAD")
                return binary_path

        analyzer.decoder = Decoder()
        analyzer.memory_shims = {}
        missing_result = analyzer.analyze_memory_event_window(
            _records(current_cper))
        missing_event = analyzer.default_memory_events(missing_result)[0]
        missing_path = analyzer.create_sppr_cpad_from_memory_event(
            missing_event, current_cper, output_stem="missing",
            record_location=False)

        analyzer.memory_shims = {
            tuple(MICRON): FakeShim(error="vendor failed")}
        failed_result = analyzer.analyze_memory_event_window(
            _records(current_cper))
        failed_event = analyzer.default_memory_events(failed_result)[0]
        failed_path = analyzer.create_sppr_cpad_from_memory_event(
            failed_event, current_cper, output_stem="failed",
            record_location=False)

        assert Path(missing_path).name == "missing_sppr_cpad.cpad"
        assert Path(failed_path).name == "failed_sppr_cpad.cpad"


def test_invalid_later_cpad_discards_entire_shim_result():
    analyzer = ContosoAnalyzer()

    def partly_invalid(events):
        valid = _cpad_for_event(events[0])
        invalid = copy.deepcopy(valid)
        invalid["sectionDescriptors"][0]["confidence"] = 101
        return [valid, invalid]

    analyzer.memory_shims = {
        tuple(MICRON): FakeShim(result=partly_invalid),
    }

    result = analyzer.analyze_memory_event_window(_records(_memory_cper()))

    assert result["cpads"] == []
    assert result["handled_manufacturers"] == set()
    assert result["failed_manufacturers"] == {tuple(MICRON)}
    assert "confidence" in result["invocations"][0]["error"]


def test_rejects_invalid_shim_cpad_section_structure():
    analyzer = ContosoAnalyzer()

    def wrong_section_count(events):
        cpad = _cpad_for_event(events[0])
        cpad["header"]["sectionCount"] = 2
        return [cpad]

    analyzer.memory_shims = {
        tuple(MICRON): FakeShim(result=wrong_section_count),
    }
    result = analyzer.analyze_memory_event_window(_records(_memory_cper()))
    assert result["cpads"] == []
    assert "sectionCount" in result["invocations"][0]["error"]

    def invalid_section(events):
        cpad = _cpad_for_event(events[0])
        cpad["sections"] = [None]
        return [cpad]

    analyzer.memory_shims = {
        tuple(MICRON): FakeShim(result=invalid_section),
    }
    result = analyzer.analyze_memory_event_window(_records(_memory_cper()))
    assert result["cpads"] == []
    assert "sections must contain objects" in result["invocations"][0]["error"]


def test_validates_and_deduplicates_arbitrary_shim_cpads():
    analyzer = ContosoAnalyzer()

    def duplicate_cpads(events):
        cpad = _cpad_for_event(events[0], action_id="0x9123")
        return [cpad, copy.deepcopy(cpad)]

    shim = FakeShim(result=duplicate_cpads)
    analyzer.memory_shims = {tuple(MICRON): shim}

    result = analyzer.analyze_memory_event_window(_records(_memory_cper()))

    assert result["handled_manufacturers"] == {tuple(MICRON)}
    assert len(result["cpads"]) == 1
    assert result["invocations"][0]["cpad_count"] == 1
    assert result["cpads"][0][1]["sectionDescriptors"][0]["actionID"][
        "code"] == "0x9123"


def test_emits_paired_shim_json_and_binary_files():
    with tempfile.TemporaryDirectory() as directory:
        analyzer = ContosoAnalyzer(output_dir=directory)
        event = decode_memory_events(_records(_memory_cper()))[0]
        shim = FakeShim()
        cpad = _cpad_for_event(event)

        class Decoder:
            @staticmethod
            def _convert_json_to_binary_cpad(json_path, binary_path):
                Path(binary_path).write_bytes(b"CPAD")
                return binary_path

        analyzer.decoder = Decoder()
        outputs = analyzer.emit_shim_cpads([(shim, cpad)], "source")

        binary = Path(outputs[0])
        paired_json = binary.with_suffix(".json")
        assert binary.name == "source_micron_1_cpad.cpad"
        assert binary.read_bytes() == b"CPAD"
        assert json.loads(paired_json.read_text())["header"] == cpad["header"]


def test_one_vendor_emission_failure_preserves_other_vendor_outputs():
    with tempfile.TemporaryDirectory() as directory:
        analyzer = ContosoAnalyzer(output_dir=directory)
        micron_event = decode_memory_events(_records(_memory_cper(MICRON)))[0]
        samsung_event = decode_memory_events(_records(_memory_cper(SAMSUNG)))[0]
        micron_shim = FakeShim(vendor="micron")
        samsung_shim = FakeShim(vendor="samsung")
        result = {
            "cpads_by_manufacturer": {
                tuple(MICRON): [(micron_shim, _cpad_for_event(micron_event))],
                tuple(SAMSUNG): [(samsung_shim, _cpad_for_event(samsung_event))],
            },
            "handled_manufacturers": {tuple(MICRON), tuple(SAMSUNG)},
            "failed_manufacturers": set(),
            "invocations": [
                {"manufacturer_id": MICRON, "status": "ok", "cpad_count": 1},
                {"manufacturer_id": SAMSUNG, "status": "ok", "cpad_count": 1},
            ],
        }

        class Decoder:
            @staticmethod
            def _convert_json_to_binary_cpad(json_path, binary_path):
                if "samsung" in binary_path:
                    return None
                Path(binary_path).write_bytes(b"CPAD")
                return binary_path

        analyzer.decoder = Decoder()
        outputs, errors = analyzer.emit_shim_cpad_groups(result, "source")

        assert [Path(path).name for path in outputs] == [
            "source_micron_802c_1_cpad.cpad"]
        assert len(errors) == 1
        assert result["handled_manufacturers"] == {tuple(MICRON)}
        assert result["failed_manufacturers"] == {tuple(SAMSUNG)}
        assert (Path(directory) / "source_micron_802c_1_cpad.json").exists()
        assert not (Path(directory) / "source_samsung_80ce_1_cpad.json").exists()


def test_multi_id_shim_outputs_have_distinct_names():
    with tempfile.TemporaryDirectory() as directory:
        analyzer = ContosoAnalyzer(output_dir=directory)
        micron_event = decode_memory_events(_records(_memory_cper(MICRON)))[0]
        samsung_event = decode_memory_events(_records(_memory_cper(SAMSUNG)))[0]
        shim = FakeShim(vendor="multi")
        result = {
            "cpads_by_manufacturer": {
                tuple(MICRON): [(shim, _cpad_for_event(micron_event))],
                tuple(SAMSUNG): [(shim, _cpad_for_event(samsung_event))],
            },
            "handled_manufacturers": {tuple(MICRON), tuple(SAMSUNG)},
            "failed_manufacturers": set(),
            "invocations": [
                {"manufacturer_id": MICRON, "status": "ok", "cpad_count": 1},
                {"manufacturer_id": SAMSUNG, "status": "ok", "cpad_count": 1},
            ],
        }

        class Decoder:
            @staticmethod
            def _convert_json_to_binary_cpad(json_path, binary_path):
                Path(binary_path).write_bytes(b"CPAD")
                return binary_path

        analyzer.decoder = Decoder()
        outputs, errors = analyzer.emit_shim_cpad_groups(result, "source")

        assert errors == []
        assert [Path(path).name for path in outputs] == [
            "source_multi_802c_1_cpad.cpad",
            "source_multi_80ce_1_cpad.cpad",
        ]


def test_default_conversion_failure_cleans_outputs_and_returns_none():
    with tempfile.TemporaryDirectory() as directory:
        analyzer = ContosoAnalyzer(output_dir=directory)
        cper = _memory_cper()
        event = decode_memory_events(_records(cper))[0]
        current = analyzer._memory_location_from_event(event)
        prior = copy.deepcopy(current)
        prior["column"] -= 1
        analyzer.seen_locations = [prior]

        class Decoder:
            @staticmethod
            def _convert_json_to_binary_cpad(json_path, binary_path):
                Path(binary_path).write_bytes(b"partial")
                raise RuntimeError("conversion failed")

        analyzer.decoder = Decoder()
        output = analyzer.create_sppr_cpad_from_memory_event(
            event, cper, output_stem="failed", record_location=False)

        assert output is None
        assert list(Path(directory).glob("failed_sppr_cpad.*")) == []


def test_default_conversion_failure_is_not_reported_as_recommendation():
    analyzer = ContosoAnalyzer()
    location = analyzer._memory_location_from_event(
        decode_memory_events(_records(_memory_cper()))[0])
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        analyzer.print_batch_recommendation(
            [{
                "cper_data": _memory_cper(),
                "sppr_created": False,
                "sppr_filename": None,
                "dram_row_failure_detected": True,
                "memory_location": location,
            }],
            successful=1,
            cpad_generation_failed=True,
        )

    report = output.getvalue()
    assert "Recommendation:     No action emitted" in report
    assert "Reason:             CPAD generation failed." in report
    assert "Recommendation:     Perform SPPR" not in report
    assert "Recommendation:     Soft Post Package Repair" not in report


def test_vendor_action_takes_precedence_over_sibling_generation_failure():
    analyzer = ContosoAnalyzer()
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        analyzer.print_batch_recommendation(
            [{
                "cper_data": _memory_cper(),
                "sppr_created": False,
                "sppr_filename": None,
                "dram_row_failure_detected": True,
                "memory_location": None,
            }],
            successful=1,
            vendor_cpad_files=["vendor.cpad"],
            cpad_generation_failed=True,
        )

    report = output.getvalue()
    assert "Recommendation:     Memory vendor-recommended RAS action" in report
    assert "Warning:            CPAD generation failed for another memory section." in report
    assert "Recommendation:     No action emitted" not in report


def test_orchestrator_pairs_each_binary_with_matching_json():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        analyzer_dir = root / "analyzer"
        destination = root / "records"
        analyzer_dir.mkdir()
        destination.mkdir()
        cper_path = destination / "newest.cper"
        cper_path.write_bytes(b"CPER")
        (analyzer_dir / "run_analysis.json").write_text("{}")
        for stem in ("run_micron_1_cpad", "run_samsung_1_cpad"):
            (analyzer_dir / f"{stem}.json").write_text("{}")
            (analyzer_dir / f"{stem}.cpad").write_bytes(b"CPAD")

        orchestrator = AnalysisOrchestrator.__new__(AnalysisOrchestrator)
        pairs = []
        orchestrator._policy_and_submit = lambda **kwargs: pairs.append(kwargs)

        orchestrator._handle_outputs(analyzer_dir, cper_path)

        assert [(pair["cpad_binary"].stem, pair["cpad_json"].stem)
                for pair in pairs] == [
            ("run_micron_1_cpad", "run_micron_1_cpad"),
            ("run_samsung_1_cpad", "run_samsung_1_cpad"),
        ]


def test_orchestrator_never_submits_unpaired_binary_without_policy():
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "unpaired.cpad"
        binary.write_bytes(b"CPAD")
        orchestrator = AnalysisOrchestrator.__new__(AnalysisOrchestrator)

        class Submitter:
            def __init__(self):
                self.called = False

            def submit(self, *args, **kwargs):
                self.called = True

        orchestrator.policy_engine = None
        orchestrator.submitter = Submitter()
        rejections = []
        orchestrator._emit_policy_rejection_cper = (
            lambda cpad, decision: rejections.append((cpad, decision)))

        with contextlib.redirect_stdout(io.StringIO()):
            orchestrator._policy_and_submit(
                cpad_binary=binary, cpad_json=None)

        assert orchestrator.submitter.called is False
        assert rejections == [(binary, None)]


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
