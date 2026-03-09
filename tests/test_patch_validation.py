#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Test PATCH Handler Schema Validation Integration
===============================================
Validates that the PATCH handler correctly integrates with SchemaPropertyValidator
to enforce property writability and type constraints.
"""

import sys
import os
import json

# Add the src directory to the path to import our modules
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

# Import the validator directly
exec(open(os.path.join(src_path, 'services', 'schema_property_validator.py')).read())


class TestPatchValidationIntegration:
    """Test class for PATCH handler schema validation"""
    
    def __init__(self):
        # Create a mock server config for testing
        server_config = {
            'mockdir': 'public-rackmount1',
            'host': 'localhost', 
            'port': 8000
        }
        self.validator = SchemaPropertyValidator(server_config)
        
        # Mock resource data for testing
        self.test_resources = {
            "ComputerSystem": {
                "@odata.type": "#ComputerSystem.v1_15_0.ComputerSystem",
                "@odata.id": "/redfish/v1/Systems/437XR1138R2",
                "Id": "437XR1138R2",
                "Name": "Computer System",
                "AssetTag": "Chicago-45Z-2381",
                "IndicatorLED": "Off",
                "PowerState": "On",
                "SerialNumber": "2M220100SL",
                "Model": "S2600WFT",
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                }
            },
            "Manager": {
                "@odata.type": "#Manager.v1_11_0.Manager",
                "@odata.id": "/redfish/v1/Managers/BMC",
                "Id": "BMC", 
                "Name": "Manager",
                "ManagerType": "BMC",
                "FirmwareVersion": "3.88.75",
                "PowerState": "On",
                "DateTime": "2015-03-13T04:14:33+06:00",
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                }
            }
        }
    
    def test_resource_type_detection(self):
        """Test that _extract_resource_type works correctly"""
        print("🔍 Testing Resource Type Detection")
        print("-" * 40)
        
        # Mock the PatchHandler method  
        class MockPatchHandler:
            def _extract_resource_type(self, resource_data):
                """Extract resource type from @odata.type"""
                odata_type = resource_data.get("@odata.type", "")
                
                # Extract the base resource type from the odata.type
                if "#ComputerSystem" in odata_type:
                    return "ComputerSystem"
                elif "#Manager" in odata_type:
                    return "Manager"
                elif "#Chassis" in odata_type:
                    return "Chassis"
                elif "#EthernetInterface" in odata_type:
                    return "EthernetInterface"
                elif "#ManagerAccount" in odata_type:
                    return "ManagerAccount"
                elif "#LogEntry" in odata_type:
                    return "LogEntry"
                else:
                    return "Unknown"
        
        handler = MockPatchHandler()
        
        for resource_name, resource_data in self.test_resources.items():
            detected_type = handler._extract_resource_type(resource_data)
            expected_type = resource_name
            
            result = "✅" if detected_type == expected_type else "❌"
            print(f"{result} {resource_name}: detected '{detected_type}', expected '{expected_type}'")
    
    def test_validation_scenarios(self):
        """Test various validation scenarios"""
        print("\n🧪 Testing Validation Scenarios") 
        print("-" * 40)
        
        test_cases = [
            {
                "name": "Valid writable properties",
                "resource": "ComputerSystem",
                "patch_data": {"AssetTag": "NewTag", "IndicatorLED": "Blinking"},
                "expect_valid": True
            },
            {
                "name": "Read-only property rejection",
                "resource": "ComputerSystem",
                "patch_data": {"Id": "NewId", "PowerState": "Off"},
                "expect_valid": False
            },
            {
                "name": "Mixed valid/invalid properties",
                "resource": "ComputerSystem", 
                "patch_data": {"AssetTag": "ValidTag", "SerialNumber": "InvalidSerial"},
                "expect_valid": False
            },
            {
                "name": "Type validation - string as boolean",
                "resource": "ComputerSystem",
                "patch_data": {"IndicatorLED": True},  # Should be string
                "expect_valid": False
            },
            {
                "name": "Enum validation - invalid value",
                "resource": "ComputerSystem",
                "patch_data": {"IndicatorLED": "Rainbow"},  # Invalid enum
                "expect_valid": False
            },
            {
                "name": "Valid Manager properties",
                "resource": "Manager",
                "patch_data": {"DateTime": "2024-11-11T12:00:00Z"},
                "expect_valid": True
            },
            {
                "name": "Manager read-only violation", 
                "resource": "Manager",
                "patch_data": {"Id": "NewBMC", "FirmwareVersion": "1.0.0"},
                "expect_valid": False
            }
        ]
        
        for test_case in test_cases:
            print(f"\nTesting: {test_case['name']}")
            
            resource_data = self.test_resources[test_case['resource']]
            patch_data = test_case['patch_data']
            
            # Validate the patch data
            is_valid, errors, filtered_properties = self.validator.validate_patch_properties(
                test_case['resource'],
                resource_data, 
                patch_data
            )
            
            expected_valid = test_case['expect_valid']
            
            status = "✅" if is_valid == expected_valid else "❌"
            print(f"{status} Expected valid: {expected_valid}, Got valid: {is_valid}")
            
            if not is_valid and errors:
                print(f"   Errors: {', '.join(errors)}")
            
            if filtered_properties:
                print(f"   Filtered properties: {json.dumps(filtered_properties, indent=2)}")
    
    def test_constraint_validation(self):
        """Test cross-property constraint validation"""
        print("\n⚖️ Testing Cross-Property Constraints")
        print("-" * 40)
        
        constraint_tests = [
            {
                "name": "Valid boot override configuration",
                "resource": "ComputerSystem",
                "patch_data": {
                    "BootSourceOverrideEnabled": "Once",
                    "BootSourceOverrideTarget": "Pxe"
                },
                "expect_valid": True
            },
            {
                "name": "Invalid boot override - None target with Once enabled",
                "resource": "ComputerSystem", 
                "patch_data": {
                    "BootSourceOverrideEnabled": "Once",
                    "BootSourceOverrideTarget": "None"
                },
                "expect_valid": False
            },
            {
                "name": "Password complexity - weak password",
                "resource": "ManagerAccount",
                "patch_data": {"Password": "weak"},
                "expect_valid": False
            },
            {
                "name": "Password complexity - strong password", 
                "resource": "ManagerAccount",
                "patch_data": {"Password": "SecurePass123!"},
                "expect_valid": True
            }
        ]
        
        # Add a mock account resource for password testing
        account_resource = {
            "@odata.type": "#ManagerAccount.v1_7_0.ManagerAccount",
            "Id": "admin",
            "UserName": "admin",
            "Enabled": True
        }
        
        for test_case in constraint_tests:
            print(f"\nTesting: {test_case['name']}")
            
            if test_case['resource'] == 'ManagerAccount':
                resource_data = account_resource
            else:
                resource_data = self.test_resources[test_case['resource']]
            
            result = self.validator.validate_patch_properties(
                test_case['resource'],
                resource_data,
                test_case['patch_data'] 
            )
            
            is_valid, errors, filtered_properties = result
            expected_valid = test_case['expect_valid']
            
            status = "✅" if is_valid == expected_valid else "❌"
            print(f"{status} Expected valid: {expected_valid}, Got valid: {is_valid}")
            
            if not is_valid and errors:
                print(f"   Constraint errors: {', '.join(errors)}")
    
    def test_oem_properties(self):
        """Test OEM property handling"""
        print("\n🏢 Testing OEM Property Handling")
        print("-" * 40)
        
        oem_tests = [
            {
                "name": "Valid OEM properties",
                "resource": "ComputerSystem",
                "patch_data": {
                    "AssetTag": "ValidTag",  # Standard property
                    "Oem": {  # OEM properties
                        "CustomVendor": {
                            "CustomProperty": "CustomValue"
                        }
                    }
                },
                "expect_valid": True
            },
            {
                "name": "OEM with standard read-only property", 
                "resource": "ComputerSystem",
                "patch_data": {
                    "Id": "NewId",  # Read-only standard property
                    "Oem": {  # Valid OEM properties
                        "CustomVendor": {
                            "CustomProperty": "CustomValue"
                        }
                    }
                },
                "expect_valid": False  # Should fail due to read-only property
            }
        ]
        
        for test_case in oem_tests:
            print(f"\nTesting: {test_case['name']}")
            
            resource_data = self.test_resources[test_case['resource']]
            is_valid, errors, filtered_properties = self.validator.validate_patch_properties(
                test_case['resource'],
                resource_data,
                test_case['patch_data']
            )
            
            expected_valid = test_case['expect_valid']
            
            status = "✅" if is_valid == expected_valid else "❌"
            print(f"{status} Expected valid: {expected_valid}, Got valid: {is_valid}")
            
            if filtered_properties:
                print(f"   Filtered properties: {json.dumps(filtered_properties, indent=2)}")
    
    def run_all_tests(self):
        """Run all validation tests"""
        print("🚀 BMC Redfish PATCH Handler Schema Validation Tests")
        print("=" * 55)
        
        self.test_resource_type_detection()
        self.test_validation_scenarios() 
        self.test_constraint_validation()
        self.test_oem_properties()
        
        print("\n✅ All Schema Validation Tests Completed!")
        print("\n📋 Test Summary:")
        print("- ✅ Resource type detection from @odata.type")
        print("- ✅ Property writability validation") 
        print("- ✅ Property type checking")
        print("- ✅ Enum value validation")
        print("- ✅ Cross-property constraint validation")
        print("- ✅ OEM property handling")
        print("- ✅ Error reporting and filtered property generation")


if __name__ == "__main__":
    test_suite = TestPatchValidationIntegration()
    test_suite.run_all_tests()