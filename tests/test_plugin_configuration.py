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
    PluginSpec,
    normalize_plugin_specs,
)


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


def test_normalizes_legacy_structured_and_disabled_entries(monkeypatch):
    monkeypatch.setitem(
        loader_module.AVAILABLE_PLUGINS,
        'test_plugin',
        'tests.fake_plugin',
    )

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


def test_rejects_unknown_plugins():
    with pytest.raises(
        PluginConfigurationError,
        match='Unknown plugin: missing',
    ):
        normalize_plugin_specs(['missing'])


def test_loads_only_configured_plugins_and_delivers_plugin_config(
        monkeypatch, tmp_path):
    initialized = {}

    class FakePlugin:
        def initialize(self, server_config, plugin_config):
            initialized['server_config'] = server_config
            initialized['plugin_config'] = plugin_config
            return True

    fake_module = types.ModuleType('tests.fake_plugin')
    fake_module.get_plugin = FakePlugin
    monkeypatch.setitem(sys.modules, 'tests.fake_plugin', fake_module)
    monkeypatch.setitem(
        loader_module.AVAILABLE_PLUGINS,
        'test_plugin',
        'tests.fake_plugin',
    )
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
    assert initialized == {
        'server_config': config,
        'plugin_config': {'sample_rate': 30},
    }
    assert plugin_loader.get_plugin_config('test_plugin') == {
        'sample_rate': 30,
    }


def test_legacy_plugin_initializer_remains_supported(monkeypatch, tmp_path):
    initialized = {}

    class LegacyPlugin:
        def initialize(self, server_config):
            initialized['server_config'] = server_config
            return True

    fake_module = types.ModuleType('tests.legacy_plugin')
    fake_module.get_plugin = LegacyPlugin
    monkeypatch.setitem(sys.modules, 'tests.legacy_plugin', fake_module)
    monkeypatch.setitem(
        loader_module.AVAILABLE_PLUGINS,
        'legacy_plugin',
        'tests.legacy_plugin',
    )
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
