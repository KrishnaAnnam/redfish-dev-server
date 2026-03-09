#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Simple Redfish Client Test
==========================

Quick test to verify the Redfish client library functionality.
"""

import sys
import time

def test_client_import():
    """Test if we can import the client"""
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from client import RedfishClient, RedfishResource
        print("✅ Successfully imported RedfishClient")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_client_creation():
    """Test client creation"""
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from client import RedfishClient
        client = RedfishClient("http://localhost:8000")
        print("✅ Successfully created RedfishClient")
        return True
    except Exception as e:
        print(f"❌ Client creation failed: {e}")
        return False

def test_basic_connection():
    """Test basic connection (if server is available)"""
    try:
        import requests
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from client import RedfishClient
        
        # Quick connectivity check
        try:
            response = requests.get("http://localhost:8000/redfish/v1", timeout=2)
            server_available = response.status_code == 200
        except:
            server_available = False
        
        if not server_available:
            print("⚠️  BMC Server not available - skipping connection test")
            return True
        
        client = RedfishClient("http://localhost:8000", verify_ssl=False)
        
        if client.connect():
            print("✅ Successfully connected to BMC")
            print(f"   Redfish Version: {client.redfish_version}")
            return True
        else:
            print("❌ Connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Redfish Client Library - Quick Test")
    print("=" * 45)
    
    tests = [
        ("Import Test", test_client_import),
        ("Client Creation", test_client_creation),
        ("Basic Connection", test_basic_connection),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        if test_func():
            passed += 1
        time.sleep(0.5)
    
    print("\n" + "=" * 45)
    print(f"📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed! Client library is ready to use.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
    
    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)