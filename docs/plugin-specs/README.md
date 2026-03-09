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
from src.plugins import get_plugin_loader

loader = get_plugin_loader(config)
loader.load_plugins(['ras', 'telemetry'])

# Check if a plugin handles a path
plugin = loader.get_plugin_for_path('/redfish/v1/RASService')
if plugin:
    status, headers, body = plugin.handle_get(path)
```

Or via platform configuration:

```yaml
platform:
  name: "My Server"
  extensions:
    - ras
    - telemetry
```
