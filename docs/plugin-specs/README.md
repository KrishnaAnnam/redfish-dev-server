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
   │   RAS   │   │Telemetry│   │ Future  │
   │ Plugin  │   │ Plugin  │   │ Plugin  │
   └─────────┘   └─────────┘   └─────────┘
```

## Plugin Directory Structure

Each plugin has its own subdirectory containing:

```
plugin-specs/
├── README.md                 # This file
├── ras/                      # RAS (Reliability, Availability, Serviceability) Plugin
│   ├── README.md             # Plugin overview
│   ├── OCPRAS_MESSAGE_REGISTRY.md  # Custom message registry
│   └── ...                   # Additional specs
├── telemetry/                # Telemetry Plugin
│   └── README.md             # Plugin overview
└── <plugin-name>/            # Future plugins
```

## Available Plugins

| Plugin | Status | Description |
|--------|--------|-------------|
| [RAS](ras/) | Active | CPER/CPAD handling, error injection, PPR/SPPR operations |
| [Telemetry](telemetry/) | Active | Metric collection, reporting, and streaming |

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
response = loader.handle_get('/redfish/v1/TelemetryService')
if response is not None:
    status, headers, body = response
```

Or via platform configuration:

```json
{
  "extensions": [
    "telemetry",
    {
      "name": "ras",
      "enabled": true,
      "config": {
        "endpoint_config": "ras_endpoint_config.json"
      }
    }
  ]
}
```

String entries preserve the original configuration format. Structured
entries provide plugin-owned configuration and can be disabled explicitly.
The loader rejects malformed, duplicate, and unknown entries; no plugin is
loaded when `extensions` is absent or empty.

The server currently routes GET and POST through the domain Plugin SDK.
Plugins may decline a method by omitting its handler, allowing normal mockup
handling to continue. PATCH, PUT, and DELETE are not currently part of this
routing path.
