#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Standalone Platform Simulator Framework

This module provides a lightweight, independent BMC simulator framework that allows
platform developers to build, test, and run platform-specific implementations
without dependencies on the main server architecture.

Key Features:
- Independent platform development environment
- Isolated testing framework
- Minimal dependencies
- Platform-specific handler and service testing
- Mock data generation and validation
"""

import json
import http.server
import socketserver
import urllib.parse
import logging
import os
import sys
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime
from abc import ABC, abstractmethod


class StandalonePlatformInterface(ABC):
    """Abstract interface for standalone platform implementations"""
    
    @abstractmethod
    def get_platform_id(self) -> str:
        """Return unique platform identifier"""
        pass
    
    @abstractmethod
    def get_platform_name(self) -> str:
        """Return human-readable platform name"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the platform"""
        pass
    
    @abstractmethod
    def get_supported_endpoints(self) -> List[str]:
        """Return list of supported endpoint patterns"""
        pass
    
    @abstractmethod
    def handle_request(self, method: str, path: str, headers: Dict, 
                      body: Optional[str] = None) -> Tuple[int, Dict, Any]:
        """Handle HTTP request and return (status_code, headers, response_data)"""
        pass


class MockDataManager:
    """Manages mock data for standalone platform testing"""
    
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or "mock_data"
        self.mock_data = {}
        self.load_mock_data()
    
    def load_mock_data(self):
        """Load mock data from directory or create default data"""
        if os.path.exists(self.data_dir):
            for filename in os.listdir(self.data_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.data_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            key = filename[:-5]  # Remove .json extension
                            self.mock_data[key] = json.load(f)
                    except Exception as e:
                        logging.warning(f"Failed to load mock data from {filepath}: {e}")
        else:
            self._create_default_mock_data()
    
    def _create_default_mock_data(self):
        """Create default mock data structure"""
        self.mock_data = {
            "service_root": {
                "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
                "@odata.id": "/redfish/v1/",
                "Id": "RootService",
                "Name": "Root Service",
                "RedfishVersion": "1.8.0",
                "UUID": "12345678-1234-1234-1234-123456789012",
                "Systems": {"@odata.id": "/redfish/v1/Systems/"},
                "Managers": {"@odata.id": "/redfish/v1/Managers/"},
                "Chassis": {"@odata.id": "/redfish/v1/Chassis/"},
                "EventService": {"@odata.id": "/redfish/v1/EventService/"}
            },
            "systems": {
                "@odata.type": "#ComputerSystemCollection.ComputerSystemCollection",
                "@odata.id": "/redfish/v1/Systems/",
                "Name": "Computer System Collection",
                "Members": [
                    {"@odata.id": "/redfish/v1/Systems/1/"}
                ],
                "Members@odata.count": 1
            },
            "system_1": {
                "@odata.type": "#ComputerSystem.v1_8_0.ComputerSystem",
                "@odata.id": "/redfish/v1/Systems/1/",
                "Id": "1",
                "Name": "System",
                "SystemType": "Physical",
                "Manufacturer": "Platform Vendor",
                "Model": "Platform Model",
                "SerialNumber": "123456789",
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                },
                "PowerState": "On",
                "ProcessorSummary": {
                    "Count": 2,
                    "Model": "Platform CPU"
                },
                "MemorySummary": {
                    "TotalSystemMemoryGiB": 32
                }
            }
        }
    
    def get_data(self, key: str) -> Optional[Dict]:
        """Get mock data by key"""
        return self.mock_data.get(key)
    
    def set_data(self, key: str, data: Dict):
        """Set mock data for key"""
        self.mock_data[key] = data
    
    def save_mock_data(self):
        """Save mock data to files"""
        os.makedirs(self.data_dir, exist_ok=True)
        for key, data in self.mock_data.items():
            filepath = os.path.join(self.data_dir, f"{key}.json")
            try:
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logging.warning(f"Failed to save mock data to {filepath}: {e}")


