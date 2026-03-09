#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Working Features Demo - BMC Redfish Simulator
Shows actual working features with the current mockup data
"""

import requests
import json
import time
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def demo_working_endpoints():
    """Test and demonstrate actually working endpoints"""
    print("🔍 Testing Available Endpoints")
    print("="*50)
    
    base_url = "http://localhost:8000"
    
    # Test available endpoints
    working_endpoints = []
    test_endpoints = [
        "/redfish/v1",
        "/redfish/v1/Systems",
        "/redfish/v1/Systems/437XR1138R2", 
        "/redfish/v1/Registries",
        "/redfish/v1/AccountService",
        "/redfish/v1/SessionService",
        "/redfish/v1/EventService",
        "/redfish/v1/CertificateService",
        "/redfish/v1/Chassis",
        "/redfish/v1/Managers",
        "/redfish/v1/JsonSchemas",
        "/redfish/v1/TaskService"
    ]
    
    for endpoint in test_endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=2)
            status = "✅ WORKS" if response.status_code == 200 else f"❌ {response.status_code}"
            print(f"{status:<12} {endpoint}")
            
            if response.status_code == 200:
                working_endpoints.append(endpoint)
                
        except Exception as e:
            print(f"❌ ERROR    {endpoint} - {str(e)}")
    
    print(f"\n📊 Working Endpoints: {len(working_endpoints)}")
    print("="*50)
    
    return working_endpoints

def show_detailed_response(endpoint, description):
    """Show detailed response for an endpoint"""
    print(f"\n🔍 {description}")
    print("-" * len(description))
    
    try:
        response = requests.get(f"http://localhost:8000{endpoint}", timeout=2)
        data = response.json()
        
        print(f"Status: {response.status_code}")
        print(f"Type: {data.get('@odata.type', 'N/A')}")
        print(f"Name: {data.get('Name', 'N/A')}")
        
        if "Members@odata.count" in data:
            print(f"Count: {data['Members@odata.count']}")
        
        if "Members" in data and data["Members"]:
            print("Members:")
            for member in data["Members"][:3]:  # Show first 3
                print(f"  • {member.get('@odata.id', 'N/A')}")
        
        # Show interesting properties
        interesting_props = ["Description", "Status", "SystemType", "Manufacturer", "Model"]
        for prop in interesting_props:
            if prop in data:
                print(f"{prop}: {data[prop]}")
                
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("BMC Redfish Simulator - Working Features Demo")
    print("=" * 60)
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:8000/redfish/v1", timeout=2)
        print("✅ Server is running")
    except:
        print("❌ Server not running. Please start it first:")
        print("   python3 servers/redfishMockupServer_modular.py")
        return
    
    # Test endpoints
    working_endpoints = demo_working_endpoints()
    
    if not working_endpoints:
        print("No working endpoints found!")
        return
    
    print("\n🎯 DETAILED EXPLORATION")
    print("="*60)
    
    # Show detailed responses for working endpoints
    endpoint_descriptions = {
        "/redfish/v1": "Service Root - Main Entry Point",
        "/redfish/v1/Systems": "Computer Systems Collection", 
        "/redfish/v1/Systems/437XR1138R2": "Individual Computer System",
        "/redfish/v1/Registries": "Message Registry Files"
    }
    
    for endpoint in working_endpoints:
        if endpoint in endpoint_descriptions:
            show_detailed_response(endpoint, endpoint_descriptions[endpoint])
    
    print("\n✨ Summary")
    print("="*60)
    print("✅ This demo shows the actual working features")
    print("✅ All responses use standard Redfish format")
    print("✅ Proper OData annotations and structure")
    print("✅ Mockup data provides realistic system information")

if __name__ == "__main__":
    main()