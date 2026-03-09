#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Message Service for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
==========================================

Provides comprehensive Redfish message response generation with proper
MessageRegistry compliance, standardized error handling, and ExtendedInfo support.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path

logger = logging.getLogger(__name__)

class RedfishMessage:
    """Represents a single Redfish message"""
    
    def __init__(self, message_id: str, message: str, severity: str, 
                 resolution: str = "None", message_args: List[str] = None,
                 related_properties: List[str] = None):
        self.message_id = message_id
        self.message = message
        self.severity = severity
        self.resolution = resolution
        self.message_args = message_args or []
        self.related_properties = related_properties or []
        self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Redfish ExtendedInfo format"""
        result = {
            "MessageId": self.message_id,
            "Message": self._format_message(),
            "Severity": self.severity,
            "Resolution": self.resolution,
            "@odata.type": "#Message.v1_0_0.Message"
        }
        
        if self.message_args:
            result["MessageArgs"] = self.message_args
        
        if self.related_properties:
            result["RelatedProperties"] = self.related_properties
            
        return result
    
    def _format_message(self) -> str:
        """Format message with arguments"""
        formatted_message = self.message
        for i, arg in enumerate(self.message_args, 1):
            formatted_message = formatted_message.replace(f"%{i}", str(arg))
        return formatted_message

class MessageRegistry:
    """Manages Redfish message registries"""
    
    def __init__(self):
        self.registries: Dict[str, Dict] = {}
        self._load_base_registry()
    
    def _load_base_registry(self):
        """Load DMTF Base message registry"""
        base_messages = {
            "Success": {
                "Message": "Successfully Completed Request",
                "Severity": "OK",
                "NumberOfArgs": 0,
                "Resolution": "None"
            },
            "Created": {
                "Message": "The resource has been created successfully",
                "Severity": "OK", 
                "NumberOfArgs": 0,
                "Resolution": "None"
            },
            "GeneralError": {
                "Message": "A general error has occurred. See Resolution for information on how to resolve the error.",
                "Severity": "Critical",
                "NumberOfArgs": 0,
                "Resolution": "None."
            },
            "PropertyUnknown": {
                "Message": "The property %1 is not in the list of valid properties for the resource.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Remove the unknown property from the request body and resubmit the request if the operation failed."
            },
            "PropertyValueTypeError": {
                "Message": "The value %1 for the property %2 is of a different type than the property can accept.",
                "Severity": "Warning", 
                "NumberOfArgs": 2,
                "Resolution": "Correct the value for the property in the request body and resubmit the request if the operation failed."
            },
            "PropertyValueNotInList": {
                "Message": "The value %1 for the property %2 is not in the list of acceptable values.",
                "Severity": "Warning",
                "NumberOfArgs": 2,
                "Resolution": "Choose a value from the enumeration list that the implementation can support and resubmit the request if the operation failed."
            },
            "PropertyNotWritable": {
                "Message": "The property %1 is a read only property and cannot be assigned a value.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Remove the property from the request body and resubmit the request if the operation failed."
            },
            "PropertyMissing": {
                "Message": "The property %1 is a required property and must be included in the request.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Ensure that the property is in the request body and has a valid value and resubmit the request if the operation failed."
            },
            "ActionParameterMissing": {
                "Message": "The action %1 requires the parameter %2 to be present in the request body.",
                "Severity": "Warning",
                "NumberOfArgs": 2,
                "Resolution": "Supply the missing parameter in the request body."
            },
            "ActionParameterValueError": {
                "Message": "The value %1 for the parameter %2 in the action %3 is invalid.",
                "Severity": "Warning",
                "NumberOfArgs": 3,
                "Resolution": "Correct the value for the parameter in the request body."
            },
            "ResourceNotFound": {
                "Message": "The requested resource of type %1 named %2 was not found.",
                "Severity": "Critical",
                "NumberOfArgs": 2,
                "Resolution": "Provide a valid resource identifier and resubmit the request."
            },
            "ResourceInUse": {
                "Message": "The change to the requested resource failed because the resource is in use or in transition.",
                "Severity": "Warning",
                "NumberOfArgs": 0,
                "Resolution": "Remove the condition and resubmit the request if the operation failed."
            },
            "InsufficientPrivilege": {
                "Message": "There are insufficient privileges for the account or credentials associated with the current session to perform the requested operation.",
                "Severity": "Critical",
                "NumberOfArgs": 0,
                "Resolution": "Either abandon the operation or change the associated access rights and resubmit the request if the operation failed."
            }
        }
        
        self.registries["Base.1.5.0"] = {
            "RegistryPrefix": "Base",
            "RegistryVersion": "1.5.0",
            "Messages": base_messages
        }
    
    def load_registry_file(self, registry_path: Path):
        """Load registry from file"""
        try:
            with open(registry_path, 'r') as f:
                registry_data = json.load(f)
                registry_id = registry_data.get("Id", registry_path.stem)
                self.registries[registry_id] = registry_data
                logger.info(f"Loaded message registry: {registry_id}")
        except Exception as e:
            logger.error(f"Failed to load registry {registry_path}: {e}")
    
    def get_message_template(self, message_id: str) -> Optional[Dict]:
        """Get message template by MessageId"""
        if "." not in message_id:
            return None
            
        registry_prefix = message_id.split(".")[0]
        message_key = message_id.split(".")[-1]
        
        # Find registry by prefix
        for registry_id, registry_data in self.registries.items():
            if registry_data.get("RegistryPrefix") == registry_prefix:
                messages = registry_data.get("Messages", {})
                return messages.get(message_key)
        
        return None

class MessageService:
    """Core service for generating Redfish messages and responses"""
    
    def __init__(self, config):
        self.config = config
        self.registry = MessageRegistry()
        self.message_counter = 0
        
        # Load additional registries from mockup if available
        self._load_mockup_registries()
    
    def _load_mockup_registries(self):
        """Load message registries from mockup directory"""
        if not self.config or not hasattr(self.config, 'mock_dir'):
            return
            
        registries_path = Path(self.config.mock_dir) / "redfish" / "v1" / "Registries"
        if registries_path.exists():
            for registry_file in registries_path.rglob("*.json"):
                if registry_file.name != "index.json":
                    self.registry.load_registry_file(registry_file)
    
    def create_message(self, message_id: str, message_args: List[str] = None,
                      related_properties: List[str] = None) -> RedfishMessage:
        """Create a Redfish message"""
        template = self.registry.get_message_template(message_id)
        
        if not template:
            # Fallback for unknown message IDs
            return RedfishMessage(
                message_id="Base.1.5.0.GeneralError",
                message="A general error has occurred.",
                severity="Critical",
                resolution="None.",
                message_args=message_args or []
            )
        
        return RedfishMessage(
            message_id=message_id,
            message=template["Message"],
            severity=template["Severity"], 
            resolution=template["Resolution"],
            message_args=message_args or [],
            related_properties=related_properties or []
        )
    
    def create_success_response(self, resource_data: Dict[str, Any] = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create successful operation response"""
        message = self.create_message("Base.1.5.0.Success")
        
        response_data = resource_data or {}
        response_data["@Message.ExtendedInfo"] = [message.to_dict()]
        
        return 200, {}, response_data
    
    def create_created_response(self, resource_data: Dict[str, Any], 
                              location: str = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create resource created response"""
        message = self.create_message("Base.1.5.0.Created")
        
        response_data = resource_data.copy()
        response_data["@Message.ExtendedInfo"] = [message.to_dict()]
        
        headers = {}
        if location:
            headers["Location"] = location
        
        return 201, headers, response_data
    
    def create_error_response(self, message_id: str, message_args: List[str] = None,
                            related_properties: List[str] = None,
                            http_status: int = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create error response with ExtendedInfo"""
        message = self.create_message(message_id, message_args, related_properties)
        
        # Determine HTTP status from severity if not provided
        if http_status is None:
            severity_to_status = {
                "Critical": 500,
                "Warning": 400,
                "OK": 200
            }
            http_status = severity_to_status.get(message.severity, 400)
        
        response_data = {
            "error": {
                "@Message.ExtendedInfo": [message.to_dict()]
            }
        }
        
        return http_status, {}, response_data
    
    def create_property_error_response(self, property_name: str, 
                                     error_type: str = "PropertyUnknown",
                                     property_value: str = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create property-related error response"""
        if error_type == "PropertyValueTypeError" and property_value:
            message_args = [property_value, property_name]
        else:
            message_args = [property_name]
        
        return self.create_error_response(
            f"Base.1.5.0.{error_type}",
            message_args,
            related_properties=[property_name]
        )
    
    def create_action_error_response(self, action_name: str, parameter_name: str,
                                   error_type: str = "ActionParameterMissing",
                                   parameter_value: str = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create action parameter error response"""
        if error_type == "ActionParameterValueError" and parameter_value:
            message_args = [parameter_value, parameter_name, action_name]
        else:
            message_args = [action_name, parameter_name]
        
        return self.create_error_response(f"Base.1.5.0.{error_type}", message_args)
    
    def create_not_found_response(self, resource_type: str, 
                                resource_id: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create resource not found response"""
        return self.create_error_response(
            "Base.1.5.0.ResourceNotFound", 
            [resource_type, resource_id],
            http_status=404
        )
    
    def create_insufficient_privilege_response(self) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create insufficient privilege response"""
        return self.create_error_response(
            "Base.1.5.0.InsufficientPrivilege",
            http_status=403
        )
    
    def create_multi_message_response(self, messages: List[RedfishMessage],
                                    resource_data: Dict[str, Any] = None,
                                    http_status: int = 200) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Create response with multiple messages"""
        response_data = resource_data or {}
        response_data["@Message.ExtendedInfo"] = [msg.to_dict() for msg in messages]
        
        return http_status, {}, response_data
    
    def enhance_response_with_messages(self, response_data: Dict[str, Any],
                                     messages: List[RedfishMessage]) -> Dict[str, Any]:
        """Add ExtendedInfo messages to existing response"""
        enhanced_data = response_data.copy()
        enhanced_data["@Message.ExtendedInfo"] = [msg.to_dict() for msg in messages]
        return enhanced_data

# Convenience function for global access
_message_service_instance = None

def get_message_service(config=None) -> MessageService:
    """Get global message service instance"""
    global _message_service_instance
    if _message_service_instance is None:
        _message_service_instance = MessageService(config)
    return _message_service_instance

def init_message_service(config):
    """Initialize global message service"""
    global _message_service_instance
    _message_service_instance = MessageService(config)