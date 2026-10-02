#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

import json
import sys
import types

import pytest

from src.config.settings import ServerConfig
from src.core.interfaces import PlatformType
from src.core.platform_config import PlatformConfig, load_platform_config
from src.plugins import loader as loader_module
from src.plugins.loader import (
    PluginConfigurationError,
    PluginLoadError,
    PluginLoader,
    PluginRouteConflictError,
    PluginSpec,
    normalize_plugin_specs,
)
from src.plugins import PluginRoute


def _register_plugin(monkeypatch, name, plugin_factory):
    module_name = f'src.plugins.{name}'
    module = types.ModuleType(module_name)
    module.get_plugin = plugin_factory
    monkeypatch.setitem(sys.modules, module_name, module)


def test_platform_config_preserves_extensions():
    extensions = [
        'telemetry',
        {
            'name': 'test_plugin',
            'enabled': True,
            'config': {'sample_rate': 30},
        },
    ]
    config = PlatformConfig(
        platform_id='test',
        platform_type=PlatformType.GENERIC,
        display_name='Test Platform',
        extensions=extensions,
    )

    restored = PlatformConfig.from_dict(config.to_dict())

    assert restored.extensions == extensions


def test_normalizes_legacy_structured_and_disabled_entries():
    specs = normalize_plugin_specs([
        'telemetry',
        {
            'name': 'test_plugin',
            'config': {'sample_rate': 30},
        },
        {
            'name': 'disabled_plugin',
            'enabled': False,
        },
    ])

    assert specs == [
        PluginSpec(name='telemetry', config={}),
        PluginSpec(name='test_plugin', config={'sample_rate': 30}),
    ]


@pytest.mark.parametrize('extensions', [
    'telemetry',
    [42],
    [{'name': ''}],
    [{'name': 'telemetry', 'enabled': 'yes'}],
    [{'name': 'telemetry', 'config': []}],
    [{'name': 'telemetry', 'unexpected': True}],
    ['invalid-plugin-name'],
])
def test_rejects_malformed_entries(extensions):
    with pytest.raises(PluginConfigurationError):
        normalize_plugin_specs(extensions)


def test_rejects_duplicate_entries():
    with pytest.raises(
        PluginConfigurationError,
        match="Plugin 'telemetry' is configured more than once",
    ):
        normalize_plugin_specs([
            'telemetry',
            {'name': 'telemetry', 'enabled': False},
        ])


def test_unknown_plugins_fail_during_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(loader_module, '_loader_instance', None)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        extensions=['missing'],
    )

    with pytest.raises(
        PluginLoadError,
        match="Configured plugin 'missing' failed to load",
    ):
        loader_module.load_plugins_from_config(config)


def test_loads_only_configured_plugins_and_delivers_plugin_config(
        monkeypatch, tmp_path):
    initialized = {}

    class FakePlugin:
        def initialize(self, server_config, plugin_config, context):
            initialized['server_config'] = server_config
            initialized['plugin_config'] = plugin_config
            initialized['context'] = context
            return True

        def get_routes(self):
            return []

    _register_plugin(monkeypatch, 'test_plugin', FakePlugin)
    monkeypatch.setattr(loader_module, '_loader_instance', None)

    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        short_form=True,
        extensions=[{
            'name': 'test_plugin',
            'config': {'sample_rate': 30},
        }],
    )

    plugin_loader = loader_module.load_plugins_from_config(config)

    assert plugin_loader.enabled_plugins == ['test_plugin']
    assert initialized['server_config'] is config
    assert initialized['plugin_config'] == {'sample_rate': 30}
    assert initialized['context'].server_config is config
    assert plugin_loader.get_plugin_config('test_plugin') == {
        'sample_rate': 30,
    }


def test_legacy_plugin_initializer_remains_supported(monkeypatch, tmp_path):
    initialized = {}

    class LegacyPlugin:
        def initialize(self, server_config):
            initialized['server_config'] = server_config
            return True

        def get_routes(self):
            return []

    _register_plugin(monkeypatch, 'legacy_plugin', LegacyPlugin)
    monkeypatch.setattr(loader_module, '_loader_instance', None)

    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        short_form=True,
        extensions=['legacy_plugin'],
    )

    plugin_loader = loader_module.load_plugins_from_config(config)

    assert plugin_loader.enabled_plugins == ['legacy_plugin']
    assert initialized['server_config'] is config


