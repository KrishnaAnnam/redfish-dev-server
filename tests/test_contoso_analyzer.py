#!/usr/bin/env python3
"""Focused tests for Contoso analyzer SPPR row-failure detection."""

import base64
import contextlib
import importlib.util
import io
import json
import tempfile
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
dispatch_subcomponent_analysis = ANALYZER_MODULE.dispatch_subcomponent_analysis


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


def _contoso_section(section_name, bank_name, fields):
    body = contoso_encoder.pack_section_body(section_name, bank_name, fields)
    return (
        {"sectionType": {
            "data": contoso_catalog.SECTION_TYPES[section_name]["guid"],
            "type": "Unknown",
        }},
        {"Unknown": {"data": base64.b64encode(body).decode("ascii")}},
    )


def _cpu_section(core=0):
    return _contoso_section(
        "CPU Core - First Generation",
        "Core Errors",
        {
            "subcomponent": {"chiplet": 1, "core": core},
            "error_status": (True, False, 3, 2),
            "error_address": 0x1234,
            "misc0": (False, 7),
            "misc1": 0x55,
            "additional": {
                "timeout_transaction_details": 1,
                "register_parity_details": 2,
                "cache_location": 3,
                "assert_details": 4,
                "core_debug_details": 5,
            },
        },
    )


def _memory_section(vendor=(0x80, 0x2C)):
    return _contoso_section(
        "Memory Controller - First Generation",
        "DRAM Errors",
        {
            "subcomponent": {"chiplet": 0, "controller": 0},
            "error_status": (True, False, 2, 1),
            "error_address": 0x2000,
            "misc0": (False, 1),
            "misc1": 0,
            "additional": {
                "channel": 0,
                "dimm": 0,
                "subchannel": 0,
                "rank": 0,
                "device": 1,
                "bank_group": 2,
                "bank": 3,
                "row": 4,
                "column": 5,
                "beat_mask": [0, 0, 0, 0],
                "serial_number": "SERIAL",
                "part_number": "PART",
                "module_manufacturer_id": [0x04, 0xD5],
                "dram_manufacturer_id": list(vendor),
                "spd_temperature": 40,
                "total_memory_bytes": 0,
                "memory_repair_capabilities": 0,
                "reserved": 0,
                "repairs": [],
            },
        },
    )


def _decoded_cper(*section_pairs):
    return {
        "header": {
            "creatorID": "11111111-2222-3333-4444-555555555555",
            "platformID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "partitionID": "11111111-aaaa-bbbb-cccc-222222222222",
        },
        "sectionDescriptors": [pair[0] for pair in section_pairs],
        "sections": [pair[1] for pair in section_pairs],
    }


def test_contoso_memory_action_builders_emit_distinct_action_ids():
    cper = _decoded_cper(_memory_section())
    event = {
        "source": {"section_index": 0},
        "memory_error": {"physical_address": 0x2000},
    }
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    analyzer.sppr_template_path = (
        ANALYZER_PATH.parents[2] / "cpad_storage" / "spprTemplate.json")

    class StubDecoder:
        @staticmethod
        def _convert_json_to_binary_cpad(_json_path, binary_path):
            Path(binary_path).write_bytes(b"CPAD")
            return binary_path

    with tempfile.TemporaryDirectory() as tmp_dir:
        analyzer.output_dir = Path(tmp_dir)
        analyzer.decoder = StubDecoder()
        page_path = analyzer.create_page_offline_cpad_from_memory_event(
            event, cper, output_stem="page")
        retrain_path = (
            analyzer.create_reboot_with_retraining_cpad_from_memory_event(
                event, cper, output_stem="retrain"))

        assert Path(page_path).read_bytes() == b"CPAD"
        assert Path(retrain_path).read_bytes() == b"CPAD"
        page_json = json.loads(
            (analyzer.output_dir / "page_page_offline_cpad.json").read_text())
        retrain_json = json.loads(
            (analyzer.output_dir /
             "retrain_reboot_with_retraining_cpad.json").read_text())
        assert page_json["sectionDescriptors"][0]["actionID"] == (
            contoso_catalog.PAGE_OFFLINE_ACTION)
        assert retrain_json["sectionDescriptors"][0]["actionID"] == (
            contoso_catalog.REBOOT_WITH_RETRAINING_ACTION)


def test_page_offline_builder_requires_4k_alignment():
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    event = {
        "source": {"section_index": 0},
        "memory_error": {"physical_address": 0x2001},
    }

    try:
        analyzer.create_page_offline_cpad_from_memory_event(
            event, _decoded_cper(_memory_section()))
    except ValueError as exc:
        assert str(exc) == (
            "Page Offline physical address must be 4 KiB aligned")
    else:
        raise AssertionError("unaligned Page Offline address was accepted")


