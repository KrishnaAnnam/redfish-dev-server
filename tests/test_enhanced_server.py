#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Test script for the BMC Redfish Simulator (Enhanced Server)
Based on DMTF Redfish-Mockup-Server
Tests the new OEM actions and UpdateService handlers extracted from the UpdateService code
"""

import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000/redfish/v1"

# Redfish resources require authentication.  The mockup runs in permissive
# simulator mode (no AccountService), so any Basic credentials are accepted.
AUTH = ("demo", "demo")

def test_request(method, path, data=None, expected_status=200):
    """Helper function to test HTTP requests"""
    url = f"{BASE_URL}{path}"
    
    try:
        if method == "GET":
            response = requests.get(url, auth=AUTH)
        elif method == "POST":
            response = requests.post(url, json=data, auth=AUTH, headers={"Content-Type": "application/json"})
        
        print(f"\n{method} {path}")
        print(f"Status: {response.status_code} (expected: {expected_status})")
        
        if response.status_code == expected_status:
            print("✅ PASS")
        else:
            print("❌ FAIL")
        
        if response.text:
            try:
                response_data = response.json()
                print(f"Response: {json.dumps(response_data, indent=2)[:200]}...")
            except:
                print(f"Response: {response.text[:200]}...")
        
        return response.status_code == expected_status
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Run comprehensive tests"""
    print("🚀 Testing BMC Redfish Simulator (Enhanced Server)")
    print("=" * 60)
    
    # Test basic server functionality
    print("\n📋 BASIC SERVER TESTS")
    test_request("GET", "", expected_status=200)
    test_request("GET", "/Oem/OCPRASAPIWS/RASService", expected_status=200)
    
    # Test UpdateService Handlers
    print("\n📦 UPDATESERVICE TESTS")
    
    # Generic UpdateService action
    test_request("POST", "/UpdateService", 
                {"ImageURI": "http://example.com/firmware.bin"}, expected_status=202)
    
    # SimpleUpdate action
    test_request("POST", "/UpdateService/Actions/UpdateService.SimpleUpdate", 
                {"ImageURI": "http://example.com/firmware.bin", 
                 "Targets": ["/redfish/v1/Systems/system"]}, expected_status=202)
    
    # SimpleUpdate with missing ImageURI
    test_request("POST", "/UpdateService/Actions/UpdateService.SimpleUpdate", 
                {"Targets": ["/redfish/v1/Systems/system"]}, expected_status=400)
    
    # FirmwareInventory creation
    test_request("POST", "/UpdateService/FirmwareInventory", 
                {"Name": "Test Firmware", "Version": "1.0.0", "Id": "test-fw"}, expected_status=201)
    
    # FirmwareInventory with missing required field
    test_request("POST", "/UpdateService/FirmwareInventory", 
                {"Version": "1.0.0"}, expected_status=400)
    
    print("\n" + "=" * 60)
    print("✅ All tests completed! Check the results above.")

if __name__ == "__main__":
    main()