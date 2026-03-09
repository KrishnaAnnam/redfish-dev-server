# Platform Development Guide

## Overview

This guide walks you through creating custom platform providers for the Enhanced Redfish Simulator Server. Platform providers enable vendor-specific functionality while leveraging the shared Redfish foundation.

## Platform Provider Basics

### Core Concepts

**Platform Provider** - Main entry point that identifies the platform and registers components
**Platform Services** - Extend core services with vendor-specific behavior  
**Platform Handlers** - Handle vendor-specific HTTP endpoints and OEM actions
**Platform Configuration** - Define platform capabilities and settings

### Minimal Platform Implementation

The simplest platform requires only a platform provider:

```python
# src/plugins/myvendor/platform.py
from src.core.interfaces import BasePlatformProvider, PlatformType

class MyVendorProvider(BasePlatformProvider):
    def get_platform_info(self) -> Dict[str, Any]:
        return {
            "platform_id": "myvendor_bmc",
            "platform_type": "custom",
            "display_name": "MyVendor BMC",
            "version": "1.0.0",
            "description": "MyVendor BMC simulator"
        }
    
    def get_platform_type(self) -> PlatformType:
        return PlatformType.CUSTOM
    
    def initialize(self) -> bool:
        return True

# Required for auto-discovery
MyProvider = MyVendorProvider
```

## Step-by-Step Development

### Step 1: Setup Platform Directory

```bash
mkdir -p src/plugins/myvendor
touch src/plugins/myvendor/__init__.py
touch src/plugins/myvendor/platform.py
```

### Step 2: Implement Platform Provider

```python
# src/plugins/myvendor/platform.py
from typing import Dict, Any, List, Optional
from src.core.interfaces import (
    BasePlatformProvider, 
    PlatformType, 
    ServiceCapability
)

class MyVendorProvider(BasePlatformProvider):
    def __init__(self):
        super().__init__()
        self.oem_namespace = "MyVendor"
        self.platform_services = {}
        self.platform_handlers = {}
    
    def get_platform_info(self) -> Dict[str, Any]:
        return {
            "platform_id": "myvendor_bmc",
            "platform_type": "custom",
            "display_name": "MyVendor BMC Platform",
            "vendor": "MyVendor Inc.",
            "version": "1.0.0",
            "description": "Custom BMC simulator for MyVendor hardware",
            "oem_namespace": self.oem_namespace,
            "supported_capabilities": [
                ServiceCapability.EVENT_SERVICE.value,
                ServiceCapability.TELEMETRY_SERVICE.value
            ]
        }
    
    def get_platform_type(self) -> PlatformType:
        return PlatformType.CUSTOM
    
    def get_supported_capabilities(self) -> List[ServiceCapability]:
        return [
            ServiceCapability.EVENT_SERVICE,
            ServiceCapability.TELEMETRY_SERVICE
        ]
    
    def initialize(self) -> bool:
        """Initialize the platform provider"""
        try:
            self.register_services()
            self.register_handlers()
            return True
        except Exception as e:
            print(f"Failed to initialize MyVendor platform: {e}")
            return False
    
    def register_services(self):
        """Register platform-specific services"""
        # Import services locally to avoid circular imports
        from .services import MyVendorEventService
        
        event_service = MyVendorEventService()
        self.platform_services["event_service"] = event_service
    
    def register_handlers(self):
        """Register platform-specific handlers"""
        from .handlers import MyVendorOemHandler
        
        oem_handler = MyVendorOemHandler()
        self.platform_handlers["oem_handler"] = oem_handler
    
    def get_platform_services(self) -> Dict[str, Any]:
        """Return registered platform services"""
        return self.platform_services
    
    def get_platform_handlers(self) -> Dict[str, Any]:
        """Return registered platform handlers"""
        return self.platform_handlers

# Required for auto-discovery
MyProvider = MyVendorProvider
```

### Step 3: Add Platform Services (Optional)