def test_cpu_only_dispatch_reports_all_cpu_sections_without_memory_initialization():
    cper = _decoded_cper(_cpu_section(2), _cpu_section(7))
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    memory_initialized = False

    def forbidden_memory_factory(*_args):
        nonlocal memory_initialized
        memory_initialized = True
        raise AssertionError("memory analyzer initialized for CPU-only CPER")

    result = dispatch_subcomponent_analysis(
        analyzer,
        [{"cper_data": cper, "cper_file": "cpu.cper", "is_newest": True}],
        "cpu",
        memory_analyzer_factory=forbidden_memory_factory,
    )

    assert memory_initialized is False
    assert [item["subcomponent"] for item in result["subcomponents"]] == [
        "cpu_core"]
    cpu_result = result["subcomponents"][0]
    assert cpu_result["section_indexes"] == [0, 1]
    assert cpu_result["cpads"] == []
    assert cpu_result["history_summary"]["messages"] == [
        "This error does not require historical analysis; "
        "0 prior CPER candidate(s) were not used."
    ]
    assert [finding["error"]["subcomponent"]["core"]
            for finding in cpu_result["findings"]] == [2, 7]
    assert all(finding["error"]["name"] == "Transaction Timeout"
               for finding in cpu_result["findings"])


def test_mixed_cpu_and_memory_dispatch_invokes_both_with_original_indexes():
    cpu = _cpu_section()
    memory = _memory_section()
    unsupported = (
        {"sectionType": {"data": "00000000-0000-0000-0000-000000000000"}},
        {"Unknown": {"data": ""}},
    )
    cper = _decoded_cper(unsupported, cpu, memory)
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)

    class FakeMemoryAnalyzer:
        def __init__(self, _host, _shim_dir):
            pass

        def analyze(self, sections, _records, _source_stem,
                    _prior_cper_count=0):
            return {
                "subcomponent": "memory_controller",
                "section_indexes": [
                    section["source"]["section_index"] for section in sections],
                "findings": [],
                "cpads": [],
            }

    result = dispatch_subcomponent_analysis(
        analyzer,
        [{"cper_data": cper, "cper_file": "mixed.cper", "is_newest": True}],
        "mixed",
        memory_analyzer_factory=FakeMemoryAnalyzer,
    )

    assert [item["subcomponent"] for item in result["subcomponents"]] == [
        "cpu_core", "memory_controller"]
    assert [item["section_indexes"] for item in result["subcomponents"]] == [
        [1], [2]]
    assert [finding["source"]["section_index"]
            for finding in result["findings"]] == [1]


def test_memory_location_uses_single_failing_dram_as_device():
    beat_mask = [0] * 4
    beat_mask[2] = 1 << 5
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
            "device": 3,
            "bank_group": 3,
            "bank": 1,
            "row": 42,
            "column": 10,
            "serial_number": "SN123456789",
            "part_number": "PN-1234",
            "dram_manufacturer_id": [0x80, 0x2C],
            "module_manufacturer_id": [0x04, 0xD5],
            "reserved": 0,
            "beat_mask": beat_mask,
            "repairs": [],
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
    assert location["serial_number"] == "SN123456789"
    assert location["part_number"] == "PN-1234"
    assert location["dram_manufacturer_id"] == [0x80, 0x2C]
    assert location["dram_manufacturer"] == "Micron"
    assert location["module_manufacturer_id"] == [0x04, 0xD5]
    assert location["module_manufacturer"] == "Microsoft"
    assert location["spd_temperature"] == 0


def test_manufacturer_id_format_includes_unknown_decode():
    code = ("bytes", 2)
    assert ContosoAnalyzer._fmt_register(
        "dram_manufacturer_id", code, [0x80, 0xCE]) == "80 CE (Samsung)"
    assert ContosoAnalyzer._fmt_register(
        "module_manufacturer_id", code, [0x80, 0x01]) == "80 01 (Unknown)"


def test_memory_total_and_repair_capabilities_format():
    assert ContosoAnalyzer._fmt_register(
        "total_memory_bytes", "Q", 512 * 1024 ** 3
    ) == "512 GiB (549755813888 bytes)"
    assert ContosoAnalyzer._fmt_register(
        "memory_repair_capabilities", "B", 0b101
    ) == ("Soft PPR at runtime: Supported; Soft PPR at boot time: Not supported; "
          "Hard PPR at boot time: Supported")
    assert ContosoAnalyzer._fmt_register(
        "spd_temperature", "b", -5) == "-5 C"


