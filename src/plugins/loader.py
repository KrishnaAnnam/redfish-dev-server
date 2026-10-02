#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Plugin Loader for BMC Simulator

This module provides the plugin loading and management infrastructure.
Plugins are discovered and loaded based on platform configuration.

Usage:
    from src.plugins.loader import PluginLoader
    
    loader = PluginLoader(config)
    loader.load_plugins(['telemetry'])
    
    # Check if a plugin handles a path
    plugin = loader.get_plugin_for_path('/redfish/v1/RASService/Endpoints')
    if plugin:
        status, headers, body = plugin.handle_get(path)
"""

import logging
import importlib
import inspect
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Registry of available plugins
AVAILABLE_PLUGINS = {
    'telemetry': 'src.plugins.telemetry',
    # 'ras': 'src.plugins.ras',
    # Future plugins:
    # 'storage': 'src.plugins.storage',
    # 'network': 'src.plugins.network',
}


class PluginConfigurationError(ValueError):
    """Raised when configured plugin entries are invalid."""


class PluginLoadError(RuntimeError):
    """Raised when a configured plugin cannot be loaded."""


@dataclass(frozen=True)
class PluginSpec:
    """Normalized configuration for one enabled plugin."""

    name: str
    config: Dict[str, Any] = field(default_factory=dict)


def normalize_plugin_specs(extensions: Any) -> List[PluginSpec]:
    """Validate and normalize legacy and structured plugin entries."""
    if extensions is None:
        return []
    if not isinstance(extensions, list):
        raise PluginConfigurationError("'extensions' must be a list")

    normalized = []
    configured_names = set()
    allowed_keys = {'name', 'enabled', 'config'}

    for index, entry in enumerate(extensions):
        if isinstance(entry, str):
            name = entry
            enabled = True
            plugin_config = {}
        elif isinstance(entry, dict):
            unsupported_keys = set(entry) - allowed_keys
            if unsupported_keys:
                keys = ', '.join(sorted(unsupported_keys))
                raise PluginConfigurationError(
                    f"Extension entry {index} contains unsupported keys: {keys}"
                )

            name = entry.get('name')
            enabled = entry.get('enabled', True)
            plugin_config = entry.get('config', {})

            if not isinstance(enabled, bool):
                raise PluginConfigurationError(
                    f"Extension entry {index} field 'enabled' must be a boolean"
                )
            if not isinstance(plugin_config, dict):
                raise PluginConfigurationError(
                    f"Extension entry {index} field 'config' must be an object"
                )
        else:
            raise PluginConfigurationError(
                f"Extension entry {index} must be a plugin name or object"
            )

        if not isinstance(name, str) or not name.strip():
            raise PluginConfigurationError(
                f"Extension entry {index} requires a non-empty string 'name'"
            )
        name = name.strip()

        if name in configured_names:
            raise PluginConfigurationError(
                f"Plugin '{name}' is configured more than once"
            )
        configured_names.add(name)

        if not enabled:
            continue

        if name not in AVAILABLE_PLUGINS:
            raise PluginConfigurationError(f"Unknown plugin: {name}")

        normalized.append(PluginSpec(name=name, config=dict(plugin_config)))

    return normalized


class PluginLoader:
    """
    Plugin loader and manager for BMC Simulator.
    
    Handles discovery, loading, and lifecycle of plugins.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the plugin loader.
        
        Args:
            config: Server/platform configuration
        """
        self._config = config or {}
        self._loaded_plugins: Dict[str, Any] = {}
        self._enabled_plugins: List[str] = []
        self._plugin_configs: Dict[str, Dict[str, Any]] = {}
        logger.info("Plugin Loader initialized")
    
    @property
    def loaded_plugins(self) -> Dict[str, Any]:
        """Return dict of loaded plugins"""
        return self._loaded_plugins
    
    @property
    def enabled_plugins(self) -> List[str]:
        """Return list of enabled plugin names"""
        return self._enabled_plugins
    
    def discover_plugins(self) -> List[str]:
        """
        Discover available plugins.
        
        Returns:
            List of available plugin names
        """
        return list(AVAILABLE_PLUGINS.keys())

    def _initialize_plugin(self, plugin: Any, plugin_name: str,
                           plugin_config: Dict[str, Any]) -> bool:
        """Initialize a plugin without breaking the legacy one-argument API."""
        initialize = plugin.initialize
        parameters = inspect.signature(initialize).parameters.values()
        accepts_plugin_config = (
            len(inspect.signature(initialize).parameters) >= 2 or
            any(parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ) for parameter in parameters)
        )

        if accepts_plugin_config:
            return initialize(self._config, plugin_config)
        if plugin_config:
            raise PluginConfigurationError(
                f"Plugin '{plugin_name}' does not accept plugin-specific config"
            )
        return initialize(self._config)
    
    def load_plugin(self, plugin_name: str,
                    plugin_config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Load a single plugin by name.
        
        Args:
            plugin_name: Name of plugin to load
            plugin_config: Configuration owned by this plugin
            
        Returns:
            True if plugin loaded successfully
        """
        if plugin_name in self._loaded_plugins:
            logger.debug(f"Plugin '{plugin_name}' already loaded")
            return True
        
        if plugin_name not in AVAILABLE_PLUGINS:
            logger.warning(f"Unknown plugin: {plugin_name}")
            return False
        
        try:
            # Import the plugin module
            module_path = AVAILABLE_PLUGINS[plugin_name]
            module = importlib.import_module(module_path)
            
            # Get the plugin instance
            if hasattr(module, 'get_plugin'):
                plugin = module.get_plugin()
            elif hasattr(module, 'RASPlugin'):
                # Fallback for RAS plugin
                plugin = module.RASPlugin()
            else:
                logger.error(f"Plugin '{plugin_name}' has no get_plugin() function")
                return False
            
            # Initialize the plugin
            if hasattr(plugin, 'initialize'):
                if not self._initialize_plugin(
                        plugin, plugin_name, plugin_config or {}):
                    logger.error(f"Plugin '{plugin_name}' initialization failed")
                    return False
            
            self._loaded_plugins[plugin_name] = plugin
            self._enabled_plugins.append(plugin_name)
            self._plugin_configs[plugin_name] = dict(plugin_config or {})
            
            logger.info(f"Plugin '{plugin_name}' loaded successfully")
            return True
            
        except PluginConfigurationError:
            raise
        except ImportError as e:
            logger.error(f"Failed to import plugin '{plugin_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading plugin '{plugin_name}': {e}")
            return False
    
    def load_plugins(self, plugin_names: List[str]) -> Dict[str, bool]:
        """
        Load multiple plugins.
        
        Args:
            plugin_names: List of plugin names to load
            
        Returns:
            Dict mapping plugin name to load success status
        """
        results = {}
        for name in plugin_names:
            results[name] = self.load_plugin(name)
        return results
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of plugin to unload
            
        Returns:
            True if plugin unloaded successfully
        """
        if plugin_name not in self._loaded_plugins:
            logger.debug(f"Plugin '{plugin_name}' not loaded")
            return True
        
        try:
            plugin = self._loaded_plugins[plugin_name]
            
            # Shutdown the plugin
            if hasattr(plugin, 'shutdown'):
                plugin.shutdown()
            
            del self._loaded_plugins[plugin_name]
            self._enabled_plugins.remove(plugin_name)
            self._plugin_configs.pop(plugin_name, None)
            
            logger.info(f"Plugin '{plugin_name}' unloaded")
            return True
            
        except Exception as e:
            logger.error(f"Error unloading plugin '{plugin_name}': {e}")
            return False
    
    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """
        Get a loaded plugin by name.
        
        Args:
            plugin_name: Name of plugin
            
        Returns:
            Plugin instance or None
        """
        return self._loaded_plugins.get(plugin_name)

    def get_plugin_config(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Return a copy of a loaded plugin's configuration."""
        config = self._plugin_configs.get(plugin_name)
        return dict(config) if config is not None else None
    
    def get_plugin_for_path(self, path: str) -> Optional[Any]:
        """
        Find the plugin that handles a given path.
        
        Args:
            path: URL path to check
            
        Returns:
            Plugin instance that handles path, or None
        """
        for plugin in self._loaded_plugins.values():
            if hasattr(plugin, 'handles_path') and plugin.handles_path(path):
                return plugin
        return None
    
    def is_plugin_path(self, path: str) -> bool:
        """
        Check if any loaded plugin handles this path.
        
        Args:
            path: URL path to check
            
        Returns:
            True if a plugin handles this path
        """
        return self.get_plugin_for_path(path) is not None
    
    def handle_get(self, path: str, query_params: Dict[str, Any] = None,
                   cached_links: Dict[str, Any] = None) -> Optional[Tuple[int, Dict, Dict]]:
        """
        Route GET request to appropriate plugin.
        
        Args:
            path: URL path
            query_params: Query parameters
            cached_links: Cached link data
            
        Returns:
            Tuple of (status, headers, body) or None if no plugin handles path
        """
        plugin = self.get_plugin_for_path(path)
        if plugin and hasattr(plugin, 'handle_get'):
            return plugin.handle_get(path, query_params, cached_links)
        return None
    
    def handle_post(self, path: str, data: Dict[str, Any],
                    cached_links: Dict[str, Any] = None) -> Optional[Tuple[int, Dict, Dict]]:
        """
        Route POST request to appropriate plugin.
        
        Args:
            path: URL path
            data: Request body
            cached_links: Cached link data
            
        Returns:
            Tuple of (status, headers, body) or None if no plugin handles path
        """
        plugin = self.get_plugin_for_path(path)
        if plugin and hasattr(plugin, 'handle_post'):
            return plugin.handle_post(path, data, cached_links)
        return None
    
    def get_all_routes(self) -> Dict[str, List[str]]:
        """
        Get all routes from all loaded plugins.
        
        Returns:
            Dict mapping plugin name to list of routes
        """
        routes = {}
        for name, plugin in self._loaded_plugins.items():
            if hasattr(plugin, 'get_routes'):
                routes[name] = plugin.get_routes()
        return routes


