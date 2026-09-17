#!/usr/bin/env python3
"""Integration tests for endpoint-owned Contoso DIMM data and repair state."""

import base64
import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTOSO_DIR = ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CONTOSO_DIR))

import contoso_catalog as catalog  # noqa: E402
import contoso_encoder as encoder  # noqa: E402
import injection_spec as spec_model  # noqa: E402
from src.plugins.ras.contoso_memory import (  # noqa: E402
    active_cpad_memory_bank,
    overlay_cpad_memory_state,
)
from src.plugins.ras.handlers.submit_cpad_action import SubmitCPADActionHandler  # noqa: E402
from src.plugins.ras.memory_config import (  # noqa: E402
    MemoryRepairState,
    RASEndpointConfiguration,
)
from src.plugins.ras.plugin import RASPlugin  # noqa: E402
from src.config.settings import ServerConfig  # noqa: E402


CONFIG_PATH = ROOT / "mockups" / "ras_gen1" / "ras_endpoint_config.json"


def _memory_cpad():
    spec = spec_model.build_template(
        "Memory Controller - First Generation", "Corrected Memory ECC Error")
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
        "column": 567,
        "serial_number": "UNTRUSTED",
        "part_number": "UNTRUSTED",
        "repairs": [{"subchannel": 0, "rank": 0, "device": 3,
                     "bank_group": 2, "bank": 3, "count": 99}],
    })
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors",
        spec_model.to_encoder_fields(spec))
    return {
        "sectionDescriptors": [{
            "sectionType": {
                "data": catalog.SECTION_TYPES[
                    "Memory Controller - First Generation"]["guid"],
                "type": "Unknown",
            },
        }],
        "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        }}],
    }


def _other_error_cpad():
    spec = spec_model.build_template(
        "Memory Controller - First Generation", "DLL Lock Error")
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "Other Errors",
        spec_model.to_encoder_fields(spec))
    return {
        "sectionDescriptors": [{
            "sectionType": {
                "data": catalog.SECTION_TYPES[
                    "Memory Controller - First Generation"]["guid"],
                "type": "Unknown",
            },
        }],
        "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        }}],
    }


def _handler():
    handler = SubmitCPADActionHandler.__new__(SubmitCPADActionHandler)
    config = RASEndpointConfiguration.load(CONFIG_PATH)
    endpoint = config.endpoint_by_id("Endpoint-1")
    state = MemoryRepairState(
        endpoint.memory, endpoint.memory_repair_capabilities)
    handler.endpoint_configuration = config
    handler.memory_repair_states = {endpoint.partition_id: state}
    handler.memory_repair_state = state
    return handler


def test_successful_sppr_increments_target_bank():
    handler = _handler()
    cpad = _memory_cpad()

    return_code, reason, count = handler._perform_sppr(cpad)

    assert return_code == 0
    assert reason is None
    assert count == 1
    assert handler.memory_repair_state.entries_for_dimm(0, 0, 0, 1) == [{
        "subchannel": 0, "rank": 0, "device": 3,
        "bank_group": 2, "bank": 3, "count": 1,
    }]


def test_sppr_at_dimm_limit_fails_without_incrementing():
    handler = _handler()
    cpad = _memory_cpad()
    for expected in range(1, 17):
        assert handler._perform_sppr(cpad)[2] == expected

    return_code, reason, count = handler._perform_sppr(cpad)

    assert return_code == 1
    assert "repair limit 16 reached" in reason
    assert count is None
    assert handler.memory_repair_state.entries_for_dimm(0, 0, 0, 1)[0]["count"] == 16


def test_sppr_fails_when_runtime_soft_ppr_is_not_supported():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream)
    data["ras_endpoints"][0]["memory"]["memory_repair_capabilities"][
        "soft_ppr_runtime_supported"] = False
    config = RASEndpointConfiguration.from_dict(data)
    endpoint = config.endpoint_by_id("Endpoint-1")
    state = MemoryRepairState(
        endpoint.memory, endpoint.memory_repair_capabilities)
    handler = SubmitCPADActionHandler.__new__(SubmitCPADActionHandler)
    handler.endpoint_configuration = config
    handler.memory_repair_states = {endpoint.partition_id: state}
    handler.memory_repair_state = state

    return_code, reason, count = handler._perform_sppr(
        _memory_cpad(), endpoint.partition_id)

    assert return_code == 1
    assert reason == "soft PPR is not supported at runtime"
    assert count is None
    assert state.entries_for_dimm(0, 0, 0, 1) == []


