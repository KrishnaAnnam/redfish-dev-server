#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
LogEntry POST/PATCH Demo for BMC Redfish Simulator
=================================================
Demonstrates how to:
1. Create new LogEntry resources via POST 
2. Modify LogEntry resources via PATCH
3. Trigger EventService notifications automatically

This example shows the complete flow from creating log entries to receiving events.
"""

import requests
import json
import time
from datetime import datetime


class LogEntryDemo:
    """Demo class for LogEntry operations"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        
    def create_event_subscription(self):
        """Create an event subscription to receive notifications"""
        subscription_data = {
            "Destination": "http://localhost:8080/events",
            "Protocol": "Redfish", 
            "Context": "LogEntryDemo",
            "SubscriptionType": "RedfishEvent",
            "EventFormatType": "Event",
            "EventTypes": ["Alert", "ResourceUpdated"]
        }
        
        url = f"{self.base_url}/redfish/v1/EventService/Subscriptions"
        response = self.session.post(url, json=subscription_data)
        print(f"Event subscription: {response.status_code}")
        if response.status_code in [200, 201]:
            print(f"Subscription created: {response.json()}")
        return response.status_code in [200, 201]
    
    def create_log_entry(self, log_service_path, log_data):
        """Create a new LogEntry via POST"""
        entries_url = f"{self.base_url}{log_service_path}/Entries"
        
        print(f"\n🔄 Creating LogEntry at: {entries_url}")
        print(f"Data: {json.dumps(log_data, indent=2)}")
        
        response = self.session.post(entries_url, json=log_data)
        print(f"Response: {response.status_code}")
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ LogEntry created: {result['Created']}")
            print(f"Generated LogEntry: {json.dumps(result['LogEntry'], indent=2)}")
            return result['Created']
        else:
            print(f"❌ Failed to create LogEntry: {response.text}")
            return None
    
    def modify_log_entry(self, log_entry_path, updates):
        """Modify an existing LogEntry via PATCH"""
        entry_url = f"{self.base_url}{log_entry_path}"
        
        print(f"\n🔄 Modifying LogEntry at: {entry_url}")
        print(f"Updates: {json.dumps(updates, indent=2)}")
        
        response = self.session.patch(entry_url, json=updates)
        print(f"Response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ LogEntry updated: {result.get('Updated')}")
            print(f"Modified fields: {result.get('ModifiedFields')}")
            print(f"Updated LogEntry: {json.dumps(result.get('LogEntry', {}), indent=2)}")
            return True
        else:
            print(f"❌ Failed to modify LogEntry: {response.text}")
            return False
    
    def get_log_entry(self, log_entry_path):
        """Get LogEntry to verify changes"""
        entry_url = f"{self.base_url}{log_entry_path}"
        response = self.session.get(entry_url)
        
        if response.status_code == 200:
            return response.json()
        return None
    
    def run_demo(self):
        """Run the complete LogEntry demo"""
        print("🚀 BMC Redfish Simulator - LogEntry POST/PATCH Demo")
        print("=" * 60)
        
        # 1. Create event subscription (optional)
        print("\n1. Setting up EventService subscription...")
        self.create_event_subscription()
        
        # 2. Create a critical error log entry
        print("\n2. Creating CRITICAL error LogEntry...")
        critical_log = {
            "Message": "System temperature exceeded critical threshold",
            "Severity": "Critical", 
            "EntryType": "Event",
            "MessageId": "Thermal.1.0.TempCritical",
            "MessageArgs": ["88°C", "CPU1"],
            "OriginOfCondition": "/redfish/v1/Chassis/1U/Thermal/Temperatures/1"
        }
        
        critical_entry_path = self.create_log_entry(
            "/redfish/v1/Managers/BMC/LogServices/Log",
            critical_log
        )
        
        # 3. Create a warning log entry
        print("\n3. Creating WARNING LogEntry...")
        warning_log = {
            "Message": "Fan speed reduced due to thermal conditions",
            "Severity": "Warning",
            "EntryType": "Event", 
            "MessageId": "Fan.1.0.SpeedReduced",
            "MessageArgs": ["Fan1", "60%"],
            "SensorNumber": 5,
            "Resolution": "Monitor system temperature"
        }
        
        warning_entry_path = self.create_log_entry(
            "/redfish/v1/Managers/BMC/LogServices/Log", 
            warning_log
        )
        
        # 4. Modify the critical log entry (e.g., mark as resolved)
        if critical_entry_path:
            print("\n4. Resolving the critical LogEntry...")
            time.sleep(1)  # Brief delay
            
            resolution_updates = {
                "Severity": "OK",
                "Resolution": "Temperature returned to normal range",
                "Resolved": True,
                "Message": "System temperature critical condition resolved"
            }
            
            self.modify_log_entry(critical_entry_path, resolution_updates)
        
        # 5. Update warning entry
        if warning_entry_path:
            print("\n5. Updating warning LogEntry...")
            time.sleep(1)  # Brief delay
            
            warning_updates = {
                "Message": "Fan speed restored to normal operation",
                "Resolution": "Thermal condition improved, fan operating normally"
            }
            
            self.modify_log_entry(warning_entry_path, warning_updates)
        
        # 6. Verify final state
        print("\n6. Verifying final LogEntry states...")
        if critical_entry_path:
            final_critical = self.get_log_entry(critical_entry_path)
            if final_critical:
                print(f"Final Critical Entry: Severity={final_critical.get('Severity')}, Resolved={final_critical.get('Resolved')}")
        
        if warning_entry_path:
            final_warning = self.get_log_entry(warning_entry_path)
            if final_warning:
                print(f"Final Warning Entry: Message='{final_warning.get('Message')}'")
        
        print("\n✅ LogEntry POST/PATCH Demo completed!")
        print("\n📊 Summary:")
        print("- LogEntry resources are dynamically created in the mockup tree")
        print("- Events are automatically triggered for LogEntry creation/modification")
        print("- EventService subscriptions receive notifications")
        print("- All operations persist to the file system")


def main():
    """Main demo function"""
    # Note: Make sure the BMC Redfish Simulator is running first:
    # python3 redfishMockupServer_modular.py -D mockups/public-rackmount1 -S -p 8000
    
    demo = LogEntryDemo()
    demo.run_demo()


if __name__ == "__main__":
    main()