# Global plugin loader instance
_loader_instance: Optional[PluginLoader] = None


def get_plugin_loader(config: Dict[str, Any] = None) -> PluginLoader:
    """
    Get or create the global plugin loader instance.
    
    Args:
        config: Configuration (used on first call)
        
    Returns:
        PluginLoader instance
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = PluginLoader(config)
    return _loader_instance


def load_plugins_from_config(config: Dict[str, Any]) -> PluginLoader:
    """
    Load plugins based on platform configuration.
    
    Args:
        config: Platform/server configuration containing 'extensions' list
        
    Returns:
        Configured PluginLoader instance
    """
    loader = get_plugin_loader(config)
    
    extensions = []

    if hasattr(config, 'extensions'):
        extensions = config.extensions
    elif isinstance(config, dict):
        extensions = config.get('extensions', [])
        if 'platform' in config:
            extensions = config['platform'].get('extensions', extensions)

    plugin_specs = normalize_plugin_specs(extensions)
    if not plugin_specs:
        logger.debug("No plugins specified in configuration")
        return loader

    logger.info(
        "Loading plugins from config: %s",
        [plugin_spec.name for plugin_spec in plugin_specs]
    )
    for plugin_spec in plugin_specs:
        if not loader.load_plugin(plugin_spec.name, plugin_spec.config):
            raise PluginLoadError(
                f"Configured plugin '{plugin_spec.name}' failed to load"
            )

    return loader
