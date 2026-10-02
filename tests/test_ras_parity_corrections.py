#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

import json

from src.config.settings import ServerConfig
from src.plugins import PluginContext
from src.plugins.loader import PluginLoader
from src.plugins.ras.plugin import (
    RAS_ANALYTICS_PATH,
    RAS_HEALTH_PATH,
    RAS_SUBMIT_CPAD_PATH,
    RASPlugin,
)
from src.plugins.ras.services.queue_manager import CPERQueueItem
from src.services.event_service import EventServiceHandler


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


def _initialize_real_plugin(tmp_path):
    published_events = []
    config = ServerConfig(mock_dir_path=str(tmp_path))
    context = PluginContext(
        config,
        lambda event: published_events.append(event) or 200,
    )
    plugin = RASPlugin()

    assert plugin.initialize(config, {}, context)
    return plugin, published_events


def test_real_handler_serves_analytics_health_and_one_reset_instance(tmp_path):
    plugin, _published_events = _initialize_real_plugin(tmp_path)

    try:
        analytics_path = RAS_ANALYTICS_PATH.format(ManagerId="System")
        health_path = RAS_HEALTH_PATH.format(ManagerId="System")

        analytics_status, _, analytics = plugin.handle_get(
            analytics_path, {}, {})
        health_status, _, health = plugin.handle_get(health_path, {}, {})

        assert analytics_status == 200
        assert analytics["@odata.id"] == analytics_path
        assert health_status == 200
        assert health["@odata.id"] == health_path

        submit_handler = plugin.submit_cpad_handler
        calls = []
        submit_handler.handle_post = (
            lambda manager_id, data:
            calls.append(("POST", id(submit_handler), manager_id, data))
            or (202, {}))
        submit_handler.on_system_reset = (
            lambda system_id, reset_type:
            calls.append((
                "RESET",
                id(submit_handler),
                system_id,
                reset_type,
            ))
            or 1)

        assert plugin.handle_post(
            RAS_SUBMIT_CPAD_PATH, {"CPADData": "payload"}, {}) == (
                202, {}, {})
        assert plugin.on_system_reset("System", "PowerCycle") == 1
        assert calls == [
            (
                "POST",
                id(submit_handler),
                "System",
                {"CPADData": "payload"},
            ),
            (
                "RESET",
                id(submit_handler),
                "System",
                "PowerCycle",
            ),
        ]
    finally:
        plugin.shutdown()


def test_real_log_queue_event_and_delete_paths(tmp_path):
    plugin, published_events = _initialize_real_plugin(tmp_path)

    try:
        log_service = plugin.handler.log_service_handler
        status, entry_id = log_service.add_cper_log_entry(_cper(41))

        assert status == 201
        assert published_events[0]["MessageId"] == (
            "OCPRAS.1.0.0.CorrectedError")
        assert published_events[0]["AdditionalDataURI"].endswith(
            f"/Entries/{entry_id}/Attachment")
        assert published_events[0]["OriginOfCondition"] == (
            f"/redfish/v1/Managers/System/LogServices/CPER/Entries/"
            f"{entry_id}")

        queue_manager = plugin.handler.queue_manager
        queue_manager.stop()
        queue_item = CPERQueueItem(
            priority=1,
            timestamp=0,
            cper_data=_cper(42),
            manager_id="System",
            metadata={"severity": "Warning"},
        )
        queue_manager.handlers[0](queue_item)

        queued_status, queued_entry = log_service.get_log_entry("42")
        assert queued_status == 200
        assert queued_entry["Id"] == "42"

        entry_path = (
            f"/redfish/v1/Managers/System/LogServices/CPER/Entries/"
            f"{entry_id}"
        )
        delete_status, _, _ = plugin.handle_delete(entry_path, {})

        assert delete_status == 200
        assert log_service.get_log_entry(entry_id) == (404, None)
    finally:
        plugin.shutdown()


def test_log_entry_event_reaches_core_event_service_and_workers_stop(
        tmp_path):
    subscriptions = (
        tmp_path / "redfish" / "v1" / "EventService" / "Subscriptions")
    subscriptions.mkdir(parents=True)
    (subscriptions / "index.json").write_text(
        json.dumps({
            "Members@odata.count": 0,
            "Members": [],
        }),
        encoding="utf-8",
    )
    config = ServerConfig(mock_dir_path=str(tmp_path))
    loader = PluginLoader(config)
    workers = []

    try:
        assert loader.load_plugin("ras", {})
        plugin = loader.get_plugin("ras")
        workers = list(plugin.handler.queue_manager.workers)

        status, _entry_id = (
            plugin.handler.log_service_handler.add_cper_log_entry(
                _cper(43)))

        assert status == 201
        assert isinstance(loader._event_service, EventServiceHandler)
        assert loader._event_service.event_id == 2
        assert workers
        assert all(worker.is_alive() for worker in workers)
    finally:
        assert loader.shutdown()

    assert all(not worker.is_alive() for worker in workers)
