#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Enhanced HTTP Handlers with Message Service Integration
=====================================================

Provides enhanced HTTP handlers that integrate with MessageService, LogService,
and EventService for standardized Redfish responses and comprehensive logging.
"""

import json
import logging
from typing import Dict, Any, Tuple, Optional
from urllib.parse import urlparse, parse_qs

from .base_handler import BaseRedfishHandler
from ..services.message_service import get_message_service
from ..services.log_service import get_log_service, LogServiceType
from ..services.enhanced_event_service import get_enhanced_event_service
from ..models.redfish_models import SeverityType

logger = logging.getLogger(__name__)

class EnhancedResponseMixin:
    """Mixin for enhanced response handling with message service integration"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message_service = None
        self.log_service = None
        self.event_service = None
    
    def _init_services(self):
        """Initialize services if not already done"""
        if not self.message_service:
            self.message_service = get_message_service(getattr(self, 'server_config', None))
        if not self.log_service:
            self.log_service = get_log_service(getattr(self, 'server_config', None))
        if not self.event_service:
            self.event_service = get_enhanced_event_service(getattr(self, 'server_config', None))
    
    def _log_request(self, method: str, path: str, success: bool, 
                    status_code: int, details: str = None):
        """Log HTTP request with details"""
        self._init_services()
        
        if success:
            severity = SeverityType.OK
            message = f"{method} request to {path} completed successfully"
        else:
            severity = SeverityType.WARNING if status_code < 500 else SeverityType.CRITICAL
            message = f"{method} request to {path} failed with status {status_code}"
            if details:
                message += f": {details}"
        
        self.log_service.create_and_log_entry(
            LogServiceType.AUDIT,
            f"Base.1.5.0.HttpRequest{method}",
            message,
            severity,
            message_args=[method, path, str(status_code)]
        )
    
    def _publish_resource_event(self, operation: str, path: str, resource_type: str = None):
        """Publish resource lifecycle event"""
        self._init_services()
        
        if not resource_type:
            # Try to determine resource type from path
            path_parts = path.strip('/').split('/')
            if len(path_parts) >= 3:
                resource_type = path_parts[-2] if path_parts[-1] else path_parts[-1]
            else:
                resource_type = "Resource"
        
        self.event_service.publish_resource_event(operation, path, resource_type)
    
    def send_enhanced_response(self, status_code: int, response_data: Dict[str, Any],
                             headers: Dict[str, str] = None, log_request: bool = True):
        """Send response with enhanced logging and event publishing"""
        self._init_services()
        
        # Log the request
        if log_request:
            success = 200 <= status_code < 400
            self._log_request(self.command, self.path, success, status_code)
        
        # Send the response using base handler method
        self.send_response(status_code)
        
        # Set headers
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        # Write response body
        if response_data:
            response_json = json.dumps(response_data, indent=2)
            self.wfile.write(response_json.encode('utf-8'))
    
    def send_message_response(self, message_response: Tuple[int, Dict[str, str], Dict[str, Any]],
                            log_request: bool = True):
        """Send response from message service tuple format"""
        status_code, headers, response_data = message_response
        self.send_enhanced_response(status_code, response_data, headers, log_request)

