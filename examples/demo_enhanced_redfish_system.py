#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Enhanced Redfish System Demo
============================

Demonstrates the comprehensive Redfish message responses, logging, and event system
with examples of all major features and integration points.
"""

import json
import time
import requests
import subprocess
from datetime import datetime
from typing import Dict, Any

class EnhancedRedfishDemo:
    """Demo class for enhanced Redfish system capabilities"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.server_process = None
        
    def start_server(self):
        """Start the enhanced BMC simulator"""
        print("🚀 Starting Enhanced BMC Simulator...")
        
        # Use the enhanced server that includes message/log/event services
        cmd = [
            "python3", "redfishMockupServer_enhanced.py",
            "-D", "../GEN_10", 
            "-p", "8000",
            "--enhanced-responses"  # Enable enhanced response system
        ]
        
        try:
            self.server_process = subprocess.Popen(
                cmd, 
                cwd=".",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for server to start
            for i in range(30):
                try:
                    response = requests.get(f"{self.base_url}/redfish/v1", timeout=2)
                    if response.status_code == 200:
                        print("✅ Server started successfully")
                        return True
                except:
                    pass
                time.sleep(1)
                
            print("❌ Server startup timeout")
            return False
            
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False
    
    def stop_server(self):
        """Stop the server"""
        if self.server_process:
            self.server_process.terminate()
            time.sleep(2)
            self.server_process = None
            print("🛑 Server stopped")
    
    def make_request(self, method: str, path: str, data: Dict = None) -> Dict[str, Any]:
        """Make HTTP request and return response with enhanced info"""
        url = f"{self.base_url}{path}"
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=10)
            elif method == "PATCH":
                response = requests.patch(url, json=data, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, timeout=10)
            else:
                return {"error": f"Unsupported method: {method}"}
            
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "url": url,
                "method": method
            }
            
            if response.text:
                try:
                    result["data"] = response.json()
                except:
                    result["data"] = response.text
            
            return result
            
        except Exception as e:
            return {"error": str(e), "url": url, "method": method}
    
    def demo_enhanced_responses(self):
        """Demonstrate enhanced Redfish message responses"""
        print("\n" + "="*60)
        print("📊 ENHANCED REDFISH RESPONSES DEMO")
        print("="*60)
        
        print("\n1️⃣ Standard GET Response with ExtendedInfo")
        response = self.make_request("GET", "/redfish/v1")
        self._show_response("Service Root", response)
        
        print("\n2️⃣ Successful Resource Creation with ExtendedInfo")
        subscription_data = {
            "Destination": "http://example.com/events",
            "Protocol": "Redfish",
            "Context": "demo-subscription",
            "EventTypes": ["Alert", "ResourceAdded", "ResourceUpdated"]
        }
        response = self.make_request("POST", "/redfish/v1/EventService/Subscriptions", subscription_data)
        self._show_response("Event Subscription Creation", response)
        
        print("\n3️⃣ Property Error Response with ExtendedInfo")
        invalid_data = {
            "InvalidProperty": "SomeValue",
            "AnotherBadProp": 123
        }
        response = self.make_request("PATCH", "/redfish/v1/Systems/system", invalid_data)
        self._show_response("Invalid Property Update", response)
        
        print("\n4️⃣ Action with Parameters and ExtendedInfo")
        test_event_data = {
            "EventType": "Alert",
            "Message": "Demo test event with enhanced response",
            "Severity": "Warning"
        }
        response = self.make_request("POST", "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent", test_event_data)
        self._show_response("Submit Test Event", response)
    
    def demo_logging_system(self):
        """Demonstrate comprehensive logging system"""
        print("\n" + "="*60)
        print("📝 LOGGING SYSTEM DEMO")
        print("="*60)
        
        print("\n1️⃣ View Available Log Services")
        response = self.make_request("GET", "/redfish/v1/Systems/system/LogServices")
        self._show_response("Log Services Collection", response)
        
        print("\n2️⃣ Event Log Service Details")
        response = self.make_request("GET", "/redfish/v1/Systems/system/LogServices/Event")
        self._show_response("Event Log Service", response)
        
        print("\n3️⃣ Current Event Log Entries")
        response = self.make_request("GET", "/redfish/v1/Systems/system/LogServices/Event/Entries")
        self._show_response("Event Log Entries", response)
        
        print("\n4️⃣ Security Log Entries")
        response = self.make_request("GET", "/redfish/v1/Systems/system/LogServices/Security/Entries")
        self._show_response("Security Log Entries", response)
        
        print("\n5️⃣ Audit Log Entries") 
        response = self.make_request("GET", "/redfish/v1/Systems/system/LogServices/Audit/Entries")
        self._show_response("Audit Log Entries", response)
        
        # Demonstrate log entry details
        if response.get("data") and "Members" in response["data"] and response["data"]["Members"]:
            entry_id = response["data"]["Members"][0]["@odata.id"].split("/")[-1]
            print(f"\n6️⃣ Individual Log Entry Details (ID: {entry_id})")
            response = self.make_request("GET", f"/redfish/v1/Systems/system/LogServices/Audit/Entries/{entry_id}")
            self._show_response(f"Log Entry {entry_id}", response)
    
    def demo_event_system(self):
        """Demonstrate enhanced event system"""
        print("\n" + "="*60)
        print("🎯 EVENT SYSTEM DEMO")
        print("="*60)
        
        print("\n1️⃣ EventService Information")
        response = self.make_request("GET", "/redfish/v1/EventService")
        self._show_response("EventService Root", response)
        
        print("\n2️⃣ Current Event Subscriptions")
        response = self.make_request("GET", "/redfish/v1/EventService/Subscriptions")
        self._show_response("Event Subscriptions", response)
        
        print("\n3️⃣ Create New Event Subscription")
        subscription_data = {
            "Destination": "http://demo.example.com/events",
            "Protocol": "Redfish",
            "Context": "comprehensive-demo",
            "EventTypes": ["Alert", "ResourceAdded", "ResourceRemoved", "StatusChange"],
            "RegistryPrefixes": ["Base", "Platform"],
            "MessageIds": ["Base.1.5.0.Success", "Base.1.5.0.GeneralError"]
        }
        response = self.make_request("POST", "/redfish/v1/EventService/Subscriptions", subscription_data)
        self._show_response("New Event Subscription", response)
        
        # Get subscription ID for further operations
        subscription_id = None
        if response.get("data") and "@odata.id" in response["data"]:
            subscription_id = response["data"]["@odata.id"].split("/")[-1]
        
        print("\n4️⃣ Submit Test Events")
        test_events = [
            {"EventType": "Alert", "Message": "High temperature alert", "Severity": "Critical"},
            {"EventType": "StatusChange", "Message": "Component status changed", "Severity": "Warning"},
            {"EventType": "ResourceAdded", "Message": "New resource added", "Severity": "OK"}
        ]
        
        for i, event_data in enumerate(test_events, 1):
            print(f"\n   4.{i} Submitting {event_data['EventType']} Event")
            response = self.make_request("POST", "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent", event_data)
            self._show_compact_response(f"{event_data['EventType']} Event", response)
        
        if subscription_id:
            print(f"\n5️⃣ View Subscription Details (ID: {subscription_id})")
            response = self.make_request("GET", f"/redfish/v1/EventService/Subscriptions/{subscription_id}")
            self._show_response(f"Subscription {subscription_id}", response)
    
    def demo_message_registry_system(self):
        """Demonstrate message registry and standardized responses"""
        print("\n" + "="*60)
        print("📚 MESSAGE REGISTRY SYSTEM DEMO")
        print("="*60)
        
        print("\n1️⃣ Success Response with ExtendedInfo")
        response = self.make_request("GET", "/redfish/v1/Systems")
        if response.get("data") and "@Message.ExtendedInfo" in response["data"]:
            extended_info = response["data"]["@Message.ExtendedInfo"]
            print("   Extended Info Messages:")
            for msg in extended_info:
                print(f"     • MessageId: {msg.get('MessageId', 'N/A')}")
                print(f"       Message: {msg.get('Message', 'N/A')}")
                print(f"       Severity: {msg.get('Severity', 'N/A')}")
        
        print("\n2️⃣ Error Responses with Different Severities")
        error_scenarios = [
            ("Missing Parameter", "POST", "/redfish/v1/EventService/Subscriptions", {}),
            ("Invalid Property", "PATCH", "/redfish/v1/Systems/system", {"InvalidProp": "value"}),
            ("Not Found Resource", "GET", "/redfish/v1/NonExistent/Resource", None)
        ]
        
        for scenario, method, path, data in error_scenarios:
            print(f"\n   2.{error_scenarios.index((scenario, method, path, data)) + 1} {scenario}")
            response = self.make_request(method, path, data)
            if response.get("data") and "error" in response["data"]:
                error_info = response["data"]["error"].get("@Message.ExtendedInfo", [])
                for msg in error_info[:1]:  # Show first message
                    print(f"     Status: {response['status_code']}")
                    print(f"     MessageId: {msg.get('MessageId', 'N/A')}")
                    print(f"     Message: {msg.get('Message', 'N/A')}")
                    print(f"     Severity: {msg.get('Severity', 'N/A')}")
    
    def demo_log_management_operations(self):
        """Demonstrate log management operations"""
        print("\n" + "="*60)
        print("🗂️ LOG MANAGEMENT OPERATIONS DEMO")
        print("="*60)
        
        print("\n1️⃣ Generate Some Activity for Logging")
        
        # Create and modify resources to generate logs
        activities = [
            ("Creating subscription", "POST", "/redfish/v1/EventService/Subscriptions", 
             {"Destination": "http://test.com/events"}),
            ("Submitting test event", "POST", "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent",
             {"Message": "Demo activity event"}),
            ("Updating resource", "PATCH", "/redfish/v1/Systems/system",
             {"Description": "Updated description"}),
        ]
        
        for desc, method, path, data in activities:
            print(f"   • {desc}")
            response = self.make_request(method, path, data)
            print(f"     Result: {response.get('status_code', 'Error')}")
        
        print("\n2️⃣ Check Generated Log Entries")
        log_services = ["Event", "Audit", "Security"]
        
        for service in log_services:
            response = self.make_request("GET", f"/redfish/v1/Systems/system/LogServices/{service}/Entries")
            if response.get("data") and "Members@odata.count" in response["data"]:
                count = response["data"]["Members@odata.count"]
                print(f"   • {service} Log: {count} entries")
                
                # Show latest entry if available
                if count > 0 and "Members" in response["data"]:
                    latest_entry_path = response["data"]["Members"][0]["@odata.id"]
                    entry_response = self.make_request("GET", latest_entry_path)
                    if entry_response.get("data"):
                        entry = entry_response["data"]
                        print(f"     Latest: [{entry.get('Severity', 'N/A')}] {entry.get('Message', 'N/A')[:50]}...")
        
        print("\n3️⃣ Clear Event Log")
        response = self.make_request("POST", "/redfish/v1/Systems/system/LogServices/Event/Actions/LogService.ClearLog", {})
        self._show_compact_response("Clear Event Log", response)
        
        # Verify log was cleared
        response = self.make_request("GET", "/redfish/v1/Systems/system/LogServices/Event/Entries")
        if response.get("data"):
            count = response["data"].get("Members@odata.count", 0)
            print(f"   Event log entries after clear: {count}")
    
    def _show_response(self, title: str, response: Dict[str, Any]):
        """Show formatted response"""
        print(f"\n🔹 {title}")
        print(f"   Status: {response.get('status_code', 'Error')}")
        
        if "error" in response:
            print(f"   Error: {response['error']}")
            return
        
        if "data" in response:
            # Show key fields
            data = response["data"]
            
            # Show ExtendedInfo if present
            if "@Message.ExtendedInfo" in data:
                print("   Extended Info:")
                for msg in data["@Message.ExtendedInfo"]:
                    print(f"     • {msg.get('MessageId', 'N/A')}: {msg.get('Message', 'N/A')}")
            
            # Show other key fields
            key_fields = ["@odata.id", "@odata.type", "Id", "Name", "Description", "Status"]
            for field in key_fields:
                if field in data:
                    value = data[field]
                    if isinstance(value, dict):
                        print(f"   {field}: {json.dumps(value)}")
                    else:
                        print(f"   {field}: {value}")
            
            # Show collection info
            if "Members@odata.count" in data:
                print(f"   Collection Count: {data['Members@odata.count']}")
    
    def _show_compact_response(self, title: str, response: Dict[str, Any]):
        """Show compact response"""
        status = response.get('status_code', 'Error')
        print(f"   {title}: {status}")
        
        if response.get("data") and "@Message.ExtendedInfo" in response["data"]:
            msg = response["data"]["@Message.ExtendedInfo"][0]
            print(f"     {msg.get('Message', 'N/A')}")
    
    def run_complete_demo(self):
        """Run complete demonstration"""
        print("🎪 Enhanced Redfish Message & Logging System Demo")
        print("=" * 70)
        
        if not self.start_server():
            print("❌ Failed to start server. Exiting.")
            return False
        
        try:
            # Wait a moment for services to initialize
            time.sleep(3)
            
            # Run all demonstrations
            self.demo_enhanced_responses()
            self.demo_logging_system()
            self.demo_event_system()
            self.demo_message_registry_system()
            self.demo_log_management_operations()
            
            print("\n" + "="*70)
            print("✅ Demo completed successfully!")
            print("\nKey Features Demonstrated:")
            print("• Standardized Redfish message responses with ExtendedInfo")
            print("• Comprehensive logging system with multiple log types")
            print("• Enhanced event system with subscriptions and notifications")
            print("• Message registry integration for consistent error handling")
            print("• Log management operations (create, read, clear)")
            print("• Event-log correlation for comprehensive tracking")
            print("• HTTP method integration with enhanced responses")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Demo failed: {e}")
            return False
            
        finally:
            self.stop_server()

def main():
    """Main demo runner"""
    demo = EnhancedRedfishDemo()
    
    print("Enhanced Redfish Message & Logging System")
    print("This demo showcases comprehensive Redfish message responses,")
    print("logging capabilities, and event management.")
    print("")
    
    success = demo.run_complete_demo()
    
    if success:
        print("\n🎉 All demonstrations completed successfully!")
        print("The enhanced system provides:")
        print("  - Redfish-compliant message responses")
        print("  - Comprehensive logging and audit trails")
        print("  - Real-time event notifications")
        print("  - Standardized error handling")
    else:
        print("\n❌ Demo encountered issues.")
        print("Please check server configuration and try again.")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())