class TestFramework:
    """Testing framework for standalone platform development"""
    
    def __init__(self, platform: StandalonePlatformInterface):
        self.platform = platform
        self.results = []
        self.logger = logging.getLogger(f"TestFramework-{platform.get_platform_id()}")
    
    def add_test(self, test_name: str, test_func: Callable):
        """Add a test case"""
        setattr(self, f"test_{test_name}", test_func)
    
    def run_tests(self) -> Dict[str, Any]:
        """Run all test methods and return results"""
        results = {
            "platform": self.platform.get_platform_id(),
            "timestamp": datetime.utcnow().isoformat(),
            "tests": [],
            "summary": {}
        }
        
        # Find all test methods (callable methods that start with test_)
        test_methods = [method for method in dir(self) 
                       if method.startswith('test_') and callable(getattr(self, method))]
        
        passed = 0
        failed = 0
        
        for method_name in test_methods:
            try:
                self.logger.info(f"Running test: {method_name}")
                test_method = getattr(self, method_name)
                test_method()
                
                results["tests"].append({
                    "name": method_name,
                    "status": "PASSED",
                    "message": "Test completed successfully"
                })
                passed += 1
                
            except AssertionError as e:
                results["tests"].append({
                    "name": method_name,
                    "status": "FAILED",
                    "message": str(e)
                })
                failed += 1
                self.logger.error(f"Test {method_name} failed: {e}")
                
            except Exception as e:
                results["tests"].append({
                    "name": method_name,
                    "status": "ERROR",
                    "message": str(e)
                })
                failed += 1
                self.logger.error(f"Test {method_name} error: {e}")
        
        results["summary"] = {
            "total": len(test_methods),
            "passed": passed,
            "failed": failed,
            "success_rate": passed / len(test_methods) if test_methods else 0
        }
        
        return results
    
    def assert_response(self, response: Tuple[int, Dict, Any], 
                       expected_status: int, expected_fields: List[str] = None):
        """Assert response meets expectations"""
        status_code, headers, data = response
        
        assert status_code == expected_status, \
            f"Expected status {expected_status}, got {status_code}"
        
        if expected_fields:
            for field in expected_fields:
                assert field in data, f"Expected field '{field}' not found in response"
    
    def test_initialization(self):
        """Test platform initialization"""
        result = self.platform.initialize()
        assert result is True, "Platform initialization failed"
    
    def test_platform_info(self):
        """Test platform information"""
        platform_id = self.platform.get_platform_id()
        platform_name = self.platform.get_platform_name()
        
        assert isinstance(platform_id, str) and len(platform_id) > 0, \
            "Platform ID must be non-empty string"
        assert isinstance(platform_name, str) and len(platform_name) > 0, \
            "Platform name must be non-empty string"
    
    def test_supported_endpoints(self):
        """Test supported endpoints"""
        endpoints = self.platform.get_supported_endpoints()
        assert isinstance(endpoints, list), "Supported endpoints must be a list"
        assert len(endpoints) > 0, "Platform must support at least one endpoint"


