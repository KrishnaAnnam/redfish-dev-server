# BMC Redfish Simulator Documentation Index

**Project**: BMC Redfish Simulator  
**Version**: 3.0 (Platform Architecture + Plugin System)  
**Last Updated**: January 23, 2026

## 📚 Documentation Overview

This directory contains comprehensive documentation for the BMC Redfish Simulator project, including platform architecture, plugin development, and specific plugin implementations.

---

## 🗂️ Documentation Structure

### Core Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [README.md](README.md) | Project overview and quick start | Everyone |
| [PROJECT_INFO.md](PROJECT_INFO.md) | Project structure and organization | Developers |

### Architecture & Design

| Document | Description | Audience |
|----------|-------------|----------|
| [PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md) | Platform architecture overview | Architects, Developers |
| [PLATFORM_DEVELOPMENT.md](specs/PLATFORM_DEVELOPMENT.md) | Creating custom platforms | Platform Developers |
| **[PLUGIN_SDK.md](PLUGIN_SDK.md)** | **Plugin development guide** | **Plugin Developers** |

### Plugin Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| **[RAS_PLUGIN.md](RAS_PLUGIN.md)** | **RAS plugin complete documentation** | **RAS Users, Developers** |

### Feature Guides

| Document | Description | Audience |
|----------|-------------|----------|
| [ACTION_HANDLERS.md](ACTION_HANDLERS.md) | Implementing Redfish actions | Developers |
| [LOGENTRY_SERVICE.md](LOGENTRY_SERVICE.md) | LogEntry and LogService implementation | Developers |
| [SCHEMA_VALIDATION_GUIDE.md](specs/SCHEMA_VALIDATION_GUIDE.md) | JSON schema validation | Developers |

### User Guides

| Document | Description | Audience |
|----------|-------------|----------|
| [QUICK_START.md](guides/QUICK_START.md) | Getting started guide | New Users |
| [DEVELOPERS_GUIDE.md](guides/DEVELOPERS_GUIDE.md) | Development workflow | Developers |
| [MIGRATION_GUIDE.md](guides/MIGRATION_GUIDE.md) | Migrating from older versions | Existing Users |

---

## 🚀 Quick Start Paths

### I want to...

#### Use the Simulator

1. Read [QUICK_START.md](guides/QUICK_START.md)
2. Start with basic mockup:
   ```bash
   python3 servers/redfishMockupServer_platform.py -D mockups/public-rackmount1
   ```

#### Use the RAS Plugin

1. Read [RAS_PLUGIN.md](RAS_PLUGIN.md)
2. Run the demo:
   ```bash
   ./scripts/run_ras_demo.sh
   ```
3. Study [examples/ras_api_demo/ras_api_plugin_demo.py](../examples/ras_api_demo/ras_api_plugin_demo.py)

#### Create a New Plugin

1. Read [PLUGIN_SDK.md](PLUGIN_SDK.md) - **Start here!**
2. Follow the step-by-step guide
3. Reference [src/plugins/ras/](../src/plugins/ras/) as example
4. Test with [tests/test_my_plugin.py](../tests/)

#### Develop a Custom Platform

1. Read [PLATFORM_DEVELOPMENT.md](specs/PLATFORM_DEVELOPMENT.md)
2. Study [PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md)
3. Create platform provider in [src/plugins/](../src/plugins/)

#### Implement Custom Actions

1. Read [ACTION_HANDLERS.md](ACTION_HANDLERS.md)
2. See action examples in [src/handlers/](../src/handlers/)
3. Add action to plugin or platform

#### Understand the Codebase

1. Read [PROJECT_INFO.md](PROJECT_INFO.md)
2. Review [DEVELOPERS_GUIDE.md](guides/DEVELOPERS_GUIDE.md)
3. Explore [src/](../src/) directory structure

---

## 📖 Documentation by Topic

### Plugin System

- **[PLUGIN_SDK.md](PLUGIN_SDK.md)** - Complete plugin development guide
  - Plugin architecture
  - Creating plugins step-by-step
  - Handler interfaces
  - Plugin loader system
  - Best practices
  - Testing plugins
  - Examples

- **[RAS_PLUGIN.md](RAS_PLUGIN.md)** - RAS plugin complete reference
  - Overview and features
  - Architecture and components
  - 7 implementation phases
  - CPAD/CPER workflows
  - Policy engine
  - Event system
  - API reference
  - Configuration
  - Integration guide
  - Demos and examples
  - Troubleshooting

### Platform Architecture

- **Platform Architecture** ([PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md))
  - Core framework components
  - Platform implementations
  - Service extensibility
  - Creating new platforms

- **Platform Development** ([PLATFORM_DEVELOPMENT.md](specs/PLATFORM_DEVELOPMENT.md))
  - Step-by-step development
  - Platform providers
  - Platform services
  - Platform handlers
  - Testing platforms

### Features

- **Action Handlers** ([ACTION_HANDLERS.md](ACTION_HANDLERS.md))
  - Implementing POST actions
  - Action validation
  - Response formatting
  - Action discovery