def test_cper_overlay_uses_configured_spd_and_authoritative_repairs():
    handler = _handler()
    cpad = _memory_cpad()
    assert handler._perform_sppr(cpad)[0] == 0

    body = overlay_cpad_memory_state(cpad, handler.memory_repair_state)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)
    additional = decoded["additional"]

    assert additional["serial_number"] == "MSFT-C0-CH0-D1"
    assert additional["part_number"] == "MSFT-DDR5-64GB"
    assert additional["module_manufacturer_id"] == [0x04, 0xD5]
    assert additional["dram_manufacturer_id"] == [0x04, 0xD5]
    assert additional["total_memory_bytes"] == 512 * 1024 ** 3
    assert additional["memory_repair_capabilities"] == 0b111
    assert additional["repairs"] == [{
        "subchannel": 0, "rank": 0, "device": 3,
        "bank_group": 2, "bank": 3, "count": 1,
    }]
    assert len(body) == 183


def test_sppr_rejects_uninstalled_dimm():
    handler = _handler()
    cpad = _memory_cpad()
    raw = bytearray(base64.b64decode(cpad["sections"][0]["Unknown"]["data"]))
    raw[89] = 9
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(raw).decode("ascii")

    return_code, reason, count = handler._perform_sppr(cpad)

    assert return_code == 1
    assert "no DIMM is installed" in reason
    assert count is None


def test_sppr_rejects_redirected_additional_offset():
    handler = _handler()
    cpad = _memory_cpad()
    raw = bytearray(base64.b64decode(cpad["sections"][0]["Unknown"]["data"]))
    raw[40:44] = (100).to_bytes(4, "little")
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(raw).decode("ascii")

    return_code, reason, count = handler._perform_sppr(cpad)

    assert return_code == 1
    assert "offset is invalid" in reason
    assert count is None
    assert handler.memory_repair_state.entries_for_dimm(0, 0, 0, 1) == []


def test_sppr_rejects_nonzero_error_bank_reserved_word():
    handler = _handler()
    cpad = _memory_cpad()
    raw = bytearray(base64.b64decode(cpad["sections"][0]["Unknown"]["data"]))
    raw[44:48] = (1).to_bytes(4, "little")
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(raw).decode("ascii")

    return_code, reason, count = handler._perform_sppr(cpad)

    assert return_code == 1
    assert "Error Bank reserved field must be zero" in reason
    assert count is None


def test_sppr_requires_active_dram_error_bank():
    handler = _handler()
    cpad = _memory_cpad()
    raw = bytearray(base64.b64decode(cpad["sections"][0]["Unknown"]["data"]))
    raw[8:16] = b"\x00" * 8
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(raw).decode("ascii")

    return_code, reason, count = handler._perform_sppr(cpad)

    assert return_code == 1
    assert "exactly one active error bank" in reason
    assert count is None


def test_controller_error_remains_valid_but_cannot_target_sppr():
    handler = _handler()
    cpad = _other_error_cpad()

    assert active_cpad_memory_bank(cpad) == "other"
    return_code, reason, count = handler._perform_sppr(cpad)
    assert return_code == 1
    assert "DRAM Errors bank to be active" in reason
    assert count is None


