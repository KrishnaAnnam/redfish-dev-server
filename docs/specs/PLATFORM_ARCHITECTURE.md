# BMC Redfish Simulator - Platform Architecture

**Project:** bmc-redfish-simulator  
**Based on:** DMTF Redfish-Mockup-Server

## Overview

The BMC Redfish Simulator provides a sophisticated platform architecture that separates common Redfish functionality from vendor-specific implementations. This allows building customized BMC simulators for different hardware platforms while maintaining a shared foundation.

## Architecture Components

### Core Framework (`src/core/`)

**Interfaces (`interfaces.py`)**
- `BasePlatformProvider` - Main platform provider interface
- `BasePlatformService` - Interface for platform-specific services  
- `BasePlatformHandler` - Interface for platform-specific HTTP handlers
- `OemActionHandler` - Interface for OEM action implementations
- Enums for platform types and service capabilities

**Registry System (`registry.py`)**  
- `PlatformRegistry` - Central registry for platform providers
- Auto-discovery of platform implementations
- Provider lifecycle management
- Capability-based provider lookup

**Extensible Services (`extensible_services.py`)**
- `ExtensibleEventService` - Enhanced EventService with platform hooks
- `ExtensibleTelemetryService` - Enhanced TelemetryService with platform hooks  
- `ServiceManager` - Coordinates core and platform services

**Platform Configuration (`platform_config.py`)**
- `PlatformConfig` - Configuration dataclass for platforms
- `PlatformDetector` - Auto-detection from mockup data
- Support for configuration files and manifests

**Discovery System (`discovery.py`)**
- `PlatformDiscovery` - Automatic platform detection and loading
- Multiple detection methods (mockup analysis, manifests, hints)
- Platform provider instantiation and initialization

### Platform Implementations (`src/plugins/`)

Each platform implementation consists of:

**Platform Provider**
- Main entry point implementing `BasePlatformProvider`
- Registers services and handlers for the platform
- Provides platform identification and capabilities

**Platform Services** 
- Extend core services with platform-specific behavior
- Handle vendor-specific business logic
- Integrate with platform handlers

**Platform Handlers**
- Handle platform-specific HTTP endpoints
- Implement OEM actions and extensions
- Process vendor-specific resource paths

## Creating a New Platform

### Step 1: Create Platform Structure

```
src/plugins/myplatform/
├── __init__.py
├── platform.py          # Main platform provider
├── services.py          # Platform services (optional)
├── handlers.py          # Platform handlers (optional)  
└── actions.py           # OEM actions (optional)
```

### Step 2: Implement Platform Provider

```python
# src/plugins/myplatform/platform.py
from ...core.interfaces import BasePlatformProvider, PlatformType

class MyPlatformProvider(BasePlatformProvider):
    def get_platform_info(self) -> Dict[str, Any]:
        return {
            "platform_id": "myplatform",
            "platform_type": "custom", 
            "display_name": "My Custom Platform",
            "version": "1.0.0",
            "description": "Custom platform implementation"
        }
    
    def get_platform_type(self) -> PlatformType:
        return PlatformType.CUSTOM
    
    def initialize(self) -> bool:
        self.register_services()
        self.register_handlers()
        return True
    
    def register_services(self):
        # Add platform services
        pass
    
    def register_handlers(self):
        # Add platform handlers  
        pass

# Auto-registration
MyProvider = MyPlatformProvider
```

### Step 3: Implement Platform Services (Optional)

```python
# src/plugins/myplatform/services.py
from ...core.interfaces import BasePlatformService, ServiceCapability

class MyEventService(BasePlatformService):
    def get_service_name(self) -> str:
        return "my_event_service"
    
    def get_supported_capabilities(self) -> List[ServiceCapability]:
        return [ServiceCapability.EVENT_SERVICE]
    
    def initialize(self) -> bool:
        return True
    
    def preprocess_event(self, event_data):
        # Add platform-specific event processing
        return event_data
```

### Step 4: Implement Platform Handlers (Optional)

