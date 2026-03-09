#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Enhanced Redfish Message Service for BMC Redfish Simulator
===========================================================
Provides Redfish-compliant message responses with proper MessageRegistry
support, including schema validation error mapping and ExtendedInfo formatting.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path

logger = logging.getLogger(__name__)

class RedfishMessageService:
    """Enhanced service for generating Redfish-compliant error responses"""
    
    def __init__(self, config):
        self.config = config
        self.base_registry = self._load_base_registry()
        
    def _load_base_registry(self) -> Dict[str, Any]:
        """Load Base message registry with schema validation specific messages"""
        return {
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
            "PropertyNotWritable": {
                "Message": "The property %1 is a read only property and cannot be assigned a value.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Remove the property from the request body and resubmit the request if the operation failed."
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
            "PropertyValueFormatError": {
                "Message": "The value %1 for the property %2 is of a different format than the property can accept.",
                "Severity": "Warning",
                "NumberOfArgs": 2,
                "Resolution": "Correct the value for the property in the request body and resubmit the request if the operation failed."
            },
            "PropertyValueError": {
                "Message": "The value provided for the property %1 is not valid.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Correct the value for the property in the request body and resubmit the request if the operation failed."
            },
            "PropertyMissing": {
                "Message": "The property %1 is a required property and must be included in the request.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Ensure that the property is in the request body and has a valid value and resubmit the request if the operation failed."
            },
            "PropertyValueConflict": {
                "Message": "The property %1 could not be updated due to conflicts with other properties.",
                "Severity": "Warning",
                "NumberOfArgs": 1,
                "Resolution": "Resolve the conflicts with other properties and resubmit the request if the operation failed."
            },
            "InsufficientPrivilege": {
                "Message": "There are insufficient privileges for the account or credentials associated with the current session to perform the requested operation.",
                "Severity": "Critical",
                "NumberOfArgs": 0,
                "Resolution": "Either abandon the operation or change the associated access rights and resubmit the request if the operation failed."
            },
            "ResourceNotFound": {
                "Message": "The requested resource of type %1 named %2 was not found.",
                "Severity": "Critical", 
                "NumberOfArgs": 2,
                "Resolution": "Provide a valid resource identifier and resubmit the request."
            },
            "ActionParameterMissing": {
                "Message": "The action %1 requires the parameter %2 to be present in the request body.",
                "Severity": "Warning",
                "NumberOfArgs": 2,
                "Resolution": "Supply the missing parameter in the request body."
            },
            "ActionParameterValueTypeError": {
                "Message": "The value %1 for the parameter %2 in the action %3 is of a different type than the parameter can accept.",
                "Severity": "Warning",
                "NumberOfArgs": 3,
                "Resolution": "Correct the value for the parameter in the request body and resubmit the request if the operation failed."
            },
            "PasswordChangeRequired": {
                "Message": "The password provided for this account must be changed before access is granted.  PATCH the 'Password' property for this account located at the target URI '%1' to complete this process.",
                "Severity": "Critical",
                "NumberOfArgs": 1,
                "Resolution": "Change the password for this account using a PATCH operation."
            }
        }

    def _classify_validation_error(self, error_message: str) -> Tuple[str, List[str], List[str]]:
        """
        Classify validation error message and extract property names and values.
        Returns: (MessageId, MessageArgs, RelatedProperties)
        """
        error_lower = error_message.lower()
        
        # Extract property name from error message using common patterns
        property_patterns = [
            r"property '([^']+)'",
            r"property \"([^\"]+)\"", 
            r"property ([a-zA-Z][a-zA-Z0-9]*)",
            r"'([^']+)' property",
            r"([a-zA-Z][a-zA-Z0-9]*) is",
            r"([a-zA-Z][a-zA-Z0-9]*) cannot",
            r"([a-zA-Z][a-zA-Z0-9]*) must"
        ]
        
        property_name = None
        for pattern in property_patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                property_name = match.group(1)
                break
        
        # Extract values from error messages
        value_patterns = [
            r"value '([^']+)'",
            r"value \"([^\"]+)\"",
            r"value ([a-zA-Z0-9]+)",
        ]
        
        value = None
        for pattern in value_patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                value = match.group(1)
                break
        
        # Classify error type
        if "read-only" in error_lower or "read only" in error_lower or "cannot be modified" in error_lower:
            return "Base.1.5.0.PropertyNotWritable", [property_name] if property_name else [], [property_name] if property_name else []
        
        elif "not writable" in error_lower or "unknown property" in error_lower:
            return "Base.1.5.0.PropertyUnknown", [property_name] if property_name else [], [property_name] if property_name else []
        
        elif "must be one of" in error_lower or "not in the list" in error_lower or "invalid enum" in error_lower:
            # Extract enum values if possible
            enum_match = re.search(r"must be one of:?\s*(.+?)(?:\.|$)", error_message, re.IGNORECASE)
            if enum_match and value and property_name:
                return "Base.1.5.0.PropertyValueNotInList", [value, property_name], [property_name]
            elif property_name:
                return "Base.1.5.0.PropertyValueError", [property_name], [property_name]
        
        elif "type" in error_lower and "different" in error_lower:
            if value and property_name:
                return "Base.1.5.0.PropertyValueTypeError", [value, property_name], [property_name]
            elif property_name:
                return "Base.1.5.0.PropertyValueError", [property_name], [property_name]
        
        elif "format" in error_lower or "datetime" in error_lower or "invalid format" in error_lower:
            if value and property_name:
                return "Base.1.5.0.PropertyValueFormatError", [value, property_name], [property_name]
            elif property_name:
                return "Base.1.5.0.PropertyValueError", [property_name], [property_name]
        
        elif "required" in error_lower or "missing" in error_lower:
            return "Base.1.5.0.PropertyMissing", [property_name] if property_name else [], [property_name] if property_name else []
        
        elif "conflict" in error_lower or "cannot be" in error_lower and "when" in error_lower:
            return "Base.1.5.0.PropertyValueConflict", [property_name] if property_name else [], [property_name] if property_name else []
        
        elif "length" in error_lower or "characters" in error_lower or "password" in error_lower:
            return "Base.1.5.0.PropertyValueError", [property_name] if property_name else [], [property_name] if property_name else []
        
        else:
            # Default to generic property error
            return "Base.1.5.0.PropertyValueError", [property_name] if property_name else [], [property_name] if property_name else []

    def _format_message_with_args(self, message_template: str, message_args: List[str]) -> str:
        """Format message template with arguments"""
        formatted_message = message_template
        for i, arg in enumerate(message_args, 1):
            formatted_message = formatted_message.replace(f"%{i}", str(arg) if arg else "")
        return formatted_message

    def create_redfish_message(self, message_id: str, message_args: List[str] = None, 
                              related_properties: List[str] = None) -> Dict[str, Any]:
        """Create a single Redfish message in ExtendedInfo format"""
        message_key = message_id.split(".")[-1] if "." in message_id else message_id
        template = self.base_registry.get(message_key)
        
        if not template:
            # Fallback to general error
            template = self.base_registry["GeneralError"]
            message_id = "Base.1.5.0.GeneralError"
        
        message_args = message_args or []
        formatted_message = self._format_message_with_args(template["Message"], message_args)
        
        redfish_message = {
            "@odata.type": "#Message.v1_1_1.Message",
            "MessageId": message_id,
            "Message": formatted_message,
            "Severity": template["Severity"],
            "Resolution": template["Resolution"]
        }
        
        if message_args:
            redfish_message["MessageArgs"] = message_args
            
        if related_properties:
            redfish_message["RelatedProperties"] = related_properties
            
        return redfish_message

    def create_validation_error_response(self, validation_errors: List[str], 
                                       http_status: int = 400) -> Tuple[Dict[str, Any], int]:
        """Create a Redfish-compliant error response from validation errors"""
        extended_info = []
        
        for error in validation_errors:
            message_id, message_args, related_props = self._classify_validation_error(error)
            redfish_message = self.create_redfish_message(message_id, message_args, related_props)
            extended_info.append(redfish_message)
        
        # If we have multiple errors, include a general summary message
        if len(validation_errors) > 1:
            summary_message = self.create_redfish_message(
                "Base.1.5.0.GeneralError",
                [],
                []
            )
            summary_message["Message"] = f"Request contained {len(validation_errors)} validation errors."
            extended_info.insert(0, summary_message)
        
        error_response = {
            "error": {
                "@Message.ExtendedInfo": extended_info
            }
        }
        
        return error_response, http_status

    def create_success_response(self, message_id: str = "Base.1.5.0.Success",
                               resource_data: Dict[str, Any] = None,
                               additional_messages: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a success response with optional ExtendedInfo"""
        response_data = resource_data or {}
        
        extended_info = [self.create_redfish_message(message_id)]
        if additional_messages:
            extended_info.extend(additional_messages)
        
        response_data["@Message.ExtendedInfo"] = extended_info
        return response_data

    def create_property_error_response(self, property_name: str, property_value: str = None,
                                     error_type: str = "PropertyNotWritable") -> Tuple[Dict[str, Any], int]:
        """Create property-specific error response"""
        if error_type == "PropertyValueTypeError" and property_value:
            message_args = [property_value, property_name]
        elif error_type == "PropertyValueNotInList" and property_value:
            message_args = [property_value, property_name]
        else:
            message_args = [property_name]
        
        message_id = f"Base.1.5.0.{error_type}"
        redfish_message = self.create_redfish_message(message_id, message_args, [property_name])
        
        error_response = {
            "error": {
                "@Message.ExtendedInfo": [redfish_message]
            }
        }
        
        return error_response, 400

    def create_action_error_response(self, action_name: str, parameter_name: str = None,
                                   parameter_value: str = None, error_type: str = "ActionParameterMissing") -> Tuple[Dict[str, Any], int]:
        """Create action parameter error response"""
        if error_type == "ActionParameterValueTypeError" and parameter_value and parameter_name:
            message_args = [parameter_value, parameter_name, action_name]
        elif parameter_name:
            message_args = [action_name, parameter_name]
        else:
            message_args = [action_name]
        
        message_id = f"Base.1.5.0.{error_type}"
        redfish_message = self.create_redfish_message(message_id, message_args, [])
        
        error_response = {
            "error": {
                "@Message.ExtendedInfo": [redfish_message]
            }
        }
        
        return error_response, 400

    def create_resource_created_response(self, resource_data: Dict[str, Any], 
                                       resource_uri: str = None) -> Tuple[Dict[str, Any], int, Dict[str, str]]:
        """Create resource created response with location header"""
        message = self.create_redfish_message("Base.1.5.0.Created")
        
        response_data = resource_data.copy()
        response_data["@Message.ExtendedInfo"] = [message]
        
        headers = {}
        if resource_uri:
            headers["Location"] = resource_uri
        
        return response_data, 201, headers

    def enhance_response_with_info_messages(self, response_data: Dict[str, Any], 
                                          info_messages: List[str]) -> Dict[str, Any]:
        """Add informational messages to response"""
        extended_info = response_data.get("@Message.ExtendedInfo", [])
        
        for msg in info_messages:
            # Create informational message (OK severity)
            info_message = {
                "@odata.type": "#Message.v1_1_1.Message",
                "MessageId": "Base.1.5.0.Success",
                "Message": msg,
                "Severity": "OK",
                "Resolution": "None"
            }
            extended_info.append(info_message)
        
        response_data["@Message.ExtendedInfo"] = extended_info
        return response_data

    def get_message_registry_info(self) -> Dict[str, Any]:
        """Get information about loaded message registries"""
        return {
            "LoadedRegistries": ["Base.1.5.0"],
            "SupportedMessageIds": list(self.base_registry.keys()),
            "TotalMessages": len(self.base_registry)
        }

# Global instance for convenience
_redfish_message_service = None

def get_redfish_message_service(config=None) -> RedfishMessageService:
    """Get global Redfish message service instance"""
    global _redfish_message_service
    if _redfish_message_service is None:
        _redfish_message_service = RedfishMessageService(config)
    return _redfish_message_service

def init_redfish_message_service(config):
    """Initialize global Redfish message service"""
    global _redfish_message_service 
    _redfish_message_service = RedfishMessageService(config)