class EnhancedPostHandler(BaseRedfishHandler, EnhancedResponseMixin):
    """Enhanced POST handler with message service integration"""
    
    def do_POST(self):
        """Handle POST request with enhanced response handling"""
        try:
            self._init_services()
            
            # Parse request data
            content_length = int(self.headers.get('content-length', 0))
            if content_length == 0:
                response = self.message_service.create_error_response(
                    "Base.1.5.0.PropertyMissing", ["Request Body"], http_status=411
                )
                self.send_message_response(response)
                return
            
            # Read and parse request body
            post_data = self.rfile.read(content_length)
            
            try:
                if self.headers.get('content-type', '').startswith('application/json'):
                    data_received = json.loads(post_data.decode('utf-8'))
                else:
                    # Handle multipart or other content types
                    data_received = {"raw_data": post_data}
            except json.JSONDecodeError:
                response = self.message_service.create_error_response(
                    "Base.1.5.0.PropertyValueFormatError", 
                    ["Request Body", "JSON"], 
                    http_status=400
                )
                self.send_message_response(response)
                return
            
            # Route to appropriate service handlers
            response = self._route_post_request(self.path, data_received)
            self.send_message_response(response)
            
            # Publish resource event for successful creates
            if response[0] == 201:  # Created
                self._publish_resource_event("CREATE", self.path)
                
        except Exception as e:
            logger.error(f"Error in POST handler: {e}")
            response = self.message_service.create_error_response("Base.1.5.0.GeneralError")
            self.send_message_response(response, log_request=False)
    
    def _route_post_request(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Route POST request to appropriate service"""
        path_lower = path.lower()
        
        # EventService endpoints
        if '/eventservice' in path_lower:
            return self.event_service.handle_event_service_post(path, data)
        
        # LogService endpoints
        elif '/logservices' in path_lower:
            return self.log_service.handle_log_service_post(path, data)
        
        # RAS Service endpoints
        elif '/rasservice' in path_lower:
            from ..services.ras_service import get_ras_service
            ras_service = get_ras_service()
            if hasattr(ras_service, 'handle_post_ras_service'):
                return ras_service.handle_post_ras_service(path, data)
        
        # UpdateService endpoints
        elif '/updateservice' in path_lower:
            from ..services.update_service import UpdateServiceHandler
            update_service = UpdateServiceHandler(self.server_config)
            if hasattr(update_service, 'handle_update_service_post'):
                return update_service.handle_update_service_post(path, data)
        
        # Default: Resource creation or action
        else:
            return self._handle_generic_post(path, data)
    
    def _handle_generic_post(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle generic POST requests (actions, resource creation)"""
        
        # Check if it's an action
        if '/actions/' in path.lower():
            return self._handle_action_request(path, data)
        
        # Otherwise treat as resource creation attempt
        return self._handle_resource_creation(path, data)
    
    def _handle_action_request(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle action requests"""
        # Extract action name from path
        action_parts = path.split('/Actions/')
        if len(action_parts) != 2:
            return self.message_service.create_not_found_response("Action", path)
        
        action_name = action_parts[1].rstrip('/')
        
        # Validate action exists (simplified validation)
        if not action_name:
            return self.message_service.create_not_found_response("Action", path)
        
        # Log action execution
        self.log_service.create_and_log_entry(
            LogServiceType.AUDIT,
            "Base.1.5.0.ActionCompleted",
            f"Action {action_name} executed successfully",
            SeverityType.OK,
            message_args=[action_name]
        )
        
        # Return success response
        response_data = {
            "ActionName": action_name,
            "Status": "Completed",
            "Message": f"Action {action_name} executed successfully"
        }
        
        return self.message_service.create_success_response(response_data)
    
    def _handle_resource_creation(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle resource creation requests"""
        
        # Validate required fields based on resource type
        required_fields = self._get_required_fields_for_path(path)
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return self.message_service.create_error_response(
                "Base.1.5.0.PropertyMissing",
                missing_fields,
                http_status=400
            )
        
        # Create resource (simplified - would normally interact with mockup files)
        resource_id = data.get("Id", "NewResource")
        resource_data = data.copy()
        
        # Add standard fields
        resource_data.update({
            "@odata.id": f"{path.rstrip('/')}/{resource_id}",
            "@odata.type": self._get_odata_type_for_path(path),
            "Id": resource_id,
            "Name": data.get("Name", f"New {resource_id}")
        })
        
        location = resource_data["@odata.id"]
        return self.message_service.create_created_response(resource_data, location)
    
    def _get_required_fields_for_path(self, path: str) -> list:
        """Get required fields for resource type based on path"""
        # Simplified logic - would be more comprehensive in real implementation
        if '/accounts' in path.lower():
            return ["UserName", "Password", "RoleId"]
        elif '/subscriptions' in path.lower():
            return ["Destination"]
        else:
            return []
    
    def _get_odata_type_for_path(self, path: str) -> str:
        """Get OData type for resource based on path"""
        # Simplified mapping
        path_mappings = {
            'accounts': '#ManagerAccount.v1_0_0.ManagerAccount',
            'subscriptions': '#EventDestination.v1_0_0.EventDestination',
            'sessions': '#Session.v1_0_0.Session'
        }
        
        for key, odata_type in path_mappings.items():
            if key in path.lower():
                return odata_type
        
        return "#Resource.v1_0_0.Resource"

class EnhancedPatchHandler(BaseRedfishHandler, EnhancedResponseMixin):
    """Enhanced PATCH handler with message service integration"""
    
    def do_PATCH(self):
        """Handle PATCH request with enhanced response handling"""
        try:
            self._init_services()
            
            # Parse request data
            content_length = int(self.headers.get('content-length', 0))
            if content_length == 0:
                response = self.message_service.create_error_response(
                    "Base.1.5.0.PropertyMissing", ["Request Body"], http_status=400
                )
                self.send_message_response(response)
                return
            
            # Read and parse request body
            patch_data = self.rfile.read(content_length)
            
            try:
                data_received = json.loads(patch_data.decode('utf-8'))
            except json.JSONDecodeError:
                response = self.message_service.create_error_response(
                    "Base.1.5.0.PropertyValueFormatError", 
                    ["Request Body", "JSON"], 
                    http_status=400
                )
                self.send_message_response(response)
                return
            
            # Handle PATCH request
            response = self._handle_patch_request(self.path, data_received)
            self.send_message_response(response)
            
            # Publish resource event for successful updates
            if response[0] == 200:
                self._publish_resource_event("UPDATE", self.path)
                
        except Exception as e:
            logger.error(f"Error in PATCH handler: {e}")
            response = self.message_service.create_error_response("Base.1.5.0.GeneralError")
            self.send_message_response(response, log_request=False)
    
    def _handle_patch_request(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle PATCH request with property validation"""
        
        # Validate properties (simplified validation)
        readonly_properties = self._get_readonly_properties_for_path(path)
        invalid_properties = [prop for prop in data.keys() if prop in readonly_properties]
        
        if invalid_properties:
            return self.message_service.create_property_error_response(
                invalid_properties[0], "PropertyNotWritable"
            )
        
        # Log property changes
        for prop_name, new_value in data.items():
            self.log_service.log_property_change(
                path, prop_name, "previous_value", new_value
            )
        
        # Return success response with updated data
        updated_data = {
            "@odata.id": path,
            **data,
            "LastModified": "2025-11-05T12:00:00Z"
        }
        
        return self.message_service.create_success_response(updated_data)
    
    def _get_readonly_properties_for_path(self, path: str) -> list:
        """Get readonly properties for resource type based on path"""
        # Common readonly properties
        return ["@odata.id", "@odata.type", "Id", "Created", "Modified"]

class EnhancedGetHandler(BaseRedfishHandler, EnhancedResponseMixin):
    """Enhanced GET handler with message service integration"""
    
    def do_GET(self):
        """Handle GET request with enhanced response handling"""
        try:
            self._init_services()
            
            # Route to appropriate service handlers
            response = self._route_get_request(self.path)
            self.send_message_response(response)
            
        except Exception as e:
            logger.error(f"Error in GET handler: {e}")
            response = self.message_service.create_error_response("Base.1.5.0.GeneralError")
            self.send_message_response(response, log_request=False)
    
    def _route_get_request(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Route GET request to appropriate service"""
        path_lower = path.lower()
        
        # EventService endpoints
        if '/eventservice' in path_lower:
            return self.event_service.handle_event_service_get(path)
        
        # LogService endpoints
        elif '/logservices' in path_lower:
            return self.log_service.handle_log_service_get(path)
        
        # RAS Service endpoints
        elif '/rasservice' in path_lower:
            from ..services.ras_service import get_ras_service
            ras_service = get_ras_service()
            if hasattr(ras_service, 'handle_get_ras_service'):
                return ras_service.handle_get_ras_service(path)
        
        # Default: Not found
        else:
            return self.message_service.create_not_found_response("Resource", path)

class EnhancedDeleteHandler(BaseRedfishHandler, EnhancedResponseMixin):
    """Enhanced DELETE handler with message service integration"""
    
    def do_DELETE(self):
        """Handle DELETE request with enhanced response handling"""
        try:
            self._init_services()
            
            # Handle DELETE request
            response = self._route_delete_request(self.path)
            self.send_message_response(response)
            
            # Publish resource event for successful deletions
            if response[0] == 200:
                self._publish_resource_event("DELETE", self.path)
                
        except Exception as e:
            logger.error(f"Error in DELETE handler: {e}")
            response = self.message_service.create_error_response("Base.1.5.0.GeneralError")
            self.send_message_response(response, log_request=False)
    
    def _route_delete_request(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Route DELETE request to appropriate service"""
        path_lower = path.lower()
        
        # EventService endpoints
        if '/eventservice' in path_lower and '/subscriptions/' in path_lower:
            return self.event_service.handle_event_service_delete(path)
        
        # LogService endpoints
        elif '/logservices' in path_lower and '/entries/' in path_lower:
            return self.log_service.handle_log_service_delete(path)
        
        # Default resource deletion
        else:
            return self._handle_generic_delete(path)
    
    def _handle_generic_delete(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle generic resource deletion"""
        # Log deletion
        self.log_service.log_operation("DELETE", path, success=True)
        
        return self.message_service.create_success_response({
            "Message": f"Resource at {path} deleted successfully"
        })