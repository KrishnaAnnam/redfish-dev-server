#!/usr/bin/env python3
"""
RAS Plugin Registration and Lifecycle

This module defines the RAS plugin's registration with the BMC Simulator core.
It implements the plugin interface allowing the RAS service to be optionally
loaded based on platform configuration.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from ..contracts import PluginContext, PluginRoute

logger = logging.getLogger(__name__)

RAS_SERVICE_PATH = "/redfish/v1/Oem/OpenCompute_FaultMgmt/RASService"
RAS_ENDPOINTS_PATH = f"{RAS_SERVICE_PATH}/RASEndpoints"
RAS_ACTION_INFO_PATH = f"{RAS_SERVICE_PATH}/SubmitCPADActionInfo"
RAS_SUBMIT_CPAD_PATH = (
    f"{RAS_SERVICE_PATH}/Actions/RASService.SubmitCPAD"
)
CPER_LOG_SERVICE_PATH = (
    "/redfish/v1/Managers/{ManagerId}/LogServices/CPER"
)
CPER_ENTRIES_PATH = f"{CPER_LOG_SERVICE_PATH}/Entries"
RAS_ANALYTICS_PATH = (
    "/redfish/v1/Managers/{ManagerId}/Oem/"
    "OpenCompute_FaultMgmt/Analytics"
)
RAS_HEALTH_PATH = (
    "/redfish/v1/Managers/{ManagerId}/Oem/"
    "OpenCompute_FaultMgmt/Health"
)

# Plugin metadata
PLUGIN_INFO = {
    "name": "ras",
    "version": "1.0.0",
    "description": "Reliability, Availability, Serviceability (RAS) Plugin",
    "author": "BMC Simulator Team",
    "requires": [],  # No dependencies on other plugins
    "provides": [
        "RASService",
        "Endpoints",
        "Initiators", 
        "ErrorQueues",
        "CPAD",
        "CPER"
    ]
}


class RASPlugin:
    """
    RAS Plugin class that manages plugin lifecycle and registration.
    
    This plugin provides RAS capabilities to the BMC Simulator including:
    - RAS Endpoints management
    - RAS Initiators management  
    - Error Queues (IB/OOB × 4 severities)
    - CPAD submission and processing
    - CPER collection and retrieval
    """
    
    def __init__(self):
        self._enabled = False
        self._handler = None
        self._config = None
        self._plugin_config = {}
        self._context = None
        logger.info("RAS Plugin initialized")
    
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
        """Get the RAS service handler instance"""
        return self._handler
    
    def initialize(
            self,
            config: Any,
            plugin_config: Optional[Dict[str, Any]] = None,
            context: Optional[PluginContext] = None) -> bool:
        """
        Initialize the plugin with configuration.
        
        Args:
            config: Shared server configuration
            plugin_config: RAS-specific configuration
            context: Shared Plugin SDK capabilities
            
        Returns:
            True if initialization successful
        """
        try:
            self._config = config
            self._plugin_config = dict(plugin_config or {})
            self._context = context

            if isinstance(config, dict):
                mockup_dir = config.get('mockup_dir') or config.get('mock_dir')
            else:
                mockup_dir = (getattr(config, 'mockup_dir', None) or
                              getattr(config, 'mock_dir', None))

            handler_config = dict(self._plugin_config)
            handler_config['mockup_dir'] = mockup_dir

            from .provider import RASHandler

            self._handler = RASHandler(handler_config)
            self.submit_cpad_handler = self._handler.submit_cpad_handler
            self.discovery_handler = self._handler.discovery_handler

            if context is not None:
                self._handler.event_handler.register_callback(
                    self._publish_event)

            self._enabled = True
            
            logger.info(f"RAS Plugin v{PLUGIN_INFO['version']} initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize RAS Plugin: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def shutdown(self) -> bool:
        """
        Shutdown the plugin gracefully.
        
        Returns:
            True if shutdown successful
        """
        try:
            queue_manager = getattr(self._handler, 'queue_manager', None)
            if queue_manager is not None:
                queue_manager.stop()
            self._enabled = False
            self._handler = None
            self._context = None
            logger.info("RAS Plugin shutdown complete")
            return True
        except Exception as e:
            logger.error(f"Error during RAS Plugin shutdown: {e}")
            return False
    
    def get_routes(self) -> List[PluginRoute]:
        """Return the Redfish routes owned by the RAS plugin."""
        return [
            PluginRoute(RAS_SERVICE_PATH, {'GET'}),
            PluginRoute(RAS_ENDPOINTS_PATH, {'GET'}),
            PluginRoute(f"{RAS_ENDPOINTS_PATH}/{{EndpointId}}", {'GET'}),
            PluginRoute(RAS_ACTION_INFO_PATH, {'GET'}),
            PluginRoute(RAS_SUBMIT_CPAD_PATH, {'POST'}),
            PluginRoute(CPER_LOG_SERVICE_PATH, {'GET'}),
            PluginRoute(CPER_ENTRIES_PATH, {'GET'}),
            PluginRoute(
                f"{CPER_ENTRIES_PATH}/{{EntryId}}",
                {'GET', 'DELETE'},
            ),
            PluginRoute(
                f"{CPER_ENTRIES_PATH}/{{EntryId}}/Attachment",
                {'GET'},
            ),
            PluginRoute(
                f"{CPER_LOG_SERVICE_PATH}/Actions/LogService.ClearLog",
                {'POST'},
            ),
            PluginRoute(RAS_ANALYTICS_PATH, {'GET'}),
            PluginRoute(RAS_HEALTH_PATH, {'GET'}),
        ]

    def _publish_event(self, event: Dict[str, Any]) -> None:
        """Publish each RAS event record through the core EventService."""
        if self._context is None:
            return

        for event_record in event.get('Events', []):
            payload = dict(event_record)
            origin = payload.get('OriginOfCondition')
            if isinstance(origin, dict) and '@odata.id' in origin:
                payload['OriginOfCondition'] = origin['@odata.id']
            self._context.publish_event(payload)
    
    def handle_get(self, path: str, query_params: Dict[str, Any] = None,
                   cached_links: Dict[str, Any] = None) -> Tuple[int, Dict, Dict]:
        """
        Handle GET requests for the plugin-served RAS discovery tree.
        
        Args:
            path: URL path
            query_params: Query parameters
            cached_links: Cached link data
            
        Returns:
            Tuple of (status_code, headers, body)
        """
        if not self._enabled or self._handler is None:
            return 503, {}, {"error": "RAS Plugin not available"}

        status, body = self._handler.handle_get(
            path,
            query_params or {},
            cached_links or {},
        )
        return status, {}, body
    
    def handle_post(self, path: str, data: Dict[str, Any],
                    cached_links: Dict[str, Any] = None) -> Tuple[int, Dict, Dict]:
        """
        Handle POST requests.
        
        Args:
            path: URL path
            data: Request body data
            cached_links: Cached link data
            
        Returns:
            Tuple of (status_code, headers, body)
        """
        if not self._enabled or self._handler is None:
            return 503, {}, {"error": "RAS Plugin not available"}

        status, body = self._handler.handle_post(
            path,
            data,
            cached_links or {},
        )
        return status, {}, body

    def handle_delete(
            self,
            path: str,
            cached_links: Dict[str, Any] = None) -> Tuple[int, Dict, Any]:
        """Handle individual CPER LogEntry deletion."""
        if not self._enabled or self._handler is None:
            return 503, {}, {"error": "RAS Plugin not available"}

        status, body = self._handler.handle_delete(
            path,
            cached_links or {},
        )
        return status, {}, body

    def on_system_reset(self, system_id: str, reset_type: str) -> int:
        """Complete RAS actions deferred until the system resets."""
        if not self._enabled or self._handler is None:
            return 0
        return self._handler.submit_cpad_handler.on_system_reset(
            system_id, reset_type)


# Singleton instance
_plugin_instance: Optional[RASPlugin] = None


def get_plugin() -> RASPlugin:
    """
    Get or create the singleton RAS plugin instance.
    
    Returns:
        RASPlugin instance
    """
    global _plugin_instance
    if _plugin_instance is None:
        _plugin_instance = RASPlugin()
    return _plugin_instance


def register_plugin() -> Dict[str, Any]:
    """
    Register this plugin with the plugin system.
    
    Returns:
        Plugin registration info
    """
    return {
        "info": PLUGIN_INFO,
        "plugin_class": RASPlugin,
        "get_instance": get_plugin
    }
