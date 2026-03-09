#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Client Examples
======================

Example scripts showing how to use the Redfish client library
for common BMC operations and development scenarios.
"""

import logging
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import RedfishClient, RedfishClientError, AuthenticationError, ResourceNotFoundError, OperationError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def example_basic_operations():
    """Example: Basic Redfish operations"""
    print("="*60)
    print("Example 1: Basic Redfish Operations")
    print("="*60)
    
    # Create client (use BMC Simulator URL)
    client = RedfishClient("http://localhost:8000", verify_ssl=False)
    
    try:
        # Connect and login
        if not client.connect():
            print("❌ Failed to connect to service")
            return
        
        if not client.login("admin", "admin"):
            print("❌ Authentication failed")
            return
        
        print(f"✅ Connected to {client.vendor} {client.product}")
        print(f"   Redfish Version: {client.redfish_version}")
        
        # Get service root information
        service_root = client.service_root
        print(f"\n📋 Service Root:")
        print(f"   UUID: {service_root.get('UUID', 'N/A')}")
        print(f"   Product: {service_root.get('Product', 'N/A')}")
        print(f"   Vendor: {service_root.get('Vendor', 'N/A')}")
        
        # Get systems
        print("\n🖥️  Computer Systems:")
        systems = client.get_systems()
        for system in systems:
            status = system.data.get('Status', {})
            print(f"   - {system.name} ({system.id})")
            print(f"     State: {status.get('State', 'Unknown')}")
            print(f"     Health: {status.get('Health', 'Unknown')}")
            print(f"     Power: {system.data.get('PowerState', 'Unknown')}")
        
        # Get chassis
        print("\n🏗️  Chassis:")
        chassis_list = client.get_chassis()
        for chassis in chassis_list:
            status = chassis.data.get('Status', {})
            print(f"   - {chassis.name} ({chassis.id})")
            print(f"     Type: {chassis.data.get('ChassisType', 'Unknown')}")
            print(f"     Health: {status.get('Health', 'Unknown')}")
        
        # Get managers (BMCs)
        print("\n⚙️  Managers:")
        managers = client.get_managers()
        for manager in managers:
            status = manager.data.get('Status', {})
            print(f"   - {manager.name} ({manager.id})")
            print(f"     Type: {manager.data.get('ManagerType', 'Unknown')}")
            print(f"     Health: {status.get('Health', 'Unknown')}")
            print(f"     Firmware: {manager.data.get('FirmwareVersion', 'Unknown')}")
        
        # Get overall health
        print("\n🏥 System Health Summary:")
        health = client.get_health_status()
        for component, status in health.items():
            print(f"   {component.title()}: {status}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        client.logout()
        print("\n👋 Disconnected")

def example_system_power_management():
    """Example: System power management operations"""
    print("\n" + "="*60)
    print("Example 2: System Power Management")
    print("="*60)
    
    client = RedfishClient("http://localhost:8000")
    
    try:
        if not client.connect() or not client.login("admin", "admin"):
            print("❌ Connection/authentication failed")
            return
        
        # Get first system
        systems = client.get_systems()
        if not systems:
            print("❌ No systems found")
            return
        
        system = systems[0]
        system_id = system.id
        print(f"🖥️  Managing system: {system.name} ({system_id})")
        print(f"   Current Power State: {system.data.get('PowerState', 'Unknown')}")
        
        # Demonstrate power operations (commented out to avoid actual power cycling)
        print("\n⚡ Available Power Operations:")
        print("   - Power On System")
        print("   - Power Off System") 
        print("   - Reboot System")
        
        # Example power on (uncomment to test)
        # print("\n🔌 Powering on system...")
        # result = client.power_on_system(system_id)
        # print(f"   Result: {result}")
        
        # Example graceful reboot (uncomment to test)
        # print("\n🔄 Rebooting system...")
        # result = client.reboot_system(system_id)
        # print(f"   Result: {result}")
        
        print("\n✅ Power management operations available")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        client.logout()

def example_resource_management():
    """Example: Resource creation and management"""
    print("\n" + "="*60)
    print("Example 3: Resource Management")
    print("="*60)
    
    client = RedfishClient("http://localhost:8000")
    
    try:
        if not client.connect() or not client.login("admin", "admin"):
            print("❌ Connection/authentication failed")
            return
        
        # Get first system for demonstration
        systems = client.get_systems()
        if not systems:
            print("❌ No systems found")
            return
        
        system = systems[0]
        print(f"🖥️  Working with system: {system.name}")
        
        # Example: Get memory resources
        memory_collection_url = f"/redfish/v1/Systems/{system.id}/Memory"
        
        try:
            print("\n💾 Memory Modules:")
            memory_modules = client.get_collection(memory_collection_url)
            
            for memory in memory_modules[:3]:  # Show first 3
                data = memory.data
                print(f"   - {memory.name} ({memory.id})")
                print(f"     Capacity: {data.get('CapacityMiB', 0)} MiB")
                print(f"     Type: {data.get('MemoryType', 'Unknown')}")
                print(f"     Status: {data.get('Status', {}).get('Health', 'Unknown')}")
        
        except Exception as e:
            print(f"   Memory collection not available: {e}")
        
        # Example: Create a new resource (if supported)
        print("\n➕ Resource Creation Example:")
        print("   (Creating test memory module)")
        
        try:
            new_memory = {
                "Name": "Test DIMM",
                "CapacityMiB": 8192,
                "MemoryType": "DDR4",
                "BaseModuleType": "UDIMM"
            }
            
            # Uncomment to test actual creation
            # created = client.create_resource(memory_collection_url, new_memory)
            # print(f"   ✅ Created: {created.name} ({created.id})")
            print("   📝 Resource creation example prepared")
            
        except Exception as e:
            print(f"   ⚠️  Creation not supported: {e}")
        
        # Example: Update resource properties
        print("\n✏️  Resource Update Example:")
        print("   (Updating asset tag)")
        
        try:
            if memory_modules:
                memory_url = memory_modules[0].odata_id
                updates = {"AssetTag": f"ASSET-{int(time.time())}"}
                
                # Uncomment to test actual update
                # updated = client.update_resource(memory_url, updates)
                # print(f"   ✅ Updated asset tag: {updated.data.get('AssetTag')}")
                print("   📝 Resource update example prepared")
            
        except Exception as e:
            print(f"   ⚠️  Update not supported: {e}")
        
        print("\n✅ Resource management examples completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        client.logout()

def example_event_handling():
    """Example: Event subscription and handling"""
    print("\n" + "="*60)
    print("Example 4: Event Subscription and Handling")
    print("="*60)
    
    client = RedfishClient("http://localhost:8000")
    
    try:
        if not client.connect() or not client.login("admin", "admin"):
            print("❌ Connection/authentication failed")
            return
        
        # Check if EventService is available
        event_service = client.service_root.get('EventService')
        if not event_service:
            print("❌ EventService not available")
            return
        
        print("🔔 Event Service Available")
        print(f"   Service Enabled: {event_service.get('ServiceEnabled', False)}")
        
        # Get existing subscriptions
        existing_subscriptions = client.get_event_subscriptions()
        print(f"\n📋 Existing Subscriptions: {len(existing_subscriptions)}")
        
        for sub in existing_subscriptions[:3]:  # Show first 3
            print(f"   - {sub.id}: {sub.destination}")
            print(f"     Context: {sub.context}")
            print(f"     Events: {sub.event_types}")
        
        # Create new subscription
        print("\n➕ Creating Event Subscription:")
        
        try:
            subscription = client.create_event_subscription(
                destination="http://client.example.com:9999/events",
                event_types=["Alert", "ResourceAdded", "ResourceUpdated"],
                context="RedFishClient-Example"
            )
            
            print(f"   ✅ Created subscription: {subscription.id}")
            print(f"   Destination: {subscription.destination}")
            print(f"   Event Types: {subscription.event_types}")
            
            # Submit test event
            print("\n🧪 Submitting Test Event:")
            test_result = client.submit_test_event(
                event_type="Alert",
                message="This is a test event from the Redfish client",
                severity="Warning"
            )
            print(f"   ✅ Test event submitted: {test_result}")
            
            # Wait a moment then clean up
            time.sleep(2)
            
            print(f"\n🗑️  Cleaning up subscription...")
            if client.delete_event_subscription(subscription.id):
                print("   ✅ Subscription deleted")
            else:
                print("   ⚠️  Failed to delete subscription")
        
        except Exception as e:
            print(f"   ⚠️  Subscription creation failed: {e}")
        
        print("\n✅ Event handling example completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        client.logout()

def example_advanced_operations():
    """Example: Advanced Redfish operations"""
    print("\n" + "="*60)
    print("Example 5: Advanced Operations")
    print("="*60)
    
    client = RedfishClient("http://localhost:8000")
    
    try:
        if not client.connect() or not client.login("admin", "admin"):
            print("❌ Connection/authentication failed")
            return
        
        # Get detailed system information
        systems = client.get_systems()
        if not systems:
            print("❌ No systems found")
            return
        
        system = systems[0]
        system_data = system.data
        
        print(f"🔍 Detailed System Analysis: {system.name}")
        
        # System specifications
        print("\n📊 System Specifications:")
        print(f"   Model: {system_data.get('Model', 'Unknown')}")
        print(f"   SKU: {system_data.get('SKU', 'Unknown')}")
        print(f"   Serial: {system_data.get('SerialNumber', 'Unknown')}")
        print(f"   BIOS Version: {system_data.get('BiosVersion', 'Unknown')}")
        
        # Memory summary
        memory_summary = system_data.get('MemorySummary', {})
        print(f"\n💾 Memory Summary:")
        print(f"   Total: {memory_summary.get('TotalSystemMemoryGiB', 0)} GiB")
        print(f"   Status: {memory_summary.get('Status', {}).get('Health', 'Unknown')}")
        
        # Processor summary
        processor_summary = system_data.get('ProcessorSummary', {})
        print(f"\n⚙️  Processor Summary:")
        print(f"   Count: {processor_summary.get('Count', 0)}")
        print(f"   Model: {processor_summary.get('Model', 'Unknown')}")
        print(f"   Status: {processor_summary.get('Status', {}).get('Health', 'Unknown')}")
        
        # Boot information
        boot_info = system_data.get('Boot', {})
        print(f"\n🔄 Boot Information:")
        print(f"   Boot Source: {boot_info.get('BootSourceOverrideTarget', 'None')}")
        print(f"   Boot Mode: {boot_info.get('BootSourceOverrideMode', 'UEFI')}")
        print(f"   Boot Enabled: {boot_info.get('BootSourceOverrideEnabled', 'Disabled')}")
        
        # Power metrics (if available)
        power_url = system_data.get('PowerState')
        if power_url:
            print(f"\n⚡ Power State: {power_url}")
        
        # Available actions
        actions = system_data.get('Actions', {})
        print(f"\n🎬 Available Actions:")
        for action_name, action_info in actions.items():
            if isinstance(action_info, dict) and 'target' in action_info:
                print(f"   - {action_name}")
                allowed_values = action_info.get('ResetType@Redfish.AllowableValues', [])
                if allowed_values:
                    print(f"     Allowed Values: {allowed_values}")
        
        # OEM extensions (if any)
        oem_data = system_data.get('Oem', {})
        if oem_data:
            print(f"\n🏭 OEM Extensions:")
            for vendor, vendor_data in oem_data.items():
                print(f"   {vendor}: {len(vendor_data) if isinstance(vendor_data, dict) else 'Available'}")
        
        print("\n✅ Advanced analysis completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        client.logout()

def example_error_handling():
    """Example: Error handling and recovery"""
    print("\n" + "="*60)
    print("Example 6: Error Handling and Recovery")  
    print("="*60)
    
    client = RedfishClient("http://localhost:8000")
    
    try:
        # Test connection to non-existent service
        print("🔍 Testing Error Scenarios:")
        
        # Test authentication failure
        print("\n1. Authentication Error Test:")
        if client.connect():
            try:
                client.login("baduser", "badpass")
                print("   ⚠️  Unexpected: Authentication should have failed")
            except AuthenticationError as e:
                print(f"   ✅ Caught authentication error: {e}")
            except Exception as e:
                print(f"   ⚠️  Unexpected error type: {e}")
        
        # Test successful authentication
        if client.login("admin", "admin"):
            print("\n2. Resource Not Found Test:")
            try:
                client.get_resource("/redfish/v1/Systems/NonExistentSystem")
                print("   ⚠️  Unexpected: Should have thrown ResourceNotFoundError")
            except ResourceNotFoundError as e:
                print(f"   ✅ Caught resource not found: {e}")
            except Exception as e:
                print(f"   ⚠️  Unexpected error type: {e}")
            
            print("\n3. Invalid Operation Test:")
            try:
                # Try to create resource in read-only collection
                client.create_resource("/redfish/v1/", {"Invalid": "Data"})
                print("   ⚠️  Unexpected: Should have thrown OperationError")
            except OperationError as e:
                print(f"   ✅ Caught operation error: {e}")
            except Exception as e:
                print(f"   ⚠️  Unexpected error type: {e}")
            
            print("\n4. Session Expiry Test:")
            if client.is_authenticated():
                print("   ✅ Session is valid")
            
            # Simulate session expiry
            client.session_expiry = time.time() - 1  # Set to past
            if not client.is_authenticated():
                print("   ✅ Session expiry detected correctly")
        
        print("\n✅ Error handling tests completed")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    finally:
        client.close()

def main():
    """Run all examples"""
    print("🎪 Redfish Client Library Examples")
    print("=" * 60)
    print("Demonstrating comprehensive BMC interaction capabilities")
    print("Using BMC Simulator at http://localhost:8000")
    print()
    
    examples = [
        ("Basic Operations", example_basic_operations),
        ("Power Management", example_system_power_management),
        ("Resource Management", example_resource_management),
        ("Event Handling", example_event_handling),
        ("Advanced Operations", example_advanced_operations),
        ("Error Handling", example_error_handling),
    ]
    
    for name, example_func in examples:
        try:
            example_func()
            print()
        except KeyboardInterrupt:
            print("\n\n👋 Examples interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Example '{name}' failed: {e}")
            print()
    
    print("🎉 All examples completed!")
    print("\n💡 Tips for Development:")
    print("   - Always handle authentication and connection errors")
    print("   - Use try/finally blocks to ensure proper logout")
    print("   - Check resource availability before operations")
    print("   - Monitor session expiry for long-running applications")
    print("   - Implement retry logic for transient failures")
    print("   - Use event subscriptions for real-time monitoring")

if __name__ == "__main__":
    main()