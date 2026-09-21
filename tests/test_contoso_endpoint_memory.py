#!/usr/bin/env python3
"""Integration tests for endpoint-owned Contoso DIMM data and repair state."""

import base64
import copy
import contextlib
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTOSO_DIR = ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CONTOSO_DIR))

import contoso_catalog as catalog  # noqa: E402
import contoso_action_parameters as action_encoder  # noqa: E402
import contoso_encoder as encoder  # noqa: E402
import injection_spec as spec_model  # noqa: E402
from memory_events import decode_memory_events  # noqa: E402
from src.plugins.ras.action_provider import (  # noqa: E402
    ACTION_COMPLETED,
    ActionResult,
)
from src.plugins.ras.contoso_memory import (  # noqa: E402
    active_cpad_memory_bank,
    overlay_cpad_memory_state,
)
from src.plugins.ras.contoso_actions import (  # noqa: E402
    CONTOSO_CREATOR_ID,
    PAGE_OFFLINE_ACTION_ID,
    REBOOT_WITH_RETRAINING_ACTION_ID,
    RETRAINING_RESET_TYPES,
    SPPR_ACTION_ID,
)
from src.plugins.ras.contoso_action_parameters import (  # noqa: E402
    CONTOSO_ACTION_PARAMETER_GUID,
    PPR_TYPE_HARD_BOOT_TIME,
    PPR_TYPE_SOFT_BOOT_TIME,
    PPR_TYPE_SOFT_RUNTIME,
    decode_cpad_action_parameters,
)
from src.plugins.ras.handlers.submit_cpad_action import SubmitCPADActionHandler  # noqa: E402
from src.plugins.ras.memory_config import (  # noqa: E402
    MemoryRepairState,
    RASEndpointConfiguration,
)
from src.plugins.ras.plugin import RASPlugin  # noqa: E402
from src.config.settings import ServerConfig  # noqa: E402
from src.services.custom_actions_service import CustomActionsService  # noqa: E402
from src.plugins.loader import PluginLoader  # noqa: E402


CONFIG_PATH = ROOT / "mockups" / "ras_gen1" / "ras_endpoint_config.json"
PARTITION_ID = "22222222-3333-4444-5555-666666666666"


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


def _set_error_address(cpad, address, valid=True):
    raw = bytearray(base64.b64decode(cpad["sections"][0]["Unknown"]["data"]))
    status = int.from_bytes(raw[8:16], "little")
    if valid:
        status |= 1 << 63
    else:
        status &= ~(1 << 63)
    raw[8:16] = status.to_bytes(8, "little")
    raw[16:24] = address.to_bytes(8, "little")
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(raw).decode("ascii")


def _set_spd_temperature(cpad, temperature):
    raw = bytearray(base64.b64decode(cpad["sections"][0]["Unknown"]["data"]))
    raw[157] = temperature & 0xFF
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(raw).decode("ascii")


