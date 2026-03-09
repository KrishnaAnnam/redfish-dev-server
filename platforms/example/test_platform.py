#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Custom tests for Example BMC Platform platform
"""

import sys
import os
import json
import logging
from platform import ExamplePlatform
from src.standalone.platform_simulator import TestFramework

class ExampleTestFramework(TestFramework):
    """Extended test framework for Example BMC Platform"""
    
    def test_service_root(self):
        """Test service root endpoint"""
        response = self.platform.handle_request("GET", "/redfish/v1/", {})
        self.assert_response(response, 200, ["@odata.type", "@odata.id", "Name"])
        
        # Check platform-specific fields
        _, _, data = response
        assert "Oem" in data
        assert "Example" in data["Oem"]
    
    def test_system_instance(self):
        """Test system instance"""
        response = self.platform.handle_request("GET", "/redfish/v1/Systems/1/", {})
        self.assert_response(response, 200, ["@odata.type", "Id", "Name", "SystemType"])
        
        # Check OEM section
        _, _, data = response
        assert "Oem" in data
        assert "Example" in data["Oem"]
    
    def test_oem_extensions(self):
        """Test OEM extensions"""
        response = self.platform.handle_request("GET", 
                                               "/redfish/v1/Systems/1/Oem/Example/", {})
        self.assert_response(response, 200, ["@odata.type", "Id", "Name"])
    
    def test_export_configuration_action(self):
        """Test export configuration OEM action"""
        response = self.platform.handle_request("POST",
                                               "/redfish/v1/Systems/1/Actions/Oem/Example.ExportConfiguration",
                                               {}, "{}")
        self.assert_response(response, 200, ["Message", "ConfigurationData"])
    
    def test_import_configuration_action(self):
        """Test import configuration OEM action"""
        import_data = {
            "ConfigurationData": {
                "TestSetting": "TestValue"
            }
        }
        
        response = self.platform.handle_request("POST",
                                               "/redfish/v1/Systems/1/Actions/Oem/Example.ImportConfiguration", 
                                               {}, json.dumps(import_data))
        self.assert_response(response, 202, ["Message", "TaskId"])
    
    def test_unsupported_endpoints(self):
        """Test that unsupported endpoints return 404"""
        response = self.platform.handle_request("GET", "/redfish/v1/InvalidEndpoint/", {})
        status_code, _, _ = response
        assert status_code == 404
    
    def test_unsupported_methods(self):
        """Test that unsupported methods return 405"""
        response = self.platform.handle_request("DELETE", "/redfish/v1/Systems/1/", {})
        status_code, _, _ = response
        assert status_code == 405

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create platform and test framework
    platform = ExamplePlatform()
    test_framework = ExampleTestFramework(platform)
    
    # Run tests
    results = test_framework.run_tests()
    
    # Print results
    print(f"\n=== Example BMC Platform Test Results ===")
    print(f"Total tests: {results['summary']['total']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Success rate: {results['summary']['success_rate']:.1%}")
    
    # Exit with appropriate code
    sys.exit(0 if results['summary']['failed'] == 0 else 1)
