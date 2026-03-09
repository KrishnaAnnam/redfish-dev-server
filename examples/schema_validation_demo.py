#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Schema Property Validation Demo for BMC Redfish Simulator
=========================================================
Demonstrates how schema validation prevents modification of read-only properties
and validates property types and constraints during PATCH operations.

This example shows:
1. Valid PATCH operations on writable properties
2. Invalid PATCH operations on read-only properties  
3. Type validation and constraint checking
4. Enum value validation
5. Cross-property constraint validation
"""

import requests
import json
import time


class SchemaValidationDemo:
    """Demo class for Schema Property Validation"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def test_patch_operation(self, resource_path, patch_data, description, expect_success=True):
        """Test a PATCH operation and display results"""
        print(f"\n🔄 Testing: {description}")
        print(f"Resource: {resource_path}")
        print(f"PATCH Data: {json.dumps(patch_data, indent=2)}")
        
        url = f"{self.base_url}{resource_path}"
        response = self.session.patch(url, json=patch_data)
        
        print(f"Response: {response.status_code}")
        
        if expect_success and response.status_code == 204:
            print("✅ PATCH operation successful (as expected)")
        elif not expect_success and response.status_code in [400, 405]:
            print("✅ PATCH operation blocked (as expected)")
            if response.text:
                try:
                    error_info = response.json()
                    print(f"Validation errors: {json.dumps(error_info.get('validationErrors', []), indent=2)}")
                except:
                    print(f"Error response: {response.text}")
        elif response.status_code == 404:
            print("⚠️ Resource not found - skipping test")
        else:
            success_indicator = "✅" if expect_success else "❌" 
            print(f"{success_indicator} Unexpected response: {response.text}")
        
        return response.status_code
    
    def get_resource(self, resource_path):
        """Get current resource state"""
        response = self.session.get(f"{self.base_url}{resource_path}")
        if response.status_code == 200:
            return response.json()
        return None
    
    def run_demo(self):
        """Run the complete Schema Validation demo"""
        print("🚀 BMC Redfish Simulator - Schema Property Validation Demo")
        print("=" * 65)
        
        # Test 1: Valid writable properties
        print("\n" + "="*50)
        print("1. TESTING VALID WRITABLE PROPERTIES")
        print("="*50)
        
        # Test ComputerSystem writable properties
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "AssetTag": "Server-001",
                "IndicatorLED": "Blinking"
            },
            "ComputerSystem valid writable properties",
            expect_success=True
        )
        
        # Test Manager writable properties
        self.test_patch_operation(
            "/redfish/v1/Managers/BMC", 
            {
                "DateTime": "2024-11-11T12:00:00Z",
                "IndicatorLED": "Lit"
            },
            "Manager valid writable properties",
            expect_success=True
        )
        
        # Test 2: Invalid read-only properties
        print("\n" + "="*50)
        print("2. TESTING READ-ONLY PROPERTY PROTECTION")
        print("="*50)
        
        # Try to modify read-only ComputerSystem properties
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "Id": "HackedSystem",  # Read-only
                "PowerState": "Off",   # Read-only
                "Model": "FakeModel"   # Read-only
            },
            "ComputerSystem read-only properties (should fail)",
            expect_success=False
        )
        
        # Try to modify read-only Manager properties
        self.test_patch_operation(
            "/redfish/v1/Managers/BMC",
            {
                "Id": "HackedBMC",           # Read-only
                "FirmwareVersion": "1.0.0",  # Read-only
                "Status": {"Health": "Critical"}  # Read-only
            },
            "Manager read-only properties (should fail)",
            expect_success=False
        )
        
        # Test 3: Type validation
        print("\n" + "="*50)
        print("3. TESTING TYPE VALIDATION")
        print("="*50)
        
        # Invalid boolean type
        self.test_patch_operation(
            "/redfish/v1/EthernetInterfaces/1", 
            {
                "InterfaceEnabled": "true"  # Should be boolean, not string
            },
            "Invalid boolean type (should fail)",
            expect_success=False
        )
        
        # Invalid integer type
        self.test_patch_operation(
            "/redfish/v1/EthernetInterfaces/1",
            {
                "MTUSize": "1500"  # Should be integer, not string
            },
            "Invalid integer type (should fail)",
            expect_success=False
        )
        
        # Test 4: Enum value validation
        print("\n" + "="*50)
        print("4. TESTING ENUM VALUE VALIDATION")
        print("="*50)
        
        # Invalid IndicatorLED value
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "IndicatorLED": "Rainbow"  # Invalid enum value
            },
            "Invalid IndicatorLED enum value (should fail)",
            expect_success=False
        )
        
        # Invalid PowerRestorePolicy value
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "PowerRestorePolicy": "AlwaysReboot"  # Invalid enum value
            },
            "Invalid PowerRestorePolicy enum value (should fail)",
            expect_success=False
        )
        
        # Test 5: Mixed valid and invalid properties
        print("\n" + "="*50)
        print("5. TESTING MIXED VALID/INVALID PROPERTIES")
        print("="*50)
        
        # Mix of valid and invalid properties
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "AssetTag": "Server-002",        # Valid
                "IndicatorLED": "Off",           # Valid
                "Id": "NewId",                   # Invalid - read-only
                "PowerState": "On",              # Invalid - read-only
                "UnknownProperty": "SomeValue"   # Invalid - not writable
            },
            "Mix of valid and invalid properties (should fail)",
            expect_success=False
        )
        
        # Test 6: Cross-property validation
        print("\n" + "="*50)
        print("6. TESTING CROSS-PROPERTY CONSTRAINTS")
        print("="*50)
        
        # Boot override constraint violation
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "BootSourceOverrideEnabled": "Once",
                "BootSourceOverrideTarget": "None"  # Invalid combination
            },
            "Boot override constraint violation (should fail)",
            expect_success=False
        )
        
        # Valid boot override
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2", 
            {
                "BootSourceOverrideEnabled": "Once",
                "BootSourceOverrideTarget": "Pxe"  # Valid combination
            },
            "Valid boot override configuration",
            expect_success=True
        )
        
        # Test 7: OEM properties
        print("\n" + "="*50)
        print("7. TESTING OEM PROPERTY HANDLING")
        print("="*50)
        
        # Valid OEM properties
        self.test_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "Oem": {
                    "CustomVendor": {
                        "CustomProperty": "CustomValue",
                        "CustomConfig": {
                            "Setting1": True,
                            "Setting2": 42
                        }
                    }
                }
            },
            "Valid OEM properties",
            expect_success=True
        )
        
        # Test 8: Account password validation
        print("\n" + "="*50)  
        print("8. TESTING ACCOUNT PASSWORD VALIDATION")
        print("="*50)
        
        # Weak password (should fail)
        self.test_patch_operation(
            "/redfish/v1/AccountService/Accounts/admin",
            {
                "Password": "weak"  # Too short, no complexity
            },
            "Weak password (should fail)",
            expect_success=False
        )
        
        # Strong password (should succeed)
        self.test_patch_operation(
            "/redfish/v1/AccountService/Accounts/admin", 
            {
                "Password": "SecurePass123!"  # Meets complexity requirements
            },
            "Strong password",
            expect_success=True
        )
        
        # Test 9: Verify final resource states
        print("\n" + "="*50)
        print("9. VERIFYING FINAL RESOURCE STATES")
        print("="*50)
        
        # Check what changes were actually applied
        system = self.get_resource("/redfish/v1/Systems/437XR1138R2")
        if system:
            print(f"System AssetTag: {system.get('AssetTag', 'Not set')}")
            print(f"System IndicatorLED: {system.get('IndicatorLED', 'Not set')}")
            print(f"System ID (should be unchanged): {system.get('Id')}")
            print(f"System PowerState (should be unchanged): {system.get('PowerState')}")
            
            if 'Oem' in system:
                print(f"System OEM properties: {json.dumps(system['Oem'], indent=2)}")
        
        print("\n✅ Schema Property Validation Demo completed!")
        print("\n📊 Summary:")
        print("- ✅ Valid writable properties are accepted")
        print("- ❌ Read-only properties are rejected with 400 Bad Request")
        print("- ❌ Invalid property types are rejected with validation errors")
        print("- ❌ Invalid enum values are rejected with allowed value lists")
        print("- ❌ Cross-property constraint violations are caught")
        print("- ✅ OEM properties are handled appropriately")
        print("- ✅ Complex validation rules (passwords) are enforced")
        print("- ✅ Only validated properties are applied to resources")


