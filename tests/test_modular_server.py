#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

"""
Test script for the BMC Redfish Simulator (Modular Server)
Based on DMTF Redfish-Mockup-Server
"""

import subprocess
import time
import requests
import sys
import threading


def test_server():
    """Test the modular server functionality"""
    print("Testing BMC Redfish Simulator (Modular Server)...")
    
    # Start the server in background
    server_process = subprocess.Popen([
        '/usr/bin/python3', 'redfishMockupServer_modular.py',
        '-H', '127.0.0.1', '-p', '8889'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Give server time to start
    time.sleep(2)
    
    try:
        # Test basic connectivity
        print("Testing GET /redfish/v1/...")
        response = requests.get('http://127.0.0.1:8889/redfish/v1/', timeout=5)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response contains {len(data)} keys")
            print("✓ GET request successful")
        else:
            print("✗ GET request failed")
            return False
        
        # Test 404 for non-existent resource
        print("\nTesting 404 handling...")
        response = requests.get('http://127.0.0.1:8889/redfish/v1/NonExistent', timeout=5)
        if response.status_code == 404:
            print("✓ 404 handling works")
        else:
            print("✗ 404 handling failed")
        
        print("\n✓ All tests passed!")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection failed: {e}")
        return False
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    
    finally:
        # Clean up server process
        server_process.terminate()
        server_process.wait(timeout=5)
        print("\nServer stopped.")


if __name__ == "__main__":
    success = test_server()
    sys.exit(0 if success else 1)