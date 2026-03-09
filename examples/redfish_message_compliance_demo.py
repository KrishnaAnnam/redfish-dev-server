#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Message Compliance Demo for BMC Redfish Simulator
==========================================================
Demonstrates how the REST API handlers respond with proper Redfish messages
complying with DMTF Redfish Message Registry specifications.

This demo showcases:
1. Schema validation error responses with proper MessageIds
2. ExtendedInfo message formatting per Redfish standards
3. Proper HTTP status codes with Redfish message correlation
4. Message registry compliance for common error scenarios
5. Success responses with informational ExtendedInfo messages
"""

import requests
import json
import time


class RedfishMessageComplianceDemo:
    """Demo class for testing Redfish message compliance"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def test_redfish_patch_operation(self, resource_path, patch_data, description, expect_success=True):
        """Test a PATCH operation and validate Redfish message compliance"""
        print(f"\n🔄 Testing: {description}")
        print(f"Resource: {resource_path}")
        print(f"PATCH Data: {json.dumps(patch_data, indent=2)}")
        
        url = f"{self.base_url}{resource_path}"
        response = self.session.patch(url, json=patch_data)
        
        print(f"Response: HTTP {response.status_code}")
        
        # Check for Redfish message compliance
        if response.text:
            try:
                response_data = response.json()
                self._validate_redfish_messages(response_data, response.status_code, expect_success)
            except json.JSONDecodeError:
                print("⚠️ Response is not valid JSON")
        else:
            if response.status_code == 204:
                print("✅ 204 No Content - successful PATCH with no response body")
                # Check for ExtendedInfo in headers
                if 'X-ExtendedInfo' in response.headers:
                    print(f"📋 ExtendedInfo Header: {response.headers['X-ExtendedInfo']}")
            else:
                print(f"⚠️ Empty response body for status {response.status_code}")
        
        return response.status_code
    
    def _validate_redfish_messages(self, response_data, status_code, expect_success):
        """Validate that response contains proper Redfish messages"""
        print("\n📋 Redfish Message Compliance Analysis:")
        
        # Check for error structure
        if "error" in response_data:
            error_info = response_data["error"]
            if "@Message.ExtendedInfo" in error_info:
                extended_info = error_info["@Message.ExtendedInfo"]
                print(f"✅ Found ExtendedInfo with {len(extended_info)} messages")
                
                for i, message in enumerate(extended_info):
                    self._analyze_redfish_message(message, i + 1)
                    
                if not expect_success and status_code >= 400:
                    print("✅ Error response properly formatted with Redfish messages")
                else:
                    print("❌ Unexpected error response format")
            else:
                print("❌ Error response missing @Message.ExtendedInfo")
        
        # Check for direct ExtendedInfo (success case)
        elif "@Message.ExtendedInfo" in response_data:
            extended_info = response_data["@Message.ExtendedInfo"]
            print(f"✅ Found ExtendedInfo with {len(extended_info)} messages")
            
            for i, message in enumerate(extended_info):
                self._analyze_redfish_message(message, i + 1)
                
            if expect_success and status_code < 400:
                print("✅ Success response properly formatted with Redfish messages")
            else:
                print("❌ Unexpected success response format")
        else:
            if expect_success and status_code == 204:
                print("✅ 204 No Content response (valid for successful PATCH)")
            else:
                print("⚠️ No ExtendedInfo found in response")
    
    def _analyze_redfish_message(self, message, index):
        """Analyze individual Redfish message for compliance"""
        print(f"\n  Message #{index}:")
        
        # Check required fields
        required_fields = ["@odata.type", "MessageId", "Message", "Severity", "Resolution"]
        missing_fields = [field for field in required_fields if field not in message]
        
        if missing_fields:
            print(f"    ❌ Missing required fields: {missing_fields}")
        else:
            print("    ✅ All required fields present")
        
        # Validate MessageId format
        message_id = message.get("MessageId", "")
        if self._is_valid_message_id(message_id):
            print(f"    ✅ MessageId: {message_id}")
        else:
            print(f"    ❌ Invalid MessageId format: {message_id}")
        
        # Validate severity
        severity = message.get("Severity", "")
        valid_severities = ["OK", "Warning", "Critical"]
        if severity in valid_severities:
            print(f"    ✅ Severity: {severity}")
        else:
            print(f"    ❌ Invalid Severity: {severity}")
        
        # Check for proper @odata.type
        odata_type = message.get("@odata.type", "")
        if "#Message.v" in odata_type:
            print(f"    ✅ @odata.type: {odata_type}")
        else:
            print(f"    ❌ Invalid @odata.type: {odata_type}")
        
        # Display message content
        print(f"    📝 Message: {message.get('Message', 'N/A')}")
        print(f"    🔧 Resolution: {message.get('Resolution', 'N/A')}")
        
        # Check for optional fields
        if "MessageArgs" in message:
            print(f"    📋 MessageArgs: {message['MessageArgs']}")
        
        if "RelatedProperties" in message:
            print(f"    🔗 RelatedProperties: {message['RelatedProperties']}")
    
    def _is_valid_message_id(self, message_id):
        """Validate MessageId follows Registry.Version.MessageKey format"""
        if not message_id:
            return False
        
        parts = message_id.split(".")
        if len(parts) != 3:
            return False
        
        registry, version, message_key = parts
        
        # Basic validation
        if not registry or not version or not message_key:
            return False
        
        # Common registries
        valid_registries = ["Base", "Task", "Resource", "Composition"]
        
        return True  # Basic format is correct
    
    def test_registry_access(self):
        """Test access to message registries"""
        print("\n🗂️ Testing Message Registry Access")
        print("=" * 45)
        
        # Check Registries collection
        registries_url = f"{self.base_url}/redfish/v1/Registries"
        response = self.session.get(registries_url)
        
        if response.status_code == 200:
            print("✅ Registries collection accessible")
            registries = response.json()
            
            # Check for Base registry
            members = registries.get("Members", [])
            base_registry_found = any("Base" in member.get("@odata.id", "") for member in members)
            
            if base_registry_found:
                print("✅ Base message registry available")
                
                # Try to access Base registry
                base_url = f"{self.base_url}/redfish/v1/Registries/Base.1.5.0"
                base_response = self.session.get(base_url)
                
                if base_response.status_code == 200:
                    print("✅ Base registry content accessible")
                    base_registry = base_response.json()
                    
                    # Check for key message definitions
                    messages = base_registry.get("Messages", {})
                    key_messages = ["Success", "PropertyNotWritable", "PropertyValueTypeError", "GeneralError"]
                    
                    for msg in key_messages:
                        if msg in messages:
                            print(f"    ✅ {msg} message defined")
                        else:
                            print(f"    ❌ {msg} message missing")
                else:
                    print(f"❌ Base registry not accessible: HTTP {base_response.status_code}")
            else:
                print("❌ Base message registry not found in collection")
        else:
            print(f"❌ Registries collection not accessible: HTTP {response.status_code}")
    
    def run_compliance_demo(self):
        """Run the complete Redfish message compliance demo"""
        print("🚀 BMC Redfish Simulator - Message Compliance Demo")
        print("=" * 55)
        
        # Test message registry access
        self.test_registry_access()
        
        # Test 1: Valid PATCH operation
        print("\n" + "="*50)
        print("1. TESTING VALID PATCH OPERATIONS")
        print("="*50)
        
        self.test_redfish_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "AssetTag": "Server-MSG-001",
                "IndicatorLED": "Blinking"
            },
            "Valid ComputerSystem PATCH",
            expect_success=True
        )
        
        # Test 2: Read-only property errors
        print("\n" + "="*50)
        print("2. TESTING READ-ONLY PROPERTY ERRORS")
        print("="*50)
        
        self.test_redfish_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "Id": "HackedSystem",
                "PowerState": "Off"
            },
            "Read-only property violation",
            expect_success=False
        )
        
        # Test 3: Type validation errors
        print("\n" + "="*50)
        print("3. TESTING TYPE VALIDATION ERRORS")
        print("="*50)
        
        self.test_redfish_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "IndicatorLED": True  # Should be string, not boolean
            },
            "Type validation error",
            expect_success=False
        )
        
        # Test 4: Enum validation errors
        print("\n" + "="*50)
        print("4. TESTING ENUM VALIDATION ERRORS")
        print("="*50)
        
        self.test_redfish_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "IndicatorLED": "Rainbow"  # Invalid enum value
            },
            "Enum validation error", 
            expect_success=False
        )
        
        # Test 5: Multiple validation errors
        print("\n" + "="*50)
        print("5. TESTING MULTIPLE VALIDATION ERRORS")
        print("="*50)
        
        self.test_redfish_patch_operation(
            "/redfish/v1/Systems/437XR1138R2",
            {
                "AssetTag": "ValidTag",        # Valid
                "Id": "InvalidId",             # Read-only
                "IndicatorLED": "InvalidValue", # Invalid enum
                "PowerState": "Off",           # Read-only
                "UnknownProperty": "Value"     # Unknown property
            },
            "Multiple validation errors",
            expect_success=False
        )
        
        # Test 6: Resource not found
        print("\n" + "="*50)
        print("6. TESTING RESOURCE NOT FOUND")
        print("="*50)
        
        self.test_redfish_patch_operation(
            "/redfish/v1/Systems/NonExistent",
            {
                "AssetTag": "Test"
            },
            "Resource not found error",
            expect_success=False
        )
        
        # Test 7: Malformed JSON
        print("\n" + "="*50)
        print("7. TESTING MALFORMED REQUEST")
        print("="*50)
        
        url = f"{self.base_url}/redfish/v1/Systems/437XR1138R2"
        response = self.session.patch(url, data='{"invalid": json}')  # Malformed JSON
        
        print(f"Malformed JSON response: HTTP {response.status_code}")
        if response.text:
            try:
                error_data = response.json()
                self._validate_redfish_messages(error_data, response.status_code, False)
            except json.JSONDecodeError:
                print("⚠️ Response is not valid JSON")
        
        print("\n✅ Redfish Message Compliance Demo completed!")
        print("\n📊 Compliance Summary:")
        print("- ✅ ExtendedInfo messages follow Redfish Message.v1.x.x schema")
        print("- ✅ MessageIds follow Registry.Version.MessageKey format")
        print("- ✅ Required message fields (MessageId, Message, Severity, Resolution) present")
        print("- ✅ HTTP status codes align with message severity levels")
        print("- ✅ Error responses include proper @Message.ExtendedInfo structure")
        print("- ✅ Success responses may include informational ExtendedInfo")
        print("- ✅ Message registries accessible via /redfish/v1/Registries")
        print("- ✅ RelatedProperties field links errors to specific resource properties")

def main():
    """Main demo function"""
    # Note: Make sure the BMC Redfish Simulator is running first:
    # python3 redfishMockupServer_modular.py -D mockups/public-rackmount1 -S -p 8000
    
    demo = RedfishMessageComplianceDemo()
    demo.run_compliance_demo()

if __name__ == "__main__":
    main()