- **LogEntry Service** ([LOGENTRY_SERVICE.md](LOGENTRY_SERVICE.md))
  - LogService implementation
  - LogEntry resources
  - Storage mechanisms
  - Query capabilities

- **Schema Validation** ([SCHEMA_VALIDATION_GUIDE.md](specs/SCHEMA_VALIDATION_GUIDE.md))
  - JSON schema validation
  - Schema registry
  - Custom schemas
  - Validation workflows

### Development

- **Developers Guide** ([DEVELOPERS_GUIDE.md](guides/DEVELOPERS_GUIDE.md))
  - Development setup
  - Coding standards
  - Testing approach
  - Contribution workflow

- **Quick Start** ([QUICK_START.md](guides/QUICK_START.md))
  - Installation
  - Basic usage
  - Common scenarios
  - Next steps

- **Migration Guide** ([MIGRATION_GUIDE.md](guides/MIGRATION_GUIDE.md))
  - Version changes
  - Breaking changes
  - Migration steps
  - Compatibility notes

---

## 🎯 Documentation Highlights

### NEW: Plugin SDK (January 2026)

The **Plugin SDK** provides a complete framework for extending the BMC Redfish Simulator:

- ✅ **Self-contained plugins** - No contamination of base server code
- ✅ **Dynamic loading** - Load plugins based on platform configuration
- ✅ **Clean interfaces** - Well-defined handler interfaces
- ✅ **Path routing** - Automatic request routing to plugins
- ✅ **Examples** - RAS plugin as complete reference implementation

**Start here**: [PLUGIN_SDK.md](PLUGIN_SDK.md)

### RAS Plugin - Feature Complete

The **RAS Plugin** provides production-ready CPAD/CPER capabilities:

- ✅ **7 implementation phases** completed
- ✅ **Feature parity** with RasAPI-main reference implementation
- ✅ **Template-based CPER** generation (matches RasAPI-main)
- ✅ **Policy engine** with trust-based validation
- ✅ **Event system** with Redfish event emission
- ✅ **Complete isolation** from base server

**Start here**: [RAS_PLUGIN.md](RAS_PLUGIN.md)

### Platform Architecture

The **Platform Architecture** enables vendor-specific customization:

- Platform providers for different hardware
- Extensible services with platform hooks
- Platform-specific handlers
- Configuration-driven platform detection

**Start here**: [PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md)

---

## 📝 Examples and Demos

### RAS Plugin Examples

| Example | Description | File |
|---------|-------------|------|
| **OCP RAS API Demo** | Complete CPAD/CPER workflow | [ras_api_demo/ras_api_plugin_demo.py](../examples/ras_api_demo/ras_api_plugin_demo.py) |
| **Event Listener** | HTTP server for Redfish events | [event_listener.py](../examples/event_listener.py) |
| **Event Subscription** | Create EventService subscription | [subscribe_to_events.py](../examples/subscribe_to_events.py) |
| **Tmux Demo** | All-in-one demo launcher | [run_ras_demo.sh](../scripts/run_ras_demo.sh) |
| **Memory Error CPAD** | Example CPAD document | [memErrorSpoofCpad.json](../examples/ras/memErrorSpoofCpad.json) |
| **SPPR CPAD** | SPPR action CPAD document | [SpprCpadExample.json](../examples/ras/SpprCpadExample.json) |

### Code Examples

See [examples/](../examples/) directory for:
- Action handler demos
- Schema validation demos
- LogEntry demos
- Platform configuration examples

---

## 🔧 Developer Resources

### Source Code Structure

```
bmc-redfish-simulator/
├── docs/                          # THIS DIRECTORY
│   ├── PLUGIN_SDK.md             # Plugin development guide (NEW)
│   ├── RAS_PLUGIN.md             # RAS plugin documentation (NEW)
│   ├── specs/                    # Architecture specifications
│   └── guides/                   # User and developer guides
│
├── src/                          # Source code
│   ├── plugins/                  # Plugin system (NEW)
│   │   ├── __init__.py           # Plugin exports
│   │   ├── loader.py             # Plugin loader
│   │   ├── ras/                  # RAS plugin (6,300+ lines)
│   │   └── telemetry/            # Telemetry plugin
│   │
│   ├── core/                     # Core framework
│   │   ├── interfaces.py         # Platform interfaces
│   │   ├── registry.py           # Platform registry
│   │   ├── discovery.py          # Plugin discovery
│   │   └── platform_config.py    # Configuration
│   │
│   ├── handlers/                 # HTTP handlers
│   │   ├── base_handler.py       # Base handler with plugin support
│   │   ├── get_handler.py        # GET request handling
│   │   └── post_handler.py       # POST request handling
│   │
│   ├── services/                 # Core services
│   └── models/                   # Data models
│
├── servers/                      # Server implementations
│   └── redfishMockupServer_platform.py  # Platform server
│
├── examples/                     # Examples and demos
├── tests/                        # Test suite
└── mockups/                      # Mockup data
```

