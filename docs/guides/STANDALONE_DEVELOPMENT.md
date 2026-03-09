# Standalone Platform Development Framework

## Overview

The Standalone Platform Development Framework enables independent development and testing of platform-specific BMC simulators without dependencies on the main server architecture. This allows platform developers to:

- **Develop Independently**: Work on platform-specific features in isolation
- **Test Thoroughly**: Use built-in testing framework with platform-specific tests
- **Iterate Quickly**: Fast development cycle with immediate feedback
- **Integrate Easily**: Seamless integration into the main server when ready

## Key Features

### 🔧 Independent Development Environment
- **Standalone Platform Interface**: Abstract interface for platform implementations
- **Mock Data Management**: Automatic loading and management of test data
- **Lightweight HTTP Server**: Built-in server for testing and development
- **No External Dependencies**: Self-contained development environment

### 🧪 Built-in Testing Framework
- **Automated Tests**: Comprehensive test suite for platform validation
- **Custom Test Cases**: Easy to add platform-specific test scenarios
- **Performance Benchmarking**: Built-in performance testing and metrics
- **Validation Tools**: Structure and implementation validation

### 🚀 Development Tools
- **CLI Interface**: Command-line tools for creating and managing platforms
- **Code Generation**: Automatic generation of platform templates
- **Live Reloading**: Quick iteration and testing cycle
- **Integration Helpers**: Tools for integrating with main server

## Architecture Components

### Core Framework (`src/standalone/`)

#### Platform Simulator (`platform_simulator.py`)
- **StandalonePlatformInterface**: Abstract base class for platform implementations
- **MockDataManager**: Manages mock data and test scenarios
- **TestFramework**: Automated testing framework with assertions
- **StandalonePlatformServer**: Lightweight HTTP server for development
- **PlatformDevelopmentKit**: Tools for creating and managing platforms

#### Platform CLI (`platform-cli`)
- **Platform Creation**: Generate new platform templates
- **Testing Tools**: Run tests and validation
- **Development Server**: Start platforms for testing
- **Performance Tools**: Benchmark and analyze performance

### Generated Platform Structure
```
platforms/
└── myvendor/
    ├── platform.py          # Main platform implementation
    ├── test_platform.py     # Platform-specific tests
    ├── README.md            # Documentation and usage
    └── mock_data/           # Test data and scenarios
        ├── service_root.json
        ├── systems.json
        └── ...
```

## Quick Start

### 1. Create a New Platform

```bash
# Create platform using CLI
./platform-cli create myvendor --name "MyVendor BMC Platform"

# This creates:
# platforms/myvendor/platform.py
# platforms/myvendor/test_platform.py  
# platforms/myvendor/README.md
# platforms/myvendor/mock_data/
```

### 2. Develop Platform Features

```python
# Edit platforms/myvendor/platform.py
class MyVendorPlatform(StandalonePlatformInterface):
    def get_platform_id(self) -> str:
        return "myvendor"
    
    def handle_request(self, method, path, headers, body=None):
        # Implement platform-specific logic
        if path.startswith("/redfish/v1/Systems/1/Oem/MyVendor/"):
            return self._handle_oem_request(method, path, headers, body)
        # ... rest of implementation
```

### 3. Test Your Platform

```bash
# Run platform tests
./platform-cli test platforms/myvendor/

# Run specific test file
cd platforms/myvendor/
python test_platform.py

# Validate implementation
./platform-cli validate platforms/myvendor/
```

### 4. Run Development Server

```bash
# Start platform server
./platform-cli run platforms/myvendor/ --port 8001

# Test endpoints
curl http://localhost:8001/redfish/v1/
curl http://localhost:8001/redfish/v1/Systems/1/Oem/MyVendor/
```

### 5. Benchmark Performance

```bash
# Run performance tests
./platform-cli benchmark platforms/myvendor/ --requests 100
```

## Platform Development Guide

### Creating Custom Endpoints

```python
def get_supported_endpoints(self) -> List[str]:
    return [
        "/redfish/v1/",
        "/redfish/v1/Systems/1/",
        "/redfish/v1/Systems/1/Oem/MyVendor/*",
        "/redfish/v1/Systems/1/Actions/Oem/MyVendor.*"
    ]

def handle_request(self, method, path, headers, body=None):
    if "/Oem/MyVendor/" in path:
        return self._handle_oem_get(path)
    elif "Actions/Oem/MyVendor." in path and method == "POST":
        return self._handle_oem_action(path, json.loads(body))
```

### Adding OEM Actions

```python
def _handle_oem_action(self, path, data):
    if "ExportConfiguration" in path:
        return 200, {}, {
            "Message": "Configuration exported",
            "ConfigurationData": self._get_platform_config()
        }
    elif "ImportConfiguration" in path:
        return 202, {}, {
            "Message": "Configuration import accepted",
            "TaskId": "task-12345"
        }
```

### Custom Test Cases

```python
class MyVendorTestFramework(TestFramework):
    def test_oem_extensions(self):
        response = self.platform.handle_request("GET", 
                    "/redfish/v1/Systems/1/Oem/MyVendor/", {})
        self.assert_response(response, 200, ["@odata.type", "Id"])
    
    def test_export_action(self):
        response = self.platform.handle_request("POST",
                    "/redfish/v1/Systems/1/Actions/Oem/MyVendor.ExportConfiguration",
                    {}, "{}")
        self.assert_response(response, 200, ["Message", "ConfigurationData"])
```