def _submission_handler(
        action_id, address=0x12345000,
        creator_id=CONTOSO_CREATOR_ID,
        ppr_type=PPR_TYPE_SOFT_RUNTIME,
        page_ranges=None):
    handler = _handler()
    cpad = _memory_cpad()
    _set_error_address(cpad, address)
    cpad["header"] = {
        "platformID": "990f8820-bd4d-5064-58cc-961a053dea79",
        "partitionID": PARTITION_ID,
        "creatorID": creator_id,
        "recordID": 42,
    }
    cpad["sectionDescriptors"][0].update({
        "actionID": {"code": action_id},
        "fruID": "75824856-bd36-2cc8-61f4-39bb3276da2a",
        "fruText": "DIMM A1",
    })
    if action_id != "0x0006":
        source_cper = {
            "header": cpad["header"],
            "sectionDescriptors": copy.deepcopy(cpad["sectionDescriptors"]),
            "sections": copy.deepcopy(cpad["sections"]),
        }
        source_event = decode_memory_events([{
            "cper_data": source_cper,
            "cper_file": "source.cper",
            "is_newest": True,
        }])[0]
        if action_id == SPPR_ACTION_ID:
            parameters = {"ppr_type": ppr_type}
        elif action_id == PAGE_OFFLINE_ACTION_ID:
            if page_ranges is None:
                page_ranges = [{
                    "start_address":
                        source_event["memory_error"]["error_address"],
                    "page_count": 1,
                }]
            parameters = {
                "page_ranges": page_ranges,
            }
        else:
            parameters = {}
        action_body = action_encoder.encode_action_parameters(
            action_id, source_event, parameters)
        cpad["sectionDescriptors"][0]["sectionType"] = {
            "data": CONTOSO_ACTION_PARAMETER_GUID,
            "type": "Unknown",
        }
        cpad["sectionDescriptors"][0]["sectionLength"] = len(action_body)
        cpad["sections"] = [{
            "Unknown": {
                "data": base64.b64encode(action_body).decode("ascii"),
            },
        }]
    metadata = {
        "record_id": 42,
        "creator_id": creator_id,
        "platform_id": cpad["header"]["platformID"],
        "partition_id": PARTITION_ID,
        "record_length": 48,
        "action_id": action_id,
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

        def next_record_id(self):
            return len(self.records) + 1

        def add_cper_log_entry(self, cper, _binary_path):
            self.records.append(cper)
            return 201, str(len(self.records))

    handler.cpad_handler = StubCpadHandler()
    handler.log_service_handler = StubLogService()
    handler.event_handler = None
    handler.submission_history = []
    handler._convert_binary_cpad_to_json = lambda _raw: cpad
    handler._convert_json_to_binary_cper = lambda _cper, _metadata: None
    return handler, cpad


def _submission_request():
    return {
        "EncodingType": "Base64",
        "CPADData": base64.b64encode(b"CPAD" + b"\x00" * 44).decode("ascii"),
    }


def test_analyzer_and_endpoint_share_contoso_action_contract():
    assert CONTOSO_CREATOR_ID == catalog.CONTOSO_CREATOR_ID
    assert SPPR_ACTION_ID == catalog.SPPR_ACTION["code"]
    assert PAGE_OFFLINE_ACTION_ID == catalog.PAGE_OFFLINE_ACTION["code"]
    assert REBOOT_WITH_RETRAINING_ACTION_ID == (
        catalog.REBOOT_WITH_RETRAINING_ACTION["code"])
    assert RETRAINING_RESET_TYPES == {
        "On", "GracefulRestart", "ForceRestart", "PowerCycle"}


def test_analyzer_and_endpoint_share_action_parameter_binary_contract():
    handler, cpad = _submission_handler(
        SPPR_ACTION_ID, ppr_type=PPR_TYPE_HARD_BOOT_TIME)

    endpoint_parameters = decode_cpad_action_parameters(
        cpad, SPPR_ACTION_ID)

    assert CONTOSO_ACTION_PARAMETER_GUID == (
        action_encoder.CONTOSO_ACTION_PARAMETER_GUID)
    assert endpoint_parameters == {
        "ppr_type": PPR_TYPE_HARD_BOOT_TIME,
        "chiplet": 0,
        "controller": 0,
        "channel": 0,
        "dimm": 1,
        "subchannel": 0,
        "rank": 0,
        "device": 3,
        "bank_group": 2,
        "bank": 3,
        "row": 1234,
    }
    assert handler._contoso_action_provider() is not None


def test_error_injection_keeps_memory_error_section_guid():
    _handler_instance, cpad = _submission_handler("0x0006")

    assert cpad["sectionDescriptors"][0]["sectionType"]["data"] == (
        catalog.SECTION_TYPES[
            "Memory Controller - First Generation"]["guid"])


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


def test_successful_runtime_ppr_prints_complete_repair_target():
    handler, _cpad = _submission_handler(SPPR_ACTION_ID)
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        status, _response = handler.handle_submit_cpad(
            "System", _submission_request())

    assert status == 202
    text = output.getvalue()
    assert "           ✓ runtime soft PPR applied:" in text
    assert "             Chiplet:      0" in text
    assert "             Controller:   0" in text
    assert "             Channel:      0" in text
    assert "             DIMM:         1" in text
    assert "             Subchannel:   0" in text
    assert "             Rank:         0" in text
    assert "             DRAM device:  3" in text
    assert "             Bank group:   2" in text
    assert "             Bank:         3" in text
    assert "             Row:          1234" in text
    assert "             Repair count: 1" in text


def test_page_offline_accepts_one_physical_page():
    handler, cpad = _submission_handler(PAGE_OFFLINE_ACTION_ID)
    endpoint = handler.endpoint_configuration.endpoint_by_partition(PARTITION_ID)
    metadata = handler.cpad_handler.validate_and_extract(cpad)[1]
    provider = handler._contoso_action_provider()

    result = provider.execute(
        "System", PAGE_OFFLINE_ACTION_ID, cpad, metadata, endpoint)

    assert result.return_code == 0
    assert result.details["page_count"] == 1
    assert result.details["page_ranges"] == [{
        "start_address": 0x12345000,
        "page_count": 1,
    }]
    assert "forwarded to the OS" in result.context


def test_page_offline_emits_action_event_without_error_cper():
    handler, _cpad = _submission_handler(PAGE_OFFLINE_ACTION_ID)

    status, response = handler.handle_submit_cpad(
        "System", _submission_request())

    assert status == 202
    assert response["TaskState"] == "Completed"
    assert len(handler.log_service_handler.records) == 1
    action_event = handler.log_service_handler.records[0]["sections"][0][
        "PlatformActionEvent"]
    assert action_event["cpadActionId"] == PAGE_OFFLINE_ACTION_ID
    assert base64.b64decode(action_event["additionalContext"]).decode() == (
        "Page Offline request for physical address 0x0000000012345000 "
        "was forwarded to the OS")


def test_page_offline_for_multiple_pages_reports_page_count():
    ranges = [{
        "start_address": 0x20000000 + index * 0x100000,
        "page_count": 1,
    } for index in range(10)]
    handler, _cpad = _submission_handler(
        PAGE_OFFLINE_ACTION_ID, page_ranges=ranges)

    status, _response = handler.handle_submit_cpad(
        "System", _submission_request())

    assert status == 202
    assert len(handler.log_service_handler.records) == 1
    action_event = handler.log_service_handler.records[0]["sections"][0][
        "PlatformActionEvent"]
    assert base64.b64decode(action_event["additionalContext"]).decode() == (
        "Page Offline request for 10 physical pages was forwarded to the OS")


def test_chunked_page_offline_reports_batch_and_chunk():
    handler, cpad = _submission_handler(PAGE_OFFLINE_ACTION_ID)
    source = _memory_cpad()
    source["header"] = copy.deepcopy(cpad["header"])
    source_event = decode_memory_events([{
        "cper_data": source,
        "cper_file": "source.cper",
        "is_newest": True,
    }])[0]
    pages = [{
        "start_address": 0x10000000 + index * 0x100000,
        "page_count": 1,
    } for index in range(10_000)]
    bodies = action_encoder.encode_action_parameter_bodies(
        PAGE_OFFLINE_ACTION_ID,
        source_event,
        {"page_ranges": pages},
    )
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(
        bodies[0]).decode("ascii")
    metadata = handler.cpad_handler.validate_and_extract(cpad)[1]
    endpoint = handler.endpoint_configuration.endpoint_by_partition(PARTITION_ID)

    result = handler._contoso_action_provider().execute(
        "System", PAGE_OFFLINE_ACTION_ID, cpad, metadata, endpoint)

    assert result.return_code == 0
    assert "chunk 1 of 4" in result.context
    assert result.details["chunk_count"] == 4


def test_error_injection_is_the_only_action_that_emits_an_error_cper():
    handler, _cpad = _submission_handler("0x0006")
    handler._convert_cpad_to_cper = (
        lambda _cpad, _metadata: {"kind": "injected-error"})

    status, _response = handler.handle_submit_cpad(
        "System", _submission_request())

    assert status == 202
    assert len(handler.log_service_handler.records) == 2
    assert handler.log_service_handler.records[0] == {
        "kind": "injected-error"}
    assert "PlatformActionEvent" in (
        handler.log_service_handler.records[1]["sections"][0])


def test_retraining_waits_for_qualifying_whole_machine_reset():
    handler, _cpad = _submission_handler(REBOOT_WITH_RETRAINING_ACTION_ID)

    status, response = handler.handle_submit_cpad(
        "System", _submission_request())

    assert status == 202
    assert response["TaskState"] == "Pending"
    assert handler.submission_history[-1]["decision"] == "PENDING"
    assert handler.log_service_handler.records == []
    assert handler.on_system_reset("system", "GracefulShutdown") == 0
    assert handler.log_service_handler.records == []

    assert handler.on_system_reset("system", "On") == 1
    assert len(handler.log_service_handler.records) == 1
    action_event = handler.log_service_handler.records[0]["sections"][0][
        "PlatformActionEvent"]
    assert action_event["cpadActionId"] == REBOOT_WITH_RETRAINING_ACTION_ID
    context = base64.b64decode(action_event["additionalContext"]).decode()
    assert PARTITION_ID in context
    assert "during On" in context
    assert handler.on_system_reset("system", "PowerCycle") == 0


def test_boot_time_ppr_waits_for_reset_and_repairs_once():
    for ppr_type, label in (
            (PPR_TYPE_SOFT_BOOT_TIME, "boot-time soft PPR"),
            (PPR_TYPE_HARD_BOOT_TIME, "boot-time hard PPR")):
        handler, _cpad = _submission_handler(
            SPPR_ACTION_ID, ppr_type=ppr_type)

        status, response = handler.handle_submit_cpad(
            "System", _submission_request())

        assert status == 202
        assert response["TaskState"] == "Pending"
        assert handler.memory_repair_state.entries_for_dimm(
            0, 0, 0, 1) == []
        assert handler.on_system_reset("system", "GracefulShutdown") == 0
        assert handler.on_system_reset("system", "PowerCycle") == 1
        assert handler.memory_repair_state.entries_for_dimm(
            0, 0, 0, 1)[0]["count"] == 1
        action_event = handler.log_service_handler.records[0]["sections"][0][
            "PlatformActionEvent"]
        context = base64.b64decode(
            action_event["additionalContext"]).decode()
        assert label in context
        assert handler.on_system_reset("system", "PowerCycle") == 0
        assert handler.memory_repair_state.entries_for_dimm(
            0, 0, 0, 1)[0]["count"] == 1


def test_ppr_type_must_be_advertised_by_endpoint_capabilities():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream)
    capabilities = data["ras_endpoints"][0]["memory"][
        "memory_repair_capabilities"]
    capabilities["hard_ppr_boot_time_supported"] = False
    config = RASEndpointConfiguration.from_dict(data)
    endpoint = config.endpoint_by_partition(PARTITION_ID)
    state = MemoryRepairState(
        endpoint.memory, endpoint.memory_repair_capabilities)
    handler, cpad = _submission_handler(
        SPPR_ACTION_ID, ppr_type=PPR_TYPE_HARD_BOOT_TIME)
    handler.endpoint_configuration = config
    handler.memory_repair_states = {PARTITION_ID: state}
    handler.memory_repair_state = state
    handler.action_providers = {}
    metadata = handler.cpad_handler.validate_and_extract(cpad)[1]

    result = handler._contoso_action_provider().execute(
        "System", SPPR_ACTION_ID, cpad, metadata, endpoint)

    assert result.return_code == 1
    assert result.reason == "boot-time hard PPR is not supported"