def test_empty_configuration_does_not_load_default_plugins(
        monkeypatch, tmp_path):
    monkeypatch.setattr(loader_module, '_loader_instance', None)
    config = ServerConfig(
        mock_dir_path=str(tmp_path),
        short_form=True,
    )

    plugin_loader = loader_module.load_plugins_from_config(config)

    assert plugin_loader.enabled_plugins == []


def test_loads_extensions_from_platform_config_file(tmp_path):
    extensions = [{
        'name': 'telemetry',
        'config': {'sample_rate': 30},
    }]
    platform_config = {
        'platform_id': 'test',
        'platform_type': 'generic',
        'display_name': 'Test Platform',
        'extensions': extensions,
    }
    (tmp_path / 'platform_config.json').write_text(
        json.dumps(platform_config),
        encoding='utf-8',
    )

    loaded_config = load_platform_config(
        str(tmp_path / 'platform_config.json')
    )

    assert loaded_config.extensions == extensions


def test_rejects_route_conflicts_at_plugin_load(monkeypatch, tmp_path):
    class FirstPlugin:
        def initialize(self, server_config, plugin_config):
            return True

        def shutdown(self):
            return True

        def get_routes(self):
            return [PluginRoute('/redfish/v1/Shared', {'GET'})]

        def handle_get(self, path, query_params, cached_links):
            return 200, {}, {}

    class SecondPlugin(FirstPlugin):
        pass

    _register_plugin(monkeypatch, 'first_plugin', FirstPlugin)
    _register_plugin(monkeypatch, 'second_plugin', SecondPlugin)

    loader = PluginLoader(ServerConfig(mock_dir_path=str(tmp_path)))
    assert loader.load_plugin('first_plugin')

    with pytest.raises(
        PluginRouteConflictError,
        match='Plugin route conflict for GET /redfish/v1/Shared',
    ):
        loader.load_plugin('second_plugin')


def test_rejects_equivalent_parameterized_route_conflicts(
        monkeypatch, tmp_path):
    class FirstPlugin:
        def initialize(self, server_config, plugin_config):
            return True

        def get_routes(self):
            return [PluginRoute('/redfish/v1/Shared/{EntryId}', {'GET'})]

        def handle_get(self, path, query_params, cached_links):
            return 200, {}, {}

    class SecondPlugin(FirstPlugin):
        def get_routes(self):
            return [PluginRoute('/redfish/v1/Shared/*', {'GET'})]

    _register_plugin(monkeypatch, 'first_plugin', FirstPlugin)
    _register_plugin(monkeypatch, 'second_plugin', SecondPlugin)
    loader = PluginLoader(ServerConfig(mock_dir_path=str(tmp_path)))

    assert loader.load_plugin('first_plugin')
    with pytest.raises(PluginRouteConflictError):
        loader.load_plugin('second_plugin')


def test_plugin_context_publishes_through_core_event_service(
        monkeypatch, tmp_path):
    subscriptions = (
        tmp_path / 'redfish' / 'v1' / 'EventService' / 'Subscriptions'
    )
    subscriptions.mkdir(parents=True)
    (subscriptions / 'index.json').write_text(
        json.dumps({'Members': [], 'Members@odata.count': 0}),
        encoding='utf-8',
    )
    received = {}

    class EventPlugin:
        def initialize(self, server_config, plugin_config, context):
            received['context'] = context
            return True

        def get_routes(self):
            return []

    _register_plugin(monkeypatch, 'event_plugin', EventPlugin)
    loader = PluginLoader(ServerConfig(mock_dir_path=str(tmp_path)))

    assert loader.load_plugin('event_plugin')
    status = received['context'].publish_event({
        'MessageId': 'Test.1.0.Event',
        'Message': 'Plugin event',
    })

    assert status == 200
