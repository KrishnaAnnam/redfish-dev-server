#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Telemetry Plugin Registration and Lifecycle

This module defines the Telemetry plugin's registration with the BMC Simulator core.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

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
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the plugin with configuration.
        
        Args:
            config: Server/platform configuration dict
            
        Returns:
            True if initialization successful
        """
        try:
            self._config = config
            
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
            logger.info("Telemetry Plugin shutdown complete")
            return True
        except Exception as e:
            logger.error(f"Error during Telemetry Plugin shutdown: {e}")
            return False
    
    def get_routes(self) -> List[str]:
        """Return list of URL paths this plugin handles."""
        return [
            "/redfish/v1/TelemetryService",
            "/redfish/v1/TelemetryService/",
            "/redfish/v1/TelemetryService/MetricReports",
            "/redfish/v1/TelemetryService/MetricReports/*",
            "/redfish/v1/TelemetryService/MetricReportDefinitions",
            "/redfish/v1/TelemetryService/MetricReportDefinitions/*",
            "/redfish/v1/TelemetryService/MetricDefinitions",
            "/redfish/v1/TelemetryService/MetricDefinitions/*",
            "/redfish/v1/TelemetryService/Triggers",
            "/redfish/v1/TelemetryService/Triggers/*",
            "/redfish/v1/TelemetryService/Actions/*",
        ]
    
    def handles_path(self, path: str) -> bool:
        """Check if this plugin handles the given path."""
        return path.startswith('/redfish/v1/TelemetryService')
    
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
        
        return self._handler.handle_telemetry(path, data, cached_links or {})
    
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