```python
# src/plugins/myvendor/services.py
from typing import Dict, Any, List
from src.core.interfaces import BasePlatformService, ServiceCapability

class MyVendorEventService(BasePlatformService):
    """MyVendor-specific event service extensions"""
    
    def __init__(self):
        super().__init__()
        self.vendor_events = []
    
    def get_service_name(self) -> str:
        return "myvendor_event_service"
    
    def get_supported_capabilities(self) -> List[ServiceCapability]:
        return [ServiceCapability.EVENT_SERVICE]
    
    def initialize(self) -> bool:
        """Initialize the service"""
        print("MyVendor Event Service initialized")
        return True
    
    def shutdown(self):
        """Cleanup service resources"""
        self.vendor_events.clear()
    
    def preprocess_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add MyVendor-specific event processing"""
        # Add vendor-specific fields
        event_data["Oem"] = {
            "MyVendor": {
                "VendorEventId": len(self.vendor_events) + 1,
                "ProcessingTimestamp": self._get_timestamp()
            }
        }
        
        # Store event for tracking
        self.vendor_events.append(event_data)
        
        return event_data
    
    def handle_event_submission(self, path: str, data: Dict[str, Any], 
                              cached_links=None) -> tuple:
        """Handle vendor-specific event submission"""
        if "MyVendor" in path:
            # Process MyVendor-specific event submission
            processed_data = self.preprocess_event(data)
            return 202, {
                "Message": "MyVendor event submitted successfully",
                "EventId": processed_data["Oem"]["MyVendor"]["VendorEventId"]
            }
        
        # Fall back to default handling
        return None
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

class MyVendorTelemetryService(BasePlatformService):
    """MyVendor-specific telemetry service"""
    
    def get_service_name(self) -> str:
        return "myvendor_telemetry_service"
    
    def get_supported_capabilities(self) -> List[ServiceCapability]:
        return [ServiceCapability.TELEMETRY_SERVICE]
    
    def initialize(self) -> bool:
        return True
    
    def get_telemetry_data(self, resource_path: str) -> Dict[str, Any]:
        """Provide vendor-specific telemetry data"""
        return {
            "MyVendor": {
                "CustomMetrics": {
                    "VendorTemperature": 42.5,
                    "VendorPowerConsumption": 150.0,
                    "VendorUtilization": 75.2
                }
            }
        }
```

### Step 4: Add Platform Handlers (Optional)

