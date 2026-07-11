"""
RAS Platform Provider

Integrates RAS plugin with the BMC Redfish Server platform framework.
Provides handlers for RAS-specific endpoints and OEM extensions.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import re

try:
    from src.core.interfaces import BasePlatformHandler
except ImportError:
    # Fallback for direct imports
    BasePlatformHandler = object

logger = logging.getLogger(__name__)


class RASHandler(BasePlatformHandler):
    """
    Handler for RAS-specific endpoints.
    
    Handles paths:
    - /redfish/v1/Managers/{ManagerId}/Oem/RasProto/RASService
    - /redfish/v1/Managers/{ManagerId}/Oem/RasProto/RASService/Actions/*
    """
    
    def __init__(self, platform_config: Dict[str, Any] = None):
        """Initialize RAS handler"""
        super().__init__(platform_config or {})
        
        # Import handlers
        from .handlers.manager_extension import ManagerOEMExtensionHandler
        from .handlers.submit_cpad_action import SubmitCPADActionHandler
        from .handlers.log_service import RASLogServiceHandler
        from .handlers.event_service import RASEventServiceHandler
        
        # Import Phase 7 services
        from .services import (
            CPERQueueManager,
            RASAnalyticsEngine,
            AutomatedRemediationEngine,
            RASHealthMonitor
        )
        
        # Get mockup directory from config if available
        mockup_dir = platform_config.get('mockup_dir') if platform_config else None
        
        # Initialize event service handler
        self.event_handler = RASEventServiceHandler()
        logger.info("RAS EventService handler initialized")
        
        # Initialize Phase 7 services
        self.queue_manager = None
        self.analytics_engine = None
        self.remediation_engine = None
        self.health_monitor = None
        
        # Initialize handlers with event support
        self.manager_handler = ManagerOEMExtensionHandler()
        self.submit_cpad_handler = SubmitCPADActionHandler(
            mockup_dir=mockup_dir,
            event_handler=self.event_handler
        )
        
        # Initialize LogService handler if mockup directory available
        self.log_service_handler = None
        if mockup_dir:
            try:
                self.log_service_handler = RASLogServiceHandler(
                    mockup_dir,
                    event_handler=self.event_handler
                )
                logger.info("RAS LogService handler initialized")
                
                # Initialize Phase 7 services with LogService
                self._initialize_advanced_services()
                
            except Exception as e:
                logger.warning(f"RAS LogService handler initialization failed: {e}")
        
        # Compile path patterns
        self.manager_oem_pattern = re.compile(
            r'^/redfish/v1/Managers/([^/]+)/Oem/RasProto/RASService/?$'
        )
        self.submit_cpad_pattern = re.compile(
            r'^/redfish/v1/Managers/([^/]+)/Oem/RasProto/RASService/Actions/RasProto\.SubmitCPAD/?$'
        )
        self.logservice_pattern = re.compile(
            r'^/redfish/v1/Managers/([^/]+)/LogServices/CPER(/.*)?$'
        )
        self.analytics_pattern = re.compile(
            r'^/redfish/v1/Managers/([^/]+)/Oem/RasProto/Analytics/?$'
        )
        self.health_pattern = re.compile(
            r'^/redfish/v1/Managers/([^/]+)/Oem/RasProto/Health/?$'
        )
        
        logger.info("RAS Handler initialized")
    
    def _initialize_advanced_services(self):
        """Initialize Phase 7 advanced services"""
        from .services import (
            CPERQueueManager,
            RASAnalyticsEngine,
            AutomatedRemediationEngine,
            RASHealthMonitor
        )
        
        try:
            # Initialize CPER queue manager
            self.queue_manager = CPERQueueManager(
                max_queue_size=1000,
                worker_count=2,
                defer_threshold=100
            )
            
            # Register CPER processing handler
            def process_cper(queue_item):
                """Process CPER from queue"""
                if not self.log_service_handler:
                    return
                
                try:
                    # Create log entry if not already created
                    if not queue_item.entry_id:
                        severity = queue_item.metadata.get("severity", "OK")
                        self.log_service_handler.add_cper_log_entry(
                            manager_id=queue_item.manager_id,
                            cper_data=queue_item.cper_data,
                            severity=severity
                        )
                except Exception as e:
                    logger.error(f"Failed to process CPER from queue: {e}")
            
            self.queue_manager.register_handler(process_cper)
            self.queue_manager.start()
            logger.info("CPER Queue Manager started")
            
            # Initialize analytics engine
            self.analytics_engine = RASAnalyticsEngine(
                log_service_handler=self.log_service_handler
            )
            logger.info("Analytics Engine initialized")
            
            # Initialize remediation engine
            self.remediation_engine = AutomatedRemediationEngine(
                event_handler=self.event_handler
            )
            
            # Register remediation handler for queue items
            def remediation_handler(queue_item):
                """Evaluate queue items for remediation"""
                try:
                    # Convert queue item to event format
                    event_data = {
                        "Severity": queue_item.metadata.get("severity", "OK"),
                        "Oem": {
                            "RasProto": queue_item.cper_data
                        }
                    }
                    self.remediation_engine.evaluate_event(event_data)
                except Exception as e:
                    logger.error(f"Remediation evaluation failed: {e}")
            
            self.queue_manager.register_handler(remediation_handler)
            logger.info("Remediation Engine initialized")
            
            # Initialize health monitor
            self.health_monitor = RASHealthMonitor(
                analytics_engine=self.analytics_engine,
                queue_manager=self.queue_manager,
                remediation_engine=self.remediation_engine
            )
            logger.info("Health Monitor initialized")
            
            logger.info("All Phase 7 advanced services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize advanced services: {e}", exc_info=True)
    
    def get_handler_name(self) -> str:
        """Return handler name"""
        return "ras_handler"
    
    def get_supported_paths(self) -> List[str]:
        """Return list of path patterns this handler supports"""
        return [
            '/redfish/v1/Managers/*/Oem/RasProto/RASService',
            '/redfish/v1/Managers/*/Oem/RasProto/RASService/Actions/RasProto.SubmitCPAD',
            '/redfish/v1/Managers/*/LogServices/CPER',
            '/redfish/v1/Managers/*/LogServices/CPER/Entries',
            '/redfish/v1/Managers/*/LogServices/CPER/Entries/*',
            '/redfish/v1/Managers/*/Oem/RasProto/Analytics',
            '/redfish/v1/Managers/*/Oem/RasProto/Health',
        ]
    
    def can_handle_path(self, path: str) -> bool:
        """Check if this handler can handle the given path"""
        # Remove query string if present
        path_without_query = path.split('?')[0]
        
        # Check Manager OEM path
        if self.manager_oem_pattern.match(path_without_query):
            return True
        
        # Check SubmitCPAD action path
        if self.submit_cpad_pattern.match(path_without_query):
            return True
        
        # Check LogService paths
        if self.logservice_pattern.match(path_without_query):
            return True
        
        # Check Analytics path
        if self.analytics_pattern.match(path_without_query):
            return True
        
        # Check Health path
        if self.health_pattern.match(path_without_query):
            return True
        
        return False
    
    def handle_get(self, path: str, query_params: Dict[str, Any], cached_links: Dict) -> Tuple[int, Dict[str, Any]]:
        """
        Handle GET requests.
        
        Args:
            path: Request path
            query_params: Query parameters
            cached_links: Cached resource links
            
        Returns:
            Tuple of (status_code, response_data)
        """
        # Remove query string
        path_without_query = path.split('?')[0]
        
        # Handle Manager OEM extension
        match = self.manager_oem_pattern.match(path_without_query)
        if match:
            manager_id = match.group(1)
            return self.manager_handler.handle_get(manager_id)
        
        # Handle LogService paths
        if self.log_service_handler and self.logservice_pattern.match(path_without_query):
            return self.log_service_handler.handle_get(path_without_query)
        
        # Handle Analytics endpoint
        match = self.analytics_pattern.match(path_without_query)
        if match and self.analytics_engine:
            manager_id = match.group(1)
            return self._handle_analytics_get(manager_id)
        
        # Handle Health endpoint
        match = self.health_pattern.match(path_without_query)
        if match and self.health_monitor:
            manager_id = match.group(1)
            return self._handle_health_get(manager_id)
        
        # SubmitCPAD action endpoint doesn't support GET
        if self.submit_cpad_pattern.match(path_without_query):
            return (405, {
                "error": {
                    "@Message.ExtendedInfo": [{
                        "MessageId": "Base.1.16.0.ActionNotSupported",
                        "Message": "The action SubmitCPAD is not supported on this resource.",
                        "Severity": "Warning",
                        "Resolution": "Use POST method for this action."
                    }]
                }
            })
        
        # Should not reach here if can_handle_path works correctly
        return (404, {})
    
    def handle_post(self, path: str, data: Dict[str, Any], cached_links: Dict) -> Tuple[int, Dict[str, Any]]:
        """
        Handle POST requests.
        
        Args:
            path: Request path
            data: Request body data
            cached_links: Cached resource links
            
        Returns:
            Tuple of (status_code, response_data)
        """
        # Remove query string
        path_without_query = path.split('?')[0]
        
        # Handle LogService actions (ClearLog)
        if self.log_service_handler and 'LogServices/CPER/Actions' in path_without_query:
            return self.log_service_handler.handle_post(path_without_query, data)
        
        # Manager OEM extension doesn't support POST
        match = self.manager_oem_pattern.match(path_without_query)
        if match:
            return (405, {
                "error": {
                    "@Message.ExtendedInfo": [{
                        "MessageId": "Base.1.16.0.ActionNotSupported",
                        "Message": "POST is not supported on this resource.",
                        "Severity": "Warning",
                        "Resolution": "Use GET method to retrieve this resource."
                    }]
                }
            })
        
        # Handle SubmitCPAD action
        match = self.submit_cpad_pattern.match(path_without_query)
        if match:
            manager_id = match.group(1)
            return self.submit_cpad_handler.handle_post(manager_id, data)
        
        # Should not reach here if can_handle_path works correctly
        return (404, {})
    
    def handle_patch(self, path: str, data: Dict[str, Any], cached_links: Dict) -> Tuple[int, Dict[str, Any]]:
        """
        Handle PATCH requests (not supported for RAS endpoints).
        
        Args:
            path: Request path
            data: Request body data
            cached_links: Cached resource links
            
        Returns:
            Tuple of (status_code, response_data)
        """
        return (405, {
            "error": {
                "@Message.ExtendedInfo": [{
                    "MessageId": "Base.1.16.0.ActionNotSupported",
                    "Message": "PATCH is not supported on RAS endpoints.",
                    "Severity": "Warning",
                    "Resolution": "Use GET or POST methods."
                }]
            }
        })
    
    def handle_delete(self, path: str, cached_links: Dict) -> Tuple[int, Dict[str, Any]]:
        """
        Handle DELETE requests for RAS endpoints.
        
        Per OCP RAS API §4.8, individual CPER deletion uses:
            DELETE /redfish/v1/Managers/{ManagerId}/LogServices/CPER/Entries/{EntryId}
        
        Args:
            path: Request path
            cached_links: Cached resource links
            
        Returns:
            Tuple of (status_code, response_data)
        """
        # Route individual LogEntry deletion to log_service_handler
        if "/LogServices/CPER/Entries/" in path:
            return self.log_service_handler.handle_delete(path)
        
        return (405, {
            "error": {
                "@Message.ExtendedInfo": [{
                    "MessageId": "Base.1.16.0.ActionNotSupported",
                    "Message": "DELETE is not supported on this RAS endpoint.",
                    "Severity": "Warning",
                    "Resolution": "Use DELETE on individual LogEntries or POST LogService.ClearLog to clear all."
                }]
            }
        })


