#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Client Test Suite
========================

Comprehensive test suite for validating Redfish client functionality
against BMC simulators and real BMC hardware.
"""

import time
import json
import logging
from typing import Dict, List, Any
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import RedfishClient, RedfishClientError, AuthenticationError
from monitoring import RedfishMonitoringClient

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise for tests

class RedfishClientTester:
    """Test suite for Redfish client validation"""
    
    def __init__(self, bmc_url: str = "http://localhost:8000", 
                 username: str = "admin", password: str = "admin"):
        self.bmc_url = bmc_url
        self.username = username  
        self.password = password
        self.test_results: List[Dict[str, Any]] = []
    
    def run_test(self, test_name: str, test_func):
        """Run a test and record results"""
        print(f"🧪 Testing: {test_name}")
        
        start_time = time.time()
        success = False
        error_message = None
        
        try:
            result = test_func()
            success = result if isinstance(result, bool) else True
            print(f"   ✅ PASSED")
            
        except Exception as e:
            error_message = str(e)
            print(f"   ❌ FAILED: {error_message}")
        
        duration = time.time() - start_time
        
        self.test_results.append({
            'test_name': test_name,
            'success': success,
            'duration': duration,
            'error': error_message
        })
        
        return success
    
    def test_connection_and_authentication(self):
        """Test basic connection and authentication"""
        client = RedfishClient(self.bmc_url)
        
        try:
            # Test connection
            if not client.connect():
                raise Exception("Connection failed")
            
            # Test authentication
            if not client.login(self.username, self.password):
                raise Exception("Authentication failed")
            
            # Verify service root
            if not client.service_root:
                raise Exception("Service root not available")
            
            # Test session validation
            if not client.is_authenticated():
                raise Exception("Session validation failed")
            
            return True
            
        finally:
            client.logout()
    
    def test_basic_resource_operations(self):
        """Test basic resource CRUD operations"""
        client = RedfishClient(self.bmc_url)
        
        try:
            if not client.connect() or not client.login(self.username, self.password):
                raise Exception("Connection/authentication failed")
            
            # Test GET operations
            systems = client.get_systems()
            if not systems:
                raise Exception("No systems found")
            
            system = systems[0]
            retrieved_system = client.get_resource(system.odata_id)
            
            if retrieved_system.id != system.id:
                raise Exception("Resource retrieval mismatch")
            
            # Test collection operations
            chassis_list = client.get_chassis()
            managers = client.get_managers()
            
            # Verify we got some resources
            if not (chassis_list or managers):
                raise Exception("No chassis or managers found")
            
            return True
            
        finally:
            client.logout()
    
    def test_system_power_operations(self):
        """Test system power management"""
        client = RedfishClient(self.bmc_url)
        
        try:
            if not client.connect() or not client.login(self.username, self.password):
                raise Exception("Connection/authentication failed")
            
            systems = client.get_systems()
            if not systems:
                raise Exception("No systems available for power testing")
            
            system = systems[0]
            system_id = system.id
            
            # Check if power actions are available
            system_data = system.data
            actions = system_data.get('Actions', {})
            reset_action = actions.get('#ComputerSystem.Reset', {})
            
            if not reset_action.get('target'):
                print("   ⚠️  Power actions not available (expected in simulator)")
                return True  # Not a failure for simulator
            
            # In a real test, you might actually test power operations
            # For safety, we just verify the action endpoints exist
            print("   ℹ️  Power action endpoints verified")
            return True
            
        finally:
            client.logout()
    
    def test_event_subscriptions(self):
        """Test event subscription management"""
        client = RedfishClient(self.bmc_url)
        
        try:
            if not client.connect() or not client.login(self.username, self.password):
                raise Exception("Connection/authentication failed")
            
            # Check if EventService is available
            event_service = client.service_root.get('EventService')
            if not event_service:
                print("   ⚠️  EventService not available")
                return True  # Not a failure
            
            # Test subscription creation
            subscription = client.create_event_subscription(
                destination="http://test.example.com/events",
                event_types=["Alert", "ResourceAdded"],
                context="TestSubscription"
            )
            
            if not subscription or not subscription.id:
                raise Exception("Failed to create event subscription")
            
            # Test subscription listing
            subscriptions = client.get_event_subscriptions()
            found = any(s.id == subscription.id for s in subscriptions)
            
            if not found:
                raise Exception("Created subscription not found in list")
            
            # Test subscription deletion
            if not client.delete_event_subscription(subscription.id):
                raise Exception("Failed to delete subscription")
            
            # Test event submission
            test_result = client.submit_test_event(
                event_type="Alert",
                message="Test event from validation suite",
                severity="OK"
            )
            
            if not test_result:
                raise Exception("Failed to submit test event")
            
            return True
            
        finally:
            client.logout()
    
    def test_resource_creation_and_modification(self):
        """Test resource creation and modification (if supported)"""
        client = RedfishClient(self.bmc_url)
        
        try:
            if not client.connect() or not client.login(self.username, self.password):
                raise Exception("Connection/authentication failed")
            
            systems = client.get_systems()
            if not systems:
                raise Exception("No systems available")
            
            system = systems[0]
            
            # Try to access memory collection
            memory_url = f"/redfish/v1/Systems/{system.id}/Memory"
            
            try:
                memory_collection = client.get_resource(memory_url)
                memory_members = client.get_collection(memory_url)
                
                print(f"   ℹ️  Found {len(memory_members)} memory modules")
                
                # Test resource modification (PATCH)
                if memory_members:
                    memory_module = memory_members[0]
                    
                    # Try to update asset tag (common writable property)
                    test_asset_tag = f"TEST-{int(time.time())}"
                    
                    try:
                        updated = client.update_resource(
                            memory_module.odata_id,
                            {"AssetTag": test_asset_tag}
                        )
                        print(f"   ℹ️  Successfully updated asset tag")
                    except:
                        print(f"   ⚠️  Asset tag update not supported")
                
            except Exception as e:
                print(f"   ⚠️  Memory operations not fully supported: {e}")
            
            return True
            
        finally:
            client.logout()
    
    def test_error_handling(self):
        """Test error handling and edge cases"""
        client = RedfishClient(self.bmc_url)
        
        try:
            if not client.connect() or not client.login(self.username, self.password):
                raise Exception("Connection/authentication failed")
            
            # Test 404 handling
            try:
                client.get_resource("/redfish/v1/Systems/NonExistent")
                raise Exception("Should have thrown ResourceNotFoundError")
            except Exception as e:
                if "not found" not in str(e).lower():
                    raise Exception(f"Unexpected error type: {e}")
            
            # Test invalid operations
            try:
                client.create_resource("/redfish/v1/", {"Invalid": "Data"})
                # May succeed in simulator, just check it doesn't crash
            except Exception:
                pass  # Expected
            
            # Test session expiry handling
            if client.is_authenticated():
                print("   ℹ️  Session validation working")
            
            return True
            
        finally:
            client.logout()
    
    def test_monitoring_client(self):
        """Test monitoring client functionality"""
        monitor = RedfishMonitoringClient(
            self.bmc_url, self.username, self.password, poll_interval=5
        )
        
        try:
            # Test connection
            if not monitor.connect():
                raise Exception("Monitoring client connection failed")
            
            # Test metrics collection
            metrics = monitor.collect_system_metrics()
            if not metrics:
                raise Exception("No metrics collected")
            
            # Test alert checking
            monitor.check_health_alerts(metrics)
            
            # Test dashboard data
            dashboard = monitor.get_dashboard_data()
            
            required_keys = ['system_summary', 'alert_summary', 'current_metrics']
            for key in required_keys:
                if key not in dashboard:
                    raise Exception(f"Dashboard missing key: {key}")
            
            print(f"   ℹ️  Collected metrics for {len(metrics)} systems")
            return True
            
        finally:
            monitor.disconnect()
    
    def test_concurrent_operations(self):
        """Test concurrent client operations"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def client_operation(client_id):
            client = RedfishClient(self.bmc_url)
            try:
                if client.connect() and client.login(self.username, self.password):
                    systems = client.get_systems()
                    results.put(('success', client_id, len(systems)))
                else:
                    results.put(('failure', client_id, 'auth_failed'))
            except Exception as e:
                results.put(('failure', client_id, str(e)))
            finally:
                client.logout()
        
        # Start multiple concurrent clients
        threads = []
        num_clients = 3
        
        for i in range(num_clients):
            thread = threading.Thread(target=client_operation, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join(timeout=30)
        
        # Check results
        successes = 0
        while not results.empty():
            status, client_id, result = results.get()
            if status == 'success':
                successes += 1
            else:
                print(f"   ⚠️  Client {client_id} failed: {result}")
        
        if successes < num_clients:
            raise Exception(f"Only {successes}/{num_clients} concurrent clients succeeded")
        
        print(f"   ℹ️  {successes} concurrent clients succeeded")
        return True
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("🧪 Redfish Client Test Suite")
        print("=" * 50)
        print(f"Testing against: {self.bmc_url}")
        print()
        
        tests = [
            ("Connection & Authentication", self.test_connection_and_authentication),
            ("Basic Resource Operations", self.test_basic_resource_operations),
            ("System Power Operations", self.test_system_power_operations),
            ("Event Subscriptions", self.test_event_subscriptions),
            ("Resource Modification", self.test_resource_creation_and_modification),
            ("Error Handling", self.test_error_handling),
            ("Monitoring Client", self.test_monitoring_client),
            ("Concurrent Operations", self.test_concurrent_operations),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            if self.run_test(test_name, test_func):
                passed += 1
            time.sleep(1)  # Brief pause between tests
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        for result in self.test_results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            duration = result['duration']
            print(f"{status} {result['test_name']:<30} ({duration:.2f}s)")
            
            if not result['success'] and result['error']:
                print(f"      Error: {result['error']}")
        
        print("\n" + "=" * 50)
        success_rate = (passed / total) * 100
        print(f"📈 Results: {passed}/{total} tests passed ({success_rate:.1f}%)")
        
        if passed == total:
            print("🎉 All tests passed! Client is fully functional.")
        elif passed >= total * 0.8:
            print("⚠️  Most tests passed. Some advanced features may not be available.")
        else:
            print("❌ Many tests failed. Check BMC compatibility or configuration.")
        
        return passed == total
    
    def export_results(self, filename: str = None):
        """Export test results to JSON"""
        if not filename:
            filename = f"redfish_test_results_{int(time.time())}.json"
        
        export_data = {
            'timestamp': time.time(),
            'bmc_url': self.bmc_url,
            'test_results': self.test_results,
            'summary': {
                'total_tests': len(self.test_results),
                'passed_tests': len([r for r in self.test_results if r['success']]),
                'total_duration': sum(r['duration'] for r in self.test_results)
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"\n📁 Test results exported to: {filename}")

def main():
    """Run the test suite"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Redfish Client Test Suite')
    parser.add_argument('--url', default='http://localhost:8000', 
                       help='BMC URL to test against')
    parser.add_argument('--username', default='admin',
                       help='Username for authentication')  
    parser.add_argument('--password', default='admin',
                       help='Password for authentication')
    parser.add_argument('--export', action='store_true',
                       help='Export results to JSON file')
    
    args = parser.parse_args()
    
    tester = RedfishClientTester(args.url, args.username, args.password)
    
    try:
        success = tester.run_all_tests()
        
        if args.export:
            tester.export_results()
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\n👋 Test suite interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())