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
    loader.load_plugins(['ras', 'telemetry'])
    
    # Check if a plugin handles a path
    plugin = loader.get_plugin_for_path('/redfish/v1/RASService/Endpoints')
    if plugin:
        status, headers, body = plugin.handle_get(path)
"""

import logging
import importlib
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Registry of available plugins
AVAILABLE_PLUGINS = {
    'ras': 'src.plugins.ras',
    'telemetry': 'src.plugins.telemetry',
    # Future plugins:
    # 'storage': 'src.plugins.storage',
    # 'network': 'src.plugins.network',
}


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
    
    def load_plugin(self, plugin_name: str) -> bool:
        """
        Load a single plugin by name.
        
        Args:
            plugin_name: Name of plugin to load
            
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
                if not plugin.initialize(self._config):
                    logger.error(f"Plugin '{plugin_name}' initialization failed")
                    return False
            
            self._loaded_plugins[plugin_name] = plugin
            self._enabled_plugins.append(plugin_name)
            
            logger.info(f"Plugin '{plugin_name}' loaded successfully")
            return True
            
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
    
    # Get list of plugins to load from config
    extensions = []
    
    # Check various config locations for extensions list
    if hasattr(config, 'extensions'):
        extensions = config.extensions
    elif isinstance(config, dict):
        extensions = config.get('extensions', [])
        # Also check nested platform config
        if 'platform' in config:
            extensions = config['platform'].get('extensions', extensions)
    
    if extensions:
        logger.info(f"Loading plugins from config: {extensions}")
        loader.load_plugins(extensions)
    else:
        logger.debug("No plugins specified in configuration")
    
    return loader