class ManagerOEMInjector:
    """
    Injects RASService into Manager Oem section.
    
    This is called when GET /redfish/v1/Managers/{ManagerId} is requested
    to dynamically add the RasProto OEM extension.
    """
    
    def __init__(self):
        """Initialize OEM injector"""
        from .handlers.manager_extension import ManagerOEMExtensionHandler
        self.handler = ManagerOEMExtensionHandler()
        logger.info("Manager OEM Injector initialized")
    
    def inject_oem(self, manager_resource: Dict[str, Any], manager_id: str) -> Dict[str, Any]:
        """
        Inject RASService OEM into Manager resource.
        
        Args:
            manager_resource: The Manager resource dict
            manager_id: The Manager ID
            
        Returns:
            Modified Manager resource with OEM injection
        """
        try:
            # Ensure Oem exists
            if 'Oem' not in manager_resource:
                manager_resource['Oem'] = {}
            
            # Add RasProto extension
            ras_service = self.handler.build_ras_service(manager_id)
            manager_resource['Oem']['RasProto'] = ras_service
            
            logger.debug(f"Injected RASService OEM into Manager '{manager_id}'")
            
        except Exception as e:
            logger.error(f"Failed to inject RASService OEM: {e}")
        
        return manager_resource
    
    def _handle_analytics_get(self, manager_id: str) -> Tuple[int, Dict[str, Any]]:
        """Handle GET request for Analytics endpoint"""
        if not self.analytics_engine:
            return (503, {"error": "Analytics engine not available"})
        
        try:
            report = self.analytics_engine.get_summary_report()
            
            # Wrap in Redfish OEM format
            response = {
                "@odata.type": "#RasProto.v1_0_0.Analytics",
                "@odata.id": f"/redfish/v1/Managers/{manager_id}/Oem/RasProto/Analytics",
                "Id": "Analytics",
                "Name": "RAS Analytics",
                "Description": "RAS analytics and trend analysis",
                "ErrorTrends": report.get("error_trends", {}),
                "ComponentHealth": report.get("component_health", {}),
                "SeverityDistribution": report.get("severity_distribution", {}),
                "GeneratedAt": report.get("generated_at")
            }
            
            return (200, response)
            
        except Exception as e:
            logger.error(f"Analytics GET failed: {e}")
            return (500, {"error": str(e)})
    
    def _handle_health_get(self, manager_id: str) -> Tuple[int, Dict[str, Any]]:
        """Handle GET request for Health endpoint"""
        if not self.health_monitor:
            return (503, {"error": "Health monitor not available"})
        
        try:
            health_data = self.health_monitor.get_health_summary()
            
            # Wrap in Redfish OEM format
            response = {
                "@odata.type": "#RasProto.v1_0_0.Health",
                "@odata.id": f"/redfish/v1/Managers/{manager_id}/Oem/RasProto/Health",
                "Id": "Health",
                "Name": "RAS System Health",
                "Description": "RAS system health monitoring",
                "Status": {
                    "State": "Enabled",
                    "Health": health_data["summary"]["status"]
                },
                "OverallStatus": health_data["summary"]["status"],
                "ActiveAlerts": health_data["summary"]["active_alerts"],
                "HealthChecks": health_data["details"]["health_checks"],
                "RecentAlerts": health_data.get("recent_alerts", []),
                "CheckedAt": health_data["summary"]["checked_at"]
            }
            
            # Add queue statistics if available
            if self.queue_manager:
                response["QueueStatus"] = self.queue_manager.get_queue_status()
            
            # Add remediation statistics if available
            if self.remediation_engine:
                response["RemediationStats"] = self.remediation_engine.get_stats()
                response["RemediationRules"] = self.remediation_engine.get_rule_summary()
            
            return (200, response)
            
        except Exception as e:
            logger.error(f"Health GET failed: {e}")
            return (500, {"error": str(e)})