```python  
# src/plugins/myplatform/handlers.py
from ...core.interfaces import BasePlatformHandler

class MyOemHandler(BasePlatformHandler):
    def get_handler_name(self) -> str:
        return "my_oem_handler"
    
    def get_supported_paths(self) -> List[str]:
        return ["/redfish/v1/Systems/*/Oem/MyVendor/*"]
    
    def handle_get(self, path, query_params=None, cached_links=None):
        # Handle GET requests for OEM paths
        return 200, {"MyVendor": {"CustomProperty": "value"}}
    
    def handle_post(self, path, data, cached_links=None):
        # Handle POST requests (OEM actions)
        return 200, {"Message": "Action completed"}
```

## Platform Detection

The system supports multiple detection methods:

### Auto-Detection from Mockup Data
Analyzes the mockup directory structure and service root to detect:
- OEM namespaces (Dell, Hpe, etc.)
- Available services  
- System/Manager/Chassis information
- Platform-specific indicators

### Platform Manifest Files
JSON files that explicitly define platform configuration:
```json
{
    "platform_id": "my_platform",
    "platform_type": "custom", 
    "display_name": "My Platform",
    "enabled_services": ["EventService"],
    "oem_namespace": "MyVendor"
}
```

Supported manifest locations:
- `{mockup_dir}/platform_manifest.json`
- `{mockup_dir}/.platform`  
- `{mockup_dir}/redfish/v1/platform_manifest.json`

### Manual Platform Hints
Specify platform via command line:
```bash
python redfishMockupServer_platform.py --platform generic
```

## Usage Examples

### List Available Platforms
```bash
python redfishMockupServer_platform.py --list-platforms
```

### Show Platform Detection Info
```bash  
python redfishMockupServer_platform.py --platform-info -D /path/to/mockup
```

### Run with Specific Platform
```bash
python redfishMockupServer_platform.py --platform generic -D /path/to/mockup
```

### Run with Auto-Detection
```bash
python redfishMockupServer_platform.py -D /path/to/mockup
```

## Platform Configuration

### Configuration File Structure
Platform configurations define:

- **Platform Identity**: ID, type, name, version
- **Service Configuration**: Which services to enable and their settings
- **OEM Extensions**: Namespace, actions, properties
- **Hardware Information**: System, manager, chassis details
- **Authentication**: Supported methods and limits
- **Custom Properties**: Platform-specific data

### Example Configuration
```json
{
    "platform_id": "custom_server",
    "platform_type": "generic", 
    "display_name": "Custom Rackmount Server",
    "extensions": ["ras", "telemetry"],
    "enabled_services": ["EventService", "UpdateService"],
    "system_info": {
        "Manufacturer": "Example Corp.",
        "Model": "Server S100"
    }
}
```

## Extension Points

### Service Hooks
Core services provide hooks for platform extensions:

```python
# In platform service
def preprocess_event(self, event_data):
    # Modify event before processing
    return event_data

def handle_event_submission(self, path, data, cached_links):
    # Completely override event handling
    return status_code, response_data
```

### Handler Patterns  
Platform handlers can intercept specific URL patterns:

```python
def get_supported_paths(self):
    return [
        "/redfish/v1/Systems/*/Oem/Dell/*",
        "**/Actions/Oem/Dell.*"
    ]
```

### Registry Integration
The platform registry automatically discovers and manages platforms:

```python
from src.core.registry import platform_registry

# Auto-discover all platform providers
platform_registry.auto_discover_providers()

# Get provider by capabilities
providers = platform_registry.find_providers_by_capability(
    ServiceCapability.EVENT_SERVICE
)
```

## Benefits

### For BMC Simulator Development
- **Rapid Platform Support**: Add new platforms without modifying core code
- **Vendor Differentiation**: Implement vendor-specific features and behaviors  
- **Reusable Components**: Share services and handlers across platforms
- **Easy Testing**: Test platform-specific features in isolation

### For End Users
- **Automatic Detection**: Server auto-detects platform from mockup data
- **Consistent Interface**: Same command-line interface for all platforms
- **Enhanced Fidelity**: Platform-specific behaviors for realistic simulation
- **Extensible**: Easy to add custom platforms for specific needs

This architecture provides a clean separation between generic Redfish functionality and platform-specific implementations, enabling the creation of sophisticated, vendor-accurate BMC simulators while maintaining ease of use and extensibility.