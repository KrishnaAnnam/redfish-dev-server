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
    
    response = loader.handle_get(
        '/redfish/v1/MyService',
        query_params={},
        cached_links={},
    )
"""

import logging
import importlib
import inspect
import pkgutil
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .contracts import PluginContext, PluginRoute

logger = logging.getLogger(__name__)


class PluginConfigurationError(ValueError):
    """Raised when configured plugin entries are invalid."""


class PluginLoadError(RuntimeError):
    """Raised when a configured plugin cannot be loaded."""


class PluginRouteConflictError(PluginConfigurationError):
    """Raised when multiple plugins claim the same route and method."""


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
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name):
            raise PluginConfigurationError(
                f"Extension entry {index} has invalid plugin name '{name}'"
            )

        if name in configured_names:
            raise PluginConfigurationError(
                f"Plugin '{name}' is configured more than once"
            )
        configured_names.add(name)

        if not enabled:
            continue

        normalized.append(PluginSpec(name=name, config=dict(plugin_config)))

    return normalized


def override_plugin_config(
        extensions: Any,
        plugin_name: str,
        overrides: Dict[str, Any]) -> List[Any]:
    """Return validated extensions with one enabled plugin config updated."""
    normalize_plugin_specs(extensions)
    updated = []
    found = False
    for entry in extensions:
        if entry == plugin_name:
            updated.append({
                'name': plugin_name,
                'enabled': True,
                'config': dict(overrides),
            })
            found = True
            continue
        if isinstance(entry, dict) and entry.get('name') == plugin_name:
            if not entry.get('enabled', True):
                raise PluginConfigurationError(
                    f"Plugin '{plugin_name}' is disabled")
            replacement = dict(entry)
            plugin_config = dict(replacement.get('config', {}))
            plugin_config.update(overrides)
            replacement['config'] = plugin_config
            updated.append(replacement)
            found = True
            continue
        updated.append(entry)
    if not found:
        raise PluginConfigurationError(
            f"Plugin '{plugin_name}' is not configured")
    return updated


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
        self._routes: List[Tuple[str, PluginRoute]] = []
        self._event_service = None
        self._event_cache: Dict[str, Any] = {}
        self._context = PluginContext(config, self._publish_event)
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
        plugin_dir = Path(__file__).resolve().parent
        return sorted(
            module.name
            for module in pkgutil.iter_modules([str(plugin_dir)])
            if module.ispkg and not module.name.startswith('_')
        )

    def _initialize_plugin(self, plugin: Any, plugin_name: str,
                           plugin_config: Dict[str, Any]) -> bool:
        """Initialize a plugin without breaking the legacy one-argument API."""
        initialize = plugin.initialize
        signature = inspect.signature(initialize)
        parameters = tuple(signature.parameters.values())
        positional_parameters = tuple(
            parameter
            for parameter in parameters
            if parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        accepts_variable_arguments = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        )

        if len(positional_parameters) >= 3 or accepts_variable_arguments:
            return initialize(self._config, plugin_config, self._context)
        if len(positional_parameters) >= 2:
            return initialize(self._config, plugin_config)
        if plugin_config:
            raise PluginConfigurationError(
                f"Plugin '{plugin_name}' does not accept plugin-specific config"
            )
        return initialize(self._config)

    def _register_routes(self, plugin_name: str, plugin: Any) -> None:
        """Validate and register all routes declared by a plugin."""
        if not hasattr(plugin, 'get_routes'):
            raise PluginConfigurationError(
                f"Plugin '{plugin_name}' does not declare get_routes()"
            )

        routes = plugin.get_routes()
        if not isinstance(routes, (list, tuple)):
            raise PluginConfigurationError(
                f"Plugin '{plugin_name}' get_routes() must return a list"
            )

        pending_routes = []
        for route in routes:
            if not isinstance(route, PluginRoute):
                raise PluginConfigurationError(
                    f"Plugin '{plugin_name}' returned an invalid route declaration"
                )

            for method in route.methods:
                handler_name = f'handle_{method.lower()}'
                if not callable(getattr(plugin, handler_name, None)):
                    raise PluginConfigurationError(
                        f"Plugin '{plugin_name}' route {route.path} declares "
                        f"{method} without {handler_name}()"
                    )

                for registered_name, registered_route in (
                    self._routes + pending_routes
                ):
                    if (
                        registered_route.conflict_key == route.conflict_key
                        and method in registered_route.methods
                    ):
                        raise PluginRouteConflictError(
                            f"Plugin route conflict for {method} {route.path}: "
                            f"'{registered_name}' and '{plugin_name}'"
                        )

            pending_routes.append((plugin_name, route))

        self._routes.extend(pending_routes)
        self._routes.sort(
            key=lambda registration: registration[1].specificity,
            reverse=True,
        )

    def _unregister_routes(self, plugin_name: str) -> None:
        self._routes = [
            registration
            for registration in self._routes
            if registration[0] != plugin_name
        ]

    def _publish_event(self, event: Dict[str, Any]) -> int:
        """Publish an event through the simulator's existing EventService."""
        if self._event_service is None:
            from ..services.event_service import EventServiceHandler
            self._event_service = EventServiceHandler(self._config)

        return self._event_service.handle_eventing(
            '/redfish/v1/EventService/Actions/EventService.SubmitTestEvent',
            event,
            self._event_cache,
        )
    
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
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', plugin_name):
            raise PluginConfigurationError(
                f"Invalid plugin name '{plugin_name}'"
            )
        
        try:
            module_path = f'src.plugins.{plugin_name}'
            module = importlib.import_module(module_path)
            
            if not callable(getattr(module, 'get_plugin', None)):
                raise PluginConfigurationError(
                    f"Plugin '{plugin_name}' has no get_plugin() function"
                )
            plugin = module.get_plugin()
            
            if not callable(getattr(plugin, 'initialize', None)):
                raise PluginConfigurationError(
                    f"Plugin '{plugin_name}' has no initialize() method"
                )
            if not self._initialize_plugin(
                    plugin, plugin_name, plugin_config or {}):
                logger.error(f"Plugin '{plugin_name}' initialization failed")
                return False

            try:
                self._register_routes(plugin_name, plugin)
            except Exception:
                if callable(getattr(plugin, 'shutdown', None)):
                    try:
                        plugin.shutdown()
                    except Exception:
                        logger.exception(
                            "Plugin '%s' failed while rolling back initialization",
                            plugin_name,
                        )
                raise
            
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
        
        plugin = self._loaded_plugins[plugin_name]
        success = True
        try:
            if callable(getattr(plugin, 'shutdown', None)):
                success = plugin.shutdown() is not False
        except Exception:
            logger.exception("Error shutting down plugin '%s'", plugin_name)
            success = False
        finally:
            self._unregister_routes(plugin_name)
            del self._loaded_plugins[plugin_name]
            self._enabled_plugins.remove(plugin_name)
            self._plugin_configs.pop(plugin_name, None)

        logger.info(f"Plugin '{plugin_name}' unloaded")
        return success

    def shutdown(self) -> bool:
        """Unload every plugin and release shared plugin resources."""
        success = True
        for plugin_name in list(reversed(self._enabled_plugins)):
            success = self.unload_plugin(plugin_name) and success
        self._event_service = None
        self._event_cache.clear()
        return success
    
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
    
    def get_plugin_for_path(
        self,
        path: str,
        method: Optional[str] = None,
    ) -> Optional[Any]:
        """Find the plugin that owns a path and optional HTTP method."""
        normalized_method = method.upper() if method else None
        for plugin_name, route in self._routes:
            if (
                route.matches(path)
                and (
                    normalized_method is None
                    or normalized_method in route.methods
                )
            ):
                return self._loaded_plugins.get(plugin_name)
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

    def _handle_request(
        self,
        method: str,
        path: str,
        *handler_args: Any,
    ) -> Optional[Tuple[int, Dict, Any]]:
        plugin = self.get_plugin_for_path(path, method)
        if plugin is not None:
            handler = getattr(plugin, f'handle_{method.lower()}')
            return handler(path, *handler_args)

        if self.is_plugin_path(path):
            return 405, {}, None
        return None
    
    def handle_get(self, path: str, query_params: Dict[str, Any] = None,
                   cached_links: Dict[str, Any] = None
                   ) -> Optional[Tuple[int, Dict, Any]]:
        """
        Route GET request to appropriate plugin.
        
        Args:
            path: URL path
            query_params: Query parameters
            cached_links: Cached link data
            
        Returns:
            Tuple of (status, headers, body) or None if no plugin handles path
        """
        return self._handle_request(
            'GET',
            path,
            query_params,
            cached_links,
        )
    
    def handle_post(self, path: str, data: Dict[str, Any],
                    cached_links: Dict[str, Any] = None
                    ) -> Optional[Tuple[int, Dict, Any]]:
        """
        Route POST request to appropriate plugin.
        
        Args:
            path: URL path
            data: Request body
            cached_links: Cached link data
            
        Returns:
            Tuple of (status, headers, body) or None if no plugin handles path
        """
        return self._handle_request(
            'POST',
            path,
            data,
            cached_links,
        )

    def handle_patch(self, path: str, data: Dict[str, Any],
                     cached_links: Dict[str, Any] = None
                     ) -> Optional[Tuple[int, Dict, Any]]:
        """Route PATCH requests to the plugin that owns the path."""
        return self._handle_request(
            'PATCH',
            path,
            data,
            cached_links,
        )

    def handle_delete(self, path: str,
                      cached_links: Dict[str, Any] = None
                      ) -> Optional[Tuple[int, Dict, Any]]:
        """Route DELETE requests to the plugin that owns the path."""
        return self._handle_request(
            'DELETE',
            path,
            cached_links,
        )

    def notify_system_reset(self, system_id: str, reset_type: str) -> int:
        """Notify interested plugins after a successful system reset."""
        notified = 0
        for plugin_name, plugin in self._loaded_plugins.items():
            callback = getattr(plugin, 'on_system_reset', None)
            if not callable(callback):
                continue
            try:
                callback(system_id, reset_type)
                notified += 1
            except Exception:
                logger.exception(
                    "Plugin '%s' failed during system reset notification",
                    plugin_name,
                )
        return notified
    
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


def shutdown_plugins() -> bool:
    """Shutdown the process-wide plugin loader, if it was initialized."""
    global _loader_instance
    if _loader_instance is None:
        return True
    success = _loader_instance.shutdown()
    _loader_instance = None
    return success
