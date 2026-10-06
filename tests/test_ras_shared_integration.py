#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

import json
import threading

from src.config.settings import ServerConfig
from src.plugins.loader import PluginLoader
from src.services.custom_actions_service import CustomActionsService
from src.services import event_service as event_service_module


def _cper(record_id):
    return {
        "header": {
            "recordID": record_id,
            "severity": {
                "code": 2,
                "name": "Corrected",
            },
            "timestamp": "2026-10-02T20:00:00+00:00",
            "platformID": "990f8820-bd4d-5064-58cc-961a053dea79",
            "partitionID": "22222222-3333-4444-5555-666666666666",
        },
        "sectionDescriptors": [],
        "sections": [],
    }


def test_ras_event_fields_reach_event_service_subscriber(
        monkeypatch, tmp_path):
    subscriptions = (
        tmp_path / "redfish" / "v1" / "EventService" / "Subscriptions")
    subscription = subscriptions / "1"
    subscription.mkdir(parents=True)
    (subscriptions / "index.json").write_text(
        json.dumps({
            "Members@odata.count": 1,
            "Members": [{
                "@odata.id": "/redfish/v1/EventService/Subscriptions/1",
            }],
        }),
        encoding="utf-8",
    )
    (subscription / "index.json").write_text(
        json.dumps({
            "Destination": "http://listener.invalid/events",
            "Protocol": "Redfish",
            "RegistryPrefixes": ["OCPRAS"],
            "Context": "ras-audit",
        }),
        encoding="utf-8",
    )

    published_payloads = []
    delivery_complete = threading.Event()

    def complete_delivery(_events):
        delivery_complete.set()

    monkeypatch.setattr(
        event_service_module.grequests,
        "post",
        lambda *_args, **kwargs:
        published_payloads.append(json.loads(kwargs["data"])),
    )
    monkeypatch.setattr(
        event_service_module.grequests,
        "map",
        complete_delivery,
    )

    loader = PluginLoader(ServerConfig(mock_dir_path=str(tmp_path)))
    try:
        assert loader.load_plugin("ras", {})
        plugin = loader.get_plugin("ras")

        status, entry_id = (
            plugin.handler.log_service_handler.add_cper_log_entry(
                _cper(51)))

        assert status == 201
        assert delivery_complete.wait(timeout=1)
        assert len(published_payloads) == 1
        event = published_payloads[0]["Events"][0]
        assert event["MessageId"] == "OCPRAS.1.0.0.CorrectedError"
        assert event["Severity"] == "Warning"
        assert event["MessageArgs"] == []
        assert event["OriginOfCondition"] == {
            "@odata.id": (
                "/redfish/v1/Managers/System/LogServices/CPER/Entries/"
                f"{entry_id}"
            ),
        }
        assert event["AdditionalDataURI"].endswith(
            f"/Entries/{entry_id}/Attachment")
        assert event["Oem"]["OpenCompute_FaultMgmt"]["QueueType"] == (
            "Corrected")
    finally:
        assert loader.shutdown()


def test_failed_reset_persistence_does_not_notify_plugins():
    notifications = []
    events = []
    service = CustomActionsService.__new__(CustomActionsService)
    service.reset_notifier = (
        lambda system_id, reset_type:
        notifications.append((system_id, reset_type)))
    service._update_resource_data = lambda *_args: False
    service._trigger_action_event = lambda *_args: events.append(True)

    status, headers, body = service._handle_system_reset(
        "/redfish/v1/Systems/system/Actions/ComputerSystem.Reset",
        "/redfish/v1/Systems/system",
        {"ResetType": "PowerCycle"},
        {"PowerState": "On"},
        {},
    )

    assert status == 500
    assert headers == {}
    assert body == {
        "error": "Failed to update ComputerSystem state",
    }
    assert notifications == []
    assert events == []
