#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Client Demo Launcher
============================

Interactive launcher for all Redfish client demonstrations and tools.
"""

import os
import sys
import subprocess
import time

def print_banner():
    """Print welcome banner"""
    print("🎪 Redfish Client Library - Demo Launcher")
    print("=" * 60)
    print("Comprehensive BMC interaction tools for developers")
    print("=" * 60)

def check_server_status():
    """Check if BMC simulator is running"""
    try:
        import requests
        response = requests.get("http://localhost:8000/redfish/v1", timeout=2)
        return response.status_code == 200
    except:
        return False

def start_bmc_server():
    """Offer to start BMC server"""
    if check_server_status():
        print("✅ BMC Simulator is already running at http://localhost:8000")
        return True
    
    print("⚠️  BMC Simulator is not running")
    choice = input("Would you like to start it? (y/n): ").strip().lower()
    
    if choice in ['y', 'yes']:
        print("🚀 Starting BMC Simulator...")
        try:
            # Start server in background (using modular version)
            subprocess.Popen([
                sys.executable, "redfishMockupServer_modular.py", 
                "-D", "public-rackmount1", "-p", "8000"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for startup
            for i in range(10):
                time.sleep(1)
                if check_server_status():
                    print("✅ BMC Simulator started successfully")
                    return True
                print(f"   Waiting for startup... ({i+1}/10)")
            
            print("❌ Failed to start BMC Simulator")
            return False
            
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            return False
    
    return False

def run_script(script_name, description):
    """Run a Python script"""
    print(f"\n🚀 {description}")
    print("=" * 60)
    
    try:
        result = subprocess.run([sys.executable, script_name], check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")
        return False

def main_menu():
    """Show main menu and handle user choice"""
    while True:
        print("\n🎯 Available Demonstrations:")
        print("=" * 60)
        print("1. 🧪 Basic Client Test - Verify library functionality")
        print("2. 📚 Client Examples - Comprehensive usage examples")  
        print("3. 🎯 Monitoring Client - Real-time system monitoring")
        print("4. 🧪 Test Suite - Full compatibility testing")
        print("5. 🌐 Web Dashboard - Browser-based monitoring")
        print("6. 📊 Enhanced System Demo - Complete system showcase")
        print("7. 🔍 Validate Enhanced System - Component validation")
        print("8. 🏃 Quick Enhanced Demo - Core features overview")
        print("9. ❓ Help - Show detailed descriptions")
        print("0. 👋 Exit")
        print()
        
        choice = input("Select option (0-9): ").strip()
        
        if choice == '0':
            print("\n👋 Thanks for using the Redfish Client Library!")
            break
            
        elif choice == '1':
            run_script("test_client_basic.py", "Basic Client Library Test")
            
        elif choice == '2':
            run_script("redfish_client_examples.py", "Comprehensive Client Examples")
            
        elif choice == '3':
            run_script("redfish_monitoring_client.py", "Real-time Monitoring Client Demo")
            
        elif choice == '4':
            run_script("redfish_client_test_suite.py", "Complete Test Suite")
            
        elif choice == '5':
            print("\n🌐 Starting Web Dashboard...")
            print("   Dashboard will be available at: http://localhost:5000")
            print("   Press Ctrl+C to stop the dashboard")
            run_script("redfish_web_dashboard.py", "Web-based Monitoring Dashboard")
            
        elif choice == '6':
            run_script("demo_enhanced_redfish_system.py", "Enhanced System Demonstration")
            
        elif choice == '7':
            run_script("validate_enhanced_system.py", "Enhanced System Validation")
            
        elif choice == '8':
            run_script("quick_enhanced_demo.py", "Quick Enhanced Features Demo")
            
        elif choice == '9':
            show_help()
            
        else:
            print("❌ Invalid choice. Please select 0-9.")
        
        if choice != '9':
            input("\nPress Enter to return to menu...")

def show_help():
    """Show detailed help information"""
    print("\n📖 Redfish Client Library - Detailed Help")
    print("=" * 60)
    
    help_info = {
        "Basic Client Test": {
            "script": "test_client_basic.py",
            "description": "Quick validation of library imports and basic functionality",
            "duration": "< 1 minute",
            "requirements": "None (works without server)"
        },
        "Client Examples": {
            "script": "redfish_client_examples.py", 
            "description": "Comprehensive examples of all client capabilities",
            "duration": "2-3 minutes",
            "requirements": "BMC Simulator running"
        },
        "Monitoring Client": {
            "script": "redfish_monitoring_client.py",
            "description": "Real-time system monitoring with alerts and metrics",
            "duration": "1-5 minutes (configurable)",
            "requirements": "BMC Simulator running"
        },
        "Test Suite": {
            "script": "redfish_client_test_suite.py",
            "description": "Complete validation of client functionality and BMC compatibility",
            "duration": "2-5 minutes",
            "requirements": "BMC Simulator running"
        },
        "Web Dashboard": {
            "script": "redfish_web_dashboard.py",
            "description": "Browser-based monitoring interface with real-time updates",
            "duration": "Continuous (until stopped)",
            "requirements": "BMC Simulator running, Flask library"
        },
        "Enhanced System Demo": {
            "script": "demo_enhanced_redfish_system.py",
            "description": "Demonstration of enhanced message/event/logging system",
            "duration": "3-5 minutes",
            "requirements": "Enhanced BMC Simulator"
        }
    }
    
    for title, info in help_info.items():
        print(f"\n📋 {title}")
        print(f"   Script: {info['script']}")
        print(f"   Description: {info['description']}")
        print(f"   Duration: {info['duration']}")
        print(f"   Requirements: {info['requirements']}")
    
    print("\n🔧 Prerequisites:")
    print("   • Python 3.7+ with requests library")
    print("   • BMC Simulator running at http://localhost:8000")
    print("   • For web dashboard: Flask library (pip install flask)")
    
    print("\n🎯 Quick Start Recommendation:")
    print("   1. Run 'Basic Client Test' first to verify installation")
    print("   2. Start BMC Simulator if not already running")
    print("   3. Try 'Client Examples' for comprehensive overview")
    print("   4. Use 'Web Dashboard' for interactive monitoring")

def main():
    """Main launcher function"""
    try:
        print_banner()
        
        # Check if we're in the right directory
        if not os.path.exists("redfish_client.py"):
            print("\n❌ Error: Please run this script from the Redfish-Mockup-Server directory")
            print("   Current directory:", os.getcwd())
            print("   Required files: redfish_client.py, redfish_client_examples.py")
            return 1
        
        # Check server status and offer to start
        print("\n🔍 Checking BMC Simulator status...")
        start_bmc_server()
        
        # Show main menu
        main_menu()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n👋 Demo launcher interrupted. Goodbye!")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())