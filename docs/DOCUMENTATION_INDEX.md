# BMC Redfish Simulator Documentation

**Last Updated:** October 2, 2026

## Start Here

| Document | Purpose |
|----------|---------|
| [Project README](../README.md) | Installation, server modes, and project overview |
| [Quick Start](guides/QUICK_START.md) | Basic server setup and first requests |
| [Developers Guide](guides/DEVELOPERS_GUIDE.md) | Repository structure and development workflow |
| [Plugin SDK](PLUGIN_SDK.md) | Implementing isolated Redfish feature plugins |

## Plugin Development

Telemetry and RAS are the current integrated feature plugins. Future feature
plugins should use the same common Plugin SDK contract and bring their own
source, configuration, mockup resources, schemas, registries, tests, and
demonstration assets.

| Document | Purpose |
|----------|---------|
| [Plugin SDK](PLUGIN_SDK.md) | Package convention, routes, responses, context, reset notification, and shutdown |
| [Plugin Specifications](plugin-specs/README.md) | Plugin specification organization and responsibilities |
| [Telemetry Plugin](plugin-specs/telemetry/README.md) | Current reference plugin behavior and configuration |
| [RAS Plugin](../src/plugins/ras/README.md) | OCP RAS API architecture, CPAD routing, and reset behavior |
| [RAS Endpoint Configuration](../src/plugins/ras/RAS_ENDPOINT_CONFIGURATION.md) | Endpoint identity, topology, memory inventory, and provider configuration |
| [OCP RAS API Demo](../examples/ras_api_demo/README.md) | Analyzer, policy, event listener, and end-to-end demonstration setup |

The Plugin SDK supports convention-based loading from
`src.plugins.<configured_name>`. A plugin exports `get_plugin()` and declares
GET, POST, PATCH, and DELETE ownership with `PluginRoute`. PUT is not part of
the SDK.

## Architecture

| Document | Purpose |
|----------|---------|
| [Platform Architecture](specs/PLATFORM_ARCHITECTURE.md) | Core framework, platform providers, and extension points |
| [Platform Development](specs/PLATFORM_DEVELOPMENT.md) | Creating platform-specific providers and handlers |
| [Enhanced Server](README_ENHANCED.md) | Enhanced response, logging, event, and plugin-aware server mode |
| [Modular Server](README_MODULAR.md) | Modular server organization and operation |
| [Project Information](PROJECT_INFO.md) | Project structure and maintained components |

Platform providers and feature plugins are separate extension mechanisms.
Platform providers model hardware-specific behavior. Feature plugins own
isolated Redfish domains and are loaded through the Plugin SDK.

## Redfish Features

| Document | Purpose |
|----------|---------|
| [Action Handlers](ACTION_HANDLERS.md) | Implementing and testing Redfish actions |
| [LogEntry Service](LOGENTRY_SERVICE.md) | LogService and LogEntry behavior |
| [RAS Plugin](../src/plugins/ras/README.md) | OCP RAS API discovery, CPAD submission, and CPER LogService behavior |
| [Schema Validation](specs/SCHEMA_VALIDATION_GUIDE.md) | Resource and property validation |

## Migration and Standalone Development

| Document | Purpose |
|----------|---------|
| [Migration Guide](guides/MIGRATION_GUIDE.md) | Moving from older server layouts |
| [Standalone Development](guides/STANDALONE_DEVELOPMENT.md) | Developing platform integrations independently |

## Plugin SDK Verification

Run the common Plugin SDK conformance tests:

```bash
python3 -m pytest \
  tests/test_plugin_configuration.py \
  tests/test_plugin_routing.py \
  tests/test_ras_plugin_sdk.py
```

The tests cover:

- authoritative configuration and convention-based imports
- malformed names and missing packages
- route validation, specificity, and conflicts
- GET, POST, PATCH, and DELETE dispatch
- unsupported-method 405 responses
- mockup fallthrough
- JSON, empty, and binary responses
- EventService publication
- successful reset notification
- deterministic shutdown
- modular, platform, and enhanced server integration
- RAS route, configuration, EventService, reset, and shutdown adaptation

## Current Plugin Boundary

Adding a feature plugin must not require feature-specific edits under:

```text
src/handlers/
src/services/
src/core/
src/plugins/loader.py
servers/
```

Feature-specific behavior belongs in the plugin package and its associated
configuration and assets.