### Mock Data Management

```python
def _load_platform_data(self):
    # Load custom mock data
    self.mock_data_manager = MockDataManager("platforms/myvendor/mock_data")
    
    # Set custom data
    self.mock_data_manager.set_data("system_oem", {
        "@odata.type": "#MyVendorSystem.v1_0_0.MyVendorSystem",
        "CustomProperty": "CustomValue"
    })
```

## CLI Reference

### Platform Management
```bash
# Create new platform
./platform-cli create <platform_id> [--name "Platform Name"] [--output dir]

# List available platforms  
./platform-cli list [--dir search_directory]

# Validate platform implementation
./platform-cli validate <platform_path>
```

### Development and Testing
```bash
# Run platform tests
./platform-cli test <platform_path> [--verbose]

# Start development server
./platform-cli run <platform_path> [--host HOST] [--port PORT] [--background]

# Benchmark performance
./platform-cli benchmark <platform_path> [--requests COUNT]
```

### Examples
```bash
# Create Dell-like platform
./platform-cli create dell_custom --name "Dell Custom BMC"

# Test the platform
./platform-cli test platforms/dell_custom/

# Run on custom port
./platform-cli run platforms/dell_custom/ --port 8080

# Background server for CI/CD
./platform-cli run platforms/dell_custom/ --background --port 9000
```

## Integration with Main Server

### Converting to Main Platform

Once your standalone platform is complete, convert it to integrate with the main server:

1. **Implement Main Platform Interface**
```python
# Convert from StandalonePlatformInterface to BasePlatformProvider
from src.core.interfaces import BasePlatformProvider

class MyVendorProvider(BasePlatformProvider):
    # Implement main platform interface
    pass
```

2. **Add to Plugin Registry**
```python
# Add to src/plugins/myvendor/platform.py
MyProvider = MyVendorProvider
```

3. **Test Integration**
```bash
# Test with main server
python redfishMockupServer_platform.py --platform myvendor -D mockup/
```

### Migration Helper

```python
# Use development kit to help migration
dev_kit = PlatformDevelopmentKit("myvendor", "MyVendor Platform")
dev_kit.generate_main_platform_adapter(standalone_platform)
```

## Best Practices

### Development Workflow
1. **Start Small**: Begin with basic endpoints and gradually add features
2. **Test Continuously**: Run tests after each change
3. **Use Mock Data**: Create comprehensive test scenarios
4. **Document Everything**: Keep README and code comments updated
5. **Performance Check**: Regular benchmarking during development

### Code Organization
```python
class MyVendorPlatform(StandalonePlatformInterface):
    def __init__(self):
        self.oem_namespace = "MyVendor"
        self.platform_config = {}
        self.action_handlers = self._setup_action_handlers()
    
    def _setup_action_handlers(self):
        return {
            "ExportConfiguration": self._export_config,
            "ImportConfiguration": self._import_config,
            "RunDiagnostics": self._run_diagnostics
        }
```

### Testing Strategy
- **Unit Tests**: Test individual methods and components
- **Integration Tests**: Test complete request/response cycles  
- **Error Handling**: Test error conditions and edge cases
- **Performance Tests**: Validate response times and throughput

## Advanced Features

### Custom Authentication
```python
def handle_request(self, method, path, headers, body=None):
    # Custom authentication logic
    if not self._authenticate_request(headers):
        return 401, {"WWW-Authenticate": "Basic"}, {"error": "Authentication required"}
    
    return self._process_authenticated_request(method, path, headers, body)
```

### Event Simulation
```python
def _simulate_events(self):
    # Generate platform-specific events
    event = {
        "EventType": "Alert",
        "Message": "MyVendor system alert",
        "Oem": {
            "MyVendor": {
                "AlertCode": "MV001"
            }
        }
    }
    return event
```

### Configuration Management
```python
def load_platform_config(self, config_path: str):
    with open(config_path) as f:
        self.platform_config = json.load(f)
    
    # Apply configuration
    self._apply_config(self.platform_config)
```

## Troubleshooting

### Common Issues
1. **Import Errors**: Ensure proper Python path setup
2. **Port Conflicts**: Use different ports for multiple platforms
3. **Mock Data**: Verify JSON format and file permissions
4. **Test Failures**: Check endpoint patterns and response formats

### Debug Mode
```bash
# Enable verbose logging
./platform-cli run platforms/myvendor/ --verbose

# Debug specific test
python platforms/myvendor/test_platform.py --verbose
```

### Performance Issues
```bash
# Profile platform performance
./platform-cli benchmark platforms/myvendor/ --requests 1000

# Check response times by endpoint
curl -w "Time: %{time_total}s\n" http://localhost:8000/redfish/v1/
```

## Examples and Templates

### Example Platforms
The framework includes example platforms demonstrating:
- **Basic Platform**: Minimal implementation with standard endpoints
- **OEM Extensions**: Platform with custom OEM namespace and actions
- **Event Simulation**: Platform that generates and manages events
- **Configuration Management**: Platform with import/export capabilities

### Code Templates
- **Endpoint Handler Template**: Standard pattern for handling endpoints
- **OEM Action Template**: Template for implementing OEM actions
- **Test Case Template**: Standard test case patterns
- **Mock Data Template**: JSON data structure templates

This standalone development framework provides a complete environment for building, testing, and refining platform-specific BMC simulators independently before integration with the main server architecture.