```python
# src/plugins/myvendor/handlers.py
from typing import Dict, Any, List, Optional, Tuple
from src.core.interfaces import BasePlatformHandler

class MyVendorOemHandler(BasePlatformHandler):
    """Handler for MyVendor OEM extensions"""
    
    def __init__(self):
        super().__init__()
        self.oem_namespace = "MyVendor"
    
    def get_handler_name(self) -> str:
        return "myvendor_oem_handler"
    
    def get_supported_paths(self) -> List[str]:
        """Return URL patterns this handler supports"""
        return [
            "/redfish/v1/*/Oem/MyVendor/*",
            "**/Actions/Oem/MyVendor.*",
            "/redfish/v1/Systems/*/MyVendorExtensions/*"
        ]
    
    def initialize(self) -> bool:
        return True
    
    def handle_get(self, path: str, query_params: Optional[Dict] = None, 
                   cached_links=None) -> Tuple[int, Dict[str, Any]]:
        """Handle GET requests for MyVendor OEM paths"""
        
        if "/Oem/MyVendor/" in path:
            return self._handle_oem_get(path, query_params)
        elif "/MyVendorExtensions/" in path:
            return self._handle_extensions_get(path, query_params)
        
        return 404, {"error": "MyVendor OEM resource not found"}
    
    def handle_post(self, path: str, data: Dict[str, Any], 
                    cached_links=None) -> Tuple[int, Dict[str, Any]]:
        """Handle POST requests (OEM actions)"""
        
        if "Actions/Oem/MyVendor." in path:
            return self._handle_oem_action(path, data)
        
        return 405, {"error": "Method not allowed"}
    
    def _handle_oem_get(self, path: str, query_params: Optional[Dict]) -> Tuple[int, Dict[str, Any]]:
        """Handle GET requests for OEM namespace"""
        
        # Extract resource type from path
        if "/Systems/" in path:
            return self._get_system_oem_data(path)
        elif "/Managers/" in path:
            return self._get_manager_oem_data(path)
        elif "/Chassis/" in path:
            return self._get_chassis_oem_data(path)
        
        return 404, {"error": "OEM resource not found"}
    
    def _get_system_oem_data(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """Get system-level OEM data"""
        return 200, {
            "@odata.type": "#MyVendorSystem.v1_0_0.MyVendorSystem",
            "@odata.id": path,
            "Id": "MyVendorSystemExtensions",
            "Name": "MyVendor System Extensions",
            "SystemConfiguration": {
                "BootMode": "UEFI",
                "VendorSpecificSetting": "CustomValue"
            },
            "Actions": {
                "#MyVendor.ExportConfiguration": {
                    "target": f"{path}/Actions/MyVendor.ExportConfiguration"
                },
                "#MyVendor.ImportConfiguration": {
                    "target": f"{path}/Actions/MyVendor.ImportConfiguration"
                }
            }
        }
    
    def _get_manager_oem_data(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """Get manager-level OEM data"""
        return 200, {
            "@odata.type": "#MyVendorManager.v1_0_0.MyVendorManager", 
            "@odata.id": path,
            "Id": "MyVendorManagerExtensions",
            "Name": "MyVendor Manager Extensions",
            "FirmwareVersion": "1.2.3",
            "VendorSettings": {
                "RemoteAccess": True,
                "SecurityLevel": "High"
            }
        }
    
    def _get_chassis_oem_data(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """Get chassis-level OEM data"""
        return 200, {
            "@odata.type": "#MyVendorChassis.v1_0_0.MyVendorChassis",
            "@odata.id": path, 
            "Id": "MyVendorChassisExtensions",
            "Name": "MyVendor Chassis Extensions",
            "ThermalProfile": "Balanced",
            "VendorLEDs": {
                "Status": "On",
                "Color": "Blue"
            }
        }
    
    def _handle_extensions_get(self, path: str, query_params: Optional[Dict]) -> Tuple[int, Dict[str, Any]]:
        """Handle MyVendor extensions endpoint"""
        return 200, {
            "@odata.type": "#MyVendorExtensionCollection.MyVendorExtensionCollection",
            "@odata.id": path,
            "Name": "MyVendor Extensions Collection",
            "Members": [
                {"@odata.id": f"{path}/Configuration"},
                {"@odata.id": f"{path}/Diagnostics"},
                {"@odata.id": f"{path}/Management"}
            ],
            "Members@odata.count": 3
        }
    
    def _handle_oem_action(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Handle OEM action execution"""
        
        if "ExportConfiguration" in path:
            return self._export_configuration(data)
        elif "ImportConfiguration" in path:
            return self._import_configuration(data)
        elif "RunDiagnostics" in path:
            return self._run_diagnostics(data)
        
        return 400, {"error": "Unknown MyVendor action"}
    
    def _export_configuration(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Export system configuration"""
        return 200, {
            "Message": "Configuration export initiated",
            "ExportId": "export-123456",
            "Status": "InProgress",
            "ConfigurationData": {
                "SystemSettings": {"Setting1": "Value1"},
                "NetworkSettings": {"DHCP": True},
                "SecuritySettings": {"AuthMode": "LDAP"}
            }
        }
    
    def _import_configuration(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Import system configuration"""
        return 202, {
            "Message": "Configuration import accepted",
            "ImportId": "import-789012",
            "Status": "Scheduled"
        }
    
    def _run_diagnostics(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Run system diagnostics"""
        return 202, {
            "Message": "Diagnostics started",
            "DiagnosticsId": "diag-345678", 
            "EstimatedDuration": "PT5M"
        }
```

### Step 5: Add OEM Actions (Optional)

