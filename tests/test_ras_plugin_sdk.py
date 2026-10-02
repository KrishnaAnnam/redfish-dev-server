#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

from src.config.settings import ServerConfig
from src.plugins import PluginContext
from src.plugins.ras import provider as provider_module
from src.plugins.ras.plugin import (
    CPER_ENTRIES_PATH,
    CPER_LOG_SERVICE_PATH,
    RAS_ANALYTICS_PATH,
    RAS_ACTION_INFO_PATH,
    RAS_ENDPOINTS_PATH,
    RAS_HEALTH_PATH,
    RAS_SERVICE_PATH,
    RAS_SUBMIT_CPAD_PATH,
    RASPlugin,
)


class _EventHandler:
    def __init__(self):
        self.callback = None

    def register_callback(self, callback):
        self.callback = callback


class _QueueManager:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _SubmitCPADHandler:
    def __init__(self):
        self.reset_calls = []

    def on_system_reset(self, system_id, reset_type):
        self.reset_calls.append((system_id, reset_type))
        return 2


class _RASHandler:
    def __init__(self, config):
        self.config = config
        self.event_handler = _EventHandler()
        self.queue_manager = _QueueManager()
        self.submit_cpad_handler = _SubmitCPADHandler()
        self.discovery_handler = object()
        self.calls = []

    def handle_get(self, path, query_params, cached_links):
        self.calls.append(('GET', path, query_params, cached_links))
        return 200, {'path': path}

    def handle_post(self, path, data, cached_links):
        self.calls.append(('POST', path, data, cached_links))
        return 202, {'accepted': data}

    def handle_delete(self, path, cached_links):
        self.calls.append(('DELETE', path, cached_links))
        return 200, {'deleted': path}


def _initialize_plugin(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_module, 'RASHandler', _RASHandler)
    published_events = []
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        short_form=True,
    )
    context = PluginContext(
        config,
        lambda event: published_events.append(event) or 200,
    )
    plugin = RASPlugin()

    assert plugin.initialize(
        config,
        {
            'endpoint_config': 'ras_endpoint_config.json',
            'queue_enabled': True,
        },
        context,
    )
    return plugin, published_events


def test_ras_plugin_adapts_configuration_and_routes(monkeypatch, tmp_path):
    plugin, _published_events = _initialize_plugin(monkeypatch, tmp_path)

    assert plugin.handler.config == {
        'endpoint_config': 'ras_endpoint_config.json',
        'queue_enabled': True,
        'mockup_dir': str(tmp_path.resolve()),
    }

    routes = {
        (route.path, route.methods)
        for route in plugin.get_routes()
    }
    assert routes == {
        (RAS_SERVICE_PATH, frozenset({'GET'})),
        (RAS_ENDPOINTS_PATH, frozenset({'GET'})),
        (
            f"{RAS_ENDPOINTS_PATH}/{{EndpointId}}",
            frozenset({'GET'}),
        ),
        (RAS_ACTION_INFO_PATH, frozenset({'GET'})),
        (RAS_SUBMIT_CPAD_PATH, frozenset({'POST'})),
        (CPER_LOG_SERVICE_PATH, frozenset({'GET'})),
        (CPER_ENTRIES_PATH, frozenset({'GET'})),
        (
            f"{CPER_ENTRIES_PATH}/{{EntryId}}",
            frozenset({'GET', 'DELETE'}),
        ),
        (
            f"{CPER_ENTRIES_PATH}/{{EntryId}}/Attachment",
            frozenset({'GET'}),
        ),
        (
            f"{CPER_LOG_SERVICE_PATH}/Actions/LogService.ClearLog",
            frozenset({'POST'}),
        ),
        (RAS_ANALYTICS_PATH, frozenset({'GET'})),
        (RAS_HEALTH_PATH, frozenset({'GET'})),
    }


def test_ras_plugin_delegates_requests_and_reset(monkeypatch, tmp_path):
    plugin, _published_events = _initialize_plugin(monkeypatch, tmp_path)

    assert plugin.handle_get(
        RAS_SERVICE_PATH,
        {'detail': ['full']},
        {'cached': True},
    ) == (200, {}, {'path': RAS_SERVICE_PATH})
    assert plugin.handle_post(
        RAS_SUBMIT_CPAD_PATH,
        {'CPADData': 'payload'},
        {},
    ) == (202, {}, {'accepted': {'CPADData': 'payload'}})

    entry_path = (
        "/redfish/v1/Managers/System/LogServices/CPER/Entries/42"
    )
    assert plugin.handle_delete(
        entry_path,
        {},
    ) == (200, {}, {'deleted': entry_path})
    assert plugin.on_system_reset('System', 'ForceRestart') == 2

    assert plugin.handler.calls == [
        ('GET', RAS_SERVICE_PATH, {'detail': ['full']}, {'cached': True}),
        ('POST', RAS_SUBMIT_CPAD_PATH, {'CPADData': 'payload'}, {}),
        ('DELETE', entry_path, {}),
    ]
    assert plugin.handler.submit_cpad_handler.reset_calls == [
        ('System', 'ForceRestart'),
    ]


def test_ras_plugin_publishes_through_core_context(monkeypatch, tmp_path):
    plugin, published_events = _initialize_plugin(monkeypatch, tmp_path)

    plugin.handler.event_handler.callback({
        '@odata.type': '#Event.v1_7_0.Event',
        'Events': [{
            'MessageId': 'OCPRAS.1.0.0.CPERRecordCreated',
            'Message': 'CPER record created.',
            'OriginOfCondition': {
                '@odata.id': (
                    '/redfish/v1/Managers/System/LogServices/'
                    'CPER/Entries/42'
                ),
            },
        }],
    })

    assert published_events == [{
        'MessageId': 'OCPRAS.1.0.0.CPERRecordCreated',
        'Message': 'CPER record created.',
        'OriginOfCondition': (
            '/redfish/v1/Managers/System/LogServices/CPER/Entries/42'
        ),
    }]


def test_ras_plugin_stops_owned_workers_on_shutdown(monkeypatch, tmp_path):
    plugin, _published_events = _initialize_plugin(monkeypatch, tmp_path)
    queue_manager = plugin.handler.queue_manager

    assert plugin.shutdown()

    assert queue_manager.stopped
    assert not plugin.enabled
    assert plugin.handler is None


def test_ras_plugin_initializes_real_handler_and_serves_discovery(tmp_path):
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        short_form=True,
    )
    context = PluginContext(config, lambda _event: 200)
    plugin = RASPlugin()

    try:
        assert plugin.initialize(config, {}, context)
        assert isinstance(plugin.handler, provider_module.RASHandler)

        status, headers, body = plugin.handle_get(
            RAS_SERVICE_PATH,
            {},
            {},
        )

        assert status == 200
        assert headers == {}
        assert body['@odata.id'] == RAS_SERVICE_PATH
    finally:
        plugin.shutdown()