def test_every_restart_style_reset_completes_retraining():
    for reset_type in RETRAINING_RESET_TYPES:
        handler, _cpad = _submission_handler(
            REBOOT_WITH_RETRAINING_ACTION_ID)
        handler.handle_submit_cpad("System", _submission_request())

        assert handler.on_system_reset("system", reset_type) == 1
        assert len(handler.log_service_handler.records) == 1


def test_failed_retraining_event_storage_leaves_action_pending():
    handler, _cpad = _submission_handler(REBOOT_WITH_RETRAINING_ACTION_ID)
    handler.handle_submit_cpad("System", _submission_request())
    working_log_service = handler.log_service_handler

    class FailingLogService:
        @staticmethod
        def next_record_id():
            return 1

        @staticmethod
        def add_cper_log_entry(_cper, _binary_path):
            return 500, None

    handler.log_service_handler = FailingLogService()
    assert handler.on_system_reset("system", "PowerCycle") == 0

    handler.log_service_handler = working_log_service
    assert handler.on_system_reset("system", "PowerCycle") == 1
    assert len(handler.log_service_handler.records) == 1


def test_failed_boot_ppr_event_storage_does_not_repeat_repair():
    handler, _cpad = _submission_handler(
        SPPR_ACTION_ID, ppr_type=PPR_TYPE_SOFT_BOOT_TIME)
    handler.handle_submit_cpad("System", _submission_request())
    working_log_service = handler.log_service_handler

    class FailingLogService:
        @staticmethod
        def next_record_id():
            return 1

        @staticmethod
        def add_cper_log_entry(_cper, _binary_path):
            return 500, None

    handler.log_service_handler = FailingLogService()
    assert handler.on_system_reset("system", "PowerCycle") == 0
    assert handler.memory_repair_state.entries_for_dimm(
        0, 0, 0, 1)[0]["count"] == 1

    handler.log_service_handler = working_log_service
    assert handler.on_system_reset("system", "PowerCycle") == 1
    assert handler.memory_repair_state.entries_for_dimm(
        0, 0, 0, 1)[0]["count"] == 1


