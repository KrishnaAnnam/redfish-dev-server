#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Schema-based Property Validation Service for BMC Redfish Simulator
=================================================================
Provides validation for PATCH operations to ensure only writable properties
are modified according to Redfish schema definitions.

This service validates:
1. Property writeability based on schema annotations
2. Property data types and formats
3. Enumeration values and constraints
4. Required property dependencies
5. OEM property handling
"""

import json
import logging
import re
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class SchemaPropertyValidator:
    """Validates PATCH operations against Redfish schema property definitions"""
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.logger = logging.getLogger("SchemaValidator")
        
        # Load schema property definitions
        self.property_definitions = self._load_property_definitions()
        
    def _load_property_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Load property definitions for common Redfish resources"""
        return {
            # ComputerSystem properties
            "ComputerSystem": {
                "writable_properties": {
                    "AssetTag", "IndicatorLED", "LocationIndicatorActive", 
                    "PowerRestorePolicy", "BootSourceOverrideEnabled", 
                    "BootSourceOverrideTarget", "BootSourceOverrideMode",
                    "HostWatchdogTimer", "SystemType"
                },
                "readonly_properties": {
                    "Id", "Name", "Description", "Status", "PowerState", 
                    "BiosVersion", "ProcessorSummary", "MemorySummary",
                    "SerialNumber", "Model", "Manufacturer", "PartNumber",
                    "SKU", "UUID", "SystemType", "HostingRoles"
                },
                "oem_writable": True,
                "property_types": {
                    "AssetTag": "string",
                    "IndicatorLED": "enum",
                    "PowerRestorePolicy": "enum",
                    "BootSourceOverrideEnabled": "enum",
                    "BootSourceOverrideTarget": "enum",
                    "BootSourceOverrideMode": "enum"
                },
                "enum_values": {
                    "IndicatorLED": ["Lit", "Blinking", "Off"],
                    "PowerRestorePolicy": ["AlwaysOff", "AlwaysOn", "LastState"],
                    "BootSourceOverrideEnabled": ["Disabled", "Once", "Continuous"],
                    "BootSourceOverrideTarget": [
                        "None", "Pxe", "Floppy", "Cd", "Usb", "Hdd",
                        "BiosSetup", "Utilities", "Diags", "UefiTarget",
                        "SDCard", "UefiHttp", "RemoteDrive", "UefiBootNext"
                    ]
                }
            },
            
            # Manager properties
            "Manager": {
                "writable_properties": {
                    "DateTime", "DateTimeLocalOffset", "IndicatorLED",
                    "LocationIndicatorActive", "ServiceEntryPointUUID"
                },
                "readonly_properties": {
                    "Id", "Name", "Description", "Status", "ManagerType",
                    "Model", "FirmwareVersion", "SerialNumber", "PartNumber",
                    "PowerState", "UUID"
                },
                "oem_writable": True,
                "property_types": {
                    "DateTime": "datetime",
                    "DateTimeLocalOffset": "string",
                    "IndicatorLED": "enum"
                },
                "enum_values": {
                    "IndicatorLED": ["Lit", "Blinking", "Off"]
                }
            },
            
            # Chassis properties
            "Chassis": {
                "writable_properties": {
                    "AssetTag", "IndicatorLED", "LocationIndicatorActive"
                },
                "readonly_properties": {
                    "Id", "Name", "Description", "Status", "ChassisType",
                    "Model", "Manufacturer", "SerialNumber", "PartNumber",
                    "SKU", "WeightKg", "HeightMm", "WidthMm", "DepthMm"
                },
                "oem_writable": True,
                "property_types": {
                    "AssetTag": "string",
                    "IndicatorLED": "enum"
                },
                "enum_values": {
                    "IndicatorLED": ["Lit", "Blinking", "Off"]
                }
            },
            
            # EthernetInterface properties
            "EthernetInterface": {
                "writable_properties": {
                    "InterfaceEnabled", "AutoNeg", "SpeedMbps", "FullDuplex",
                    "MTUSize", "MacAddress", "VLAN", "IPv4Addresses",
                    "IPv6Addresses", "StaticNameServers", "HostName", "FQDN"
                },
                "readonly_properties": {
                    "Id", "Name", "Description", "Status", "LinkStatus",
                    "MACAddress", "PermanentMACAddress", "MaxIPv6StaticAddresses"
                },
                "oem_writable": True,
                "property_types": {
                    "InterfaceEnabled": "boolean",
                    "AutoNeg": "boolean", 
                    "SpeedMbps": "integer",
                    "FullDuplex": "boolean",
                    "MTUSize": "integer",
                    "MacAddress": "string"
                }
            },
            
            # Account properties  
            "ManagerAccount": {
                "writable_properties": {
                    "Password", "UserName", "RoleId", "Enabled",
                    "AccountTypes", "OEMAccountTypes"
                },
                "readonly_properties": {
                    "Id", "Name", "Description", "Created", "Modified"
                },
                "oem_writable": True,
                "property_types": {
                    "Password": "string",
                    "UserName": "string", 
                    "RoleId": "string",
                    "Enabled": "boolean"
                }
            },
            
            # LogEntry properties (limited writability)
            "LogEntry": {
                "writable_properties": {
                    "Resolution", "Resolved"
                },
                "readonly_properties": {
                    "Id", "Name", "Created", "EntryType", "Severity",
                    "Message", "MessageId", "MessageArgs"
                },
                "oem_writable": True,
                "property_types": {
                    "Resolution": "string",
                    "Resolved": "boolean"
                }
            },
            
            # BIOS properties
            "Bios": {
                "writable_properties": {
                    "Attributes"  # BIOS attributes are typically writable
                },
                "readonly_properties": {
                    "Id", "Name", "Description", "AttributeRegistry"
                },
                "oem_writable": True,
                "property_types": {
                    "Attributes": "object"
                }
            }
        }
    
    def validate_patch_properties(self, resource_type: str, resource_data: Dict[str, Any], 
                                 patch_data: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate PATCH operation properties against schema
        
        :param resource_type: Type of resource (e.g., 'ComputerSystem', 'Manager')
        :param resource_data: Current resource data
        :param patch_data: Data to be patched
        :return: (is_valid, error_messages, filtered_patch_data)
        """
        try:
            # Get resource schema definition
            schema_def = self.property_definitions.get(resource_type, {})
            if not schema_def:
                # If no schema defined, allow all properties (backwards compatibility)
                self.logger.warning(f"No schema validation available for {resource_type}")
                return True, [], patch_data
            
            writable_properties = schema_def.get("writable_properties", set())
            readonly_properties = schema_def.get("readonly_properties", set()) 
            oem_writable = schema_def.get("oem_writable", True)
            property_types = schema_def.get("property_types", {})
            enum_values = schema_def.get("enum_values", {})
            
            errors = []
            filtered_data = {}
            
            # Validate each property in the PATCH data
            for prop_name, prop_value in patch_data.items():
                
                # Handle OEM properties
                if prop_name == "Oem":
                    if oem_writable:
                        if isinstance(prop_value, dict):
                            filtered_data[prop_name] = prop_value
                        else:
                            errors.append(f"Property 'Oem' must be an object")
                    else:
                        errors.append(f"OEM properties are not writable for {resource_type}")
                    continue
                
                # Check if property is writable
                if prop_name in readonly_properties:
                    errors.append(f"Property '{prop_name}' is read-only and cannot be modified")
                    continue
                
                if prop_name not in writable_properties:
                    errors.append(f"Property '{prop_name}' is not writable for {resource_type}")
                    continue
                
                # Validate property type and value
                validation_error = self._validate_property_value(
                    prop_name, prop_value, property_types, enum_values
                )
                if validation_error:
                    errors.append(validation_error)
                    continue
                
                # Property is valid, add to filtered data
                filtered_data[prop_name] = prop_value
            
            # Additional cross-property validations
            cross_validation_errors = self._validate_cross_property_constraints(
                resource_type, resource_data, filtered_data
            )
            errors.extend(cross_validation_errors)
            
            is_valid = len(errors) == 0
            return is_valid, errors, filtered_data
            
        except Exception as e:
            self.logger.error(f"Error validating PATCH properties: {e}")
            return False, [f"Schema validation error: {str(e)}"], {}
    
    def _validate_property_value(self, prop_name: str, prop_value: Any, 
                                property_types: Dict[str, str], enum_values: Dict[str, List[str]]) -> Optional[str]:
        """Validate individual property value against type and constraints"""
        
        # Get expected type
        expected_type = property_types.get(prop_name)
        if not expected_type:
            return None  # No type validation available
        
        # Type validation
        if expected_type == "string" and not isinstance(prop_value, str):
            return f"Property '{prop_name}' must be a string"
        elif expected_type == "integer" and not isinstance(prop_value, int):
            return f"Property '{prop_name}' must be an integer"
        elif expected_type == "boolean" and not isinstance(prop_value, bool):
            return f"Property '{prop_name}' must be a boolean"
        elif expected_type == "number" and not isinstance(prop_value, (int, float)):
            return f"Property '{prop_name}' must be a number"
        elif expected_type == "object" and not isinstance(prop_value, dict):
            return f"Property '{prop_name}' must be an object"
        elif expected_type == "array" and not isinstance(prop_value, list):
            return f"Property '{prop_name}' must be an array"
        elif expected_type == "datetime":
            if not isinstance(prop_value, str) or not self._validate_datetime_format(prop_value):
                return f"Property '{prop_name}' must be a valid ISO 8601 datetime string"
        
        # Enum validation
        if prop_name in enum_values:
            valid_values = enum_values[prop_name]
            if prop_value not in valid_values:
                return f"Property '{prop_name}' must be one of: {', '.join(valid_values)}"
        
        # String length validation
        if expected_type == "string" and isinstance(prop_value, str):
            if len(prop_value) > 255:  # Common Redfish string length limit
                return f"Property '{prop_name}' exceeds maximum length of 255 characters"
        
        # Integer range validation (common constraints)
        if expected_type == "integer" and isinstance(prop_value, int):
            if prop_name in ["MTUSize"] and (prop_value < 68 or prop_value > 9000):
                return f"Property '{prop_name}' must be between 68 and 9000"
            elif prop_name in ["SpeedMbps"] and prop_value < 0:
                return f"Property '{prop_name}' must be non-negative"
        
        return None
    
    def _validate_datetime_format(self, datetime_str: str) -> bool:
        """Validate ISO 8601 datetime format"""
        try:
            # Try parsing common ISO 8601 formats
            for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", 
                       "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"]:
                try:
                    datetime.strptime(datetime_str, fmt)
                    return True
                except ValueError:
                    continue
            return False
        except Exception:
            return False
    
    def _validate_cross_property_constraints(self, resource_type: str, 
                                           resource_data: Dict[str, Any], 
                                           patch_data: Dict[str, Any]) -> List[str]:
        """Validate constraints that span multiple properties"""
        errors = []
        
        # ComputerSystem specific validations
        if resource_type == "ComputerSystem":
            # Boot override validations
            if "BootSourceOverrideEnabled" in patch_data:
                enabled = patch_data["BootSourceOverrideEnabled"]
                target = patch_data.get("BootSourceOverrideTarget", resource_data.get("BootSourceOverrideTarget"))
                
                if enabled in ["Once", "Continuous"] and target == "None":
                    errors.append("BootSourceOverrideTarget cannot be 'None' when BootSourceOverrideEnabled is 'Once' or 'Continuous'")
            
            # Power policy validations
            if "PowerRestorePolicy" in patch_data:
                policy = patch_data["PowerRestorePolicy"]
                power_state = resource_data.get("PowerState", "Off")
                if policy == "LastState" and power_state == "Off":
                    # This is just a warning, not an error
                    pass
        
        # EthernetInterface specific validations
        elif resource_type == "EthernetInterface":
            # Interface enabled vs configuration
            if "InterfaceEnabled" in patch_data and not patch_data["InterfaceEnabled"]:
                # When disabling interface, certain properties become irrelevant
                if any(prop in patch_data for prop in ["IPv4Addresses", "IPv6Addresses"]):
                    # This is allowed but might generate a warning
                    pass
            
            # AutoNeg vs manual speed/duplex
            if "AutoNeg" in patch_data and not patch_data["AutoNeg"]:
                if "SpeedMbps" not in patch_data and "SpeedMbps" not in resource_data:
                    errors.append("When AutoNeg is disabled, SpeedMbps must be specified")
                if "FullDuplex" not in patch_data and "FullDuplex" not in resource_data:
                    errors.append("When AutoNeg is disabled, FullDuplex must be specified")
        
        # ManagerAccount specific validations
        elif resource_type == "ManagerAccount":
            # Password policy validations (example)
            if "Password" in patch_data:
                password = patch_data["Password"]
                if len(password) < 8:
                    errors.append("Password must be at least 8 characters long")
                if not re.search(r"[A-Z]", password):
                    errors.append("Password must contain at least one uppercase letter")
                if not re.search(r"[a-z]", password):
                    errors.append("Password must contain at least one lowercase letter")
                if not re.search(r"\d", password):
                    errors.append("Password must contain at least one digit")
        
        return errors
    
    def get_writable_properties(self, resource_type: str) -> Set[str]:
        """Get list of writable properties for a resource type"""
        schema_def = self.property_definitions.get(resource_type, {})
        writable = schema_def.get("writable_properties", set())
        
        # Add Oem if OEM properties are writable
        if schema_def.get("oem_writable", True):
            writable = writable.union({"Oem"})
        
        return writable
    
    def get_readonly_properties(self, resource_type: str) -> Set[str]:
        """Get list of read-only properties for a resource type"""
        schema_def = self.property_definitions.get(resource_type, {})
        return schema_def.get("readonly_properties", set())
    
    def is_property_writable(self, resource_type: str, property_name: str) -> bool:
        """Check if a specific property is writable for a resource type"""
        writable_props = self.get_writable_properties(resource_type)
        return property_name in writable_props
    
    def get_property_constraints(self, resource_type: str, property_name: str) -> Dict[str, Any]:
        """Get constraints for a specific property"""
        schema_def = self.property_definitions.get(resource_type, {})
        
        constraints = {}
        
        # Type constraint
        property_types = schema_def.get("property_types", {})
        if property_name in property_types:
            constraints["type"] = property_types[property_name]
        
        # Enum constraint
        enum_values = schema_def.get("enum_values", {})
        if property_name in enum_values:
            constraints["enum"] = enum_values[property_name]
        
        return constraints