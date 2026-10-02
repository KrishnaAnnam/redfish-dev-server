# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
# Plugins Package
"""
BMC Simulator Plugin System

Plugins extend the simulator with optional functionality that can be 
enabled/disabled per platform configuration.

Usage:
    from src.plugins import get_plugin_loader, load_plugins_from_config
    
    # Load plugins based on config
    loader = load_plugins_from_config(server_config)
    
    # Or manually load specific plugins
    loader = get_plugin_loader(config)
    loader.load_plugins(['telemetry'])
    
    response = loader.handle_get(path, query_params, cached_links)
"""

from .loader import (
    PluginLoader,
    get_plugin_loader,
    load_plugins_from_config,
    shutdown_plugins,
)
from .contracts import PluginContext, PluginRoute

__all__ = [
    'PluginLoader',
    'PluginContext',
    'PluginRoute',
    'get_plugin_loader', 
    'load_plugins_from_config',
    'shutdown_plugins',
]