```python
# src/plugins/myvendor/actions.py
from typing import Dict, Any, Tuple
from src.core.interfaces import OemActionHandler

class MyVendorActions(OemActionHandler):
    """MyVendor OEM action implementations"""
    
    def get_oem_namespace(self) -> str:
        return "MyVendor"
    
    def get_supported_actions(self) -> Dict[str, str]:
        return {
            "ExportConfiguration": "Export system configuration",
            "ImportConfiguration": "Import system configuration", 
            "RunDiagnostics": "Run hardware diagnostics",
            "UpdateFirmware": "Update system firmware",
            "ResetToDefaults": "Reset to factory defaults"
        }
    
    def execute_action(self, action_name: str, resource_path: str, 
                      parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Execute the specified OEM action"""
        
        if action_name == "ExportConfiguration":
            return self.export_configuration(resource_path, parameters)
        elif action_name == "ImportConfiguration":
            return self.import_configuration(resource_path, parameters)
        elif action_name == "RunDiagnostics":
            return self.run_diagnostics(resource_path, parameters)
        elif action_name == "UpdateFirmware":
            return self.update_firmware(resource_path, parameters)
        elif action_name == "ResetToDefaults":
            return self.reset_to_defaults(resource_path, parameters)
        
        return 400, {"error": f"Unknown action: {action_name}"}
    
    def export_configuration(self, resource_path: str, 
                           parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Export system configuration"""
        
        export_format = parameters.get("Format", "JSON")
        include_secure = parameters.get("IncludeSecureSettings", False)
        
        # Simulate configuration export
        config_data = {
            "SystemIdentification": {
                "SerialNumber": "MVS123456",
                "Model": "MyVendor Server Pro"
            },
            "NetworkConfiguration": {
                "ManagementInterface": {
                    "DHCP": True,
                    "IPv4Address": "192.168.1.100"
                }
            },
            "SystemSettings": {
                "PowerManagement": "Balanced",
                "BootOrder": ["HDD", "PXE", "USB"]
            }
        }
        
        if include_secure:
            config_data["SecurityConfiguration"] = {
                "AuthenticationMode": "LDAP",
                "CertificateInfo": "Present"
            }
        
        return 200, {
            "Message": "Configuration exported successfully",
            "Format": export_format,
            "ConfigurationData": config_data,
            "Timestamp": self._get_timestamp()
        }
    
    def import_configuration(self, resource_path: str,
                           parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Import system configuration"""
        
        config_data = parameters.get("ConfigurationData", {})
        validate_only = parameters.get("ValidateOnly", False)
        
        if not config_data:
            return 400, {"error": "ConfigurationData is required"}
        
        if validate_only:
            return 200, {
                "Message": "Configuration validation successful",
                "ValidationResult": "Valid",
                "Changes": len(config_data)
            }
        
        # Simulate configuration import
        return 202, {
            "Message": "Configuration import accepted",
            "TaskId": "task-import-456789",
            "Status": "InProgress",
            "EstimatedCompletion": "PT2M"
        }
    
    def run_diagnostics(self, resource_path: str,
                       parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Run hardware diagnostics"""
        
        test_level = parameters.get("TestLevel", "Basic")
        components = parameters.get("Components", ["All"])
        
        # Simulate diagnostics execution
        results = {
            "CPU": "Pass",
            "Memory": "Pass", 
            "Storage": "Pass",
            "Network": "Pass"
        }
        
        if "All" not in components:
            results = {k: v for k, v in results.items() if k in components}
        
        return 200, {
            "Message": f"{test_level} diagnostics completed",
            "TestLevel": test_level,
            "Results": results,
            "OverallStatus": "Pass",
            "Duration": "PT30S"
        }
    
    def update_firmware(self, resource_path: str,
                       parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Update system firmware"""
        
        firmware_uri = parameters.get("FirmwareURI")
        component = parameters.get("Component", "BMC")
        
        if not firmware_uri:
            return 400, {"error": "FirmwareURI is required"}
        
        # Simulate firmware update
        return 202, {
            "Message": f"{component} firmware update initiated",
            "Component": component,
            "FirmwareURI": firmware_uri,
            "TaskId": "task-fw-update-123",
            "EstimatedDuration": "PT10M"
        }
    
    def reset_to_defaults(self, resource_path: str,
                         parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Reset system to factory defaults"""
        
        preserve_network = parameters.get("PreserveNetworkSettings", False)
        preserve_users = parameters.get("PreserveUserAccounts", False)
        
        # Simulate factory reset
        return 202, {
            "Message": "Factory reset initiated",
            "PreserveNetworkSettings": preserve_network,
            "PreserveUserAccounts": preserve_users,
            "TaskId": "task-reset-789",
            "EstimatedDuration": "PT5M"
        }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
```

