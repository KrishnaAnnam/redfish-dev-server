# BMC Redfish Simulator - Modular Version

Based on DMTF Redfish-Mockup-Server

This is a modular refactoring that provides improved maintainability, extensibility, and separation of concerns for BMC simulation.

## Architecture

The modular version splits the original monolithic server into several focused modules:

### Directory Structure

```
src/
├── __init__.py
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuration management
├── handlers/
│   ├── __init__.py
│   ├── base_handler.py      # Base HTTP handler class
│   ├── get_handler.py       # GET request handling
│   ├── post_handler.py      # POST request handling
│   ├── patch_handler.py     # PATCH request handling
│   ├── put_handler.py       # PUT request handling
│   ├── delete_handler.py    # DELETE request handling
│   └── main_handler.py      # Combined handler
├── services/
│   ├── __init__.py
│   ├── event_service.py     # EventService operations
│   └── telemetry_service.py # TelemetryService operations
└── utils/
    ├── __init__.py
    ├── helpers.py           # General utility functions
    └── file_utils.py        # File and path utilities
```

### Key Improvements

1. **Separation of Concerns**: Each HTTP method has its own handler module
2. **Service Isolation**: EventService and TelemetryService logic is isolated
3. **Configuration Management**: Centralized configuration with validation
4. **Extensibility**: Easy to add new handlers and services
5. **Maintainability**: Smaller, focused modules are easier to understand and modify

## Usage

### Running the Modular Server

```bash
python servers/redfishMockupServer_modular.py [options]
```

The modular server supports all the same command-line options as the original:

```bash
# Basic usage
python servers/redfishMockupServer_modular.py -H 0.0.0.0 -p 8000 -D ./mockups/public-rackmount1

# With SSL
python servers/redfishMockupServer_modular.py -s --cert server.crt --key server.key

# With SSDP discovery
python servers/redfishMockupServer_modular.py -P

# Short form (omit /redfish/v1 in paths)
python servers/redfishMockupServer_modular.py -S
```

### Installing Dependencies

```bash
pip install -r requirements_modular.txt
```

## Adding New Features

### Adding a New HTTP Handler

1. Create a new handler module in `src/handlers/`
2. Inherit from `BaseRedfishHandler`
3. Implement the required HTTP method (e.g., `do_OPTIONS`)
4. Add the handler to `main_handler.py`

### Adding a New Service

1. Create a service module in `src/services/`
2. Implement the service class with required methods
3. Initialize the service in `base_handler.py`
4. Call service methods from appropriate HTTP handlers

### Example: Adding a Custom Service

```python
# src/services/custom_service.py
class CustomService:
    def __init__(self, server_config):
        self.server_config = server_config
    
    def handle_custom_operation(self, path, data, cached_links):
        # Your custom logic here
        return 200

# In base_handler.py, add:
from ..services.custom_service import CustomService

class BaseRedfishHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.custom_service = CustomService(server.config)
        super().__init__(request, client_address, server)
```

## Backward Compatibility

The modular server maintains full backward compatibility with the original server:

- All existing command-line options work identically
- All API endpoints behave the same way
- Mockup file formats are unchanged
- Response formats are identical

## Benefits

1. **Easier Development**: Smaller, focused modules are easier to work with
2. **Better Testing**: Individual components can be tested in isolation
3. **Enhanced Extensibility**: New features can be added without modifying core logic
4. **Improved Maintainability**: Clear separation makes bugs easier to locate and fix
5. **Code Reusability**: Services and utilities can be reused across different contexts

## Migration from Original Server

To migrate from the original server to the modular version:

1. Install the new dependencies: `pip install -r config/requirements_modular.txt`
2. Replace `python servers/redfishMockupServer.py` with `python servers/redfishMockupServer_modular.py`
3. Use the same command-line arguments as before

The modular server is a drop-in replacement for the original server.