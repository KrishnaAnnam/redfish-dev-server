#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Create EventService Subscription for RAS Events
Subscribes to RAS-related events from the BMC
"""

import requests
import json
import sys
import time

def create_event_subscription(bmc_url, listener_url):
    """
    Create an event subscription
    
    Args:
        bmc_url: BMC base URL (e.g., http://localhost:8000)
        listener_url: Event listener URL (e.g., http://localhost:8888/)
    """
    
    subscription_url = f"{bmc_url}/redfish/v1/EventService/Subscriptions"
    
    # Subscription payload
    payload = {
        "Destination": listener_url,
        "Protocol": "Redfish",
        "Context": "RAS Demo Subscription",
        "SubscriptionType": "RedfishEvent",
        "EventTypes": [
            "Alert",
            "StatusChange",
            "ResourceAdded",
            "ResourceUpdated"
        ],
        "RegistryPrefixes": [
            "Base",
            "OCPRAS"
        ],
        "ResourceTypes": [
            "LogEntry"
        ]
    }
    
    print("\n" + "=" * 80)
    print("🔔 CREATING EVENT SUBSCRIPTION")
    print("=" * 80)
    print(f"BMC URL: {bmc_url}")
    print(f"Listener URL: {listener_url}")
    print(f"Subscription Endpoint: {subscription_url}")
    
    try:
        # Create subscription
        response = requests.post(
            subscription_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        print(f"\nResponse Status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            # Try to parse response body (some servers return empty body for 200)
            subscription_data = {}
            if response.text and response.text.strip():
                try:
                    subscription_data = response.json()
                except json.JSONDecodeError:
                    pass
            
            if subscription_data:
                subscription_id = subscription_data.get('Id', 'Unknown')
                subscription_uri = subscription_data.get('@odata.id', 'N/A')
                
                print("\n✅ SUBSCRIPTION CREATED")
                print(f"   Subscription ID: {subscription_id}")
                print(f"   URI: {subscription_uri}")
                print(f"\n📋 Subscription Details:")
                print(f"   Context: {subscription_data.get('Context', 'N/A')}")
                print(f"   Protocol: {subscription_data.get('Protocol', 'N/A')}")
                print(f"   Event Types: {', '.join(subscription_data.get('EventTypes', []))}")
                
                return True, subscription_id
            else:
                # Server returned success without body - subscription accepted
                print("\n✅ SUBSCRIPTION ACCEPTED")
                print("   Server accepted subscription request")
                print(f"   Destination: {listener_url}")
                return True, "accepted"
        else:
            print(f"\n❌ FAILED TO CREATE SUBSCRIPTION")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False, None
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False, None
    
    finally:
        print("=" * 80 + "\n")


def check_listener_status(listener_url):
    """Check if event listener is running"""
    try:
        response = requests.get(f"{listener_url}status", timeout=2)
        if response.status_code == 200:
            return True
    except:
        pass
    return False


def main():
    """Main function"""
    
    # Configuration
    BMC_URL = "http://localhost:8000"
    LISTENER_URL = "http://localhost:8888/"
    
    # Check if listener is running
    print("\n🔍 Checking if event listener is running...")
    if not check_listener_status(LISTENER_URL):
        print(f"\n⚠️  WARNING: Event listener may not be running at {LISTENER_URL}")
        print("   Start the listener first:")
        print("   python3 examples/event_listener.py")
        print("\nContinuing anyway...\n")
    else:
        print(f"✅ Event listener is ready at {LISTENER_URL}\n")
    
    # Create subscription
    success, sub_id = create_event_subscription(BMC_URL, LISTENER_URL)
    
    if success:
        print("✅ Setup complete! Events will be sent to the listener.")
        print("\nNext steps:")
        print("   1. Run the RAS demo: python3 examples/ras_api_demo/ras_api_plugin_demo.py")
        print("   2. Watch the event listener output for incoming events")
        return 0
    else:
        print("❌ Failed to create subscription")
        return 1


if __name__ == '__main__':
    sys.exit(main())