## Testing Your Platform

### Step 1: Basic Platform Detection
```bash
# Test platform is discovered
python redfishMockupServer_platform.py --list-platforms

# Test platform info
python redfishMockupServer_platform.py --platform-info --platform myvendor
```

### Step 2: Test Platform Services
```bash
# Start server with your platform
python redfishMockupServer_platform.py --platform myvendor -D mockup/ -v

# Test OEM endpoints
curl http://localhost:8000/redfish/v1/Systems/1/Oem/MyVendor/

# Test OEM actions
curl -X POST -H "Content-Type: application/json" \
     -d '{"Format": "JSON"}' \
     http://localhost:8000/redfish/v1/Systems/1/Actions/Oem/MyVendor.ExportConfiguration
```

### Step 3: Create Platform Configuration
```json
{
    "platform_id": "myvendor_bmc",
    "platform_type": "custom",
    "display_name": "MyVendor BMC Platform",
    "enabled_services": ["EventService", "TelemetryService"],
    "oem_namespace": "MyVendor",
    "oem_actions": ["ExportConfiguration", "ImportConfiguration"],
    "system_info": {
        "Manufacturer": "MyVendor Inc.",
        "Model": "Server Pro"
    }
}
```

## Advanced Platform Features

### Platform-Specific Configuration
```python
def load_platform_config(self, config_data: Dict[str, Any]) -> bool:
    """Load platform-specific configuration"""
    self.vendor_settings = config_data.get("vendor_settings", {})
    self.custom_endpoints = config_data.get("custom_endpoints", [])
    return True
```

### Dynamic Handler Registration
```python
def register_dynamic_handlers(self):
    """Register handlers based on configuration"""
    for endpoint in self.custom_endpoints:
        handler = CustomEndpointHandler(endpoint)
        self.platform_handlers[endpoint["name"]] = handler
```

### Platform Lifecycle Management
```python
def shutdown(self):
    """Clean shutdown of platform resources"""
    for service in self.platform_services.values():
        if hasattr(service, 'shutdown'):
            service.shutdown()
    
    for handler in self.platform_handlers.values():
        if hasattr(handler, 'cleanup'):
            handler.cleanup()
```

## Best Practices

### Design Guidelines
- **Single Responsibility**: Each component should have a clear, focused purpose
- **Loose Coupling**: Minimize dependencies between platform components
- **Error Handling**: Always provide graceful error handling and fallbacks
- **Documentation**: Document all public methods and configuration options

### Performance Considerations  
- **Lazy Loading**: Load services and handlers only when needed
- **Caching**: Cache expensive operations and data lookups
- **Resource Management**: Properly manage memory and file handles
- **Async Operations**: Use async patterns for long-running operations

### Testing Strategy
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test platform integration with core server
- **Mock Data**: Use realistic mock data for testing
- **Error Cases**: Test error handling and edge cases

## Publishing Your Platform

### Package Structure
```
src/plugins/myvendor/
├── __init__.py
├── platform.py          # Main platform provider
├── services.py          # Platform services  
├── handlers.py          # Platform handlers
├── actions.py           # OEM action implementations
├── README.md            # Platform documentation
├── config/              # Configuration templates
│   ├── default.json
│   └── examples/
└── tests/               # Platform tests
    ├── test_platform.py
    ├── test_services.py
    └── test_handlers.py
```

### Documentation Requirements
- Platform capabilities and features
- Configuration options and examples
- OEM action documentation
- Integration examples
- Testing instructions

### Contribution Guidelines
- Follow existing code style and patterns
- Add comprehensive tests
- Update documentation
- Provide configuration examples
- Test with multiple mockup datasets

This comprehensive guide should help you create robust, feature-rich platform providers for the Enhanced Redfish Simulator Server.