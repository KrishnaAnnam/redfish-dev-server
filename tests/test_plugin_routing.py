#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

import base64
import http.client
import json
import sys
import threading
import types
from contextlib import contextmanager
from http.server import HTTPServer

import pytest

from src.config.settings import ServerConfig
from src.handlers.base_handler import BaseRedfishHandler
from src.handlers.main_handler import RedfishMockupHandler
from src.plugins import PluginRoute
from src.plugins import loader as loader_module
from src.plugins.telemetry.plugin import (
    SUBMIT_TEST_METRIC_REPORT_PATH,
    TelemetryPlugin,
)
from servers.redfishMockupServer_enhanced import (
    create_enhanced_handler_class,
)
from servers.redfishMockupServer_platform import PlatformAwareRedfishHandler


def _register_plugin(monkeypatch, name, plugin):
    module_name = f'src.plugins.{name}'
    module = types.ModuleType(module_name)
    module.get_plugin = lambda: plugin
    monkeypatch.setitem(sys.modules, module_name, module)


@contextmanager
def _running_server(config):
    loader_module._loader_instance = None
    BaseRedfishHandler.cached_links = {}
    BaseRedfishHandler.active_sessions = {}

    server = HTTPServer(('127.0.0.1', 0), RedfishMockupHandler)
    server.config = config
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        loader_module.shutdown_plugins()


def _request(address, method, path, payload=None):
    headers = {
        'Authorization': 'Basic ' + base64.b64encode(b'user:password').decode(),
    }
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers['Content-Type'] = 'application/json'
        headers['Content-Length'] = str(len(body.encode('utf-8')))

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read()
        return response.status, dict(response.getheaders()), response_body
    finally:
        connection.close()


class _RoutingPlugin:
    def __init__(self):
        self.enabled = False
        self.calls = []

    def initialize(self, server_config, plugin_config):
        self.enabled = True
        return True

    def shutdown(self):
        self.enabled = False
        self.calls.append(('SHUTDOWN',))
        return True

    def get_routes(self):
        return [
            PluginRoute('/redfish/v1/TestPlugin', {'GET'}),
            PluginRoute(
                '/redfish/v1/TestPlugin/Actions/Run',
                {'POST'},
            ),
            PluginRoute(
                '/redfish/v1/TestPlugin/Resources/{ResourceId}',
                {'PATCH', 'DELETE'},
            ),
            PluginRoute('/redfish/v1/TestPlugin/Attachment', {'GET'}),
        ]

    def handle_get(self, path, query_params, cached_links):
        self.calls.append(('GET', path, query_params))
        return 206, {'X-Plugin': 'test'}, {'path': path}

    def handle_post(self, path, data, cached_links):
        self.calls.append(('POST', path, data))
        return 202, {'Location': f'{path}/result'}, {'accepted': data}

    def handle_patch(self, path, data, cached_links):
        self.calls.append(('PATCH', path, data))
        return 204, {}, None

    def handle_delete(self, path, cached_links):
        self.calls.append(('DELETE', path))
        return 204, {}, None


def test_configured_plugin_receives_http_get_and_post(monkeypatch, tmp_path):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    with _running_server(config) as address:
        get_status, get_headers, get_body = _request(
            address,
            'GET',
            '/redfish/v1/TestPlugin?detail=full',
        )
        post_status, post_headers, post_body = _request(
            address,
            'POST',
            '/redfish/v1/TestPlugin/Actions/Run',
            {'value': 42},
        )

    assert get_status == 206
    assert get_headers['X-Plugin'] == 'test'
    assert json.loads(get_body) == {'path': '/redfish/v1/TestPlugin'}
    assert post_status == 202
    assert post_headers['Location'].endswith('/Actions/Run/result')
    assert json.loads(post_body) == {'accepted': {'value': 42}}
    assert plugin.calls[:-1] == [
        ('GET', '/redfish/v1/TestPlugin', {'detail': ['full']}),
        ('POST', '/redfish/v1/TestPlugin/Actions/Run', {'value': 42}),
    ]
    assert plugin.calls[-1] == ('SHUTDOWN',)


