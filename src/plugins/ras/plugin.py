#!/usr/bin/env python3
"""
RAS Plugin Registration and Lifecycle

This module defines the RAS plugin's registration with the BMC Simulator core.
It implements the plugin interface allowing the RAS service to be optionally
loaded based on platform configuration.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

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
            
            # Import handlers
            from .handlers.manager_extension import ManagerOEMExtensionHandler
            from .handlers.submit_cpad_action import SubmitCPADActionHandler
            
            # Initialize handlers
            self.manager_handler = ManagerOEMExtensionHandler()
            self.submit_cpad_handler = SubmitCPADActionHandler()
            
            self._enabled = True
            
            logger.info(f"RAS Plugin v{PLUGIN_INFO['version']} initialized successfully")
            logger.info("  - Manager OEM Extension Handler: Ready")
            logger.info("  - SubmitCPAD Action Handler: Ready")
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
            self._enabled = False
            self._handler = None
            logger.info("RAS Plugin shutdown complete")
            return True
        except Exception as e:
            logger.error(f"Error during RAS Plugin shutdown: {e}")
            return False
    
    def get_routes(self) -> List[str]:
        """
        Return list of URL paths this plugin handles.
        
        Returns:
            List of path patterns
        """
        return [
            # Manager OEM extension
            "/redfish/v1/Managers/*/Oem/RasProto/RASService",
            "/redfish/v1/Managers/*/Oem/RasProto/RASService/Actions/*",
            "/redfish/v1/Managers/*/Oem/RasProto/RASService/SubmitCPADActionInfo",
        ]
    
    def handles_path(self, path: str) -> bool:
        """
        Check if this plugin handles the given path.
        
        Args:
            path: URL path to check
            
        Returns:
            True if plugin handles this path
        """
        # Check for Manager OEM extension paths
        import re
        patterns = [
            r'/redfish/v1/Managers/[^/]+/Oem/RasProto/RASService',
            r'/redfish/v1/Managers/[^/]+/Oem/RasProto/RASService/Actions/.*',
            r'/redfish/v1/Managers/[^/]+/Oem/RasProto/RASService/SubmitCPADActionInfo',
        ]
        
        for pattern in patterns:
            if re.match(pattern, path):
                return True
        
        return False
    
    def handle_get(self, path: str, query_params: Dict[str, Any] = None,
                   cached_links: Dict[str, Any] = None) -> Tuple[int, Dict, Dict]:
        """
        Handle GET requests.
        
        Args:
            path: URL path
            query_params: Query parameters
            cached_links: Cached link data
            
        Returns:
            Tuple of (status_code, headers, body)
        """
        if not self._enabled:
            return 503, {}, {"error": "RAS Plugin not available"}
        
        import re
        
        # Extract manager_id from path
        manager_match = re.match(r'/redfish/v1/Managers/([^/]+)/Oem/RasProto/RASService$', path)
        if manager_match:
            manager_id = manager_match.group(1)
            status, body = self.manager_handler.handle_get_ras_service(manager_id)
            return status, {}, body
        
        # SubmitCPAD ActionInfo
        action_info_match = re.match(r'/redfish/v1/Managers/([^/]+)/Oem/RasProto/RASService/SubmitCPADActionInfo$', path)
        if action_info_match:
            manager_id = action_info_match.group(1)
            status, body = self.manager_handler.handle_get_action_info(manager_id)
            return status, {}, body
        
        return 404, {}, {"error": "Not found"}
    
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
        if not self._enabled:
            return 503, {}, {"error": "RAS Plugin not available"}
        
        import re
        
        # SubmitCPAD action
        submit_cpad_match = re.match(r'/redfish/v1/Managers/([^/]+)/Oem/RasProto/RASService/Actions/RasProto\.SubmitCPAD$', path)
        if submit_cpad_match:
            manager_id = submit_cpad_match.group(1)
            status, body = self.submit_cpad_handler.handle_submit_cpad(manager_id, data)
            return status, {}, body
        
        return 404, {}, {"error": "Not found"}


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
