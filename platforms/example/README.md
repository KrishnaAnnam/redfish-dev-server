# Example BMC Platform Platform Implementation

## Overview

This is a standalone platform implementation for Example BMC Platform that can be developed and tested independently.

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
curl http://localhost:8000/redfish/v1/Systems/1/Oem/Example/

# OEM actions
curl -X POST -H "Content-Type: application/json" \
     -d '{}' \
     http://localhost:8000/redfish/v1/Systems/1/Actions/Oem/Example.ExportConfiguration
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