def test_enhanced_server_uses_the_same_plugin_route_contract(
        monkeypatch, tmp_path):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )
    handler = create_enhanced_handler_class()

    loader_module._loader_instance = None
    BaseRedfishHandler.cached_links = {}
    server = HTTPServer(('127.0.0.1', 0), handler)
    server.config = config
    server.server_config = config
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, body = _request(
            server.server_address,
            'GET',
            '/redfish/v1/TestPlugin',
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        loader_module.shutdown_plugins()

    assert status == 206
    assert headers['X-Plugin'] == 'test'
    assert json.loads(body) == {'path': '/redfish/v1/TestPlugin'}


def test_platform_plugin_route_precedes_platform_provider(
        monkeypatch, tmp_path):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    class ConflictingProvider:
        def get_handler_for_path(self, path):
            return self

        def handle_get(self, path, query_params, cached_links):
            return 200, {'source': 'platform'}

    loader_module._loader_instance = None
    BaseRedfishHandler.cached_links = {}
    server = HTTPServer(
        ('127.0.0.1', 0),
        PlatformAwareRedfishHandler,
    )
    server.config = config
    server.service_manager = None
    server.platform_provider = ConflictingProvider()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, body = _request(
            server.server_address,
            'GET',
            '/redfish/v1/TestPlugin',
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        loader_module.shutdown_plugins()

    assert status == 206
    assert headers['X-Plugin'] == 'test'
    assert json.loads(body) == {'path': '/redfish/v1/TestPlugin'}


def test_configured_plugin_receives_http_patch_and_delete(
        monkeypatch, tmp_path):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    with _running_server(config) as address:
        patch_status, _, patch_body = _request(
            address,
            'PATCH',
            '/redfish/v1/TestPlugin/Resources/42',
            {'Enabled': True},
        )
        delete_status, _, delete_body = _request(
            address,
            'DELETE',
            '/redfish/v1/TestPlugin/Resources/42',
        )

    assert patch_status == 204
    assert patch_body == b''
    assert delete_status == 204
    assert delete_body == b''
    assert plugin.calls[:-1] == [
        (
            'PATCH',
            '/redfish/v1/TestPlugin/Resources/42',
            {'Enabled': True},
        ),
        ('DELETE', '/redfish/v1/TestPlugin/Resources/42'),
    ]


def test_plugin_binary_response_preserves_content_type(monkeypatch, tmp_path):
    plugin = _RoutingPlugin()

    def handle_get(path, query_params, cached_links):
        return 200, {'Content-Type': 'application/octet-stream'}, b'\x43\x50\x45\x52'

    plugin.handle_get = handle_get
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    with _running_server(config) as address:
        status, headers, body = _request(
            address,
            'GET',
            '/redfish/v1/TestPlugin/Attachment',
        )

    assert status == 200
    assert headers['Content-Type'] == 'application/octet-stream'
    assert body == b'\x43\x50\x45\x52'


def test_owned_path_with_unsupported_method_returns_405(
        monkeypatch, tmp_path):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    with _running_server(config) as address:
        status, _, body = _request(
            address,
            'DELETE',
            '/redfish/v1/TestPlugin',
        )

    assert status == 405
    assert body == b''


def test_unclaimed_get_falls_through_to_mockup(monkeypatch, tmp_path):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    resource_dir = tmp_path / 'redfish' / 'v1' / 'Static'
    resource_dir.mkdir(parents=True)
    (resource_dir / 'index.json').write_text(
        json.dumps({'Id': 'Static'}),
        encoding='utf-8',
    )
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    with _running_server(config) as address:
        status, _, body = _request(address, 'GET', '/redfish/v1/Static')

    assert status == 200
    assert json.loads(body)['Id'] == 'Static'
    assert plugin.calls == [('SHUTDOWN',)]


@pytest.mark.parametrize('extensions', [
    [],
    [{'name': 'test_plugin', 'enabled': False}],
])
def test_unconfigured_or_disabled_plugin_cannot_handle_requests(
        monkeypatch, tmp_path, extensions):
    plugin = _RoutingPlugin()
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=extensions,
    )

    with _running_server(config) as address:
        status, _, _ = _request(
            address,
            'POST',
            '/redfish/v1/TestPlugin/Actions/Run',
            {'value': 42},
        )

    assert status == 404
    assert plugin.calls == []


def test_plugin_failure_returns_explicit_500(monkeypatch, tmp_path):
    plugin = _RoutingPlugin()

    def fail(*args):
        raise RuntimeError('plugin failure')

    plugin.handle_get = fail
    _register_plugin(monkeypatch, 'test_plugin', plugin)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['test_plugin'],
    )

    with _running_server(config) as address:
        status, headers, body = _request(
            address,
            'GET',
            '/redfish/v1/TestPlugin',
        )

    assert status == 500
    assert headers['Content-Type'] == 'application/json'
    assert json.loads(body)['error']['code'] == 'Base.1.5.0.InternalError'


def test_system_reset_notifies_the_loaded_plugin_instance(
        monkeypatch, tmp_path):
    system_dir = tmp_path / 'redfish' / 'v1' / 'Systems' / 'System'
    system_dir.mkdir(parents=True)
    reset_path = (
        '/redfish/v1/Systems/System/Actions/ComputerSystem.Reset'
    )
    (system_dir / 'index.json').write_text(
        json.dumps({
            '@odata.id': '/redfish/v1/Systems/System',
            'Id': 'System',
            'PowerState': 'On',
            'Actions': {
                '#ComputerSystem.Reset': {
                    'target': reset_path,
                },
            },
        }),
        encoding='utf-8',
    )
    notifications = []

    class ResetPlugin:
        def initialize(self, server_config, plugin_config):
            return True

        def get_routes(self):
            return []

        def on_system_reset(self, system_id, reset_type):
            notifications.append((system_id, reset_type))

    _register_plugin(monkeypatch, 'reset_plugin', ResetPlugin())
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['reset_plugin'],
    )

    with _running_server(config) as address:
        status, _, body = _request(
            address,
            'POST',
            reset_path,
            {'ResetType': 'GracefulRestart'},
        )

    assert status == 204
    assert body == b''
    assert notifications == [('System', 'GracefulRestart')]


