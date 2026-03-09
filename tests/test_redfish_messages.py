#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Simple PATCH Handler Test with Redfish Messages
==============================================
Tests the schema validation and message generation functionality
independently to demonstrate Redfish message compliance.
"""

import sys
import os
sys.path.append('src')

from services.schema_property_validator import SchemaPropertyValidator
from services.redfish_message_service import get_redfish_message_service
import json


def test_redfish_message_generation():
    """Test Redfish message generation for various validation scenarios"""
    print("🚀 Testing Redfish Message Generation")
    print("=" * 45)
    
    # Create mock config
    config = type('Config', (), {'mock_dir': 'mockups/public-rackmount1'})()
    
    # Initialize services
    validator = SchemaPropertyValidator(config)
    message_service = get_redfish_message_service(config)
    
    # Test scenarios
    test_scenarios = [
        {
            "name": "Read-only property violation",
            "resource_type": "ComputerSystem",
            "resource_data": {
                "@odata.type": "#ComputerSystem.v1_15_0.ComputerSystem",
                "@odata.id": "/redfish/v1/Systems/437XR1138R2",
                "Id": "437XR1138R2",
                "Name": "Computer System",
                "AssetTag": "Chicago-45Z-2381",
                "PowerState": "On"
            },
            "patch_data": {
                "Id": "HackedSystem",
                "PowerState": "Off", 
                "AssetTag": "ValidTag"
            }
        },
        {
            "name": "Type validation error",
            "resource_type": "ComputerSystem", 
            "resource_data": {
                "@odata.type": "#ComputerSystem.v1_15_0.ComputerSystem",
                "@odata.id": "/redfish/v1/Systems/437XR1138R2",
                "Id": "437XR1138R2",
                "IndicatorLED": "Off"
            },
            "patch_data": {
                "IndicatorLED": True  # Should be string, not boolean
            }
        },
        {
            "name": "Enum validation error",
            "resource_type": "ComputerSystem",
            "resource_data": {
                "@odata.type": "#ComputerSystem.v1_15_0.ComputerSystem",
                "@odata.id": "/redfish/v1/Systems/437XR1138R2",
                "Id": "437XR1138R2",
                "IndicatorLED": "Off"
            },
            "patch_data": {
                "IndicatorLED": "Rainbow"  # Invalid enum value
            }
        },
        {
            "name": "Valid properties",
            "resource_type": "ComputerSystem",
            "resource_data": {
                "@odata.type": "#ComputerSystem.v1_15_0.ComputerSystem",
                "@odata.id": "/redfish/v1/Systems/437XR1138R2",
                "Id": "437XR1138R2",
                "AssetTag": "Original-Tag",
                "IndicatorLED": "Off"
            },
            "patch_data": {
                "AssetTag": "New-Asset-Tag",
                "IndicatorLED": "Blinking"
            }
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{i}. Testing: {scenario['name']}")
        print("-" * 40)
        
        # Perform validation
        is_valid, errors, filtered_data = validator.validate_patch_properties(
            scenario['resource_type'],
            scenario['resource_data'],
            scenario['patch_data']
        )
        
        if is_valid:
            # Create success response
            success_response = message_service.create_success_response()
            print("✅ Validation passed")
            print(f"📝 Filtered properties: {json.dumps(filtered_data, indent=2)}")
            print(f"📋 Success message: {json.dumps(success_response, indent=2)}")
        else:
            # Create error response
            error_response, status_code = message_service.create_validation_error_response(errors)
            print(f"❌ Validation failed (HTTP {status_code})")
            print(f"📋 Error response:")
            print(json.dumps(error_response, indent=2))
            
            # Analyze the Redfish message compliance
            analyze_redfish_compliance(error_response)
    
    print(f"\n✅ Redfish Message Generation Test Completed!")


def analyze_redfish_compliance(error_response):
    """Analyze the error response for Redfish compliance"""
    print(f"\n📊 Redfish Compliance Analysis:")
    
    if "error" in error_response and "@Message.ExtendedInfo" in error_response["error"]:
        extended_info = error_response["error"]["@Message.ExtendedInfo"]
        print(f"   ✅ ExtendedInfo contains {len(extended_info)} messages")
        
        for i, message in enumerate(extended_info):
            print(f"\n   Message #{i+1}:")
            
            # Check required fields
            required_fields = ["@odata.type", "MessageId", "Message", "Severity", "Resolution"]
            for field in required_fields:
                if field in message:
                    print(f"     ✅ {field}: {message[field]}")
                else:
                    print(f"     ❌ Missing {field}")
            
            # Check optional fields
            optional_fields = ["MessageArgs", "RelatedProperties"]
            for field in optional_fields:
                if field in message:
                    print(f"     📋 {field}: {message[field]}")
                    
            # Validate MessageId format
            message_id = message.get("MessageId", "")
            if message_id.count(".") == 2:
                registry, version, message_key = message_id.split(".")
                print(f"     ✅ MessageId format: {registry}.{version}.{message_key}")
            else:
                print(f"     ❌ Invalid MessageId format: {message_id}")
    else:
        print("   ❌ Missing ExtendedInfo structure")


if __name__ == "__main__":
    test_redfish_message_generation()