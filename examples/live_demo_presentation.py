#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
BMC Simulator Live Demo Script
=============================

Interactive presentation script for showcasing the BMC Simulator
capabilities in a live demo environment. Includes visual elements,
automated scenarios, and presenter notes.
"""

import requests
import json
import time
import subprocess
import os
import sys
from datetime import datetime
import curses

class LiveDemoPresentation:
    def __init__(self):
        self.base_url = "http://localhost:8000/redfish/v1"
        self.server_process = None
        self.current_slide = 0
        self.slides = []
        self.setup_slides()
        
    def setup_slides(self):
        """Setup presentation slides"""
        self.slides = [
            {
                "title": "BMC Simulator Overview", 
                "type": "intro",
                "content": [
                    "🎯 Enhanced Redfish Mockup Server with Multiple Architectures",
                    "",
                    "📋 What we'll demonstrate:",
                    "   • Original DMTF Mockup Server functionality",
                    "   • Modular architecture with service separation", 
                    "   • Enterprise services (RAS, OEM Actions, UpdateService)",
                    "   • Platform-specific plugins (Dell, HPE)",
                    "   • Standalone development framework",
                    "   • Real-world BMC simulation scenarios",
                    "",
                    "🚀 Live interactive demonstrations with real API calls"
                ]
            },
            {
                "title": "Architecture Evolution",
                "type": "architecture", 
                "content": [
                    "📈 BMC Simulator Architecture Progression",
                    "",
                    "1️⃣  Original DMTF Server",
                    "     └── Static JSON mockup files",
                    "     └── Basic HTTP request handling",
                    "",
                    "2️⃣  Modular Architecture", 
                    "     ├── Service separation (EventService, TelemetryService)",
                    "     ├── Enhanced error handling",
                    "     └── Extensible handler system",
                    "",
                    "3️⃣  Platform Plugin System",
                    "     ├── Dell/HPE specific implementations",
                    "     ├── Auto-discovery and registry",
                    "     └── OEM action handlers", 
                    "",
                    "4️⃣  Standalone Development Framework",
                    "     ├── Independent platform development",
                    "     ├── Built-in testing framework",
                    "     └── CLI development tools"
                ]
            },
            {
                "title": "Live Demo: Basic Redfish API",
                "type": "demo",
                "demo_func": "demo_basic_api",
                "content": [
                    "🔍 Exploring Basic Redfish API Structure",
                    "",
                    "We'll demonstrate:",
                    "• Service Root discovery",
                    "• Resource collections navigation", 
                    "• Individual resource details",
                    "• OData linking and relationships"
                ]
            },
            {
                "title": "Live Demo: Enterprise RAS Service", 
                "type": "demo",
                "demo_func": "demo_ras_service",
                "content": [
                    "🏢 Enterprise RAS Service Demonstration",
                    "",
                    "RAS = Reliability, Availability, Serviceability",
                    "",
                    "Features to demonstrate:",
                    "• RAS Endpoints (CPU, Memory, Storage)",
                    "• Error Queue Management (IB/OOB)",
                    "• CPER/CPAD Support",
                    "• Diagnostic Actions",
                    "",
                    "📊 Based on real GEN_10 BMC data"
                ]
            },
            {
                "title": "Live Demo: UpdateService",
                "type": "demo",
                "demo_func": "demo_update_service", 
                "content": [
                    "📦 Firmware Update Service Demonstration",
                    "",
                    "UpdateService capabilities:",
                    "• SimpleUpdate with task management",
                    "• Multipart firmware upload support",
                    "• FirmwareInventory management", 
                    "• Task tracking and progress monitoring",
                    "",
                    "🔄 Complete firmware update workflows"
                ]
            },
            {
                "title": "Platform Plugins Architecture",
                "type": "architecture",
                "content": [
                    "🏗️ Platform-Specific Plugin System",
                    "",
                    "🔌 Plugin Architecture:",
                    "   ├── Base Platform Provider Interface",
                    "   ├── Platform Registry & Auto-Discovery", 
                    "   ├── Service Extension Points",
                    "   └── OEM Action Handlers",
                    "",
                    "🏢 Vendor Implementations:",
                    "   📁 Dell Plugin (iDRAC simulation)",
                    "   📁 HPE Plugin (iLO simulation)",
                    "   📁 Custom Plugin Framework",
                    "",
                    "✨ Benefits:",
                    "   • Multi-vendor BMC simulation",
                    "   • Platform-specific feature testing",
                    "   • Realistic vendor responses"
                ]
            },
            {
                "title": "Standalone Development Framework",
                "type": "framework",
                "content": [
                    "🛠️ Independent Platform Development",
                    "",
                    "Framework Components:",
                    "   🎯 Platform Development Kit",
                    "   🧪 Integrated Testing Framework", 
                    "   🖥️  CLI Development Tools",
                    "   📋 Validation Utilities",
                    "",
                    "Development Workflow:",
                    "   1. Create platform template",
                    "   2. Implement service handlers", 
                    "   3. Add automated tests",
                    "   4. Validate with built-in tools",
                    "   5. Deploy independently",
                    "",
                    "🚀 Enables rapid BMC feature prototyping"
                ]
            },
            {
                "title": "Demo Summary & Use Cases",
                "type": "summary",
                "content": [
                    "🎊 BMC Simulator Capabilities Demonstrated",
                    "",
                    "✅ What we've shown:",
                    "   • Comprehensive Redfish API simulation",
                    "   • Enterprise RAS capabilities",
                    "   • OEM-specific action handling", 
                    "   • Firmware update workflows",
                    "   • Modular and extensible architecture",
                    "",
                    "🎯 Primary Use Cases:",
                    "   🔬 BMC Firmware Development & Testing",
                    "   🧪 Redfish Client Application Validation", 
                    "   🏢 Platform-Specific Feature Development",
                    "   📊 System Management Workflow Testing",
                    "   🔄 CI/CD Integration for BMC Projects",
                    "",
                    "🚀 Ready for production use and extension"
                ]
            }
        ]
    
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def print_slide_header(self, slide):
        """Print slide header with navigation"""
        print("="*80)
        print(f"🎯 BMC Simulator Demo - Slide {self.current_slide + 1}/{len(self.slides)}")
        print(f"📋 {slide['title']}")
        print("="*80)
    
    def print_slide_content(self, slide):
        """Print slide content"""
        for line in slide['content']:
            print(line)
        
        if slide['type'] == 'demo':
            print(f"\n🎬 Live demonstration follows...")
    
    def print_navigation(self):
        """Print navigation instructions"""
        print("\n" + "-"*80)
        print("Navigation: [N]ext | [P]revious | [Q]uit | [R]un Demo")
        if hasattr(self, 'server_process') and self.server_process:
            print("Server Status: 🟢 Running")
        else:
            print("Server Status: 🔴 Stopped")
        print("-"*80)
    
    def start_server(self):
        """Start the BMC simulator server"""
        if self.server_process:
            return True
            
        print("\n🚀 Starting BMC Simulator server...")
        try:
            cmd = ["python3", "redfishMockupServer_modular.py", 
                   "-D", "./mockups/sample", "-p", "8000"]
            
            self.server_process = subprocess.Popen(
                cmd, 
                cwd=".",
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            
            time.sleep(3)  # Wait for startup
            
            # Test server
            response = requests.get(f"{self.base_url}", timeout=2)
            if response.status_code == 200:
                print("✅ Server started successfully")
                return True
            else:
                print(f"❌ Server responded with status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False
    
    def stop_server(self):
        """Stop the server"""
        if self.server_process:
            self.server_process.terminate()
            self.server_process = None
            print("🛑 Server stopped")
    
    def execute_demo_request(self, method, path, data=None, description=""):
        """Execute and display a demo request"""
        url = f"{self.base_url}{path}"
        
        print(f"\n🔸 {description}")
        print(f"   → {method} {path}")
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=5)
            elif method == "POST":
                response = requests.post(url, json=data, 
                                       headers={"Content-Type": "application/json"}, 
                                       timeout=5)
            
            print(f"   ← Status: {response.status_code}")
            
            if response.text:
                try:
                    response_data = response.json()
                    # Show key fields for readability
                    key_fields = self.extract_demo_fields(response_data)
                    print(f"   📄 Response: {json.dumps(key_fields, indent=6)}")
                except:
                    print(f"   📄 Response: {response.text[:100]}...")
            
            time.sleep(1)  # Pause for readability
            return response.status_code, response_data if response.text else {}
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return 0, {}
    
    def extract_demo_fields(self, data):
        """Extract key fields for demo display"""
        if isinstance(data, dict):
            demo_fields = {}
            
            # Always show these if present
            priority_keys = ['@odata.id', '@odata.type', 'Name', 'Id', 'Status']
            for key in priority_keys:
                if key in data:
                    demo_fields[key] = data[key]
            
            # Show counts for collections
            if 'Members@odata.count' in data:
                demo_fields['Members@odata.count'] = data['Members@odata.count']
                if 'Members' in data and len(data['Members']) > 0:
                    demo_fields['Members'] = data['Members'][:2]  # First 2 members
            
            # Show task info
            for key in ['TaskState', 'TaskStatus', 'MessageId', 'Message']:
                if key in data:
                    demo_fields[key] = data[key]
            
            # Show service status
            if 'ServiceEnabled' in data:
                demo_fields['ServiceEnabled'] = data['ServiceEnabled']
                
            return demo_fields
        return data
    
    def demo_basic_api(self):
        """Demo basic Redfish API navigation"""
        print("\n🎬 LIVE DEMO: Basic Redfish API Navigation")
        print("="*60)
        
        self.execute_demo_request("GET", "", "Service Root Discovery")
        input("Press Enter to continue...")
        
        self.execute_demo_request("GET", "/Systems", "Systems Collection")
        input("Press Enter to continue...")
        
        self.execute_demo_request("GET", "/Systems/system", "Individual System")
        input("Press Enter to continue...")
        
        self.execute_demo_request("GET", "/Managers", "Managers Collection")
        print("\n✅ Basic API navigation complete!")
        input("Press Enter to return to presentation...")
    
    def demo_ras_service(self):
        """Demo RAS service capabilities"""
        print("\n🎬 LIVE DEMO: Enterprise RAS Service")
        print("="*60)
        
        self.execute_demo_request("GET", "/RASService", "RAS Service Root")
        input("Press Enter to continue...")
        
        self.execute_demo_request("GET", "/RASService/Endpoints", "RAS Endpoints")  
        input("Press Enter to continue...")
        
        self.execute_demo_request("GET", "/RASService/Endpoints/Endpoint-1", "CPU RAS Endpoint")
        input("Press Enter to continue...")
        
        self.execute_demo_request("POST", "/RASService/Actions/SubmitRASAction",
                                 {"ActionType": "DiagnosticTest", "Target": "CPU-Socket-0"},
                                 "RAS Diagnostic Action")
        input("Press Enter to continue...")
        
        self.execute_demo_request("GET", "/RASService/ErrorQueues", "Error Queues")
        print("\n✅ RAS Service demo complete!")
        input("Press Enter to return to presentation...")
    
    def demo_update_service(self):
        """Demo UpdateService capabilities"""
        print("\n🎬 LIVE DEMO: UpdateService")
        print("="*60)
        
        self.execute_demo_request("GET", "/UpdateService", "UpdateService Root")
        input("Press Enter to continue...")
        
        self.execute_demo_request("POST", "/UpdateService/Actions/UpdateService.SimpleUpdate",
                                 {"ImageURI": "http://example.com/firmware.bin",
                                  "Targets": ["/redfish/v1/Systems/system"]},
                                 "Simple Update Task")
        input("Press Enter to continue...")
        
        self.execute_demo_request("POST", "/UpdateService/FirmwareInventory",
                                 {"Name": "Demo BIOS", "Version": "3.1.0", "Id": "demo-bios-v3"},
                                 "Create Firmware Entry")
        print("\n✅ UpdateService demo complete!")
        input("Press Enter to return to presentation...")
    
    def run_slide_demo(self, slide):
        """Run the demo for a slide"""
        if 'demo_func' in slide:
            if not self.server_process:
                print("\n⚠️  Server needs to be started for live demo")
                if input("Start server now? (y/N): ").lower() == 'y':
                    if not self.start_server():
                        print("Failed to start server. Skipping demo.")
                        return
                else:
                    return
            
            # Run the demo function
            demo_func = getattr(self, slide['demo_func'])
            demo_func()
    
    def run_presentation(self):
        """Run the interactive presentation"""
        try:
            while True:
                self.clear_screen()
                
                slide = self.slides[self.current_slide]
                self.print_slide_header(slide)
                print()
                self.print_slide_content(slide)
                self.print_navigation()
                
                try:
                    choice = input("\nChoice: ").lower().strip()
                except KeyboardInterrupt:
                    break
                
                if choice in ['q', 'quit', 'exit']:
                    break
                elif choice in ['n', 'next', ''] and self.current_slide < len(self.slides) - 1:
                    self.current_slide += 1
                elif choice in ['p', 'prev', 'previous'] and self.current_slide > 0:
                    self.current_slide -= 1
                elif choice in ['r', 'run', 'demo']:
                    self.run_slide_demo(slide)
                elif choice in ['s', 'start']:
                    self.start_server()
                elif choice in ['stop']:
                    self.stop_server()
                elif choice.isdigit():
                    slide_num = int(choice) - 1
                    if 0 <= slide_num < len(self.slides):
                        self.current_slide = slide_num
        
        finally:
            if self.server_process:
                self.stop_server()
            
            self.clear_screen()
            print("🎊 Thank you for viewing the BMC Simulator Demo!")
            print("   For more information and code, visit:")
            print("   📁 ./")
            print("\n🚀 Happy BMC development!")

def main():
    """Main presentation runner"""
    if len(sys.argv) > 1 and sys.argv[1] == 'auto':
        # Auto-run all demos
        demo = LiveDemoPresentation()
        if demo.start_server():
            try:
                demo.demo_basic_api()
                demo.demo_ras_service()
                demo.demo_update_service()
            finally:
                demo.stop_server()
    else:
        # Interactive presentation
        presentation = LiveDemoPresentation()
        presentation.run_presentation()

if __name__ == "__main__":
    main()