class StandalonePlatformServer:
    """Lightweight HTTP server for standalone platform testing"""
    
    def __init__(self, platform: StandalonePlatformInterface, 
                 host: str = "127.0.0.1", port: int = 8000):
        self.platform = platform
        self.host = host
        self.port = port
        self.logger = logging.getLogger(f"StandaloneServer-{platform.get_platform_id()}")
        
        # Initialize platform
        if not self.platform.initialize():
            raise RuntimeError(f"Failed to initialize platform {platform.get_platform_id()}")
    
    def create_handler_class(self):
        """Create HTTP handler class with platform reference"""
        platform = self.platform
        logger = self.logger
        
        class PlatformRequestHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                logger.info(format % args)
            
            def do_GET(self):
                self._handle_request("GET")
            
            def do_POST(self):
                self._handle_request("POST")
            
            def do_PUT(self):
                self._handle_request("PUT")
            
            def do_PATCH(self):
                self._handle_request("PATCH")
            
            def do_DELETE(self):
                self._handle_request("DELETE")
            
            def _handle_request(self, method):
                try:
                    # Parse request
                    parsed_path = urllib.parse.urlparse(self.path)
                    path = parsed_path.path
                    
                    # Get request body for POST/PUT/PATCH
                    body = None
                    if method in ['POST', 'PUT', 'PATCH']:
                        content_length = int(self.headers.get('Content-Length', 0))
                        if content_length > 0:
                            body = self.rfile.read(content_length).decode('utf-8')
                    
                    # Call platform handler
                    status_code, response_headers, response_data = platform.handle_request(
                        method, path, dict(self.headers), body
                    )
                    
                    # Send response
                    self.send_response(status_code)
                    
                    # Set default headers
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
                    
                    # Set custom headers
                    for key, value in response_headers.items():
                        self.send_header(key, value)
                    
                    self.end_headers()
                    
                    # Send response body
                    if response_data is not None:
                        if isinstance(response_data, dict) or isinstance(response_data, list):
                            response_json = json.dumps(response_data, indent=2)
                        else:
                            response_json = str(response_data)
                        self.wfile.write(response_json.encode('utf-8'))
                
                except Exception as e:
                    logger.error(f"Error handling {method} {self.path}: {e}")
                    self.send_error(500, f"Internal server error: {e}")
        
        return PlatformRequestHandler
    
    def start(self):
        """Start the server"""
        handler_class = self.create_handler_class()
        
        try:
            with socketserver.TCPServer((self.host, self.port), handler_class) as httpd:
                self.logger.info(f"Starting {self.platform.get_platform_name()} server")
                self.logger.info(f"Platform ID: {self.platform.get_platform_id()}")
                self.logger.info(f"Server address: http://{self.host}:{self.port}")
                self.logger.info(f"Supported endpoints: {self.platform.get_supported_endpoints()}")
                self.logger.info("Press Ctrl+C to stop the server")
                
                httpd.serve_forever()
                
        except KeyboardInterrupt:
            self.logger.info("Server stopped by user")
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            raise


