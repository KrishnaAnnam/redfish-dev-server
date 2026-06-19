"""
Manager OEM Extension Handler

Handles injection of RasProto OEM extension into Manager resources,
providing the Manager-scoped RASService endpoint.

Endpoint: /redfish/v1/Managers/{ManagerId}/Oem/RasProto/RASService
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ManagerOEMExtensionHandler:
    """Handler for Manager OEM RasProto extension."""
    
    def __init__(self):
        """Initialize Manager OEM extension handler."""
        self.ras_service_enabled = True
    
    def handle_get(self, manager_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        Handle GET request for RASService resource.
        
        Args:
            manager_id: Manager ID
            
        Returns:
            Tuple of (status_code, response_body)
        """
        try:
            ras_service = self.build_ras_service_resource(manager_id)
            return (200, ras_service)
        except Exception as e:
            logger.error(f"Error building RASService resource: {e}")
            return (500, {
                "error": {
                    "@Message.ExtendedInfo": [{
                        "MessageId": "Base.1.16.0.InternalError",
                        "Message": "The request failed due to an internal service error.",
                        "Severity": "Critical"
                    }]
                }
            })
    
    def build_ras_service(self, manager_id: str) -> Dict[str, Any]:
        """
        Build RASService OEM extension (for Manager OEM injection).
        
        Args:
            manager_id: Manager ID
            
        Returns:
            dict: RasProto OEM content
        """
        return {
            '@odata.type': '#RasProto.v1_0_0.ManagerExtension',
            'RASService': {
                '@odata.id': f'/redfish/v1/Managers/{manager_id}/Oem/RasProto/RASService'
            }
        }
    
    def inject_manager_oem(self, manager_data: Dict[str, Any], manager_id: str) -> Dict[str, Any]:
        """
        Inject RasProto OEM extension into Manager resource.
        
        Args:
            manager_data: Existing Manager resource data
            manager_id: Manager ID
            
        Returns:
            dict: Manager data with RasProto OEM extension
        """
        # Ensure Oem property exists
        if 'Oem' not in manager_data:
            manager_data['Oem'] = {}
        
        # Add RasProto extension
        manager_data['Oem']['RasProto'] = {
            '@odata.type': '#RasProto.v1_0_0.ManagerExtension',
            'RASService': {
                '@odata.id': f'/redfish/v1/Managers/{manager_id}/Oem/RasProto/RASService'
            }
        }
        
        logger.debug(f"Injected RasProto OEM into Manager: {manager_id}")
        return manager_data
    
    def build_ras_service_resource(self, manager_id: str) -> Dict[str, Any]:
        """
        Build the RASService resource under Manager OEM.
        
        Args:
            manager_id: Manager ID
            
        Returns:
            dict: RASService resource representation
        """
        base_uri = f'/redfish/v1/Managers/{manager_id}/Oem/RasProto'
        
        ras_service = {
            '@odata.type': '#RasProto.v1_0_0.RASService',
            '@odata.id': f'{base_uri}/RASService',
            'Id': 'RASService',
            'Name': 'RAS Service',
            'Description': 'Reliability, Availability, and Serviceability (RAS) management service for error detection, analysis, and remediation',
            
            # Version information (for parity demo)
            'RasApiVersion': '1.0.0',
            'PluginVersion': '1.0.0-Phase7',
            
            # Service status
            'ServiceEnabled': self.ras_service_enabled,
            'Status': {
                'State': 'Enabled' if self.ras_service_enabled else 'Disabled',
                'Health': 'OK'
            },
            
            # Governance metadata (pre-standard transparency)
            'Governance': {
                '@odata.type': '#RasProto.v1_0_0.Governance',
                'StandardizationStatus': 'PreStandard',
                'ProposedNamespace': '/redfish/v1/Managers/{ManagerId}/RASService',
                'TargetStandard': 'DMTF Redfish',
                'ExperimentalTag': 'RasProto',
                'Rationale': 'Manager-scoped placement for control-plane orchestration of platform RAS capabilities',
                'SubmittedTo': 'DMTF',
                'SubmissionDate': '2026-01-22',
                'ContactInfo': 'OCP RAS Working Group'
            },
            
            # Actions
            'Actions': {
                '#RasProto.SubmitCPAD': {
                    'target': f'{base_uri}/RASService/Actions/RasProto.SubmitCPAD',
                    '@Redfish.ActionInfo': f'{base_uri}/RASService/SubmitCPADActionInfo'
                }
            },
            
            # Links section (future expansion)
            'Links': {
                'RelatedLogService': {
                    '@odata.id': f'/redfish/v1/Managers/{manager_id}/LogServices/RAS'
                }
            },
            
            # LogService reference (for parity with RasAPI)
            'LogService': {
                '@odata.id': f'/redfish/v1/Managers/{manager_id}/LogServices/RAS'
            }
        }
        
        return ras_service
    
    def build_submit_cpad_action_info(self, manager_id: str) -> Dict[str, Any]:
        """
        Build ActionInfo resource for SubmitCPAD action.
        
        Args:
            manager_id: Manager ID
            
        Returns:
            dict: ActionInfo resource
        """
        return {
            '@odata.type': '#ActionInfo.v1_2_0.ActionInfo',
            '@odata.id': f'/redfish/v1/Managers/{manager_id}/Oem/RasProto/RASService/SubmitCPADActionInfo',
            'Id': 'SubmitCPADActionInfo',
            'Name': 'SubmitCPAD Action Info',
            'Parameters': [
                {
                    'Name': 'CPADData',
                    'Required': True,
                    'DataType': 'Object',
                    'ObjectDataType': '#RasProto.v1_0_0.SubmitCPAD',
                    'AllowableValues': []
                }
            ]
        }
    
    def handle_get_ras_service(self, manager_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        Handle GET request to RASService resource.
        
        Args:
            manager_id: Manager ID
            
        Returns:
            tuple: (status_code, response_body)
        """
        try:
            response = self.build_ras_service_resource(manager_id)
            return 200, response
        except Exception as e:
            logger.error(f"Error building RASService resource: {e}")
            return 500, {
                'error': {
                    '@Message.ExtendedInfo': [{
                        'MessageId': 'Base.1.16.InternalError',
                        'Message': 'The request failed due to an internal service error.',
                        'Severity': 'Critical',
                        'Resolution': 'Resubmit the request. If the problem persists, consider resetting the service.'
                    }]
                }
            }
    
    def handle_get_action_info(self, manager_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        Handle GET request to SubmitCPAD ActionInfo.
        
        Args:
            manager_id: Manager ID
            
        Returns:
            tuple: (status_code, response_body)
        """
        try:
            response = self.build_submit_cpad_action_info(manager_id)
            return 200, response
        except Exception as e:
            logger.error(f"Error building ActionInfo: {e}")
            return 500, {
                'error': {
                    '@Message.ExtendedInfo': [{
                        'MessageId': 'Base.1.16.InternalError',
                        'Message': 'The request failed due to an internal service error.',
                        'Severity': 'Critical'
                    }]
                }
            }
    
    def get_handler_routes(self) -> Dict[str, Any]:
        """
        Get route mappings for this handler.
        
        Returns:
            dict: Route patterns and handler methods
        """
        return {
            'GET': {
                r'/redfish/v1/Managers/(?P<manager_id>[^/]+)/Oem/RasProto/RASService$': self.handle_get_ras_service,
                r'/redfish/v1/Managers/(?P<manager_id>[^/]+)/Oem/RasProto/RASService/SubmitCPADActionInfo$': self.handle_get_action_info,
            }
        }
