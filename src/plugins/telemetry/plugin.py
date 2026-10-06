#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Telemetry Plugin Registration and Lifecycle

This module defines the Telemetry plugin's registration with the BMC Simulator core.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from ..contracts import PluginContext, PluginRoute

logger = logging.getLogger(__name__)

SUBMIT_TEST_METRIC_REPORT_PATH = (
    "/redfish/v1/TelemetryService/Actions/"
    "TelemetryService.SubmitTestMetricReport"
)

# Plugin metadata
PLUGIN_INFO = {
    "name": "telemetry",
    "version": "1.0.0",
    "description": "Telemetry Service Plugin for metric collection and reporting",
    "author": "BMC Simulator Team",
    "requires": [],
    "provides": [
        "TelemetryService",
        "MetricReports",
        "MetricReportDefinitions",
        "MetricDefinitions",
        "Triggers"
    ]
}


class TelemetryPlugin:
    """
    Telemetry Plugin class that manages plugin lifecycle and registration.
    
    This plugin provides Telemetry capabilities including:
    - Metric report collection and management
    - Metric report definitions
    - Telemetry data submission
    - Subscriber notification
    """
    
    def __init__(self):
        self._enabled = False
        self._handler = None
        self._config = None
        self._plugin_config = {}
        self._context = None
        logger.info("Telemetry Plugin initialized")
    
    @property
    def info(self) -> Dict[str, Any]:
        """Return plugin metadata"""
        return PLUGIN_INFO
    
    @property
    def enabled(self) -> bool:
        """Check if plugin is enabled"""
        return self._enabled
    
    @property
    def handler(self):
        """Get the Telemetry service handler instance"""
        return self._handler
    
    def initialize(self, config: Dict[str, Any],
                   plugin_config: Dict[str, Any] = None,
                   context: PluginContext = None) -> bool:
        """
        Initialize the plugin with configuration.
        
        Args:
            config: Shared server configuration
            plugin_config: Telemetry-specific configuration
            
        Returns:
            True if initialization successful
        """
        try:
            self._config = config
            self._plugin_config = dict(plugin_config or {})
            self._context = context
            
            from .telemetry_service import TelemetryServiceHandler
            
            self._handler = TelemetryServiceHandler(config)
            self._enabled = True
            
            logger.info(f"Telemetry Plugin v{PLUGIN_INFO['version']} initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Telemetry Plugin: {e}")
            return False
    
    def shutdown(self) -> bool:
        """Shutdown the plugin gracefully."""
        try:
            self._enabled = False
            self._handler = None
            self._context = None
            logger.info("Telemetry Plugin shutdown complete")
            return True
        except Exception as e:
            logger.error(f"Error during Telemetry Plugin shutdown: {e}")
            return False
    
    def get_routes(self) -> List[PluginRoute]:
        """Return the dynamic routes owned by this plugin."""
        return [
            PluginRoute(SUBMIT_TEST_METRIC_REPORT_PATH, {'POST'}),
        ]
    
    def handle_telemetry(self, path: str, data: Dict[str, Any],
                         cached_links: Dict[str, Any] = None) -> int:
        """
        Handle telemetry data submission.
        
        Args:
            path: URL path
            data: Telemetry data
            cached_links: Cached link data
            
        Returns:
            HTTP status code
        """
        if not self._enabled or not self._handler:
            return 503
        
        links = cached_links if cached_links is not None else {}
        return self._handler.handle_telemetry(path, data, links)

    def handle_post(self, path: str, data: Dict[str, Any],
                    cached_links: Dict[str, Any] = None
                    ) -> Tuple[int, Dict, Any]:
        """Handle TelemetryService POST requests through the plugin contract."""
        if not self._enabled or not self._handler:
            return 503, {}, None

        if path.rstrip('/') != SUBMIT_TEST_METRIC_REPORT_PATH:
            return 405, {}, None

        links = cached_links if cached_links is not None else {}
        status = self._handler.handle_submit_test_metric_report(
            path,
            data,
            links,
        )
        return status, {}, None
    
    def handle_submit_test_metric_report(self, path: str, data: Dict[str, Any],
                                          cached_links: Dict[str, Any] = None) -> int:
        """Handle SubmitTestMetricReport action."""
        if not self._enabled or not self._handler:
            return 503
        
        return self._handler.handle_submit_test_metric_report(path, data, cached_links or {})


# Singleton instance
_plugin_instance: Optional[TelemetryPlugin] = None


def get_plugin() -> TelemetryPlugin:
    """Get or create the singleton Telemetry plugin instance."""
    global _plugin_instance
    if _plugin_instance is None:
        _plugin_instance = TelemetryPlugin()
    return _plugin_instance


def register_plugin() -> Dict[str, Any]:
    """Register this plugin with the plugin system."""
    return {
        "info": PLUGIN_INFO,
        "plugin_class": TelemetryPlugin,
        "get_instance": get_plugin
    }
