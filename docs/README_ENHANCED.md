# BMC Redfish Simulator - Enhanced Version

**Project:** bmc-redfish-simulator  
**Based on:** DMTF Redfish-Mockup-Server  
**Version:** 2.0

A sophisticated, modular, and platform-aware Redfish BMC simulator with vendor-specific extensions and plugin architecture.

## Overview

This enhanced BMC simulator is built upon the DMTF Redfish-Mockup-Server foundation, providing a modern, extensible architecture that separates common Redfish functionality from vendor-specific implementations. It enables building realistic BMC simulators for different hardware platforms.

## Key Features

### 🏗️ **Modular Architecture**
- Clean separation of handlers, services, and utilities
- Maintainable codebase with improved organization
- Enhanced logging and error handling
- Better performance and reliability

### 🔌 **Extension Systems**
- Automatic platform detection from mockup data
- Convention-loaded feature plugins (Telemetry and custom plugins)
- Explicit method-aware route ownership
- Registry system for dynamic platform discovery

### 🚀 **Enhanced Services**
- Extensible EventService with platform hooks
- Advanced TelemetryService with custom metrics
- Platform-aware service coordination
- Enhanced authentication and session management

### 🛠️ **Developer Experience**
- Comprehensive documentation and guides
- Example platform implementations
- Configuration templates and examples
- Migration tools and compatibility testing

## Quick Start

### Basic Usage (Drop-in Replacement)

```bash
# Original server
python redfishMockupServer.py -D public-rackmount1

# Enhanced modular server (identical functionality)
python redfishMockupServer_modular.py -D public-rackmount1

# Platform-aware server (automatic platform detection)
python redfishMockupServer_platform.py -D public-rackmount1
```

### Platform-Specific Usage

```bash
# Auto-detect and use platform-specific features
python redfishMockupServer_platform.py -D custom-mockup/

# Explicitly specify platform
python redfishMockupServer_platform.py --platform custom -D custom-mockup/

# List available platforms
python redfishMockupServer_platform.py --list-platforms

# Show platform detection info
python redfishMockupServer_platform.py --platform-info -D mockup/
```

## Server Variants

| Server | Use Case | Features |
|--------|----------|----------|
| `redfishMockupServer.py` | Original compatibility | Basic Redfish simulation |
| `redfishMockupServer_modular.py` | Improved maintenance | Modular code, enhanced logging |
| `redfishMockupServer_platform.py` | Advanced simulation | Platform detection, OEM extensions |

## Architecture

### Core Framework (`src/core/`)
- **Interfaces**: Abstract base classes for platform providers, services, and handlers
- **Registry**: Platform provider registration and discovery system
- **Services**: Extensible core services with platform hooks
- **Configuration**: Platform configuration and detection system

### Domain Plugins (`src/plugins/`)
- **Telemetry**: Current reference feature plugin
- **Contracts**: Shared route and context interfaces
- **Custom**: Additional feature packages loaded by convention

### Enhanced Components (`src/`)
- **Handlers**: Modular HTTP request handlers
- **Services**: Core Redfish services (EventService, SessionService, etc.)
- **Utils**: Shared utilities and helper functions
- **Config**: Configuration management and validation

## Platform and Plugin Support

### Supported Platforms
- **Generic**: Basic Redfish without vendor extensions
- **Custom**: Extensible framework for new platforms

### Feature Plugins
- **Telemetry**: Current reference feature plugin
- **Custom packages**: Convention-loaded from `src.plugins.<name>`

### Platform Detection
The server automatically detects platforms using:
- OEM namespaces in mockup data
- Service root analysis
- Platform manifest files
- System/Manager/Chassis information

## Configuration

### Platform Manifest (Auto-Detection)
```json
{
    "platform_id": "custom",
    "platform_type": "custom",
    "display_name": "Custom BMC Platform",
    "enabled_services": ["EventService", "UpdateService"],
    "extensions": ["telemetry"]
}
```

### Platform Configuration (Advanced)
```json
{
    "platform_id": "custom",
    "system_info": {
        "Manufacturer": "Custom Inc.",
        "Model": "Server S100",
        "SerialNumber": "ABC123"
    },
    "extensions": [
        {
            "name": "telemetry",
            "enabled": true,
            "config": {}
        }
    ],
    "oem_actions": ["Custom.ExportSystemConfiguration"],
    "service_settings": {
        "EventService": {
            "max_subscriptions": 10,
            "supported_protocols": ["Redfish"]
        }
    }
}
```

## Development

### Creating Feature Plugins

Create a package under `src/plugins/`, export `get_plugin()`, and declare
method-aware routes with `PluginRoute`. Feature plugins do not require edits to
common handlers or server entry points.

See [Plugin SDK](PLUGIN_SDK.md) for the complete contract and conformance
requirements.

### Testing
```bash
# Test platform detection
python redfishMockupServer_platform.py --platform-info -D mockup/

# Test with verbose logging
python redfishMockupServer_platform.py -D mockup/ -v

# Run compatibility tests
python scripts/test_migration.py mockup/
```

## Documentation

### User Guides
- **[Quick Start Guide](guides/QUICK_START.md)**: Get up and running quickly
- **[Migration Guide](guides/MIGRATION_GUIDE.md)**: Migrate from original server
- **[Platform Architecture](specs/PLATFORM_ARCHITECTURE.md)**: Understanding the architecture

### Developer Documentation  
- **[Platform Development Guide](specs/PLATFORM_DEVELOPMENT.md)**: Create custom platforms
- **[Plugin SDK](PLUGIN_SDK.md)**: Create feature plugins

### Examples
- **[Platform Example](../platforms/example/)**: Platform provider implementation
- **[Telemetry Plugin](../src/plugins/telemetry/)**: Feature plugin implementation
- **[Integration Examples](../examples/)**: Using with client libraries

## Migration from Original Server

The enhanced server is fully backward compatible:

```bash
# Original command
python redfishMockupServer.py -D mockup/ -p 8000

# Drop-in replacement (modular)
python redfishMockupServer_modular.py -D mockup/ -p 8000

# Enhanced version (platform-aware)
python redfishMockupServer_platform.py -D mockup/ -p 8000
```

See [Migration Guide](MIGRATION_GUIDE.md) for detailed migration steps and compatibility testing.

## Requirements

- Python 3.10 or later
- Standard library only (no external dependencies for basic functionality)
- Optional: Additional packages for SSL, advanced authentication

## License

This project maintains the same license as the original Redfish Simulator Server.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Update documentation
5. Submit a pull request

### Areas for Contribution
- New domain plugins (Storage, Network, etc.)
- Enhanced OEM action implementations
- Additional service extensions
- Performance improvements
- Documentation and examples

## Acknowledgments

Based on the original Redfish Simulator Server from the DMTF Redfish project. Enhanced with modular architecture and platform-specific capabilities for realistic BMC simulation.

## Support

- **Documentation**: Comprehensive guides and API documentation
- **Examples**: Configuration templates and implementation examples
- **Community**: GitHub issues and discussions
- **Testing**: Migration compatibility and platform validation tools

---

**Transform your Redfish development workflow with enhanced simulation capabilities, vendor-specific features, and a modern, extensible architecture.**