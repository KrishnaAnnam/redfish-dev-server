#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Example BMC Platform Platform Implementation

This is a standalone platform implementation that can be developed and tested
independently of the main server architecture.
"""

import sys
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from standalone.platform_simulator import StandalonePlatformInterface
except ImportError as e:
    print(f"Error: Cannot import platform simulator: {e}")
    print("Make sure you're running from the correct directory structure")
    sys.exit(1)


class ExamplePlatform(StandalonePlatformInterface):
    """Example BMC Platform platform implementation"""
    
    def __init__(self):
        self.logger = logging.getLogger("example")
        self.oem_namespace = "Example"
        self.initialized = False
        self.mock_data = {}
        
    def get_platform_id(self) -> str:
        return "example"
    
    def get_platform_name(self) -> str:
        return "Example BMC Platform"
    
    def initialize(self) -> bool:
        """Initialize the platform"""
        try:
            self._load_platform_data()
            self._setup_oem_extensions()
            self.initialized = True
            self.logger.info(f"{self.get_platform_name()} platform initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize platform: {e}")
            return False
    
    def get_supported_endpoints(self) -> List[str]:
        """Return supported endpoint patterns"""
        return [
            "/redfish/v1/",
            "/redfish/v1/Systems/",
            "/redfish/v1/Systems/1/",
            "/redfish/v1/Systems/1/Oem/Example/",
            "/redfish/v1/Systems/1/Actions/Oem/Example.*",
            "/redfish/v1/Managers/",
            "/redfish/v1/Managers/1/",
            "/redfish/v1/Chassis/",
            "/redfish/v1/Chassis/1/",
            "/redfish/v1/EventService/"
        ]
    
    def handle_request(self, method: str, path: str, headers: Dict, 
                      body: Optional[str] = None) -> Tuple[int, Dict, Any]:
        """Handle HTTP request"""
        
        if not self.initialized:
            return 503, {}, {"error": "Platform not initialized"}
        
        try:
            # Route request based on path and method
            if method == "GET":
                return self._handle_get(path, headers)
            elif method == "POST":
                return self._handle_post(path, headers, body)
            elif method == "PUT":
                return self._handle_put(path, headers, body)
            elif method == "PATCH":
                return self._handle_patch(path, headers, body)
            elif method == "DELETE":
                return self._handle_delete(path, headers)
            else:
                return 405, {}, {"error": "Method not allowed"}
                
        except Exception as e:
            self.logger.error(f"Error handling {method} {path}: {e}")
            return 500, {}, {"error": str(e)}
    
    def _handle_get(self, path: str, headers: Dict) -> Tuple[int, Dict, Any]:
        """Handle GET requests"""
        
        # Service root
        if path == "/redfish/v1/" or path == "/redfish/v1":
            return self._get_service_root()
        
        # Systems collection
        elif path == "/redfish/v1/Systems/" or path == "/redfish/v1/Systems":
            return self._get_systems_collection()
        
        # System instance
        elif path.startswith("/redfish/v1/Systems/1"):
            return self._handle_system_get(path)
        
        # Managers collection
        elif path == "/redfish/v1/Managers/" or path == "/redfish/v1/Managers":
            return self._get_managers_collection()
        
        # Manager instance
        elif path.startswith("/redfish/v1/Managers/1"):
            return self._handle_manager_get(path)
        
        # Chassis collection
        elif path == "/redfish/v1/Chassis/" or path == "/redfish/v1/Chassis":
            return self._get_chassis_collection()
        
        # Chassis instance
        elif path.startswith("/redfish/v1/Chassis/1"):
            return self._handle_chassis_get(path)
        
        # EventService
        elif path.startswith("/redfish/v1/EventService"):
            return self._handle_event_service_get(path)
        
        else:
            return 404, {}, {"error": "Resource not found"}
    
    def _handle_post(self, path: str, headers: Dict, body: Optional[str]) -> Tuple[int, Dict, Any]:
        """Handle POST requests (actions, creation)"""
        
        # Parse body if present
        data = {}
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return 400, {}, {"error": "Invalid JSON"}
        
        # OEM Actions
        if f"/Actions/Oem/Example." in path:
            return self._handle_oem_action(path, data)
        
        # Standard actions
        elif "/Actions/" in path:
            return self._handle_standard_action(path, data)
        
        else:
            return 404, {}, {"error": "Action not found"}
    
    def _handle_put(self, path: str, headers: Dict, body: Optional[str]) -> Tuple[int, Dict, Any]:
        """Handle PUT requests (full resource replacement)"""
        return 405, {}, {"error": "PUT not supported"}
    
    def _handle_patch(self, path: str, headers: Dict, body: Optional[str]) -> Tuple[int, Dict, Any]:
        """Handle PATCH requests (partial updates)"""
        return 405, {}, {"error": "PATCH not supported"}
    
    def _handle_delete(self, path: str, headers: Dict) -> Tuple[int, Dict, Any]:
        """Handle DELETE requests"""
        return 405, {}, {"error": "DELETE not supported"}
    
    def _get_service_root(self) -> Tuple[int, Dict, Any]:
        """Get service root"""
        return 200, {}, {
            "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
            "@odata.id": "/redfish/v1/",
            "Id": "RootService", 
            "Name": "Example BMC Platform Root Service",
            "RedfishVersion": "1.8.0",
            "UUID": "12345678-1234-1234-1234-123456789012",
            "Systems": {"@odata.id": "/redfish/v1/Systems/"},
            "Managers": {"@odata.id": "/redfish/v1/Managers/"},
            "Chassis": {"@odata.id": "/redfish/v1/Chassis/"},
            "EventService": {"@odata.id": "/redfish/v1/EventService/"},
            "Oem": {
                "Example": {
                    "PlatformVersion": "1.0.0",
                    "PlatformFeatures": ["OEM Actions", "Custom Extensions"]
                }
            }
        }
    
    def _get_systems_collection(self) -> Tuple[int, Dict, Any]:
        """Get systems collection"""
        return 200, {}, {
            "@odata.type": "#ComputerSystemCollection.ComputerSystemCollection",
            "@odata.id": "/redfish/v1/Systems/",
            "Name": "Computer System Collection",
            "Members": [
                {"@odata.id": "/redfish/v1/Systems/1/"}
            ],
            "Members@odata.count": 1
        }
    
    def _handle_system_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle system-related GET requests"""
        
        if path == "/redfish/v1/Systems/1/" or path == "/redfish/v1/Systems/1":
            return self._get_system_instance()
        elif f"/redfish/v1/Systems/1/Oem/Example/" in path:
            return self._get_system_oem(path)
        else:
            return 404, {}, {"error": "System resource not found"}
    
    def _get_system_instance(self) -> Tuple[int, Dict, Any]:
        """Get system instance"""
        return 200, {}, {
            "@odata.type": "#ComputerSystem.v1_8_0.ComputerSystem",
            "@odata.id": "/redfish/v1/Systems/1/",
            "Id": "1",
            "Name": "Example BMC Platform System",
            "SystemType": "Physical",
            "Manufacturer": "Example BMC Platform Inc.",
            "Model": "Example BMC Platform Server",
            "SerialNumber": "SN123456789",
            "Status": {
                "State": "Enabled",
                "Health": "OK"
            },
            "PowerState": "On",
            "ProcessorSummary": {
                "Count": 2,
                "Model": "Example BMC Platform CPU"
            },
            "MemorySummary": {
                "TotalSystemMemoryGiB": 64
            },
            "Actions": {
                "Oem": {
                    "Example.ExportConfiguration": {
                        "target": "/redfish/v1/Systems/1/Actions/Oem/Example.ExportConfiguration"
                    },
                    "Example.ImportConfiguration": {
                        "target": "/redfish/v1/Systems/1/Actions/Oem/Example.ImportConfiguration"
                    }
                }
            },
            "Oem": {
                "Example": {
                    "@odata.id": "/redfish/v1/Systems/1/Oem/Example/"
                }
            }
        }
    
    def _get_system_oem(self, path: str) -> Tuple[int, Dict, Any]:
        """Get system OEM data"""
        return 200, {}, {
            "@odata.type": "#ExampleSystem.v1_0_0.ExampleSystem",
            "@odata.id": path,
            "Id": "ExampleSystemExtensions",
            "Name": "Example BMC Platform System Extensions",
            "PlatformSpecificSettings": {
                "CustomSetting1": "Value1",
                "CustomSetting2": "Value2"
            },
            "FirmwareVersion": "1.2.3-example",
            "Actions": {
                "#Example.ExportConfiguration": {
                    "target": f"{path}/Actions/Example.ExportConfiguration"
                }
            }
        }
    
    def _get_managers_collection(self) -> Tuple[int, Dict, Any]:
        """Get managers collection"""  
        return 200, {}, {
            "@odata.type": "#ManagerCollection.ManagerCollection",
            "@odata.id": "/redfish/v1/Managers/",
            "Name": "Manager Collection",
            "Members": [
                {"@odata.id": "/redfish/v1/Managers/1/"}
            ],
            "Members@odata.count": 1
        }
    
    def _handle_manager_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle manager-related GET requests"""
        
        if path == "/redfish/v1/Managers/1/" or path == "/redfish/v1/Managers/1":
            return 200, {}, {
                "@odata.type": "#Manager.v1_7_0.Manager",
                "@odata.id": "/redfish/v1/Managers/1/",
                "Id": "1",
                "Name": "Example BMC Platform BMC",
                "ManagerType": "BMC",
                "Manufacturer": "Example BMC Platform Inc.",
                "Model": "Example BMC Platform BMC",
                "FirmwareVersion": "2.1.0-example",
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                }
            }
        else:
            return 404, {}, {"error": "Manager resource not found"}
    
    def _get_chassis_collection(self) -> Tuple[int, Dict, Any]:
        """Get chassis collection"""
        return 200, {}, {
            "@odata.type": "#ChassisCollection.ChassisCollection", 
            "@odata.id": "/redfish/v1/Chassis/",
            "Name": "Chassis Collection",
            "Members": [
                {"@odata.id": "/redfish/v1/Chassis/1/"}
            ],
            "Members@odata.count": 1
        }
    
    def _handle_chassis_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle chassis-related GET requests"""
        
        if path == "/redfish/v1/Chassis/1/" or path == "/redfish/v1/Chassis/1":
            return 200, {}, {
                "@odata.type": "#Chassis.v1_10_0.Chassis",
                "@odata.id": "/redfish/v1/Chassis/1/",
                "Id": "1",
                "Name": "Example BMC Platform Chassis",
                "ChassisType": "RackMount",
                "Manufacturer": "Example BMC Platform Inc.",
                "Model": "Example BMC Platform Chassis",
                "SerialNumber": "CH123456789",
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                }
            }
        else:
            return 404, {}, {"error": "Chassis resource not found"}
    
    def _handle_event_service_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle EventService GET requests"""
        
        if path == "/redfish/v1/EventService/" or path == "/redfish/v1/EventService":
            return 200, {}, {
                "@odata.type": "#EventService.v1_5_0.EventService",
                "@odata.id": "/redfish/v1/EventService/",
                "Id": "EventService",
                "Name": "Event Service",
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                },
                "ServiceEnabled": True,
                "DeliveryRetryAttempts": 3,
                "EventTypesForSubscription": ["Alert", "ResourceAdded", "ResourceRemoved"],
                "Subscriptions": {
                    "@odata.id": "/redfish/v1/EventService/Subscriptions/"
                }
            }
        else:
            return 404, {}, {"error": "EventService resource not found"}
    
    def _handle_oem_action(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Handle OEM actions"""
        
        if "ExportConfiguration" in path:
            return self._export_configuration(data)
        elif "ImportConfiguration" in path:
            return self._import_configuration(data)
        else:
            return 400, {}, {"error": "Unknown OEM action"}
    
    def _handle_standard_action(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Handle standard Redfish actions"""
        return 501, {}, {"error": "Standard action not implemented"}
    
    def _export_configuration(self, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Export platform configuration"""
        return 200, {}, {
            "Message": "Configuration exported successfully",
            "ConfigurationData": {
                "PlatformSettings": {
                    "PlatformId": self.get_platform_id(),
                    "CustomSetting1": "Value1",
                    "CustomSetting2": "Value2"
                },
                "NetworkSettings": {
                    "ManagementIP": "192.168.1.100",
                    "DHCP": True
                }
            },
            "ExportTimestamp": "2025-11-05T10:00:00Z"
        }
    
    def _import_configuration(self, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Import platform configuration"""
        config_data = data.get("ConfigurationData", {})
        
        return 202, {}, {
            "Message": "Configuration import accepted",
            "TaskId": "task-import-12345",
            "Status": "InProgress",
            "EstimatedCompletion": "PT2M"
        }
    
    def _load_platform_data(self):
        """Load platform-specific data"""
        # Load any platform-specific mock data or configuration
        pass
    
    def _setup_oem_extensions(self):
        """Setup OEM extensions and custom behavior"""
        # Initialize OEM-specific features
        pass


# Example usage and testing
if __name__ == "__main__":
    import sys
    import argparse
    from standalone.platform_simulator import StandalonePlatformServer, TestFramework
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Example BMC Platform Platform Simulator")
    parser.add_argument("--test", action="store_true", help="Run platform tests")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    
    args = parser.parse_args()
    
    # Create platform instance
    platform = ExamplePlatform()
    
    if args.test:
        # Run tests
        test_framework = TestFramework(platform)
        results = test_framework.run_tests()
        
        print(f"\n=== Test Results for {platform.get_platform_name()} ===")
        print(f"Platform: {results['platform']}")
        print(f"Total tests: {results['summary']['total']}")
        print(f"Passed: {results['summary']['passed']}")
        print(f"Failed: {results['summary']['failed']}")
        print(f"Success rate: {results['summary']['success_rate']:.1%}")
        
        for test in results['tests']:
            status_icon = "✅" if test['status'] == "PASSED" else "❌"
            print(f"  {status_icon} {test['name']}: {test['status']}")
            if test['status'] != "PASSED":
                print(f"    {test['message']}")
        
        # Exit with error code if tests failed
        sys.exit(0 if results['summary']['failed'] == 0 else 1)
    
    else:
        # Start server
        server = StandalonePlatformServer(platform, args.host, args.port)
        server.start()