class PlatformDevelopmentKit:
    """Development kit for creating standalone platform implementations"""
    
    def __init__(self, platform_id: str, platform_name: str):
        self.platform_id = platform_id
        self.platform_name = platform_name
        self.mock_data_manager = MockDataManager(f"platforms/{platform_id}/mock_data")
        self.logger = logging.getLogger(f"DevKit-{platform_id}")
    
    def create_platform_template(self) -> str:
        """Create a template platform implementation"""
        template = f'''#!/usr/bin/env python3
"""
{self.platform_name} Platform Implementation

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
    print(f"Error: Cannot import platform simulator: {{e}}")
    print("Make sure you're running from the correct directory structure")
    sys.exit(1)


class {self.platform_id.title()}Platform(StandalonePlatformInterface):
    """{self.platform_name} platform implementation"""
    
    def __init__(self):
        self.logger = logging.getLogger("{self.platform_id}")
        self.oem_namespace = "{self.platform_id.title()}"
        self.initialized = False
        self.mock_data = {{}}
        
    def get_platform_id(self) -> str:
        return "{self.platform_id}"
    
    def get_platform_name(self) -> str:
        return "{self.platform_name}"
    
    def initialize(self) -> bool:
        """Initialize the platform"""
        try:
            self._load_platform_data()
            self._setup_oem_extensions()
            self.initialized = True
            self.logger.info(f"{{self.get_platform_name()}} platform initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize platform: {{e}}")
            return False
    
    def get_supported_endpoints(self) -> List[str]:
        """Return supported endpoint patterns"""
        return [
            "/redfish/v1/",
            "/redfish/v1/Systems/",
            "/redfish/v1/Systems/1/",
            "/redfish/v1/Systems/1/Oem/{self.platform_id.title()}/",
            "/redfish/v1/Systems/1/Actions/Oem/{self.platform_id.title()}.*",
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
            return 503, {{}}, {{"error": "Platform not initialized"}}
        
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
                return 405, {{}}, {{"error": "Method not allowed"}}
                
        except Exception as e:
            self.logger.error(f"Error handling {{method}} {{path}}: {{e}}")
            return 500, {{}}, {{"error": str(e)}}
    
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
            return 404, {{}}, {{"error": "Resource not found"}}
    
    def _handle_post(self, path: str, headers: Dict, body: Optional[str]) -> Tuple[int, Dict, Any]:
        """Handle POST requests (actions, creation)"""
        
        # Parse body if present
        data = {{}}
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return 400, {{}}, {{"error": "Invalid JSON"}}
        
        # OEM Actions
        if f"/Actions/Oem/{self.platform_id.title()}." in path:
            return self._handle_oem_action(path, data)
        
        # Standard actions
        elif "/Actions/" in path:
            return self._handle_standard_action(path, data)
        
        else:
            return 404, {{}}, {{"error": "Action not found"}}
    
    def _handle_put(self, path: str, headers: Dict, body: Optional[str]) -> Tuple[int, Dict, Any]:
        """Handle PUT requests (full resource replacement)"""
        return 405, {{}}, {{"error": "PUT not supported"}}
    
    def _handle_patch(self, path: str, headers: Dict, body: Optional[str]) -> Tuple[int, Dict, Any]:
        """Handle PATCH requests (partial updates)"""
        return 405, {{}}, {{"error": "PATCH not supported"}}
    
    def _handle_delete(self, path: str, headers: Dict) -> Tuple[int, Dict, Any]:
        """Handle DELETE requests"""
        return 405, {{}}, {{"error": "DELETE not supported"}}
    
    def _get_service_root(self) -> Tuple[int, Dict, Any]:
        """Get service root"""
        return 200, {{}}, {{
            "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
            "@odata.id": "/redfish/v1/",
            "Id": "RootService", 
            "Name": "{self.platform_name} Root Service",
            "RedfishVersion": "1.8.0",
            "UUID": "12345678-1234-1234-1234-123456789012",
            "Systems": {{"@odata.id": "/redfish/v1/Systems/"}},
            "Managers": {{"@odata.id": "/redfish/v1/Managers/"}},
            "Chassis": {{"@odata.id": "/redfish/v1/Chassis/"}},
            "EventService": {{"@odata.id": "/redfish/v1/EventService/"}},
            "Oem": {{
                "{self.platform_id.title()}": {{
                    "PlatformVersion": "1.0.0",
                    "PlatformFeatures": ["OEM Actions", "Custom Extensions"]
                }}
            }}
        }}
    
    def _get_systems_collection(self) -> Tuple[int, Dict, Any]:
        """Get systems collection"""
        return 200, {{}}, {{
            "@odata.type": "#ComputerSystemCollection.ComputerSystemCollection",
            "@odata.id": "/redfish/v1/Systems/",
            "Name": "Computer System Collection",
            "Members": [
                {{"@odata.id": "/redfish/v1/Systems/1/"}}
            ],
            "Members@odata.count": 1
        }}
    
    def _handle_system_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle system-related GET requests"""
        
        if path == "/redfish/v1/Systems/1/" or path == "/redfish/v1/Systems/1":
            return self._get_system_instance()
        elif f"/redfish/v1/Systems/1/Oem/{self.platform_id.title()}/" in path:
            return self._get_system_oem(path)
        else:
            return 404, {{}}, {{"error": "System resource not found"}}
    
    def _get_system_instance(self) -> Tuple[int, Dict, Any]:
        """Get system instance"""
        return 200, {{}}, {{
            "@odata.type": "#ComputerSystem.v1_8_0.ComputerSystem",
            "@odata.id": "/redfish/v1/Systems/1/",
            "Id": "1",
            "Name": "{self.platform_name} System",
            "SystemType": "Physical",
            "Manufacturer": "{self.platform_name} Inc.",
            "Model": "{self.platform_name} Server",
            "SerialNumber": "SN123456789",
            "Status": {{
                "State": "Enabled",
                "Health": "OK"
            }},
            "PowerState": "On",
            "ProcessorSummary": {{
                "Count": 2,
                "Model": "{self.platform_name} CPU"
            }},
            "MemorySummary": {{
                "TotalSystemMemoryGiB": 64
            }},
            "Actions": {{
                "Oem": {{
                    "{self.platform_id.title()}.ExportConfiguration": {{
                        "target": "/redfish/v1/Systems/1/Actions/Oem/{self.platform_id.title()}.ExportConfiguration"
                    }},
                    "{self.platform_id.title()}.ImportConfiguration": {{
                        "target": "/redfish/v1/Systems/1/Actions/Oem/{self.platform_id.title()}.ImportConfiguration"
                    }}
                }}
            }},
            "Oem": {{
                "{self.platform_id.title()}": {{
                    "@odata.id": "/redfish/v1/Systems/1/Oem/{self.platform_id.title()}/"
                }}
            }}
        }}
    
    def _get_system_oem(self, path: str) -> Tuple[int, Dict, Any]:
        """Get system OEM data"""
        return 200, {{}}, {{
            "@odata.type": "#{self.platform_id.title()}System.v1_0_0.{self.platform_id.title()}System",
            "@odata.id": path,
            "Id": "{self.platform_id.title()}SystemExtensions",
            "Name": "{self.platform_name} System Extensions",
            "PlatformSpecificSettings": {{
                "CustomSetting1": "Value1",
                "CustomSetting2": "Value2"
            }},
            "FirmwareVersion": "1.2.3-{self.platform_id}",
            "Actions": {{
                "#{self.platform_id.title()}.ExportConfiguration": {{
                    "target": f"{{path}}/Actions/{self.platform_id.title()}.ExportConfiguration"
                }}
            }}
        }}
    
    def _get_managers_collection(self) -> Tuple[int, Dict, Any]:
        """Get managers collection"""  
        return 200, {{}}, {{
            "@odata.type": "#ManagerCollection.ManagerCollection",
            "@odata.id": "/redfish/v1/Managers/",
            "Name": "Manager Collection",
            "Members": [
                {{"@odata.id": "/redfish/v1/Managers/1/"}}
            ],
            "Members@odata.count": 1
        }}
    
    def _handle_manager_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle manager-related GET requests"""
        
        if path == "/redfish/v1/Managers/1/" or path == "/redfish/v1/Managers/1":
            return 200, {{}}, {{
                "@odata.type": "#Manager.v1_7_0.Manager",
                "@odata.id": "/redfish/v1/Managers/1/",
                "Id": "1",
                "Name": "{self.platform_name} BMC",
                "ManagerType": "BMC",
                "Manufacturer": "{self.platform_name} Inc.",
                "Model": "{self.platform_name} BMC",
                "FirmwareVersion": "2.1.0-{self.platform_id}",
                "Status": {{
                    "State": "Enabled",
                    "Health": "OK"
                }}
            }}
        else:
            return 404, {{}}, {{"error": "Manager resource not found"}}
    
    def _get_chassis_collection(self) -> Tuple[int, Dict, Any]:
        """Get chassis collection"""
        return 200, {{}}, {{
            "@odata.type": "#ChassisCollection.ChassisCollection", 
            "@odata.id": "/redfish/v1/Chassis/",
            "Name": "Chassis Collection",
            "Members": [
                {{"@odata.id": "/redfish/v1/Chassis/1/"}}
            ],
            "Members@odata.count": 1
        }}
    
    def _handle_chassis_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle chassis-related GET requests"""
        
        if path == "/redfish/v1/Chassis/1/" or path == "/redfish/v1/Chassis/1":
            return 200, {{}}, {{
                "@odata.type": "#Chassis.v1_10_0.Chassis",
                "@odata.id": "/redfish/v1/Chassis/1/",
                "Id": "1",
                "Name": "{self.platform_name} Chassis",
                "ChassisType": "RackMount",
                "Manufacturer": "{self.platform_name} Inc.",
                "Model": "{self.platform_name} Chassis",
                "SerialNumber": "CH123456789",
                "Status": {{
                    "State": "Enabled",
                    "Health": "OK"
                }}
            }}
        else:
            return 404, {{}}, {{"error": "Chassis resource not found"}}
    
    def _handle_event_service_get(self, path: str) -> Tuple[int, Dict, Any]:
        """Handle EventService GET requests"""
        
        if path == "/redfish/v1/EventService/" or path == "/redfish/v1/EventService":
            return 200, {{}}, {{
                "@odata.type": "#EventService.v1_5_0.EventService",
                "@odata.id": "/redfish/v1/EventService/",
                "Id": "EventService",
                "Name": "Event Service",
                "Status": {{
                    "State": "Enabled",
                    "Health": "OK"
                }},
                "ServiceEnabled": True,
                "DeliveryRetryAttempts": 3,
                "EventTypesForSubscription": ["Alert", "ResourceAdded", "ResourceRemoved"],
                "Subscriptions": {{
                    "@odata.id": "/redfish/v1/EventService/Subscriptions/"
                }}
            }}
        else:
            return 404, {{}}, {{"error": "EventService resource not found"}}
    
    def _handle_oem_action(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Handle OEM actions"""
        
        if "ExportConfiguration" in path:
            return self._export_configuration(data)
        elif "ImportConfiguration" in path:
            return self._import_configuration(data)
        else:
            return 400, {{}}, {{"error": "Unknown OEM action"}}
    
    def _handle_standard_action(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Handle standard Redfish actions"""
        return 501, {{}}, {{"error": "Standard action not implemented"}}
    
    def _export_configuration(self, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Export platform configuration"""
        return 200, {{}}, {{
            "Message": "Configuration exported successfully",
            "ConfigurationData": {{
                "PlatformSettings": {{
                    "PlatformId": self.get_platform_id(),
                    "CustomSetting1": "Value1",
                    "CustomSetting2": "Value2"
                }},
                "NetworkSettings": {{
                    "ManagementIP": "192.168.1.100",
                    "DHCP": True
                }}
            }},
            "ExportTimestamp": "2025-11-05T10:00:00Z"
        }}
    
    def _import_configuration(self, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Import platform configuration"""
        config_data = data.get("ConfigurationData", {{}})
        
        return 202, {{}}, {{
            "Message": "Configuration import accepted",
            "TaskId": "task-import-12345",
            "Status": "InProgress",
            "EstimatedCompletion": "PT2M"
        }}
    
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
    parser = argparse.ArgumentParser(description="{self.platform_name} Platform Simulator")
    parser.add_argument("--test", action="store_true", help="Run platform tests")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    
    args = parser.parse_args()
    
    # Create platform instance
    platform = {self.platform_id.title()}Platform()
    
    if args.test:
        # Run tests
        test_framework = TestFramework(platform)
        results = test_framework.run_tests()
        
        print(f"\\n=== Test Results for {{platform.get_platform_name()}} ===")
        print(f"Platform: {{results['platform']}}")
        print(f"Total tests: {{results['summary']['total']}}")
        print(f"Passed: {{results['summary']['passed']}}")
        print(f"Failed: {{results['summary']['failed']}}")
        print(f"Success rate: {{results['summary']['success_rate']:.1%}}")
        
        for test in results['tests']:
            status_icon = "✅" if test['status'] == "PASSED" else "❌"
            print(f"  {{status_icon}} {{test['name']}}: {{test['status']}}")
            if test['status'] != "PASSED":
                print(f"    {{test['message']}}")
        
        # Exit with error code if tests failed
        sys.exit(0 if results['summary']['failed'] == 0 else 1)
    
    else:
        # Start server
        server = StandalonePlatformServer(platform, args.host, args.port)
        server.start()
'''
        
        return template
    
    def generate_platform_structure(self, output_dir: str):
        """Generate complete platform development structure"""
        platform_dir = os.path.join(output_dir, "platforms", self.platform_id)
        os.makedirs(platform_dir, exist_ok=True)
        
        # Create platform implementation
        platform_file = os.path.join(platform_dir, "platform.py")
        with open(platform_file, 'w') as f:
            f.write(self.create_platform_template())
        
        # Create mock data directory
        mock_data_dir = os.path.join(platform_dir, "mock_data")
        os.makedirs(mock_data_dir, exist_ok=True)
        
        # Create README
        readme_file = os.path.join(platform_dir, "README.md")
        with open(readme_file, 'w') as f:
            f.write(f"""# {self.platform_name} Platform Implementation

## Overview

This is a standalone platform implementation for {self.platform_name} that can be developed and tested independently.

## Features

- Independent development environment
- Built-in testing framework
- Mock data management
- OEM action implementations
- Platform-specific extensions

## Usage

### Run Platform Server
```bash
python platform.py --host 127.0.0.1 --port 8000
```

### Run Platform Tests
```bash
python platform.py --test
```

### Test Endpoints

```bash
# Service root
curl http://localhost:8000/redfish/v1/

# Systems
curl http://localhost:8000/redfish/v1/Systems/

# System instance
curl http://localhost:8000/redfish/v1/Systems/1/

# OEM extensions
curl http://localhost:8000/redfish/v1/Systems/1/Oem/{self.platform_id.title()}/

# OEM actions
curl -X POST -H "Content-Type: application/json" \\
     -d '{{}}' \\
     http://localhost:8000/redfish/v1/Systems/1/Actions/Oem/{self.platform_id.title()}.ExportConfiguration
```

## Development

### Adding Custom Endpoints

1. Add endpoint pattern to `get_supported_endpoints()`
2. Handle the endpoint in appropriate `_handle_*` method
3. Test with the built-in test framework

### Adding OEM Actions

1. Add action to system OEM data
2. Implement handler in `_handle_oem_action()`
3. Add test cases for the action

### Mock Data

Mock data is stored in the `mock_data/` directory as JSON files. The platform automatically loads this data on initialization.

## Testing

The platform includes a built-in testing framework. Add custom tests by extending the `TestFramework` class or adding test methods to the platform.

## Integration

Once development is complete, this platform can be integrated into the main server architecture by:

1. Converting to the main platform interface
2. Adding to the plugin registry
3. Including in the enhanced server
""")
        
        # Create example test file
        test_file = os.path.join(platform_dir, "test_platform.py")
        with open(test_file, 'w') as f:
            f.write(f"""#!/usr/bin/env python3
\"\"\"
Custom tests for {self.platform_name} platform
\"\"\"

import sys
import os
import json
import logging
from platform import {self.platform_id.title()}Platform
from src.standalone.platform_simulator import TestFramework

class {self.platform_id.title()}TestFramework(TestFramework):
    \"\"\"Extended test framework for {self.platform_name}\"\"\"
    
    def test_service_root(self):
        \"\"\"Test service root endpoint\"\"\"
        response = self.platform.handle_request("GET", "/redfish/v1/", {{}})
        self.assert_response(response, 200, ["@odata.type", "@odata.id", "Name"])
        
        # Check platform-specific fields
        _, _, data = response
        assert "Oem" in data
        assert "{self.platform_id.title()}" in data["Oem"]
    
    def test_system_instance(self):
        \"\"\"Test system instance\"\"\"
        response = self.platform.handle_request("GET", "/redfish/v1/Systems/1/", {{}})
        self.assert_response(response, 200, ["@odata.type", "Id", "Name", "SystemType"])
        
        # Check OEM section
        _, _, data = response
        assert "Oem" in data
        assert "{self.platform_id.title()}" in data["Oem"]
    
    def test_oem_extensions(self):
        \"\"\"Test OEM extensions\"\"\"
        response = self.platform.handle_request("GET", 
                                               "/redfish/v1/Systems/1/Oem/{self.platform_id.title()}/", {{}})
        self.assert_response(response, 200, ["@odata.type", "Id", "Name"])
    
    def test_export_configuration_action(self):
        \"\"\"Test export configuration OEM action\"\"\"
        response = self.platform.handle_request("POST",
                                               "/redfish/v1/Systems/1/Actions/Oem/{self.platform_id.title()}.ExportConfiguration",
                                               {{}}, "{{}}")
        self.assert_response(response, 200, ["Message", "ConfigurationData"])
    
    def test_import_configuration_action(self):
        \"\"\"Test import configuration OEM action\"\"\"
        import_data = {{
            "ConfigurationData": {{
                "TestSetting": "TestValue"
            }}
        }}
        
        response = self.platform.handle_request("POST",
                                               "/redfish/v1/Systems/1/Actions/Oem/{self.platform_id.title()}.ImportConfiguration", 
                                               {{}}, json.dumps(import_data))
        self.assert_response(response, 202, ["Message", "TaskId"])
    
    def test_unsupported_endpoints(self):
        \"\"\"Test that unsupported endpoints return 404\"\"\"
        response = self.platform.handle_request("GET", "/redfish/v1/InvalidEndpoint/", {{}})
        status_code, _, _ = response
        assert status_code == 404
    
    def test_unsupported_methods(self):
        \"\"\"Test that unsupported methods return 405\"\"\"
        response = self.platform.handle_request("DELETE", "/redfish/v1/Systems/1/", {{}})
        status_code, _, _ = response
        assert status_code == 405

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create platform and test framework
    platform = {self.platform_id.title()}Platform()
    test_framework = {self.platform_id.title()}TestFramework(platform)
    
    # Run tests
    results = test_framework.run_tests()
    
    # Print results
    print(f"\\n=== {self.platform_name} Test Results ===")
    print(f"Total tests: {{results['summary']['total']}}")
    print(f"Passed: {{results['summary']['passed']}}")
    print(f"Failed: {{results['summary']['failed']}}")
    print(f"Success rate: {{results['summary']['success_rate']:.1%}}")
    
    # Exit with appropriate code
    sys.exit(0 if results['summary']['failed'] == 0 else 1)
""")
        
        self.logger.info(f"Platform structure generated in {platform_dir}")
        self.logger.info(f"Files created:")
        self.logger.info(f"  - {platform_file}")
        self.logger.info(f"  - {readme_file}")
        self.logger.info(f"  - {test_file}")
        self.logger.info(f"  - {mock_data_dir}/")
        
        return platform_dir


def main():
    """Main function for standalone platform development"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Standalone Platform Development Kit")
    parser.add_argument("--create", metavar="PLATFORM_ID", help="Create new platform template")
    parser.add_argument("--name", metavar="PLATFORM_NAME", help="Platform display name")
    parser.add_argument("--output", metavar="OUTPUT_DIR", default=".", help="Output directory")
    
    args = parser.parse_args()
    
    if args.create:
        platform_id = args.create
        platform_name = args.name or f"{platform_id.title()} Platform"
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        
        # Create development kit
        dev_kit = PlatformDevelopmentKit(platform_id, platform_name)
        
        # Generate platform structure
        platform_dir = dev_kit.generate_platform_structure(args.output)
        
        print(f"\\n✅ {platform_name} platform created successfully!")
        print(f"📁 Platform directory: {platform_dir}")
        print(f"\\n🚀 Quick start:")
        print(f"  cd {platform_dir}")
        print(f"  python platform.py --test")
        print(f"  python platform.py --host 127.0.0.1 --port 8000")
        print(f"\\n📚 See README.md for detailed usage instructions")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()