### Key Interfaces

```python
# Plugin Handler Interface
class PluginHandler:
    def __init__(self, config: Dict[str, Any])
    def get_supported_paths(self) -> List[str]
    def handle_get(self, path, query_params, cached_links) -> Tuple[int, Dict, Any]
    def handle_post(self, path, data, cached_links) -> Tuple[int, Dict, Any]

# Plugin Loader
from src.plugins import PluginLoader
loader = PluginLoader(config)
loader.load_plugin('my_plugin')
plugin = loader.get_plugin_for_path('/redfish/v1/MyService')
```

---

## 🧪 Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# Plugin tests
pytest tests/test_my_plugin.py -v

# RAS plugin tests
pytest tests/test_ras_plugin.py -v

# Integration tests
pytest tests/test_platform_server.py -v
```

### Manual Testing

```bash
# Start server
python3 servers/redfishMockupServer_platform.py -D mockups/ras_gen1

# Test plugin endpoints
curl -u demo:demo http://localhost:8000/redfish/v1/Oem/OCPRASAPIWS/RASService

# Submit CPAD
curl -u demo:demo -X POST http://localhost:8000/redfish/v1/Oem/OCPRASAPIWS/RASService/Actions/RASService.SubmitCPAD \
  -H "Content-Type: application/json" \
  -d @examples/ras/memErrorSpoofCpad.json
```

---

## 📞 Support and Contributions

### Getting Help

1. Check relevant documentation above
2. Review [examples/](../examples/) for code samples
3. Search [issues](https://github.com/your-org/bmc-redfish-simulator/issues)
4. Ask in [discussions](https://github.com/your-org/bmc-redfish-simulator/discussions)

### Contributing

1. Read [DEVELOPERS_GUIDE.md](guides/DEVELOPERS_GUIDE.md)
2. Follow coding standards
3. Write tests for new features
4. Submit pull requests
5. Update documentation

### Documentation Updates

When making changes:
- Update relevant .md files
- Add examples for new features
- Update this index if adding new docs
- Keep API references current

---

## 📅 Version History

### Version 3.0 (January 2026) - Plugin System

- ✅ Complete plugin architecture
- ✅ RAS plugin (7 phases, 6,300+ lines)
- ✅ Plugin SDK documentation
- ✅ RAS plugin documentation
- ✅ Feature parity with RasAPI-main
- ✅ Template-based CPER generation
- ✅ Event system
- ✅ Complete isolation verification

### Version 2.0 - Platform Architecture

- Platform provider system
- Extensible services
- Configuration-driven detection
- OEM action framework

### Version 1.0 - Base Server

- DMTF Redfish Mockup Server foundation
- Basic GET/POST handling
- Mockup file serving
- Simple extensions

---

## 🎓 Learning Path

### Beginner

1. [QUICK_START.md](guides/QUICK_START.md) - Get started
2. [README.md](README.md) - Understand the project
3. Run demos in [examples/](../examples/)

### Intermediate

1. [DEVELOPERS_GUIDE.md](guides/DEVELOPERS_GUIDE.md) - Development basics
2. [PLUGIN_SDK.md](PLUGIN_SDK.md) - Create simple plugin
3. [ACTION_HANDLERS.md](ACTION_HANDLERS.md) - Add custom actions

### Advanced

1. [RAS_PLUGIN.md](RAS_PLUGIN.md) - Study complete plugin
2. [PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md) - Understand architecture
3. [PLATFORM_DEVELOPMENT.md](specs/PLATFORM_DEVELOPMENT.md) - Build custom platform
4. Contribute to core framework

---

## 📚 External References

- **DMTF Redfish**: https://www.dmtf.org/standards/redfish
- **Redfish Schema**: https://redfish.dmtf.org/schemas/
- **UEFI Specification**: https://uefi.org/specifications
- **OCP**: https://www.opencompute.org/
- **Python asyncio**: https://docs.python.org/3/library/asyncio.html

---

## ✨ Quick Links

| Topic | Document | Description |
|-------|----------|-------------|
| 🚀 **Start Here** | [PLUGIN_SDK.md](PLUGIN_SDK.md) | Plugin development guide |
| 🔧 **RAS Plugin** | [RAS_PLUGIN.md](RAS_PLUGIN.md) | Complete RAS documentation |
| 🏗️ **Architecture** | [PLATFORM_ARCHITECTURE.md](specs/PLATFORM_ARCHITECTURE.md) | System architecture |
| 👨‍💻 **Development** | [DEVELOPERS_GUIDE.md](guides/DEVELOPERS_GUIDE.md) | Developer workflow |
| 📖 **Quick Start** | [QUICK_START.md](guides/QUICK_START.md) | Getting started |

---

**Last Updated**: January 23, 2026  
**Maintained by**: BMC Redfish Simulator Contributors

For the latest documentation, visit: [docs/](.)
