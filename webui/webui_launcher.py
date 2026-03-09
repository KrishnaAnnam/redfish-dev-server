#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Launcher for BMC Redfish Simulator Web UIs
Provides easy access to both Server and Client web interfaces
"""

import sys
import subprocess
import time
import webbrowser
from pathlib import Path

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║       BMC Redfish Simulator - Web UI Launcher               ║
╚══════════════════════════════════════════════════════════════╝
    """)

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import flask
        import flask_cors
        import psutil
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e.name}")
        print("\nPlease install dependencies:")
        print("  pip install -r webui/requirements_webui.txt")
        return False

def launch_server_ui(host='127.0.0.1', port=5000, open_browser=True):
    """Launch Server Web UI"""
    script_path = Path(__file__).parent / 'server' / 'server_webui.py'
    
    print(f"\n🚀 Launching Server Web UI...")
    print(f"   URL: http://{host}:{port}/")
    
    process = subprocess.Popen(
        [sys.executable, str(script_path), '-H', host, '-p', str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    # Wait a moment for server to start
    time.sleep(2)
    
    if open_browser:
        webbrowser.open(f'http://{host}:{port}/')
    
    return process

def launch_client_ui(host='127.0.0.1', port=5001, open_browser=True):
    """Launch Client Web UI"""
    script_path = Path(__file__).parent / 'client' / 'client_webui.py'
    
    print(f"\n🚀 Launching Client Web UI...")
    print(f"   URL: http://{host}:{port}/")
    
    process = subprocess.Popen(
        [sys.executable, str(script_path), '-H', host, '-p', str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    # Wait a moment for server to start
    time.sleep(2)
    
    if open_browser:
        webbrowser.open(f'http://{host}:{port}/')
    
    return process

def show_menu():
    """Show interactive menu"""
    print("\nWhat would you like to launch?\n")
    print("  1. Server Web UI (Control Panel)")
    print("  2. Client Web UI (Redfish Client)")
    print("  3. Both (Recommended)")
    print("  4. Exit")
    print()
    
    choice = input("Enter your choice (1-4): ").strip()
    return choice

def main():
    """Main launcher"""
    print_banner()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Parse arguments or show menu
    if len(sys.argv) > 1:
        if sys.argv[1] == 'server':
            process = launch_server_ui()
            print("\n✅ Server Web UI is running!")
            print("   Press Ctrl+C to stop")
            try:
                process.wait()
            except KeyboardInterrupt:
                process.terminate()
                print("\n\n👋 Server Web UI stopped")
        
        elif sys.argv[1] == 'client':
            process = launch_client_ui()
            print("\n✅ Client Web UI is running!")
            print("   Press Ctrl+C to stop")
            try:
                process.wait()
            except KeyboardInterrupt:
                process.terminate()
                print("\n\n👋 Client Web UI stopped")
        
        elif sys.argv[1] == 'both':
            server_process = launch_server_ui(open_browser=True)
            time.sleep(1)
            client_process = launch_client_ui(open_browser=True)
            
            print("\n✅ Both Web UIs are running!")
            print("   Server UI: http://127.0.0.1:5000/")
            print("   Client UI: http://127.0.0.1:5001/")
            print("\n   Press Ctrl+C to stop both")
            
            try:
                server_process.wait()
            except KeyboardInterrupt:
                server_process.terminate()
                client_process.terminate()
                print("\n\n👋 Web UIs stopped")
        
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print("  python webui_launcher.py server  # Launch Server UI")
            print("  python webui_launcher.py client  # Launch Client UI")
            print("  python webui_launcher.py both    # Launch both")
            sys.exit(1)
    
    else:
        # Interactive menu
        while True:
            choice = show_menu()
            
            if choice == '1':
                process = launch_server_ui()
                print("\n✅ Server Web UI is running!")
                print("   Press Ctrl+C to stop")
                try:
                    process.wait()
                except KeyboardInterrupt:
                    process.terminate()
                    print("\n\n👋 Server Web UI stopped")
                break
            
            elif choice == '2':
                process = launch_client_ui()
                print("\n✅ Client Web UI is running!")
                print("   Press Ctrl+C to stop")
                try:
                    process.wait()
                except KeyboardInterrupt:
                    process.terminate()
                    print("\n\n👋 Client Web UI stopped")
                break
            
            elif choice == '3':
                server_process = launch_server_ui(open_browser=True)
                time.sleep(1)
                client_process = launch_client_ui(open_browser=True)
                
                print("\n✅ Both Web UIs are running!")
                print("   Server UI: http://127.0.0.1:5000/")
                print("   Client UI: http://127.0.0.1:5001/")
                print("\n   Press Ctrl+C to stop both")
                
                try:
                    server_process.wait()
                except KeyboardInterrupt:
                    server_process.terminate()
                    client_process.terminate()
                    print("\n\n👋 Web UIs stopped")
                break
            
            elif choice == '4':
                print("\n👋 Goodbye!")
                break
            
            else:
                print("\n❌ Invalid choice. Please enter 1-4.\n")

if __name__ == '__main__':
    main()