def test_controller_error_normalizes_inactive_dram_metadata():
    handler = _handler()
    cpad = _other_error_cpad()
    body = bytearray(base64.b64decode(
        cpad["sections"][0]["Unknown"]["data"], validate=True))
    body[157:165] = (123).to_bytes(8, "little")
    body[165] = 0b001

    normalized = overlay_cpad_memory_state(
        {**cpad, "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        }}]}, handler.memory_repair_state)

    assert int.from_bytes(normalized[157:165], "little") == 512 * 1024 ** 3
    assert normalized[165] == 0b111
    assert normalized[168] == 0


def test_submit_cpad_rejects_noncanonical_base64():
    handler = _handler()
    request = {
        "EncodingType": "Base64",
        "CPADData": base64.b64encode(b"CPAD" + b"\x00" * 44).decode("ascii") + "#",
    }

    status, response = handler.handle_submit_cpad("System", request)

    assert status == 400
    assert "Failed to decode Base64" in response["error"]["@Message.ExtendedInfo"][0]["Message"]


def test_plugin_paths_load_memory_configuration():
    plugin = RASPlugin()

    assert plugin.initialize({"mockup_dir": str(CONFIG_PATH.parent)})
    assert plugin.submit_cpad_handler.memory_repair_state is not None

    server_plugin = RASPlugin()
    server_config = ServerConfig(mock_dir_path=str(CONFIG_PATH.parent))
    assert server_plugin.initialize(server_config)
    assert server_plugin.submit_cpad_handler.memory_repair_state is not None


def test_two_endpoints_keep_totals_capabilities_and_repairs_independent():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream)
    second = copy.deepcopy(data["ras_endpoints"][0])
    second["id"] = "Endpoint-2"
    second["partition_id"] = "77777777-8888-9999-aaaa-bbbbbbbbbbbb"
    second["memory"]["memory_repair_capabilities"][
        "soft_ppr_runtime_supported"] = False
    for controller in second["memory"]["memory_controllers"]:
        for dimm in controller["dimms"]:
            dimm["size_bytes"] //= 2
    data["ras_endpoints"].append(second)
    config = RASEndpointConfiguration.from_dict(data)
    first_endpoint, second_endpoint = config.endpoints
    first_state = MemoryRepairState(
        first_endpoint.memory, first_endpoint.memory_repair_capabilities)
    second_state = MemoryRepairState(
        second_endpoint.memory, second_endpoint.memory_repair_capabilities)
    handler = SubmitCPADActionHandler.__new__(SubmitCPADActionHandler)
    handler.endpoint_configuration = config
    handler.memory_repair_states = {
        first_endpoint.partition_id: first_state,
        second_endpoint.partition_id: second_state,
    }
    handler.memory_repair_state = None
    cpad = _memory_cpad()

    assert handler._perform_sppr(cpad, first_endpoint.partition_id)[0] == 0
    assert handler._perform_sppr(cpad, second_endpoint.partition_id)[0] == 1
    first_body = overlay_cpad_memory_state(cpad, first_state)
    second_body = overlay_cpad_memory_state(cpad, second_state)
    first = encoder.unpack_section_body(
        "Memory Controller - First Generation", first_body)["additional"]
    second_additional = encoder.unpack_section_body(
        "Memory Controller - First Generation", second_body)["additional"]

    assert first["total_memory_bytes"] == 512 * 1024 ** 3
    assert first["memory_repair_capabilities"] == 0b111
    assert first["repairs"][0]["count"] == 1
    assert second_additional["total_memory_bytes"] == 256 * 1024 ** 3
    assert second_additional["memory_repair_capabilities"] == 0b110
    assert second_additional["repairs"] == []


def test_failed_sppr_submission_emits_failed_action_event_and_returns_accepted():
    handler = _handler()
    cpad = _memory_cpad()
    cpad["header"] = {
        "platformID": "990f8820-bd4d-5064-58cc-961a053dea79",
        "partitionID": "22222222-3333-4444-5555-666666666666",
        "creatorID": "11111111-2222-3333-4444-555555555555",
        "recordID": 42,
    }
    cpad["sectionDescriptors"][0].update({
        "fruID": "75824856-bd36-2cc8-61f4-39bb3276da2a",
        "fruText": "DIMM A1",
    })
    for _attempt in range(16):
        assert handler._perform_sppr(cpad)[0] == 0

    metadata = {
        "record_id": 42,
        "creator_id": cpad["header"]["creatorID"],
        "platform_id": cpad["header"]["platformID"],
        "partition_id": cpad["header"]["partitionID"],
        "record_length": 48,
        "action_id": "0x8001",
        "fru_id": cpad["sectionDescriptors"][0]["fruID"],
        "fru_text": "DIMM A1",
        "confidence": 80,
    }

    class StubCpadHandler:
        @staticmethod
        def validate_and_extract(_cpad):
            return True, metadata, None

    class StubLogService:
        def __init__(self):
            self.records = []

        @staticmethod
        def next_record_id():
            return 1

        def add_cper_log_entry(self, cper, _binary_path):
            self.records.append(cper)
            return 201, "1"

    handler.cpad_handler = StubCpadHandler()
    handler.log_service_handler = StubLogService()
    handler.event_handler = None
    handler.submission_history = []
    handler._convert_binary_cpad_to_json = lambda _raw: cpad
    handler._convert_json_to_binary_cper = lambda _cper, _metadata: None
    request = {
        "EncodingType": "Base64",
        "CPADData": base64.b64encode(b"CPAD" + b"\x00" * 44).decode("ascii"),
    }

    status, _response = handler.handle_submit_cpad("System", request)

    action_event = handler.log_service_handler.records[0]["sections"][0][
        "PlatformActionEvent"]
    assert status == 202
    assert action_event["actionReturnCode"] == "0x01"
    assert handler.submission_history[-1]["decision"] == "ACTION_FAILED"
    assert handler.memory_repair_state.entries_for_dimm(0, 0, 0, 1)[0]["count"] == 16


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
