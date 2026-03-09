# BMC Redfish Simulator - Documentation Wiki

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)
![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![Status](https://img.shields.io/badge/status-production--ready-brightgreen.svg)

**Comprehensive Redfish API Simulator Server for BMC Development and Testing**

[🏠 Home](#welcome) • [🚀 Quick Start](#quick-start) • [📚 Documentation](#documentation-index) • [💻 Development](#development-guides) • [🔧 APIs](#api-references)

</div>

---

## 📖 Welcome

Welcome to the **BMC Redfish Simulator** documentation hub! This wiki serves as the central navigation point for all documentation, guides, and references for the simulator.

The BMC Redfish Simulator is built upon the DMTF Redfish-Mockup-Server foundation and provides enhanced features for message handling, logging, event management, platform detection, and comprehensive client library support.

### What's New in v2.0.0

- ✅ **Modular Architecture** - Clean separation of concerns with `src/` structure
- ✅ **Enhanced Services** - Message, logging, and event management
- ✅ **Platform Detection** - Auto-detect and simulate various BMC platforms
- ✅ **Comprehensive Client Library** - Full-featured Python client with examples
- ✅ **Production Ready** - Streamlined codebase with legacy code removed

---

## 🚀 Quick Start

### New Users Start Here

| Document | Description | Time |
|----------|-------------|------|
| **[Quick Start Guide](QUICK_START.md)** | Get up and running in 5 minutes | ⏱️ 5 min |
| **[README](README.md)** | Project overview and basic usage | ⏱️ 10 min |
| **[Project Info](PROJECT_INFO.md)** | Project identity and attribution | ⏱️ 5 min |

### Quick Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run basic server
python3 redfishMockupServer_modular.py -D public-rackmount1 -S -p 8000

# Run with enhanced features
python3 redfishMockupServer_enhanced.py -D public-rackmount1 -S -p 8000

# Run with platform detection
python3 redfishMockupServer_platform.py -D public-rackmount1 -S -p 8000

# Access the API
curl http://localhost:8000/redfish/v1
```

---

## 📚 Documentation Index

### 📘 User Documentation

#### Getting Started
- **[Quick Start Guide](QUICK_START.md)** - Fast setup and first steps
- **[README](README.md)** - Main project documentation
- **[Project Info](PROJECT_INFO.md)** - About the project, attribution, and history
- **[Migration Guide](MIGRATION_GUIDE.md)** - Migrating from DMTF Redfish-Mockup-Server

#### Server Variants
- **[Modular Server Documentation](README_MODULAR.md)** - Clean modular architecture
- **[Enhanced Server Documentation](README_ENHANCED.md)** - Enhanced features (messages, logging, events)
- **[Platform Architecture](PLATFORM_ARCHITECTURE.md)** - Platform-aware server architecture
- **[Standalone Development](STANDALONE_DEVELOPMENT.md)** - Standalone platform simulator

#### Client Library
- **[Redfish Client Library](redfish_client/README.md)** - Python client library documentation
  - Client API reference
  - Usage examples
  - Monitoring tools
  - Command-line interface

### 🔧 Developer Documentation

#### Core Development
- **[Developers Guide](DEVELOPERS_GUIDE.md)** - Comprehensive development guide
  - Architecture overview
  - Code organization
  - Contributing guidelines
  - Testing strategies
  - Debugging techniques

#### Platform Development
- **[Platform Development Guide](PLATFORM_DEVELOPMENT.md)** - Creating platform plugins
  - Plugin architecture
  - Writing platform providers
  - Platform detection
  - Domain-specific plugins (RAS, Telemetry)

#### Advanced Topics
- **[Platform Architecture Deep Dive](PLATFORM_ARCHITECTURE.md)** - Technical architecture
  - Service manager design
  - Handler system
  - Plugin lifecycle
  - Extensibility patterns

### 📋 Reference Documentation

#### Project History & Changes
- **[Changelog](CHANGELOG.md)** - Version history and release notes
- **[Authors](AUTHORS.md)** - Contributors and maintainers
- **[License](LICENSE.md)** - BSD 3-Clause License

#### Project Evolution
- **[Rebranding Summary](REBRANDING_SUMMARY.md)** - Project rebranding from DMTF upstream
- **[Rebranding Quick Reference](REBRANDING_QUICK_REFERENCE.md)** - Quick rebranding guide
- **[Cleanup Summary](CLEANUP_SUMMARY.md)** - Project cleanup documentation
- **[Removal Summary](REMOVAL_SUMMARY.md)** - Legacy code removal documentation

---

## 💻 Development Guides

### 🏗️ Architecture & Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    BMC Redfish Simulator                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Server Variants:                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Modular    │  │   Enhanced   │  │   Platform   │          │
│  │   Server     │  │   Server     │  │   Server     │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                   │
│         └──────────────────┴──────────────────┘                  │
│                            │                                      │
│         ┌──────────────────┴──────────────────┐                 │
│         │         Core Components              │                 │
│         ├──────────────────────────────────────┤                 │
│         │  • Handlers (HTTP request handling)  │                 │
│         │  • Services (Business logic)         │                 │
│         │  • Models (Data structures)          │                 │
│         │  • Config (Settings management)      │                 │
│         │  • Utils (Helper functions)          │                 │
│         └──────────────────────────────────────┘                 │
│                                                                   │
│  Platform Framework:                                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • Platform Discovery  • Service Manager                  │  │
│  │  • Plugin System      • Domain Plugins (RAS, Telemetry)     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Client Library:                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  • Python API Client  • Monitoring Tools                  │  │
│  │  • Examples          • CLI Interface                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 🛠️ Development Workflow

#### 1. **Setting Up Development Environment**
```bash
# Clone the repository
git clone <repository-url>
cd bmc-redfish-simulator

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov pylint black
```

📖 **Read:** [Developers Guide - Setup Section](DEVELOPERS_GUIDE.md#setup)

#### 2. **Understanding the Architecture**
```bash
bmc-redfish-simulator/
├── src/                          # Core modular source code
│   ├── handlers/                 # HTTP request handlers
│   ├── services/                 # Business logic services
│   ├── models/                   # Data models
│   ├── config/                   # Configuration management
│   ├── platform_framework/       # Platform detection & plugins
│   ├── plugins/                  # Domain-specific plugins (RAS, Telemetry)
│   └── utils/                    # Utility functions
├── redfishMockupServer_modular.py    # Modular server
├── redfishMockupServer_enhanced.py   # Enhanced server
├── redfishMockupServer_platform.py   # Platform-aware server
└── redfish_client/               # Client library
```

📖 **Read:** [Developers Guide - Architecture](DEVELOPERS_GUIDE.md#architecture)

#### 3. **Running Tests**
```bash
# Run all tests
python3 tests/test_enhanced_server.py
python3 tests/test_modular_server.py

# Run demo
python3 bmc_simulator_demo.py

# Run client examples
cd redfish_client/examples
python3 basic_usage.py
```

📖 **Read:** [Developers Guide - Testing](DEVELOPERS_GUIDE.md#testing)

#### 4. **Creating a Platform Plugin**
```bash
# Create new platform provider
cd src/plugins
mkdir my_platform
# Follow the plugin template
```

📖 **Read:** [Platform Development Guide](PLATFORM_DEVELOPMENT.md)

---

## 🎯 Common Use Cases

### For BMC Developers

| Task | Documentation | Example |
|------|---------------|---------|
| **Testing BMC clients** | [Quick Start](QUICK_START.md) | Run modular server with your mockup |
| **Simulating with plugins** | [Platform Architecture](PLATFORM_ARCHITECTURE.md) | Use platform server with RAS/Telemetry plugins |
| **Custom platform development** | [Platform Development](PLATFORM_DEVELOPMENT.md) | Create custom platform provider |
| **Event testing** | [Enhanced Server](README_ENHANCED.md) | Use enhanced server for subscriptions |

### For Redfish Client Developers

| Task | Documentation | Example |
|------|---------------|---------|
| **Using Python client** | [Client Library](redfish_client/README.md) | Import and use `RedfishClient` |
| **Monitoring BMC** | [Client Library - Monitoring](redfish_client/README.md#monitoring) | Use monitoring tools |
| **Testing subscriptions** | [Enhanced Server](README_ENHANCED.md) | Test event subscriptions |
| **Batch operations** | [Client Library - Examples](redfish_client/README.md#examples) | See batch operation examples |

### For System Integrators

| Task | Documentation | Example |
|------|---------------|---------|
| **Docker deployment** | [README](README.md#docker) | Use provided Dockerfile |
| **CI/CD integration** | [Developers Guide](DEVELOPERS_GUIDE.md) | See `.github/workflows/` examples |
| **Mockup creation** | [Migration Guide](MIGRATION_GUIDE.md) | Use Redfish-Mockup-Creator |
| **Custom configurations** | [Modular Server](README_MODULAR.md) | Configure via settings |

### For Contributors

| Task | Documentation | Example |
|------|---------------|---------|
| **Contributing code** | [Developers Guide](DEVELOPERS_GUIDE.md#contributing) | Follow contribution guidelines |
| **Adding features** | [Developers Guide](DEVELOPERS_GUIDE.md#adding-features) | Create feature in modular structure |
| **Writing plugins** | [Platform Development](PLATFORM_DEVELOPMENT.md) | Follow plugin architecture |
| **Documentation** | [Developers Guide](DEVELOPERS_GUIDE.md#documentation) | Update relevant docs |

---

## 🔧 API References

### Server APIs

#### Modular Server
```python
# Command line
python3 redfishMockupServer_modular.py [OPTIONS]

# Key options:
#   -H, --host HOST         Hostname or IP (default: 127.0.0.1)
#   -p, --port PORT         Port number (default: 8000)
#   -D, --dir PATH          Path to mockup directory
#   -S, --short-form        Use short form (omit /redfish/v1)
#   -s, --ssl               Enable SSL/HTTPS
#   -P, --ssdp              Enable SSDP discovery
```

📖 **Full Reference:** [Modular Server Documentation](README_MODULAR.md)

#### Enhanced Server
```python
# Command line (inherits all modular options plus:)
python3 redfishMockupServer_enhanced.py [OPTIONS]

# Enhanced options:
#   --enhanced-responses    Enable enhanced message responses (default: on)
#   --disable-logging       Disable enhanced logging
#   --disable-events        Disable enhanced event system
```

📖 **Full Reference:** [Enhanced Server Documentation](README_ENHANCED.md)

#### Platform Server
```python
# Command line (inherits all modular options plus:)
python3 redfishMockupServer_platform.py [OPTIONS]

# Platform options:
#   --platform NAME         Specify platform (generic, custom, etc.)
#   --auto-detect          Auto-detect platform from mockup
```

📖 **Full Reference:** [Platform Architecture](PLATFORM_ARCHITECTURE.md)

### Client Library API

#### Basic Usage
```python
from redfish_client import RedfishClient

# Connect to BMC
client = RedfishClient('http://localhost:8000', 'admin', 'password')

# Get service root
root = client.get_service_root()

# Get systems
systems = client.get_systems()

# Power control
client.power_on('System-1')
client.power_off('System-1')
client.reset_system('System-1', 'ForceRestart')
```

📖 **Full Reference:** [Client Library Documentation](redfish_client/README.md)

---

## 🗂️ Documentation by Category

### 📗 Beginner Level

Perfect for getting started quickly:

1. **[Quick Start Guide](QUICK_START.md)** - 5-minute setup
2. **[README](README.md)** - Project overview
3. **[Project Info](PROJECT_INFO.md)** - Understanding the project
4. **[Migration Guide](MIGRATION_GUIDE.md)** - Coming from DMTF

**Estimated Learning Time:** 30 minutes

### 📘 Intermediate Level

For users who want to use advanced features:

1. **[Modular Server Documentation](README_MODULAR.md)** - Understanding modular architecture
2. **[Enhanced Server Documentation](README_ENHANCED.md)** - Using enhanced features
3. **[Client Library Documentation](redfish_client/README.md)** - Using the Python client
4. **[Platform Architecture](PLATFORM_ARCHITECTURE.md)** - Understanding platform support

**Estimated Learning Time:** 2-3 hours

### 📕 Advanced Level

For developers extending the simulator:

1. **[Developers Guide](DEVELOPERS_GUIDE.md)** - Complete development guide
2. **[Platform Development Guide](PLATFORM_DEVELOPMENT.md)** - Creating plugins
3. **[Standalone Development](STANDALONE_DEVELOPMENT.md)** - Custom platforms
4. **[Platform Architecture Deep Dive](PLATFORM_ARCHITECTURE.md)** - Technical details

**Estimated Learning Time:** 1-2 days

### 📙 Reference Level

For project history and detailed references:

1. **[Changelog](CHANGELOG.md)** - Version history
2. **[Rebranding Summary](REBRANDING_SUMMARY.md)** - Project evolution
3. **[Cleanup Summary](CLEANUP_SUMMARY.md)** - Codebase cleanup
4. **[Removal Summary](REMOVAL_SUMMARY.md)** - Legacy code removal
5. **[Authors](AUTHORS.md)** - Contributors
6. **[License](LICENSE.md)** - Legal information

---

## 🎓 Learning Paths

### Path 1: BMC Tester
```
1. Quick Start Guide → 2. README → 3. Modular Server Docs
                                 ↓
4. Run demos → 5. Test with your mockup → 6. Done!
```

### Path 2: Client Developer
```
1. Quick Start Guide → 2. Client Library README → 3. Client Examples
                                 ↓
4. Client API Reference → 5. Build your client → 6. Done!
```

### Path 3: Platform Developer
```
1. Quick Start → 2. Developers Guide → 3. Platform Architecture
                                 ↓
4. Platform Development Guide → 5. Create Plugin → 6. Test & Deploy
```

### Path 4: Contributor
```
1. README → 2. Developers Guide → 3. Code Structure
                                 ↓
4. Choose area (handlers/services/plugins) → 5. Implement → 6. Submit PR
```

---

## 🔍 Search by Topic

### Configuration
- [Server Configuration](README_MODULAR.md#configuration)
- [Platform Configuration](PLATFORM_DEVELOPMENT.md#configuration)
- [Client Configuration](redfish_client/README.md#configuration)

### Testing
- [Running Tests](DEVELOPERS_GUIDE.md#testing)
- [Demo Scripts](DEVELOPERS_GUIDE.md#demos)
- [Client Testing](redfish_client/README.md#testing)

### Deployment
- [Docker Deployment](README.md#docker)
- [Native Installation](README.md#requirements)
- [CI/CD Integration](DEVELOPERS_GUIDE.md#cicd)

### Troubleshooting
- [Common Issues](DEVELOPERS_GUIDE.md#troubleshooting)
- [Debug Mode](README_MODULAR.md#debugging)
- [Error Handling](README_ENHANCED.md#error-handling)

### Advanced Features
- [Event Subscriptions](README_ENHANCED.md#event-system)
- [Logging System](README_ENHANCED.md#logging-system)
- [Platform Plugins](PLATFORM_DEVELOPMENT.md#plugins)
- [Service Extensions](PLATFORM_ARCHITECTURE.md#extensibility)

---

## 🆘 Getting Help

### Quick Links
- 🐛 **Found a bug?** → Check [Developers Guide - Troubleshooting](DEVELOPERS_GUIDE.md#troubleshooting)
- ❓ **Have a question?** → Read [Quick Start Guide](QUICK_START.md)
- 💡 **Feature request?** → See [Developers Guide - Contributing](DEVELOPERS_GUIDE.md#contributing)
- 📖 **Need examples?** → Check [Client Library Examples](redfish_client/README.md#examples)

### Documentation Feedback
If you find any issues with documentation or have suggestions:
1. Check existing documentation first
2. Review [Developers Guide](DEVELOPERS_GUIDE.md#documentation)
3. Submit feedback through proper channels

---

## 📊 Project Statistics

- **Total Documentation Files:** 16+ markdown files
- **Lines of Code:** 60+ Python files
- **Server Variants:** 3 (Modular, Enhanced, Platform)
- **Domain Plugins:** 2+ (RAS, Telemetry, + custom)
- **Client Library Modules:** 10+
- **Example Scripts:** 15+
- **Test Files:** 5+

---

## 🎯 Next Steps

### First Time Here?
1. ✅ Start with [Quick Start Guide](QUICK_START.md)
2. ✅ Read [README](README.md) for overview
3. ✅ Run a demo server
4. ✅ Explore [Client Library](redfish_client/README.md)

### Regular User?
1. ✅ Check [Changelog](CHANGELOG.md) for updates
2. ✅ Review [Enhanced Server](README_ENHANCED.md) features
3. ✅ Try [Platform Server](PLATFORM_ARCHITECTURE.md)

### Developer?
1. ✅ Study [Developers Guide](DEVELOPERS_GUIDE.md)
2. ✅ Understand [Architecture](DEVELOPERS_GUIDE.md#architecture)
3. ✅ Explore [Platform Development](PLATFORM_DEVELOPMENT.md)
4. ✅ Start contributing!

---

## 📝 Documentation Index (A-Z)

| Document | Category | Level |
|----------|----------|-------|
| [AUTHORS.md](AUTHORS.md) | Reference | All |
| [CHANGELOG.md](CHANGELOG.md) | Reference | All |
| [CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md) | Reference | Advanced |
| [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md) | Development | Advanced |
| [LICENSE.md](LICENSE.md) | Reference | All |
| [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) | User | Beginner |
| [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) | Development | Advanced |
| [PLATFORM_DEVELOPMENT.md](PLATFORM_DEVELOPMENT.md) | Development | Advanced |
| [PROJECT_INFO.md](PROJECT_INFO.md) | User | Beginner |
| [QUICK_START.md](QUICK_START.md) | User | Beginner |
| [README.md](README.md) | User | Beginner |
| [README_ENHANCED.md](README_ENHANCED.md) | User | Intermediate |
| [README_MODULAR.md](README_MODULAR.md) | User | Intermediate |
| [REBRANDING_QUICK_REFERENCE.md](REBRANDING_QUICK_REFERENCE.md) | Reference | All |
| [REBRANDING_SUMMARY.md](REBRANDING_SUMMARY.md) | Reference | Intermediate |
| [REMOVAL_SUMMARY.md](REMOVAL_SUMMARY.md) | Reference | Advanced |
| [STANDALONE_DEVELOPMENT.md](STANDALONE_DEVELOPMENT.md) | Development | Advanced |
| [redfish_client/README.md](redfish_client/README.md) | User/Development | Intermediate |

---

## 🌟 Featured Documentation

### Most Popular
1. 🥇 [Quick Start Guide](QUICK_START.md) - Get running in 5 minutes
2. 🥈 [Developers Guide](DEVELOPERS_GUIDE.md) - Comprehensive development guide
3. 🥉 [Client Library](redfish_client/README.md) - Python client documentation

### Recently Updated
1. ✨ [Removal Summary](REMOVAL_SUMMARY.md) - Legacy code removal (Nov 5, 2025)
2. ✨ [Cleanup Summary](CLEANUP_SUMMARY.md) - Project cleanup (Nov 5, 2025)
3. ✨ [Project Info](PROJECT_INFO.md) - Updated project information

### Must Read
1. 📌 [README](README.md) - Start here!
2. 📌 [Project Info](PROJECT_INFO.md) - Understand the project
3. 📌 [Developers Guide](DEVELOPERS_GUIDE.md) - For contributors

---

<div align="center">

## 🚀 Ready to Get Started?

**[📖 Read Quick Start](QUICK_START.md)** • **[💻 View on GitHub](https://github.com/DMTF/Redfish-Mockup-Server)** • **[📘 Full Documentation](#documentation-index)**

---

**BMC Redfish Simulator v2.0.0**  
*Based on DMTF Redfish-Mockup-Server*  
*Licensed under BSD 3-Clause*

**[⬆ Back to Top](#bmc-redfish-simulator---documentation-wiki)**

</div>
