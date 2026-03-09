# Plugin SDK Guide - BMC Redfish Simulator

**Version:** 1.0.0  
**Last Updated:** January 23, 2026

## Table of Contents

1. [Overview](#overview)
2. [Plugin Architecture](#plugin-architecture)
3. [Plugin Structure](#plugin-structure)
4. [Creating a Plugin](#creating-a-plugin)
5. [Plugin Interfaces](#plugin-interfaces)
6. [Plugin Loader System](#plugin-loader-system)
7. [Handler Integration](#handler-integration)
8. [Best Practices](#best-practices)
9. [Testing Plugins](#testing-plugins)
10. [Examples](#examples)

---

## Overview

The BMC Redfish Simulator uses a **plugin architecture** to extend functionality without contaminating the base server code. Plugins are self-contained modules that can be loaded dynamically based on platform configuration.

### Benefits of Plugin Architecture

- **Isolation**: Plugin code stays separate from base server
- **Modularity**: Plugins can be enabled/disabled independently
- **Extensibility**: Add new features without modifying core
- **Reusability**: Share plugins across different mockups
- **Maintainability**: Clear separation of concerns

### Available Plugins

- **RAS Plugin** (`src/plugins/ras/`) - Reliability, Availability, Serviceability
- **Telemetry Plugin** (`src/plugins/telemetry/`) - Metric collection and reporting
- **Your Plugin** - Follow this guide to create new plugins!

---

## Plugin Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Platform Server                          │
│  (servers/redfishMockupServer_platform.py)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  Plugin Loader                              │
│              (src/plugins/loader.py)                        │
│  • Discovers plugins from config                           │
│  • Loads plugin modules dynamically                        │
│  • Routes requests to plugin handlers                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼────────┐ ┌──▼─────────┐ ┌──▼──────────┐
│  RAS Plugin    │ │ Telemetry  │ │ Your Plugin │
│  (enabled)     │ │  Plugin    │ │  (custom)   │
└────────────────┘ └────────────┘ └─────────────┘
```

### Request Flow

```
1. HTTP Request → Platform Server
2. Platform Server → BaseHandler (do_GET/do_POST)
3. BaseHandler → PluginLoader.get_plugin_for_path()
4. PluginLoader → Plugin Handler (handle_get/handle_post)
5. Plugin Handler → Returns (status, headers, body)
6. Platform Server → Sends HTTP Response
```

---

## Plugin Structure

### Directory Layout

```
src/plugins/
├── __init__.py                 # Plugin system exports
├── loader.py                   # Plugin loader implementation
├── your_plugin/                # Your plugin directory
│   ├── __init__.py             # Plugin package init
│   ├── plugin.py               # Plugin registration
│   ├── provider.py             # Main plugin handler
│   ├── config.py               # Plugin configuration
│   ├── handlers/               # Request handlers
│   │   ├── __init__.py
│   │   ├── get_handler.py
│   │   └── post_handler.py
│   ├── models/                 # Data models
│   │   ├── __init__.py
│   │   └── types.py
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   └── core_service.py
│   ├── schemas/                # JSON schemas
│   │   └── YourSchema.v1_0_0.json
│   └── registries/             # Message registries
│       └── YourRegistry.1.0.0.json
```

### Minimal Plugin Structure

```
src/plugins/minimal_plugin/
├── __init__.py          # Export plugin class
├── plugin.py            # Plugin metadata
└── provider.py          # Main handler
```

---

## Creating a Plugin

### Step 1: Create Plugin Directory

```bash
cd /path/to/bmc-redfish-simulator
mkdir -p src/plugins/my_plugin/handlers
touch src/plugins/my_plugin/__init__.py
touch src/plugins/my_plugin/plugin.py
touch src/plugins/my_plugin/provider.py
```

### Step 2: Define Plugin Metadata

Create `src/plugins/my_plugin/plugin.py`:

```python
"""
My Plugin - Custom functionality for BMC Simulator
"""

PLUGIN_NAME = "my_plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Description of what this plugin does"
PLUGIN_ENABLED_BY_DEFAULT = False

# Required paths this plugin handles
PLUGIN_PATHS = [
    "/redfish/v1/MyService",
    "/redfish/v1/MyService/Actions/*",
    "/redfish/v1/Managers/*/Oem/MyVendor/*"
]

# Configuration defaults
PLUGIN_CONFIG_DEFAULTS = {
    "enabled": True,
    "log_level": "INFO",
    "storage_path": "/tmp/my_plugin_data"
}
```

### Step 3: Implement Plugin Provider

Create `src/plugins/my_plugin/provider.py`:

```python
"""
My Plugin Provider - Main entry point
"""
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class MyPluginHandler:
    """
    Main handler for My Plugin
    
    This class is instantiated by the PluginLoader and handles
    all requests routed to this plugin.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the plugin handler
        
        Args:
            config: Plugin configuration from platform config or defaults
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.mockup_dir = self.config.get('mockup_dir', 'mockups')
        
        logger.info(f"Initializing My Plugin (enabled={self.enabled})")
        
        # Initialize sub-handlers
        self._init_handlers()
    
    def _init_handlers(self):
        """Initialize request handlers"""
        # Import handlers here to avoid circular imports
        from .handlers.get_handler import MyGetHandler
        from .handlers.post_handler import MyPostHandler
        
        self.get_handler = MyGetHandler(self.config)
        self.post_handler = MyPostHandler(self.config)
    
    def get_supported_paths(self) -> list:
        """
        Return list of path patterns this plugin handles
        
        Supports glob-style patterns:
        - Exact: "/redfish/v1/MyService"
        - Wildcard: "/redfish/v1/MyService/*"
        - Match any: "/redfish/v1/Managers/*/Oem/MyVendor/*"
        """
        return [
            "/redfish/v1/MyService",
            "/redfish/v1/MyService/Actions/*",
            "/redfish/v1/Managers/*/Oem/MyVendor/*"
        ]
    
    def handle_get(
        self, 
        path: str, 
        query_params: Optional[Dict] = None,
        cached_links: Optional[Dict] = None
    ) -> Tuple[int, Dict, Any]:
        """
        Handle GET requests
        
        Args:
            path: Request path (e.g., "/redfish/v1/MyService")
            query_params: URL query parameters
            cached_links: Pre-cached resource links from server
        
        Returns:
            Tuple of (status_code, headers, body)
            - status_code: HTTP status (200, 404, etc.)
            - headers: Response headers dict
            - body: Response body (dict or string)
        """
        if not self.enabled:
            return 404, {}, {"error": "Plugin disabled"}
        
        logger.info(f"GET {path}")
        
        # Delegate to GET handler
        return self.get_handler.handle(path, query_params, cached_links)
    
    def handle_post(
        self,
        path: str,
        data: Dict[str, Any],
        cached_links: Optional[Dict] = None
    ) -> Tuple[int, Dict, Any]:
        """
        Handle POST requests
        
        Args:
            path: Request path
            data: Request body (parsed JSON)
            cached_links: Pre-cached resource links
        
        Returns:
            Tuple of (status_code, headers, body)
        """
        if not self.enabled:
            return 404, {}, {"error": "Plugin disabled"}
        
        logger.info(f"POST {path}")
        
        # Delegate to POST handler
        return self.post_handler.handle(path, data, cached_links)
    
    def handle_patch(
        self,
        path: str,
        data: Dict[str, Any],
        cached_links: Optional[Dict] = None
    ) -> Tuple[int, Dict, Any]:
        """Handle PATCH requests"""
        return 405, {}, {"error": "PATCH not supported"}
    
    def handle_delete(
        self,
        path: str,
        cached_links: Optional[Dict] = None
    ) -> Tuple[int, Dict, Any]:
        """Handle DELETE requests"""
        return 405, {}, {"error": "DELETE not supported"}
```

### Step 4: Implement Request Handlers

Create `src/plugins/my_plugin/handlers/__init__.py`:

```python
"""Plugin request handlers"""
from .get_handler import MyGetHandler
from .post_handler import MyPostHandler

__all__ = ['MyGetHandler', 'MyPostHandler']
```

Create `src/plugins/my_plugin/handlers/get_handler.py`:

```python
"""GET request handler"""
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class MyGetHandler:
    """Handles GET requests for the plugin"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def handle(
        self,
        path: str,
        query_params: Optional[Dict] = None,
        cached_links: Optional[Dict] = None
    ) -> Tuple[int, Dict, Any]:
        """
        Route GET requests to appropriate handlers
        
        Args:
            path: Request path
            query_params: URL query parameters
            cached_links: Server's cached links
        
        Returns:
            (status_code, headers, body)
        """
        # Route to specific handlers
        if path == "/redfish/v1/MyService":
            return self._get_service_root(query_params)
        
        elif path.startswith("/redfish/v1/Managers/") and "/Oem/MyVendor/" in path:
            return self._get_oem_resource(path, query_params)
        
        else:
            return 404, {}, {"error": "Not found"}
    
    def _get_service_root(self, query_params: Optional[Dict]) -> Tuple[int, Dict, Any]:
        """Return service root resource"""
        body = {
            "@odata.type": "#MyService.v1_0_0.MyService",
            "@odata.id": "/redfish/v1/MyService",
            "Id": "MyService",
            "Name": "My Custom Service",
            "Description": "Custom service provided by plugin",
            "ServiceEnabled": True,
            "Status": {
                "State": "Enabled",
                "Health": "OK"
            },
            "Actions": {
                "#MyService.DoSomething": {
                    "target": "/redfish/v1/MyService/Actions/DoSomething"
                }
            }
        }
        
        headers = {"Content-Type": "application/json"}
        return 200, headers, body
    
    def _get_oem_resource(self, path: str, query_params: Optional[Dict]) -> Tuple[int, Dict, Any]:
        """Return OEM resource"""
        body = {
            "MyVendor": {
                "@odata.type": "#MyVendor.v1_0_0.MyVendor",
                "CustomProperty": "CustomValue",
                "Status": "Active"
            }
        }
        
        return 200, {}, body
```

Create `src/plugins/my_plugin/handlers/post_handler.py`:

```python
"""POST request handler"""
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class MyPostHandler:
    """Handles POST requests for the plugin"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def handle(
        self,
        path: str,
        data: Dict[str, Any],
        cached_links: Optional[Dict] = None
    ) -> Tuple[int, Dict, Any]:
        """
        Route POST requests to action handlers
        
        Args:
            path: Request path
            data: Request body (parsed JSON)
            cached_links: Server's cached links
        
        Returns:
            (status_code, headers, body)
        """
        # Route to action handlers
        if "/Actions/DoSomething" in path:
            return self._do_something_action(data)
        
        else:
            return 404, {}, {"error": "Action not found"}
    
    def _do_something_action(self, data: Dict[str, Any]) -> Tuple[int, Dict, Any]:
        """Handle DoSomething action"""
        logger.info(f"Executing DoSomething action with data: {data}")
        
        # Validate input
        if "Parameter" not in data:
            return 400, {}, {
                "error": {
                    "@Message.ExtendedInfo": [{
                        "MessageId": "Base.1.0.ActionParameterMissing",
                        "Message": "Required parameter 'Parameter' is missing"
                    }]
                }
            }
        
        # Perform action
        result = self._process_action(data["Parameter"])
        
        # Return success
        return 200, {}, {
            "Success": True,
            "Result": result,
            "Message": "Action completed successfully"
        }
    
    def _process_action(self, parameter: Any) -> Any:
        """Business logic for action"""
        # Implement your action logic here
        return f"Processed: {parameter}"
```

### Step 5: Export Plugin

Create `src/plugins/my_plugin/__init__.py`:

```python
"""
My Plugin Package

Custom functionality for BMC Simulator
"""
from .provider import MyPluginHandler
from .plugin import (
    PLUGIN_NAME,
    PLUGIN_VERSION,
    PLUGIN_DESCRIPTION,
    PLUGIN_PATHS,
    PLUGIN_CONFIG_DEFAULTS
)

__all__ = [
    'MyPluginHandler',
    'PLUGIN_NAME',
    'PLUGIN_VERSION',
    'PLUGIN_DESCRIPTION',
    'PLUGIN_PATHS',
    'PLUGIN_CONFIG_DEFAULTS'
]
```

### Step 6: Register Plugin in Loader

Edit `src/plugins/loader.py` to add your plugin:

```python
# Registry of available plugins
AVAILABLE_PLUGINS = {
    'ras': 'src.plugins.ras',
    'telemetry': 'src.plugins.telemetry',
    'my_plugin': 'src.plugins.my_plugin',  # Add your plugin here
}
```

### Step 7: Enable Plugin in Configuration

Create or edit your platform configuration to enable the plugin:

```python
# In server configuration or platform detection
config.extensions = ['ras', 'telemetry', 'my_plugin']
```

Or enable in base handler:

```python
# In src/handlers/base_handler.py
extensions = getattr(server.config, 'extensions', None) or ['ras', 'telemetry', 'my_plugin']
```

---

## Plugin Interfaces

### Handler Interface

All plugin handlers should implement:

```python
class PluginHandler:
    def __init__(self, config: Dict[str, Any]):
        """Initialize with config"""
        pass
    
    def get_supported_paths(self) -> List[str]:
        """Return list of path patterns"""
        return []
    
    def handle_get(self, path: str, query_params: Dict = None, 
                   cached_links: Dict = None) -> Tuple[int, Dict, Any]:
        """Handle GET requests"""
        return 404, {}, {"error": "Not implemented"}
    
    def handle_post(self, path: str, data: Dict, 
                    cached_links: Dict = None) -> Tuple[int, Dict, Any]:
        """Handle POST requests"""
        return 404, {}, {"error": "Not implemented"}
    
    def handle_patch(self, path: str, data: Dict,
                     cached_links: Dict = None) -> Tuple[int, Dict, Any]:
        """Handle PATCH requests"""
        return 404, {}, {"error": "Not implemented"}
    
    def handle_delete(self, path: str,
                      cached_links: Dict = None) -> Tuple[int, Dict, Any]:
        """Handle DELETE requests"""
        return 404, {}, {"error": "Not implemented"}
```

### Path Matching

Plugins declare supported paths using patterns:

- **Exact match**: `/redfish/v1/MyService`
- **Wildcard**: `/redfish/v1/MyService/*` (matches any direct child)
- **Multi-level**: `/redfish/v1/MyService/**` (matches any descendant)
- **Parameter**: `/redfish/v1/Managers/{manager_id}/Oem/MyVendor` (use `*` in practice)

The loader checks paths in order of specificity.

---

## Plugin Loader System

### How Plugins are Loaded

1. **Discovery**: Loader reads `AVAILABLE_PLUGINS` registry
2. **Import**: Dynamic import of plugin module
3. **Instantiation**: Creates handler instance with config
4. **Registration**: Stores handler with supported paths
5. **Routing**: Routes requests to matching plugin

### Plugin Lifecycle

```python
from src.plugins import PluginLoader

# 1. Create loader with config
loader = PluginLoader(config={'mockup_dir': 'mockups/custom'})

# 2. Load specific plugins
loader.load_plugin('my_plugin')

# 3. Check if plugin is loaded
plugin_info = loader.get_plugin('my_plugin')
print(f"Enabled: {plugin_info.enabled}")

# 4. Route requests
plugin = loader.get_plugin_for_path('/redfish/v1/MyService')
if plugin:
    status, headers, body = plugin.handler.handle_get(path)

# 5. Reload plugin (after code changes)
loader.reload_plugin('my_plugin')
```

### Plugin Information

```python
class PluginInfo:
    name: str              # Plugin name
    handler: Any           # Handler instance
    enabled: bool          # Enabled status
    paths: List[str]       # Supported paths
    config: Dict[str, Any] # Configuration
```

---

## Handler Integration

### Integration with Platform Server

The platform server automatically routes requests through plugins:

```python
# In servers/redfishMockupServer_platform.py
class RedfishHandler(BaseHandler):
    def do_GET(self):
        # Check if plugin handles this path
        plugin = self.plugin_loader.get_plugin_for_path(self.path)
        
        if plugin and plugin.enabled:
            # Route to plugin
            status, headers, body = plugin.handler.handle_get(
                self.path,
                query_params=self.query_params,
                cached_links=self.cached_links
            )
            
            # Send response
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
            return
        
        # Fall through to mockup handling
        super().do_GET()
```

### Adding Plugin to BaseHandler

Plugins are automatically loaded in `src/handlers/base_handler.py`:

```python
class BaseHandler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        # Initialize plugin loader
        self.plugin_loader = PluginLoader(server.config)
        
        # Load configured plugins
        extensions = getattr(server.config, 'extensions', None) or ['ras', 'telemetry']
        for plugin_name in extensions:
            self.plugin_loader.load_plugin(plugin_name)
```

---

## Best Practices

### 1. Keep Plugin Self-Contained

✅ **Good**: All plugin code in `src/plugins/my_plugin/`
❌ **Bad**: Plugin code scattered across `src/handlers/`, `src/services/`, etc.

### 2. Use Configuration

```python
# Plugin should be configurable
config = {
    "enabled": True,
    "log_level": "DEBUG",
    "storage_path": "/var/lib/my_plugin",
    "custom_setting": "value"
}
handler = MyPluginHandler(config)
```

### 3. Handle Errors Gracefully

```python
def handle_get(self, path, query_params=None, cached_links=None):
    try:
        # Plugin logic
        result = self._process_request(path)
        return 200, {}, result
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 400, {}, {"error": str(e)}
    except Exception as e:
        logger.exception(f"Internal error: {e}")
        return 500, {}, {"error": "Internal server error"}
```

### 4. Use Logging

```python
import logging
logger = logging.getLogger(__name__)

class MyPluginHandler:
    def __init__(self, config):
        logger.info("Initializing My Plugin")
        self.config = config
    
    def handle_get(self, path, query_params=None, cached_links=None):
        logger.debug(f"Handling GET {path}")
        # ...
```

### 5. Validate Input

```python
def _validate_action_data(self, data: Dict) -> Tuple[bool, str]:
    """Validate action input"""
    required_fields = ["Parameter1", "Parameter2"]
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    if not isinstance(data["Parameter1"], str):
        return False, "Parameter1 must be a string"
    
    return True, ""

def handle_post(self, path, data, cached_links=None):
    valid, error = self._validate_action_data(data)
    if not valid:
        return 400, {}, {"error": error}
    
    # Process valid data
    return 200, {}, {"success": True}
```

### 6. Document Your Plugin

Create a README.md in your plugin directory:

```markdown
# My Plugin

## Overview
Description of what this plugin does

## Configuration
- `enabled`: Enable/disable plugin
- `storage_path`: Path to store plugin data

## Endpoints
- `GET /redfish/v1/MyService` - Service root
- `POST /redfish/v1/MyService/Actions/DoSomething` - Perform action

## Usage
\`\`\`bash
python servers/redfishMockupServer_platform.py -D mockups/custom
\`\`\`
```

### 7. Write Tests

```python
# tests/test_my_plugin.py
import pytest
from src.plugins.my_plugin.provider import MyPluginHandler

def test_plugin_initialization():
    config = {"enabled": True}
    handler = MyPluginHandler(config)
    assert handler.enabled == True

def test_get_service_root():
    handler = MyPluginHandler({})
    status, headers, body = handler.handle_get("/redfish/v1/MyService")
    
    assert status == 200
    assert body["Id"] == "MyService"
    assert body["ServiceEnabled"] == True
```

---

## Testing Plugins

### Manual Testing

1. **Start server with plugin enabled**:
```bash
python3 servers/redfishMockupServer_platform.py -D mockups/custom -p 8000
```

2. **Test GET requests**:
```bash
curl http://localhost:8000/redfish/v1/MyService | python3 -m json.tool
```

3. **Test POST actions**:
```bash
curl -X POST http://localhost:8000/redfish/v1/MyService/Actions/DoSomething \
  -H "Content-Type: application/json" \
  -d '{"Parameter": "test"}' \
  | python3 -m json.tool
```

### Automated Testing

Create tests in `tests/test_my_plugin.py`:

```python
import pytest
import requests
import json

@pytest.fixture
def server_url():
    return "http://localhost:8000"

def test_my_service_root(server_url):
    response = requests.get(f"{server_url}/redfish/v1/MyService")
    assert response.status_code == 200
    
    data = response.json()
    assert data["@odata.type"] == "#MyService.v1_0_0.MyService"
    assert data["ServiceEnabled"] == True

def test_my_action(server_url):
    payload = {"Parameter": "test_value"}
    response = requests.post(
        f"{server_url}/redfish/v1/MyService/Actions/DoSomething",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["Success"] == True
```

Run tests:
```bash
pytest tests/test_my_plugin.py -v
```

---

## Examples

### Example 1: Simple Status Plugin

```python
# src/plugins/status/provider.py
class StatusPluginHandler:
    def __init__(self, config):
        self.config = config
        self.enabled = True
    
    def get_supported_paths(self):
        return ["/redfish/v1/Status"]
    
    def handle_get(self, path, query_params=None, cached_links=None):
        if path == "/redfish/v1/Status":
            return 200, {}, {
                "@odata.type": "#Status.v1_0_0.Status",
                "@odata.id": "/redfish/v1/Status",
                "Id": "Status",
                "Name": "System Status",
                "Overall": "OK",
                "Components": {
                    "Processor": "OK",
                    "Memory": "OK",
                    "Storage": "OK"
                }
            }
        
        return 404, {}, {"error": "Not found"}
```

### Example 2: OEM Extension Plugin

```python
# src/plugins/vendor_oem/provider.py
class VendorOemHandler:
    def __init__(self, config):
        self.config = config
        self.vendor_name = "Acme"
    
    def get_supported_paths(self):
        return ["/redfish/v1/Systems/*/Oem/Acme/*"]
    
    def handle_get(self, path, query_params=None, cached_links=None):
        # Inject OEM data into System resource
        if "/Oem/Acme" in path:
            return 200, {}, {
                "Acme": {
                    "@odata.type": "#Acme.v1_0_0.Acme",
                    "FirmwareVersion": "1.2.3",
                    "CustomSettings": {
                        "Setting1": "Value1",
                        "Setting2": "Value2"
                    }
                }
            }
        
        return 404, {}, {}
```

### Example 3: Action Handler Plugin

```python
# src/plugins/custom_actions/provider.py
import logging

logger = logging.getLogger(__name__)

class CustomActionsHandler:
    def __init__(self, config):
        self.config = config
        self.action_count = 0
    
    def get_supported_paths(self):
        return ["/redfish/v1/CustomActions/*"]
    
    def handle_post(self, path, data, cached_links=None):
        if "/Actions/Reset" in path:
            return self._reset_action(data)
        elif "/Actions/Backup" in path:
            return self._backup_action(data)
        else:
            return 404, {}, {"error": "Action not found"}
    
    def _reset_action(self, data):
        logger.info(f"Executing Reset action")
        
        reset_type = data.get("ResetType", "GracefulRestart")
        
        # Simulate reset
        self.action_count += 1
        
        return 202, {}, {
            "@Message.ExtendedInfo": [{
                "MessageId": "Base.1.0.Success",
                "Message": f"Reset action submitted ({reset_type})"
            }]
        }
    
    def _backup_action(self, data):
        logger.info(f"Executing Backup action")
        
        backup_target = data.get("Target", "/mnt/backup")
        
        # Simulate backup
        return 200, {}, {
            "Success": True,
            "BackupLocation": backup_target,
            "Timestamp": "2026-01-23T10:30:00Z"
        }
```

---

## Additional Resources

- **RAS Plugin**: See [docs/RAS_PLUGIN.md](RAS_PLUGIN.md) for complete RAS plugin documentation
- **Platform Architecture**: See [docs/specs/PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md)
- **Plugin Loader**: See [src/plugins/loader.py](../src/plugins/loader.py)
- **Base Handler**: See [src/handlers/base_handler.py](../src/handlers/base_handler.py)

---

## Summary

Creating a plugin involves:

1. ✅ Create plugin directory structure
2. ✅ Define plugin metadata (plugin.py)
3. ✅ Implement plugin handler (provider.py)
4. ✅ Implement request handlers (handlers/)
5. ✅ Export plugin (__init__.py)
6. ✅ Register in loader (loader.py)
7. ✅ Enable in configuration
8. ✅ Test plugin functionality

Plugins keep the base server clean while extending functionality!
