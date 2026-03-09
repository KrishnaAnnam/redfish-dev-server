#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
#!/usr/bin/env python3
"""
Complete BMC Redfish Simulator Demonstration
=============================================
Project: bmc-redfish-simulator
Based on: DMTF Redfish-Mockup-Server

This comprehensive demo showcases all capabilities of the BMC Redfish Simulator
with modular architecture, platform plugins, 
standalone development, and enterprise services.

Demo Categories:
1. Basic Mockup Server - Original functionality
2. Modular Architecture - Enhanced with service separation
3. Platform-Specific Plugins - Dell/HPE platform examples
4. Standalone Development - Independent platform development
5. Enterprise Services - RAS, OEM Actions, UpdateService
6. Real-World Scenarios - Complete BMC simulation workflows
"""

import requests
import json
import time
import subprocess
import os
import sys
from datetime import datetime

class BMCSimulatorDemo:
    def __init__(self):
        self.base_url = "http://localhost:8000/redfish/v1"
        self.demo_results = {}
        
    def print_banner(self, title, subtitle=""):
        """Print a formatted banner"""
        print("\n" + "="*80)
        print(f"🎯 {title}")
        if subtitle:
            print(f"   {subtitle}")
        print("="*80)
        
    def print_section(self, title):
        """Print a section header"""
        print(f"\n📋 {title}")
        print("-"*50)
        
    def execute_request(self, method, path, data=None, description=""):
        """Execute HTTP request and display results"""
        url = f"{self.base_url}{path}"
        
        print(f"\n🔸 {description}")
        print(f"   {method} {path}")
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=5)
            elif method == "POST":
                response = requests.post(url, json=data, headers={"Content-Type": "application/json"}, timeout=5)
            
            print(f"   Status: {response.status_code}")
            
            if response.text:
                try:
                    response_data = response.json()
                    if len(str(response_data)) > 300:
                        # Show abbreviated response for long outputs
                        key_fields = self._extract_key_fields(response_data)
                        print(f"   Response: {json.dumps(key_fields, indent=2)}")
                    else:
                        print(f"   Response: {json.dumps(response_data, indent=2)}")
                except:
                    print(f"   Response: {response.text[:200]}...")
            
            return response.status_code, response_data if response.text else {}
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return 0, {}
    
    def _extract_key_fields(self, data):
        """Extract key fields from response for display"""
        if isinstance(data, dict):
            key_fields = {}
            important_keys = ['@odata.id', '@odata.type', 'Name', 'Id', 'Status', 'Members@odata.count', 
                             'TaskState', 'TaskStatus', 'MessageId', 'Message', 'ServiceEnabled']
            
            for key in important_keys:
                if key in data:
                    key_fields[key] = data[key]
            
            # Add first few Members if it's a collection
            if 'Members' in data and isinstance(data['Members'], list):
                key_fields['Members'] = data['Members'][:2] + (['...'] if len(data['Members']) > 2 else [])
                
            return key_fields
        return data
    
    def start_server(self, config_type="modular", mockup_dir="./mockups/sample", port=8000):
        """Start the BMC simulator server"""
        print(f"\n🚀 Starting BMC Simulator ({config_type} mode)")
        
        if config_type == "original":
            # Use modular as the default baseline (original removed)
            cmd = ["python3", "redfishMockupServer_modular.py", "-D", mockup_dir, "-p", str(port)]
        elif config_type == "modular":
            cmd = ["python3", "redfishMockupServer_modular.py", "-D", mockup_dir, "-p", str(port)]
        elif config_type == "platform":
            cmd = ["python3", "redfishMockupServer_platform.py", "-D", mockup_dir, "-p", str(port)]
        elif config_type == "standalone":
            cmd = ["python3", "src/standalone/platform_simulator.py", "--port", str(port)]
        
        print(f"   Command: {' '.join(cmd)}")
        
        # Start server in background
        try:
            process = subprocess.Popen(cmd, cwd=".")
            time.sleep(3)  # Wait for server to start
            
            # Test if server is running
            try:
                response = requests.get(f"http://localhost:{port}/redfish/v1", timeout=2)
                if response.status_code == 200:
                    print(f"   ✅ Server started successfully on port {port}")
                    return process
                else:
                    print(f"   ❌ Server responded with status {response.status_code}")
                    return None
            except:
                print(f"   ❌ Server not responding")
                return None
                
        except Exception as e:
            print(f"   ❌ Failed to start server: {e}")
            return None
    
    def stop_server(self, process):
        """Stop the server process"""
        if process:
            process.terminate()
            time.sleep(1)
            print("   🛑 Server stopped")
    
    def demo_1_basic_mockup(self):
        """Demo 1: Basic BMC Redfish Simulator functionality"""
        self.print_banner("DEMO 1: Basic BMC Redfish Simulator", 
                         "Original DMTF functionality with static mockup data")
        
        self.print_section("Basic Service Discovery")
        self.execute_request("GET", "", "Service Root - Core Redfish services")
        self.execute_request("GET", "/Systems", "Computer Systems Collection")
        self.execute_request("GET", "/Managers", "Manager Collection")
        self.execute_request("GET", "/Chassis", "Chassis Collection")
        
        self.print_section("Resource Navigation") 
        self.execute_request("GET", "/Systems/system", "Individual Computer System")
        self.execute_request("GET", "/Managers/BMC", "BMC Manager Details")
        
        print("\n✅ Basic mockup server provides static Redfish data from JSON files")
        print("   - Standard Redfish collections and resources")
        print("   - OData navigation and linking")
        print("   - RESTful HTTP interface")
    
    def demo_2_modular_architecture(self):
        """Demo 2: Enhanced modular architecture with services"""
        self.print_banner("DEMO 2: Modular Architecture", 
                         "Enhanced server with separated service handlers")
        
        self.print_section("Enhanced Service Discovery")
        self.execute_request("GET", "", "Service Root - Note enhanced services")
        
        self.print_section("Event Service")
        self.execute_request("GET", "/EventService", "Event Service Details")
        self.execute_request("GET", "/EventService/Subscriptions", "Event Subscriptions")
        
        self.print_section("Telemetry Service")
        self.execute_request("GET", "/TelemetryService", "Telemetry Service")
        
        self.print_section("Interactive Actions")
        self.execute_request("POST", "/EventService/Actions/EventService.SubmitTestEvent",
                           {"EventType": "Alert", "Message": "Demo test event"},
                           "Submit Test Event")
        
        print("\n✅ Modular architecture provides:")
        print("   - Separated service handlers for better maintainability")
        print("   - Enhanced error handling and validation") 
        print("   - Extensible architecture for new services")
    
    def demo_3_enterprise_services(self):
        """Demo 3: Enterprise services (RAS, OEM Actions, UpdateService)"""
        self.print_banner("DEMO 3: Enterprise Services", 
                         "RAS Service, OEM Actions, and UpdateService from real BMC data")
        
        self.print_section("RAS Service - Reliability, Availability, Serviceability")
        self.execute_request("GET", "/RASService", "RAS Service Root")
        self.execute_request("GET", "/RASService/Endpoints", "RAS Endpoints Collection")
        self.execute_request("GET", "/RASService/Endpoints/Endpoint-1", "CPU RAS Endpoint")
        self.execute_request("GET", "/RASService/Initiators", "RAS Initiators")
        self.execute_request("GET", "/RASService/ErrorQueues", "Error Queues")
        
        self.print_section("RAS Actions")
        self.execute_request("POST", "/RASService/Actions/SubmitRASAction",
                           {"ActionType": "DiagnosticTest", "Target": "CPU-Socket-0"},
                           "Submit RAS Diagnostic Action")
        
        self.execute_request("POST", "/RASService/Actions/CollectErrorLogs",
                           {"SeverityLevel": "Corrected"},
                           "Collect Error Logs")
        
        self.print_section("UpdateService - Firmware Management")
        self.execute_request("POST", "/UpdateService/Actions/UpdateService.SimpleUpdate",
                           {"ImageURI": "http://example.com/firmware.bin", 
                            "Targets": ["/redfish/v1/Systems/system"]},
                           "Simple Firmware Update")
        
        self.execute_request("POST", "/UpdateService/FirmwareInventory",
                           {"Name": "Demo BIOS", "Version": "2.1.0", "Id": "demo-bios"},
                           "Create Firmware Inventory")
        
        self.print_section("Enhanced Event Generation")
        print("   🎯 Automatic Redfish Events Generated:")
        print("      • ResourceAdded events for successful POST operations (201 Created)")
        print("      • ResourceUpdated events for successful PATCH operations (200 OK)")
        print("      • ResourceRemoved events for successful DELETE operations (200 OK)")
        print("      • StatusChange events for property modifications")
        print("      • Alert events for system conditions")
        
        # Test event subscription and generation
        self.execute_request("POST", "/EventService/Subscriptions",
                           {
                               "Destination": "http://demo.example.com/events",
                               "Protocol": "Redfish",
                               "Context": "enterprise-demo",
                               "EventTypes": ["ResourceAdded", "ResourceUpdated", "Alert"],
                               "MessageIds": ["ResourceEvent.1.0.0.ResourceCreated", "ResourceEvent.1.0.0.ResourceModified"]
                           },
                           "Create Event Subscription (generates ResourceAdded event)")
        
        self.execute_request("POST", "/EventService/Actions/EventService.SubmitTestEvent",
                           {"EventType": "Alert", "Message": "Enterprise system alert", "Severity": "Warning"},
                           "Submit Test Alert Event")
        
        print("\n✅ Enterprise services provide:")
        print("   - RAS capabilities for enterprise reliability features")
        print("   - OEM-specific actions with proper validation") 
        print("   - UpdateService with task management and multipart support")
        print("   - Real-world BMC functionality from production systems")
        print("   - Automatic Redfish event generation for all operations")
        print("   - Comprehensive logging and audit trails")
    
    def demo_4_platform_plugins(self):
        """Demo 4: Platform-specific plugins"""
        self.print_banner("DEMO 4: Platform-Specific Plugins", 
                         "Dell, HPE, and custom platform implementations")
        
        print("\n📋 Platform Plugin System Overview")
        print("   The platform plugin system allows:")
        print("   - Platform-specific service implementations")
        print("   - OEM action handlers")
        print("   - Custom resource extensions")
        print("   - Automatic platform detection")
        
        print("\n🔸 Available Platform Plugins:")
        print("   📁 Dell Platform Plugin (src/plugins/dell/)")
        print("      - Dell-specific EventService extensions")
        print("      - iDRAC-style management features") 
        print("      - Dell OEM actions and properties")
        
        print("   📁 HPE Platform Plugin (src/plugins/hpe/)")
        print("      - HPE iLO management simulation")
        print("      - HPE-specific service implementations")
        print("      - Smart Array and ProLiant features")
        
        print("   📁 Custom Platform Support")
        print("      - Easy plugin creation framework")
        print("      - Platform registry and auto-discovery")
        print("      - Extensible service architecture")
        
        print("\n✅ Platform plugins enable:")
        print("   - Multi-vendor BMC simulation")
        print("   - Platform-specific feature testing")
        print("   - OEM validation workflows")
        print("   - Realistic vendor-specific responses")
    
    def demo_5_standalone_development(self):
        """Demo 5: Standalone platform development"""
        self.print_banner("DEMO 5: Standalone Platform Development", 
                         "Independent platform development and testing framework")
        
        print("\n📋 Standalone Development Features")
        print("   The standalone framework provides:")
        print("   - Independent platform development")
        print("   - Built-in test framework")
        print("   - CLI development tools")
        print("   - Platform validation utilities")
        
        print("\n🔸 Platform Development Kit:")
        print("   📁 Platform Templates (platforms/example/)")
        print("      - Complete platform implementation example")
        print("      - Service handler templates")
        print("      - Test suite framework")
        
        print("   🛠️ Development Tools:")
        print("      - Platform simulator CLI")
        print("      - Automated testing framework")
        print("      - Resource validation")
        print("      - Mock data generation")
        
        print("\n🧪 Example Platform Structure:")
        print("   platforms/example/")
        print("   ├── platform.py        # Platform implementation")
        print("   ├── test_platform.py   # Automated tests")
        print("   ├── config.json        # Platform configuration")
        print("   └── mockdata/          # Platform-specific data")
        
        print("\n✅ Standalone development enables:")
        print("   - Isolated platform development")
        print("   - Independent testing and validation")
        print("   - Rapid prototyping of BMC features")
        print("   - Custom platform implementations")
    
    def demo_6_real_world_scenarios(self):
        """Demo 6: Real-world BMC simulation scenarios"""
        self.print_banner("DEMO 6: Real-World BMC Simulation Scenarios", 
                         "Complete workflows for common BMC operations")
        
        self.print_section("Scenario 1: System Health Monitoring")
        print("   Simulating comprehensive system health monitoring")
        self.execute_request("GET", "/Systems/system/Status", "System Health Status")
        self.execute_request("GET", "/RASService/ErrorQueues/IB/Corrected", "Corrected Errors")
        self.execute_request("POST", "/RASService/Actions/CollectErrorLogs",
                           {"SeverityLevel": "All"}, "Collect All Error Logs")
        
        self.print_section("Scenario 2: Firmware Update Workflow")
        print("   Complete firmware update simulation")
        self.execute_request("GET", "/UpdateService", "Update Service Status")
        
        update_task = self.execute_request("POST", "/UpdateService/Actions/UpdateService.SimpleUpdate",
                           {"ImageURI": "http://firmware.example.com/bios-v2.1.bin",
                            "Targets": ["/redfish/v1/Systems/system/Bios"]},
                           "Initiate BIOS Update")
        
        self.print_section("Scenario 3: Event Monitoring and Alerting")
        print("   Event subscription and monitoring simulation")
        self.execute_request("POST", "/EventService/Subscriptions",
                           {"Destination": "http://monitor.example.com/events",
                            "EventTypes": ["Alert", "ResourceAdded"],
                            "Protocol": "Redfish"},
                           "Create Event Subscription")
        
        self.execute_request("POST", "/EventService/Actions/EventService.SubmitTestEvent",
                           {"EventType": "Alert", 
                            "Message": "Temperature threshold exceeded",
                            "Severity": "Warning"},
                           "Generate Test Alert")
        
        self.print_section("Scenario 4: System Maintenance Operations")
        print("   Maintenance and recovery operations")
        
        print("\n✅ Real-world scenarios demonstrate:")
        print("   - Complete BMC operation workflows")
        print("   - Enterprise system management tasks")
        print("   - Error handling and recovery procedures")
        print("   - Production-ready simulation capabilities")
    
    def demo_7_enhanced_messaging(self):
        """Demo 7: Enhanced Redfish messaging and event generation"""
        self.print_section("Demo 7: Enhanced Redfish Messaging System")
        
        print("🔔 Enhanced Redfish Message Responses:")
        print("   Standardized ExtendedInfo messages for all operations")
        print("   Automatic event generation from POST/PATCH operations")
        print("   Comprehensive logging with multiple log types")
        print("   Real-time event subscriptions and notifications")
        
        # Test enhanced message responses
        self.print_section("Enhanced Message Responses")
        print("   Testing standardized Redfish message responses")
        
        self.execute_request("POST", "/Systems/system/Memory",
                           {"Name": "DIMM4", "CapacityMiB": 16384, 
                            "MemoryType": "DDR4", "BaseModuleType": "UDIMM"},
                           "Create Memory Module (with enhanced response)")
        
        self.execute_request("PATCH", "/Systems/system/Memory/DIMM1",
                           {"AssetTag": "MEM-001-UPDATED"},
                           "Update Memory Asset Tag (with enhanced response)")
        
        # Test event generation
        self.print_section("Automatic Event Generation")
        print("   Events automatically generated from POST/PATCH operations")
        
        self.execute_request("GET", "/Managers/BMC/LogServices/Event/Entries",
                           description="View Generated Events")
        
        # Test subscription and notification
        self.print_section("Event Subscription Management")
        print("   Real-time event subscriptions for monitoring")
        
        self.execute_request("POST", "/EventService/Subscriptions",
                           {"Destination": "http://client.example.com/events",
                            "EventTypes": ["ResourceAdded", "ResourceUpdated", "Alert"],
                            "Protocol": "Redfish",
                            "Context": "EnhancedDemo"},
                           "Create Enhanced Event Subscription")
        
        self.execute_request("POST", "/EventService/Actions/EventService.SubmitTestEvent",
                           {"EventType": "Alert",
                            "Message": "Enhanced messaging demo alert",
                            "Severity": "OK",
                            "EventId": "DEMO-001"},
                           "Submit Test Event with Enhanced Info")
        
        # Test logging capabilities
        self.print_section("Multi-Type Logging System")
        print("   Event, Audit, and Security logs with persistence")
        
        self.execute_request("GET", "/Managers/BMC/LogServices", 
                           description="Available Log Services")
        
        self.execute_request("GET", "/Managers/BMC/LogServices/Event/Entries",
                           description="Event Log Entries")
        
        self.execute_request("GET", "/Managers/BMC/LogServices/Audit/Entries",
                           description="Audit Log Entries")
        
        print("\n✅ Enhanced messaging features:")
        print("   - Standardized ExtendedInfo in all responses")
        print("   - Automatic ResourceAdded/ResourceUpdated events")
        print("   - Multi-type logging (Event/Audit/Security)")
        print("   - Real-time event subscriptions")
        print("   - DMTF Base Registry message support")
        print("   - Persistent log storage")
    
    def run_comprehensive_demo(self):
        """Run the complete demo showcase"""
        start_time = datetime.now()
        
        self.print_banner("BMC Simulator Demo Showcase", 
                         "Comprehensive demonstration of all simulator capabilities")
        
        print("🎯 Demo Overview:")
        print("   1. Basic Mockup Server - Original DMTF functionality")
        print("   2. Modular Architecture - Enhanced service separation") 
        print("   3. Enterprise Services - RAS, OEM Actions, UpdateService")
        print("   4. Platform Plugins - Dell/HPE specific implementations")
        print("   5. Standalone Development - Independent platform framework")
        print("   6. Real-World Scenarios - Complete BMC workflows")
        print("   7. Enhanced Messaging - Redfish messages, events, and logging")
        
        # Start the modular server for interactive demos
        print(f"\n🚀 Starting BMC Simulator for interactive demos...")
        server_process = self.start_server("modular")
        
        if not server_process:
            print("❌ Could not start server. Please check the setup and try again.")
            return
        
        try:
            # Run the demos
            self.demo_1_basic_mockup()
            input("\nPress Enter to continue to next demo...")
            
            self.demo_2_modular_architecture()
            input("\nPress Enter to continue to next demo...")
            
            self.demo_3_enterprise_services()
            input("\nPress Enter to continue to next demo...")
            
            self.demo_4_platform_plugins()
            input("\nPress Enter to continue to next demo...")
            
            self.demo_5_standalone_development()
            input("\nPress Enter to continue to next demo...")
            
            self.demo_6_real_world_scenarios()
            input("\nPress Enter to continue to enhanced messaging demo...")
            
            self.demo_7_enhanced_messaging()
            
        finally:
            self.stop_server(server_process)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        self.print_banner("Demo Complete!", 
                         f"Total duration: {duration:.1f} seconds")
        
        print("🎊 BMC Simulator Demo Showcase Summary:")
        print("   ✅ Basic Redfish mockup capabilities")
        print("   ✅ Enhanced modular architecture")  
        print("   ✅ Enterprise RAS and OEM services")
        print("   ✅ Platform-specific plugin system")
        print("   ✅ Standalone development framework")
        print("   ✅ Real-world BMC simulation scenarios")
        print("   ✅ Enhanced messaging and event generation")
        print(f"\n📈 The BMC Simulator provides comprehensive")
        print(f"   simulation capabilities for:")
        print(f"   - BMC firmware development and testing")
        print(f"   - Redfish client application validation")
        print(f"   - Platform-specific feature development")
        print(f"   - Enterprise system management workflows")
        
        print(f"\n🚀 Next Steps:")
        print(f"   - Explore individual demo components")
        print(f"   - Develop custom platform plugins")
        print(f"   - Create application-specific test scenarios")
        print(f"   - Integrate with CI/CD workflows")

def main():
    """Main demo execution"""
    demo = BMCSimulatorDemo()
    
    if len(sys.argv) > 1:
        demo_type = sys.argv[1]
        if demo_type == "basic":
            # Start server and run basic demo only
            server = demo.start_server("modular")
            if server:
                try:
                    demo.demo_1_basic_mockup()
                finally:
                    demo.stop_server(server)
        elif demo_type == "enterprise":
            # Run enterprise services demo
            server = demo.start_server("modular") 
            if server:
                try:
                    demo.demo_3_enterprise_services()
                finally:
                    demo.stop_server(server)
        elif demo_type == "overview":
            # Run overview without starting server
            demo.demo_4_platform_plugins()
            demo.demo_5_standalone_development()
        else:
            print(f"Unknown demo type: {demo_type}")
            print("Available options: basic, enterprise, overview, or no argument for full demo")
    else:
        # Run comprehensive demo
        demo.run_comprehensive_demo()

if __name__ == "__main__":
    main()