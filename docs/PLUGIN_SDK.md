# Plugin SDK Guide

**Version:** 2.0.0
**Last Updated:** October 2, 2026

The Plugin SDK adds dynamic Redfish behavior without adding feature-specific
branches to the simulator's handlers, services, loader, or server entry
points. A configured plugin owns its implementation, routes, state, workers,
and cleanup.

## Package Convention

Each plugin is a Python package under `src/plugins/`. The configured name is
also the package name:

```text
configured name: my_plugin
imported module: src.plugins.my_plugin
required export: get_plugin()
```

No central registration table is required. A minimal package is:

```text
src/plugins/my_plugin/
├── __init__.py
└── plugin.py
```

`src/plugins/my_plugin/__init__.py` must export `get_plugin()`:

```python
from .plugin import get_plugin

__all__ = ['get_plugin']
```

Plugin names must start with a letter and contain only letters, numbers, and
underscores.

## Configuration

Plugins are enabled only through the server or platform `extensions`
configuration. The legacy string form is supported:

```json
{
  "extensions": ["telemetry", "my_plugin"]
}
```

Use the structured form for plugin-owned configuration:

```json
{
  "extensions": [
    {
      "name": "my_plugin",
      "enabled": true,
      "config": {
        "storage_path": "/tmp/my_plugin"
      }
    }
  ]
}
```

Each name may appear once. Disabled entries are validated but not loaded.
An absent or empty `extensions` list loads no plugins.

## Plugin Contract

The loader calls `get_plugin()` and initializes the returned instance.
New plugins should accept the complete initialization signature:

```python
from src.plugins import PluginContext, PluginRoute


class MyPlugin:
    def initialize(
        self,
        server_config,
        plugin_config,
        context: PluginContext,
    ) -> bool:
        self.server_config = server_config
        self.config = dict(plugin_config)
        self.context = context
        return True

    def get_routes(self):
        return [
            PluginRoute('/redfish/v1/MyService', {'GET'}),
            PluginRoute(
                '/redfish/v1/MyService/Actions/MyService.Run',
                {'POST'},
            ),
            PluginRoute(
                '/redfish/v1/MyService/Entries/{EntryId}',
                {'GET', 'PATCH', 'DELETE'},
            ),
        ]

    def shutdown(self) -> bool:
        return True


_plugin = None


def get_plugin():
    global _plugin
    if _plugin is None:
        _plugin = MyPlugin()
    return _plugin
```

The loader also supports existing `initialize(server_config)` and
`initialize(server_config, plugin_config)` implementations. A one-argument
plugin cannot be configured with a non-empty plugin-specific `config`.

### Route Declarations

`PluginRoute` is authoritative for ownership and supported HTTP methods.
Supported methods are:

- `GET`
- `POST`
- `PATCH`
- `DELETE`

PUT is not part of the Plugin SDK.

Routes support exact segments, `*`, and named parameters such as
`{EntryId}`. Wildcards and parameters match one path segment. Fixed routes
are evaluated before less-specific parameterized routes. Trailing slashes
are normalized.

Every declared method requires the corresponding plugin handler:

```python
def handle_get(self, path, query_params, cached_links):
    return 200, {}, {'Id': 'MyService'}

def handle_post(self, path, data, cached_links):
    return 202, {'Location': f'{path}/result'}, {'Accepted': True}

def handle_patch(self, path, data, cached_links):
    return 204, {}, None

def handle_delete(self, path, cached_links):
    return 204, {}, None
```

An exact method-and-route conflict between configured plugins fails during
loading. If a plugin owns a path but does not declare the requested method,
the server returns 405. If no plugin owns the path, normal mockup and core
handling continues.

### Responses

Handlers return:

```text
(status_code, headers, body)
```

The common response adapter preserves plugin headers and supports JSON
objects, strings, bytes, and empty bodies. Bytes default to
`application/octet-stream` unless the plugin supplies another content type.

Exceptions escaping a plugin handler produce an explicit Redfish HTTP 500
response.

## Shared Capabilities

`PluginContext` deliberately exposes only narrow shared capabilities rather
than the simulator's internal service graph.

### Event Publication

Publish an event through the existing EventService:

```python
status = self.context.publish_event({
    'MessageId': 'MyRegistry.1.0.OperationComplete',
    'Message': 'The plugin operation completed.',
    'Severity': 'OK',
})
```

The plugin remains responsible for constructing a valid event payload and
for owning its schemas and message registries.

### Successful System Reset Notification

A plugin that has reset-deferred work may implement:

```python
def on_system_reset(self, system_id: str, reset_type: str):
    self.complete_pending_operations(system_id, reset_type)
```

The callback runs only after the core `ComputerSystem.Reset` action succeeds.
Callback failures are logged and do not reverse the completed reset.

This is a notification seam, not a general dependency-injection or lifecycle
framework.

## Lifecycle and Workers

Plugins own all workers, queues, files, and other resources they create.
Implement `shutdown()` to stop workers and release them deterministically:

```python
def shutdown(self) -> bool:
    self.queue_manager.stop()
    return True
```

The modular, platform, and enhanced server cleanup paths invoke plugin
shutdown. Implement cleanup so repeated calls are harmless.

Runtime hot reload is not supported. Restart the server after changing plugin
code or configuration.

## Static and Dynamic Resources

Declare only dynamic behavior in `get_routes()`. Static Redfish resources can
remain in the mockup tree and will be served by normal mockup handling when
no plugin route claims them.

Plugins should own all feature-specific assets, including:

- plugin source under `src/plugins/<name>/`
- configuration
- mockup resources and collection links
- schemas and registries
- tests, analyzers, and demonstration assets

Adding a plugin must not require feature-specific edits under
`src/handlers/`, `src/services/`, `src/core/`, `src/plugins/loader.py`, or
`servers/`.

## Request Flow

```text
HTTP handler
  -> method-aware PluginLoader dispatch
      -> matching configured plugin
          -> (status, headers, body)
  -> otherwise normal simulator handling
```

The standard and enhanced handlers use the same loader contract for GET,
POST, PATCH, and DELETE.

## Testing

At minimum, test:

1. The package loads by its configured name.
2. Every declared method reaches the plugin handler.
3. Unclaimed paths fall through to mockup handling.
4. Unsupported methods on owned paths return 405.
5. JSON, empty, and binary responses retain their status and headers.
6. Plugin exceptions return 500.
7. Event publication uses the existing EventService.
8. Successful reset notifications reach the loaded plugin instance.
9. Shutdown stops plugin-owned workers and is safe when repeated.
10. No common-code edit is required to install the plugin.

Run the Plugin SDK conformance tests with:

```bash
python3 -m pytest \
  tests/test_plugin_configuration.py \
  tests/test_plugin_routing.py
```

The Telemetry plugin under `src/plugins/telemetry/` is the reference
implementation for convention-based loading and explicit route ownership.