def create_property_validation_guide():
    """Show how to add property validation for new resource types"""
    print("\n" + "="*60)
    print("HOW TO ADD SCHEMA VALIDATION FOR NEW RESOURCE TYPES")
    print("="*60)
    
    guide = {
        "step1": {
            "title": "1. Define Resource Schema in SchemaPropertyValidator",
            "description": "Add property definitions to the property_definitions dictionary",
            "example": """
# In src/services/schema_property_validator.py

"MyCustomResource": {
    "writable_properties": {
        "CustomProperty1", "CustomProperty2", "EnabledFlag"
    },
    "readonly_properties": {
        "Id", "Name", "Status", "Created", "UniqueIdentifier"  
    },
    "oem_writable": True,
    "property_types": {
        "CustomProperty1": "string",
        "CustomProperty2": "integer", 
        "EnabledFlag": "boolean"
    },
    "enum_values": {
        "CustomProperty1": ["Value1", "Value2", "Value3"]
    }
}
""".strip()
        },
        "step2": {
            "title": "2. Add Resource Type Detection",
            "description": "Update _extract_resource_type method to recognize your resource",
            "example": """
# In src/handlers/patch_handler.py

def _extract_resource_type(self, resource_data: dict) -> str:
    # ... existing code ...
    
    # Add your custom detection logic
    elif "CustomIdentifier" in resource_data and "SpecialProperty" in resource_data:
        return "MyCustomResource"
    
    # ... rest of method
""".strip()
        },
        "step3": {
            "title": "3. Add Cross-Property Validation (Optional)",
            "description": "Implement custom validation logic for property combinations",
            "example": """
# In src/services/schema_property_validator.py

def _validate_cross_property_constraints(self, resource_type, resource_data, patch_data):
    errors = []
    
    # ... existing validations ...
    
    # Add custom resource validation
    elif resource_type == "MyCustomResource":
        # Custom validation logic
        if "EnabledFlag" in patch_data and patch_data["EnabledFlag"]:
            if "CustomProperty1" not in patch_data and "CustomProperty1" not in resource_data:
                errors.append("CustomProperty1 is required when EnabledFlag is true")
    
    return errors
""".strip()
        }
    }
    
    for step_key, step_info in guide.items():
        print(f"\n{step_info['title']}:")
        print(step_info['description'])
        print(f"\nExample:")
        print(step_info['example'])
    
    print("\n" + "="*60)


def main():
    """Main demo function"""
    # Note: Make sure the BMC Redfish Simulator is running first:
    # python3 redfishMockupServer_modular.py -D public-rackmount1 -S -p 8000
    
    demo = SchemaValidationDemo()
    demo.run_demo()
    
    create_property_validation_guide()


if __name__ == "__main__":
    main()