def test_memory_repair_capabilities_print_one_per_line():
    output = []
    fields = {
        "subcomponent": {"chiplet": 0, "controller": 0},
        "error_status": (True, False, 5, 1),
        "error_address": 0,
        "misc0": (False, 1),
        "misc1": 0,
        "additional": {
            "channel": 0,
            "dimm": 0,
            "subchannel": 0,
            "rank": 0,
            "device": 0,
            "bank_group": 0,
            "bank": 0,
            "row": 0,
            "column": 0,
            "beat_mask": [0, 0, 0, 0],
            "serial_number": "",
            "part_number": "",
            "module_manufacturer_id": [0x04, 0xD5],
            "dram_manufacturer_id": [0x80, 0x2C],
            "spd_temperature": 40,
            "total_memory_bytes": 0,
            "memory_repair_capabilities": 0b101,
            "reserved": 0,
            "repairs": [],
        },
    }
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    analyzer._print_contoso_section_body(
        output.append,
        "Memory Controller - First Generation",
        {
            "bank_name": "DRAM Errors",
            "subcomponent": fields["subcomponent"],
            "error_status": {
                "addressValid": True,
                "overflow": False,
                "severity_value": 5,
                "error_id": 1,
            },
            "error_address": fields["error_address"],
            "misc0": {"injected": False, "ce_count": 1},
            "misc1": fields["misc1"],
            "additional": fields["additional"],
        },
    )

    heading = output.index("            memory_repair_capabilities:")
    assert output[heading:heading + 4] == [
        "            memory_repair_capabilities:",
        "               Soft PPR at runtime: Supported",
        "               Soft PPR at boot time: Not supported",
        "               Hard PPR at boot time: Supported",
    ]
    assert "            spd_temperature:               40 C" in output


def test_contoso_decoder_rejects_noncanonical_base64():
    fields = {
        "subcomponent": {"chiplet": 0, "core": 0},
        "error_status": (True, False, 3, 1),
        "error_address": 0,
        "misc0": (False, 0),
        "misc1": 0,
        "additional": {},
    }
    body = contoso_encoder.pack_section_body(
        "CPU Core - First Generation", "Core Errors", fields)
    cper_data = {
        "sectionDescriptors": [{"sectionType": {
            "data": contoso_catalog.SECTION_TYPES[
                "CPU Core - First Generation"]["guid"],
        }}],
        "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii") + "#",
        }}],
    }
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)

    assert analyzer._decode_contoso_section(cper_data, 0) == (None, None)


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
    beat_mask = [0, 0x80, 0, 0]

    formatted = ContosoAnalyzer._fmt_register(
        "beat_mask", ("vector", "H", 4), beat_mask)

    assert formatted == "DQ 1, beat 7 (mask 0x80)"


def test_platform_action_event_reports_completed_action():
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    analyzer.output_dir = Path(".")
    cper_data = {
        "header": {"severity": {"name": "Platform Action Event", "code": 4}},
        "sectionDescriptors": [{
            "sectionType": {"type": "Platform Action Event"},
        }],
        "sections": [{
            "PlatformActionEvent": {"actionReturnCode": "0x00"},
        }],
    }
    result = {
        "cper_data": cper_data,
        "sppr_created": False,
        "dram_row_failure_detected": False,
        "memory_location": None,
    }
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        analyzer.print_batch_recommendation([result], successful=1)

    report = output.getvalue()
    assert "Recommendation:     No Action Required" in report
    assert "Reason:             Platform Action Completed." in report
    assert "No action required yet" not in report
    assert "Insufficient data to infer a fault" not in report


def test_failed_platform_action_event_reports_failure():
    analyzer = ContosoAnalyzer.__new__(ContosoAnalyzer)
    analyzer.output_dir = Path(".")
    cper_data = {
        "header": {"severity": {"name": "Platform Action Event", "code": 4}},
        "sectionDescriptors": [{
            "sectionType": {"type": "Platform Action Event"},
        }],
        "sections": [{
            "PlatformActionEvent": {"actionReturnCode": "0x01"},
        }],
    }
    result = {
        "cper_data": cper_data,
        "sppr_created": False,
        "dram_row_failure_detected": False,
        "memory_location": None,
    }
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        analyzer.print_batch_recommendation([result], successful=1)

    report = output.getvalue()
    assert "Recommendation:     Review Failed Platform Action" in report
    assert "Reason:             Platform Action Failed." in report
    assert "Platform Action Completed" not in report