def test_submit_rejects_creator_that_does_not_own_target_partition():
    handler, _cpad = _submission_handler(
        PAGE_OFFLINE_ACTION_ID,
        creator_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    status, response = handler.handle_submit_cpad(
        "System", _submission_request())

    assert status == 400
    message = response["error"]["@Message.ExtendedInfo"][0]["Message"]
    assert "does not match the owner of partition" in message
    assert handler.log_service_handler.records == []


def test_redfish_on_notifies_plugins_after_system_state_is_saved():
    notifications = []
    service = CustomActionsService.__new__(CustomActionsService)
    service.system_reset_notifier = (
        lambda system_id, reset_type:
        notifications.append((system_id, reset_type)))
    service._update_resource_data = (
        lambda _path, _data, _cache: True)
    service._trigger_action_event = lambda *_args: None
    resource = {"PowerState": "Off"}

    status, _headers, body = service._handle_system_reset(
        "/redfish/v1/Systems/system/Actions/ComputerSystem.Reset",
        "/redfish/v1/Systems/system",
        {"ResetType": "On"},
        resource,
        {},
    )

    assert status == 204
    assert body == {}
    assert resource["PowerState"] == "On"
    assert notifications == [("system", "On")]


def test_plugin_loader_notifies_only_plugins_with_reset_callbacks():
    calls = []

    class ResetAwarePlugin:
        @staticmethod
        def on_system_reset(system_id, reset_type):
            calls.append((system_id, reset_type))
            return 2

    loader = PluginLoader()
    loader._loaded_plugins = {
        "ras": ResetAwarePlugin(),
        "telemetry": object(),
    }

    results = loader.notify_system_reset("system", "PowerCycle")

    assert calls == [("system", "PowerCycle")]
    assert results == {"ras": 2}


def test_another_vendor_can_register_same_proprietary_action_id():
    creator_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    config = RASEndpointConfiguration.from_dict({
        "platform_id": "990f8820-bd4d-5064-58cc-961a053dea79",
        "ras_endpoints": [{
            "id": "Endpoint-2",
            "name": "Fabrikam Endpoint",
            "description": "Second vendor endpoint",
            "endpoint_type": "Processor",
            "partition_id": "fabrikam-partition",
            "creator_id": creator_id,
            "fru_id": "fabrikam-fru",
            "fru_text": "Fabrikam SoC",
            "supported_queues": ["Informational"],
        }],
    })
    endpoint = config.endpoint_by_id("Endpoint-2")
    handler = SubmitCPADActionHandler.__new__(SubmitCPADActionHandler)
    handler.action_providers = {}

    class FabrikamProvider:
        creator_ids = frozenset({creator_id})

        @staticmethod
        def execute(_manager, action_id, _cpad, _metadata, _endpoint):
            assert action_id == PAGE_OFFLINE_ACTION_ID
            return ActionResult(
                status=ACTION_COMPLETED,
                context="Fabrikam-specific 0x8002 action",
            )

    handler.register_action_provider(FabrikamProvider())
    result = handler._execute_action(
        "System",
        {},
        {
            "action_id": PAGE_OFFLINE_ACTION_ID,
            "creator_id": creator_id,
        },
        endpoint,
    )

    assert result.context == "Fabrikam-specific 0x8002 action"


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
    assert additional["spd_temperature"] == 40
    assert additional["total_memory_bytes"] == 512 * 1024 ** 3
    assert additional["memory_repair_capabilities"] == 0b111
    assert additional["repairs"] == [{
        "subchannel": 0, "rank": 0, "device": 3,
        "bank_group": 2, "bank": 3, "count": 1,
    }]
    assert len(body) == 184

    cper = {
        "header": {
            "creatorID": CONTOSO_CREATOR_ID,
            "platformID": "990f8820-bd4d-5064-58cc-961a053dea79",
            "partitionID": PARTITION_ID,
        },
        "sectionDescriptors": cpad["sectionDescriptors"],
        "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        }}],
    }
    event = decode_memory_events([{
        "cper_data": cper,
        "cper_file": "temperature.cper",
        "is_newest": True,
    }])[0]
    assert event["spd_temperature"] == 40
    assert event["memory_error"]["additional"]["spd_temperature"] == 40


def test_error_injection_can_override_configured_spd_temperature():
    handler, cpad = _submission_handler("0x0006")
    _set_spd_temperature(cpad, 75)
    without_override = overlay_cpad_memory_state(
        cpad, handler.memory_repair_state)
    assert encoder.unpack_section_body(
        "Memory Controller - First Generation",
        without_override)["additional"]["spd_temperature"] == 40

    handler.log_service_handler = None
    metadata = handler.cpad_handler.validate_and_extract(cpad)[1]

    cper = handler._convert_cpad_to_cper(cpad, metadata)
    body = base64.b64decode(
        cper["sections"][0]["Unknown"]["data"], validate=True)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)

    assert decoded["additional"]["spd_temperature"] == 75


