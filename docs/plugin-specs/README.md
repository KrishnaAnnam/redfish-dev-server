# Plugin Specifications

This directory contains specifications for plugins that extend the BMC Simulator.

## Architecture

```
┌────────────────────────────────────────────────────┐
│            BMC Simulator (Core)                    │
│                                                    │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│   │ Event    │ │ Log      │ │ Platform │          │
│   │ Service  │ │ Service  │ │ Framework│   ...    │
│   └──────────┘ └──────────┘ └──────────┘          │
│                                                    │
│   ════════════ Plugin Interface ════════════      │
│                     ▲                              │
└─────────────────────┼──────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │Telemetry│   │ Future  │   │ Future  │
   │ Plugin  │   │ Plugin  │   │ Plugin  │
   └─────────┘   └─────────┘   └─────────┘
```

## Plugin Directory Structure

Each plugin has its own subdirectory containing:

```
plugin-specs/
├── README.md                 # This file
├── telemetry/                # Telemetry Plugin
│   └── README.md             # Plugin overview
└── <plugin-name>/            # Future plugins
```

## Available Plugins

| Plugin | Status | Description |
|--------|--------|-------------|
| [Telemetry](telemetry/) | Active | Metric collection, reporting, and streaming |
| Future feature plugins | Planned | Added through the common Plugin SDK contract |

## Plugin Contract

Plugins extend the simulator by:

1. **Registering endpoints** - Custom endpoints (standard or OEM)
2. **Providing message registries** - Domain-specific messages for events/logs
3. **Using core services** - EventService, LogService, TaskService
4. **Defining platform profiles** - Platform configs that enable the plugin

## Core vs Plugin Responsibility

| Responsibility | Core Simulator | Plugin |
|----------------|----------------|--------|
| Redfish compliance | ✓ | - |
| EventService/LogService | ✓ | Uses |
| Session/Auth | ✓ | - |
| Domain endpoints | Interface | Implementation |
| Domain logic | - | ✓ |
| Message registries | Standard (DMTF) | Custom (OEM) |

## Loading Plugins

Plugins are loaded via the plugin loader:

```python
from src.plugins import load_plugins_from_config

loader = load_plugins_from_config(config)

# Route a request to a configured plugin.
response = loader.handle_post(
    '/redfish/v1/TelemetryService/Actions/'
    'TelemetryService.SubmitTestMetricReport',
    data,
    cached_links,
)
if response is not None:
    status, headers, body = response
```

Or via platform configuration:

```json
{
  "extensions": [
    {
      "name": "telemetry",
      "enabled": true,
      "config": {
        "sample_rate": 30
      }
    }
  ]
}
```

String entries preserve the original configuration format. Structured
entries provide plugin-owned configuration and can be disabled explicitly.
The loader rejects malformed, duplicate, and unknown entries; no plugin is
loaded when `extensions` is absent or empty.

Plugins declare authoritative `PluginRoute` entries for GET, POST, PATCH, and
DELETE. A plugin-owned path returns 405 for an undeclared method. Unclaimed
paths continue through normal mockup and platform handling. PUT is not part of
the domain Plugin SDK.

See [../PLUGIN_SDK.md](../PLUGIN_SDK.md) for package conventions, lifecycle,
EventService publication, reset notification, shutdown, and conformance
requirements.