def test_plugin_reset_failure_does_not_reverse_successful_reset(
        monkeypatch, tmp_path):
    system_dir = tmp_path / 'redfish' / 'v1' / 'Systems' / 'System'
    system_dir.mkdir(parents=True)
    reset_path = (
        '/redfish/v1/Systems/System/Actions/ComputerSystem.Reset'
    )
    (system_dir / 'index.json').write_text(
        json.dumps({
            '@odata.id': '/redfish/v1/Systems/System',
            'Id': 'System',
            'PowerState': 'On',
            'Actions': {
                '#ComputerSystem.Reset': {'target': reset_path},
            },
        }),
        encoding='utf-8',
    )

    class FailingResetPlugin:
        def initialize(self, server_config, plugin_config):
            return True

        def get_routes(self):
            return []

        def on_system_reset(self, system_id, reset_type):
            raise RuntimeError('callback failure')

    _register_plugin(
        monkeypatch,
        'failing_reset_plugin',
        FailingResetPlugin(),
    )
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['failing_reset_plugin'],
    )

    with _running_server(config) as address:
        status, _, body = _request(
            address,
            'POST',
            reset_path,
            {'ResetType': 'GracefulRestart'},
        )

    assert status == 204
    assert body == b''


@pytest.mark.parametrize('extensions', [
    [],
    [{'name': 'telemetry', 'enabled': False}],
])
def test_unconfigured_or_disabled_telemetry_action_is_not_activated(
        tmp_path, extensions):
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=extensions,
    )

    with _running_server(config) as address:
        status, _, _ = _request(
            address,
            'POST',
            SUBMIT_TEST_METRIC_REPORT_PATH,
            {'MetricReportName': 'Test', 'MetricReportValues': []},
        )

    assert status == 404


def test_configured_telemetry_action_uses_plugin_end_to_end(tmp_path):
    subscriptions_dir = (
        tmp_path / 'redfish' / 'v1' / 'EventService' / 'Subscriptions'
    )
    subscriptions_dir.mkdir(parents=True)
    (subscriptions_dir / 'index.json').write_text(
        json.dumps({'Members': []}),
        encoding='utf-8',
    )
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['telemetry'],
    )
    payload = {
        'MetricReportName': 'TestReport',
        'MetricReportValues': [{
            'MetricId': 'Temperature',
            'MetricValue': '42',
            'Timestamp': '2026-10-01T20:00:00Z',
            'MetricProperty': '/redfish/v1/Systems/1#Temperature',
            'MetricDefinition': {
                '@odata.id': (
                    '/redfish/v1/TelemetryService/MetricDefinitions/'
                    'Temperature'
                )
            },
        }],
    }

    with _running_server(config) as address:
        status, _, body = _request(
            address,
            'POST',
            SUBMIT_TEST_METRIC_REPORT_PATH,
            payload,
        )

        report_path = str(
            tmp_path / 'redfish' / 'v1' / 'TelemetryService' /
            'MetricReports' / 'TestReport' / 'index.json'
        )
        report = BaseRedfishHandler.cached_links[report_path]

    assert status == 204
    assert body == b''
    assert report['Id'] == 'TestReport'
    assert report['MetricValues'] == payload['MetricReportValues']


def test_telemetry_post_uses_plugin_contract_and_shared_cache():
    received = {}

    class Handler:
        def handle_submit_test_metric_report(self, path, data, cached_links):
            received['path'] = path
            received['data'] = data
            received['cached_links'] = cached_links
            return 204

    plugin = TelemetryPlugin()
    plugin._enabled = True
    plugin._handler = Handler()
    cached_links = {}
    payload = {'MetricReportName': 'Test', 'MetricReportValues': []}

    result = plugin.handle_post(
        SUBMIT_TEST_METRIC_REPORT_PATH,
        payload,
        cached_links,
    )

    assert result == (204, {}, None)
    assert received == {
        'path': SUBMIT_TEST_METRIC_REPORT_PATH,
        'data': payload,
        'cached_links': cached_links,
    }
    assert received['cached_links'] is cached_links


def test_telemetry_rejects_unsupported_post_path():
    plugin = TelemetryPlugin()
    plugin._enabled = True
    plugin._handler = object()

    result = plugin.handle_post(
        '/redfish/v1/TelemetryService/MetricReports',
        {},
        {},
    )

    assert result == (405, {}, None)