def test_unspecified_injection_temperature_uses_configured_default():
    handler, cpad = _submission_handler("0x0006")
    handler.log_service_handler = None
    metadata = handler.cpad_handler.validate_and_extract(cpad)[1]

    cper = handler._convert_cpad_to_cper(cpad, metadata)
    body = base64.b64decode(
        cper["sections"][0]["Unknown"]["data"], validate=True)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)

    assert decoded["additional"]["spd_temperature"] == 40


def test_endpoint_upgrades_v14_memory_body_with_configured_temperature():
    handler = _handler()
    cpad = _memory_cpad()
    body = bytearray(base64.b64decode(
        cpad["sections"][0]["Unknown"]["data"], validate=True))
    other_offset = int.from_bytes(body[80:84], "little")
    del body[157]
    body[1] = 4
    body[80:84] = (other_offset - 1).to_bytes(4, "little")
    cpad["sections"][0]["Unknown"]["data"] = base64.b64encode(body).decode(
        "ascii")

    upgraded = overlay_cpad_memory_state(
        cpad, handler.memory_repair_state)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", upgraded)

    assert upgraded[0:2] == bytes([1, 5])
    assert decoded["additional"]["spd_temperature"] == 40


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
    body[157] = 99
    body[158:166] = (123).to_bytes(8, "little")
    body[166] = 0b001

    normalized = overlay_cpad_memory_state(
        {**cpad, "sections": [{"Unknown": {
            "data": base64.b64encode(body).decode("ascii"),
        }}]}, handler.memory_repair_state)

    assert normalized[157] == 0
    assert int.from_bytes(normalized[158:166], "little") == 512 * 1024 ** 3
    assert normalized[166] == 0b111
    assert normalized[169] == 0


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


def test_failed_ppr_submission_emits_failed_action_event_and_returns_accepted():
    handler, _cpad = _submission_handler(SPPR_ACTION_ID)
    source_cpad = _memory_cpad()
    for _attempt in range(16):
        assert handler._perform_sppr(source_cpad)[0] == 0

    status, _response = handler.handle_submit_cpad(
        "System", _submission_request())

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
