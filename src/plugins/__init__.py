# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
# Plugins Package
"""
BMC Simulator Plugin System

Plugins extend the simulator with optional functionality that can be 
enabled/disabled per platform configuration.

Available Plugins:
- ras: Reliability, Availability, Serviceability (CPER/CPAD handling)
- telemetry: Telemetry Service (metric collection and reporting)

Usage:
    from src.plugins import get_plugin_loader, load_plugins_from_config
    
    # Load plugins based on config
    loader = load_plugins_from_config(server_config)
    
    # Or manually load specific plugins
    loader = get_plugin_loader(config)
    loader.load_plugins(['ras', 'telemetry'])
    
    # Route requests through plugins
    plugin = loader.get_plugin_for_path(path)
    if plugin:
        status, headers, body = plugin.handle_get(path)
"""

from .loader import (
    PluginLoader,
    get_plugin_loader,
    load_plugins_from_config,
    AVAILABLE_PLUGINS
)

__all__ = [
    'PluginLoader',
    'get_plugin_loader', 
    'load_plugins_from_config',
    'AVAILABLE_PLUGINS'
]