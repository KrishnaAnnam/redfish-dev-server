# Redfish Dev Server

[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Redfish](https://img.shields.io/badge/Redfish-API-green.svg)](https://www.dmtf.org/standards/redfish)

**A comprehensive Redfish API simulator for BMC development, testing, and integration using Redfish mockups.**

Based on [DMTF Redfish-Mockup-Server](https://github.com/DMTF/Redfish-Mockup-Server)  
Copyright 2016-2020 DMTF. All rights reserved.

---

## 🎯 Overview

The **Redfish Dev Server** is a powerful, feature-rich Redfish API simulator designed specifically for Baseboard Management Controller (BMC) development, testing, and integration workflows. It enables you to create and manage **Redfish mockups** - virtual BMC environments that simulate real hardware without requiring physical servers. Built upon the robust DMTF Redfish-Mockup-Server foundation, it provides:

- **🔧 Three Server Variants**: Choose from modular, enhanced, or platform-specific implementations
- **📚 Comprehensive Client Library**: Full-featured Python client with examples and tools
- **🎨 Modular Architecture**: Clean separation of concerns with handlers, services, and models
- **⚡ Enhanced Features**: Advanced logging, event management, message handling, and platform simulation
- **📖 Extensive Documentation**: Complete Wiki system, developer guides, and API references
- **🧪 Testing Framework**: Built-in demos, test suites, and validation tools

### Key Capabilities

- Serve Redfish requests against Redfish mockup data at configurable IP/port (default: `127.0.0.1:8000`)
- Simulate real BMC behavior with persistent state, event generation, and resource management
- Support for multiple platform types (rackmount, blade, modular) with custom mockup configurations
- DMTF-compliant message registry integration and standardized ExtendedInfo responses
- Docker support for containerized deployment and testing
- SSL/HTTPS support with custom certificates

### Resources

- **DMTF mockup Data**: [All Published Versions of DSP2043](https://www.dmtf.org/dsp/DSP2043)
- **Create mockups**: [Redfish-Mockup-Creator](https://github.com/DMTF/Redfish-Mockup-Creator)
- **Redfish Standard**: [DMTF Redfish Specification](https://www.dmtf.org/standards/redfish)

## 📁 Project Structure

This project has been organized for better maintainability and ease of use:

```
📁 redfish-dev-server/
├── 📁 docs/           # 📖 Complete documentation
│   ├── guides/        # 🔧 Setup and development guides  
│   ├── specs/         # 📋 Technical specifications
│   └── wiki/          # 📚 Wiki content
├── 📁 src/            # 🏗️ Core source code
├── 📁 servers/        # 🖥️ Server implementations
├── 📁 scripts/        # ⚡ Utility scripts
├── 📁 tests/          # 🧪 Test suite
├── 📁 examples/       # 💡 Demos and samples
├── 📁 config/         # ⚙️ Configuration files
└── 📁 [other dirs]    # Additional components
```

📝 **See [DIRECTORY_STRUCTURE.md](./DIRECTORY_STRUCTURE.md) for complete organization details**

## 📋 Requirements

### Native Installation

* **Python 3.7+**: [Download Python](https://www.python.org/downloads/)
* **pip**: Package installer (usually included with Python)
* **Dependencies**: Install via `pip install -r requirements.txt`

### Docker Installation

* **Docker**: [Get Docker](https://www.docker.com/get-started)

### Supported Platforms

- Linux (Ubuntu, RHEL, CentOS, Debian)
- macOS
- Windows (with WSL2 recommended)
- Docker containers (platform-independent)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Clone the repository
git clone https://github.com/microsoft/redfish-dev-server.git
cd redfish-dev-server

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Run the Simulator

**Basic usage** (default mockup, localhost:8000):
```bash
python servers/redfishMockupServer_modular.py
```

**Custom mockup directory**:
```bash
python servers/redfishMockupServer_modular.py -D /path/to/your/mockup-data
```

**With SSL/HTTPS**:
```bash
python servers/redfishMockupServer_modular.py -s --cert server.crt --key server.key
```

### 3. Test the Server

```bash
# Test basic connectivity
curl http://127.0.0.1:8000/redfish/v1

# Use the Python client library
python -m redfish_client.examples.basic_operations
```

## 📦 Redfish mockups

The `mockups/` directory contains several pre-configured Redfish mockup datasets that simulate different BMC hardware configurations:

### Ready-to-Use mockups

- **`public-rackmount1/`** - DMTF standard rackmount server mockup
  - Complete system with Chassis, Systems, Managers resources
  - Full BMC simulation with event and logging services
  - Includes thermal, power, and storage subsystems

### mockup Archives (.tgz)

- **`FullBMCMockup.tgz`** - Comprehensive BMC simulation mockup dataset
- **`RASMockup.tgz`** - Reliability, Availability, Serviceability focused mockup
- **`sample_mockup.tgz`** - Minimal example mockup for development

### Using Redfish mockups

```bash
# Use the default public-rackmount1 mockup
python servers/redfishMockupServer_modular.py -D mockups/public-rackmount1

# Extract and use archived mockups
tar -xzf mockups/FullBMCMockup.tgz -C mockups/
python servers/redfishMockupServer_modular.py -D mockups/FullBMCMockup

# Create your own custom mockup directory
mkdir -p mockups/my-custom-bmc
# Add your JSON resources and use:
python servers/redfishMockupServer_modular.py -D mockups/my-custom-bmc
```

> **Note**: Directory is named `mockups/` for backward compatibility with DMTF tools. These are Redfish mockup data directories.

See the [mockup Data Management](training/slides/04-mockup-data.md) training module for detailed guidance on creating and customizing Redfish mockup data.

## 📚 Server Variants

The Redfish Dev Server provides three server implementations for different use cases:

### 1. Modular Server (redfishMockupServer_modular.py)
**Best for: General development and testing**

```bash
python servers/redfishMockupServer_modular.py -D mockup-data-dir -p 8000
```

Features:
- Clean modular architecture with handlers, services, and models
- Persistent state management with JSON storage
- Enhanced error handling and DMTF message registry
- Resource lifecycle management (POST/PATCH/DELETE)
- Built-in logging and audit trails

### 2. Enhanced Server (redfishMockupServer_enhanced.py)
**Best for: Advanced mockup simulation**

```bash
python servers/redfishMockupServer_enhanced.py -D mockup-data-dir --enhanced-responses
```

Features:
- Advanced event management with real-time subscriptions
- Comprehensive logging (Event, Audit, Security logs)
- Automatic event generation from operations
- Extended message responses with full ExtendedInfo
- Background event delivery system

### 3. Platform Server (redfishMockupServer_platform.py)
**Best for: Platform-specific mockup testing**

```bash
python servers/redfishMockupServer_platform.py --platform rackmount --config platform-config.json
```

Features:
- Platform-specific configurations (rackmount, blade, modular)
- Custom resource types and behaviors
- Platform capability simulation
- Advanced sensor and metric emulation
- Multi-chassis and multi-node support

## 🔌 RAS Plugin (Reliability, Availability, Serviceability)

**New!** Complete RAS plugin for error detection, analysis, and remediation workflows.

### Quick Start

```bash
# Start server with RAS-enabled mockup
python servers/redfishMockupServer_platform.py -D mockups/ras_gen10 -p 8000

# Run the parity demo
python examples/ras_plugin_parity_demo.py

# Or use the tmux launcher for full demo
./scripts/run_ras_demo.sh
```

### Features
- **CPAD Submission**: Submit Corrective Platform Action Descriptors via SubmitCPAD action
- **CPER Generation**: Template-based Common Platform Error Record generation using libcper
- **Policy Engine**: Trust-based validation with TRUSTED_CREATORS, KNOWN_ACTIONS, KNOWN_PLATFORMS
- **LogService**: Redfish-compliant RAS log entries with CPER data
- **EventService**: Event subscription and notification for RAS alerts
- **Analytics**: Error pattern analysis and trend detection
- **Remediation**: Policy-based automated remediation with rate limiting

### Documentation
- [RAS Plugin Documentation](docs/RAS_PLUGIN.md) - Complete plugin reference
- [Plugin SDK Guide](docs/PLUGIN_SDK.md) - How to develop plugins
- [Documentation Index](docs/DOCUMENTATION_INDEX.md) - Navigation guide

## 🌐 Web UI Interface

**New!** Comprehensive web interfaces for server management and client operations.

### Quick Start

```bash
# Install Web UI dependencies
pip install -r webui/requirements_webui.txt

# Launch with quick start script
./webui/quickstart.sh

# Or launch individually
python webui/webui_launcher.py both    # Launch both UIs
python webui/webui_launcher.py server  # Server UI only
python webui/webui_launcher.py client  # Client UI only
```

### Server Web UI (Port 5000)
**Control Panel for managing the Redfish mockup simulator server**

- 🎛️ **Server Control**: Start/Stop/Restart mockup server with one click
- 📊 **Live Monitoring**: Real-time status, logs, and statistics
- ⚙️ **Configuration**: Set host, port, mockup directory, platform type
- 🔍 **Log Viewer**: Filter logs by level (info/success/warning/error)

Access at: http://127.0.0.1:5000/

### Client Web UI (Port 5001)
**Interactive interface for Redfish mockup operations and analysis**

- 🔗 **Connection Manager**: Manage multiple Redfish server connections
- 🎯 **Operations**: GET/POST/PATCH/DELETE requests with JSON payload editor
- 🔍 **Discovery**: Automatically discover all server resources
- 📊 **Analysis**: Analyze server capabilities and features
- 📜 **History**: Track all requests with timestamps and response times

Access at: http://127.0.0.1:5001/

See [Web UI Documentation](webui/README_WEBUI.md) for full details.

## 💻 Usage Reference

```
Redfish Dev Server, version 2.0.0
usage: redfishMockupServer.py [-h] [-H HOST] [-p PORT] [-D DIR] [-E] [-X]
                              [-t TIME] [-T] [-s] [--cert CERT] [--key KEY]
                              [-S] [-P]

optional arguments:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  hostname or IP address (default: 127.0.0.1)
  -p PORT, --port PORT  host port (default: 8000)
  -D DIR, --dir DIR     path to mockup data directory (may be relative to CWD)
  -E, --test-etag       etag testing (unimplemented)
  -X, --headers         load headers from headers.json files in mockup
  -t TIME, --time TIME  delay in seconds added to responses (float or int)
  -T                    delay response based on times in time.json files
  -s, --ssl             enable SSL (HTTPS) mode; requires cert and key
  --cert CERT           certificate file for SSL
  --key KEY             private key file for SSL
  -S, --short-form      apply short form to mockup (omit /redfish/v1 prefix)
  -P, --ssdp            make mockup SSDP discoverable
```

**Notes:**
- If the mockup lacks the `/redfish` resource, use `--short-form`
- If no mockup is specified, DMTF's `public-rackmount1` mockup is used
- SSL mode requires both certificate and key files

## 🐳 Docker Usage

### Build Container

```bash
docker build -t redfish-dev-server:latest .
```

### Run with Built-in mockup

```bash
docker run --rm -p 8000:8000 redfish-dev-server:latest
```

### Run with Custom mockup

```bash
docker run --rm -p 8000:8000 \
  -v /path/to/mockup-data:/mockup \
  redfish-dev-server:latest -D /mockup
```

### Run with SSL

```bash
docker run --rm -p 8443:8443 \
  -v /path/to/certs:/certs \
  redfish-dev-server:latest -s --cert /certs/server.crt --key /certs/server.key -p 8443
```

## ✨ Key Features

### 🔧 Enhanced BMC Simulation

**Message Handling**
- Standardized Redfish ExtendedInfo in all responses
- DMTF Base Message Registry (Base.1.5.0) integration
- Consistent error handling across all endpoints
- Proper HTTP status codes with corresponding messages

**Logging System**
- Multiple log types: Event, Audit, and Security
- JSON-based persistent storage
- Automatic CRUD operation tracking
- Property change audit trails
- Authentication event logging

**Event Management**
- Real-time event subscriptions with filtering
- Automatic event generation from POST/PATCH operations
- Multiple event types: ResourceAdded, ResourceUpdated, Alert, StatusChange
- Background non-blocking event delivery
- SSE (Server-Sent Events) support

**State Management**
- Persistent resource state across server restarts
- Transaction logging and rollback support
- Resource lifecycle management
- Dynamic mockup updates

### 📚 Python Client Library

Comprehensive Redfish client with:
- Synchronous and asynchronous operations
- Session management and authentication
- Resource discovery and navigation
- Event subscription handling
- Command-line tools and utilities
- Extensive examples and documentation

**Example usage**:
```python
from redfish_client import RedfishClient

# Connect to Redfish mockup simulator
client = RedfishClient('http://127.0.0.1:8000', username='admin', password='password')

# Get system information from mockup
systems = client.get('/redfish/v1/Systems')
print(systems.json())

# Update a resource in the mockup
client.patch('/redfish/v1/Systems/1', {'AssetTag': 'MyServer'})

# Subscribe to mockup events
client.create_event_subscription('http://my-listener/events')
```

### 🎨 Modular Architecture

```
redfish-dev-server/
├── src/                          # Core source code
│   ├── handlers/                 # Request handlers (GET, POST, PATCH, DELETE)
│   ├── services/                 # Business logic (state, events, logging)
│   ├── models/                   # Data models and schemas
│   ├── config/                   # Configuration management
│   └── plugins/                  # Extensible plugin system
├── redfish_client/               # Python client library
│   ├── client.py                 # Main client class
│   ├── session.py                # Session management
│   ├── examples/                 # Usage examples
│   └── tools/                    # Command-line utilities
├── platforms/                    # Platform-specific configurations
├── examples/                     # Demo scripts and tutorials
└── tests/                        # Test suites
```

## 🧪 Demo and Testing

### Run Demonstrations

**Quick feature demo**:
```bash
python examples/quick_enhanced_demo.py
```

**Comprehensive system demo**:
```bash
python examples/demo_enhanced_redfish_system.py
```

**Complete BMC simulator showcase**:
```bash
python examples/bmc_simulator_demo.py
```

### Client Library Examples

```bash
# Basic operations
python -m redfish_client.examples.basic_operations

# Event subscriptions
python -m redfish_client.examples.event_subscriptions

# Resource management
python -m redfish_client.examples.resource_management
```

### Testing

```bash
# Run unit tests
python -m pytest tests/

# Run integration tests
python -m pytest tests/integration/

# Run with coverage
python -m pytest --cov=src tests/
```

## 📖 Documentation

### 🚀 Quick Navigation
- **[📖 Project Structure](DIRECTORY_STRUCTURE.md)** - Complete directory organization
- **[⚡ Quick Start](docs/guides/QUICK_START.md)** - Get up and running in minutes  
- **[🔧 Developer Guide](docs/guides/DEVELOPERS_GUIDE.md)** - Comprehensive development docs
- **[📚 Wiki Hub](docs/wiki/WIKI.md)** - Complete documentation portal
- **[🔄 Migration Guide](docs/guides/MIGRATION_GUIDE.md)** - Migrating from legacy servers

### 📋 Technical References  
- **[🏗️ Platform Development](docs/specs/PLATFORM_DEVELOPMENT.md)** - Custom platform development
- **[⚙️ Architecture](docs/specs/PLATFORM_ARCHITECTURE.md)** - Platform architecture details
- **[🔗 Action Handlers](docs/specs/ACTION_HANDLERS_SUMMARY.md)** - Handler implementation
- **[📝 Schema Validation](docs/specs/SCHEMA_VALIDATION_GUIDE.md)** - Validation guidelines
- **[📊 API Reference](https://redfish.dmtf.org/)** - DMTF Redfish specification

### 💡 Examples & Demos
- **[📁 Examples Directory](examples/)** - All demo implementations
- **[🧪 Test Suite](tests/)** - Complete test examples
- **[⚡ Utility Scripts](scripts/)** - Helper tools and utilities

## 🔗 Related Projects

### Other DMTF Projects

- **[Redfish-Mockup-Creator](https://github.com/DMTF/Redfish-Mockup-Creator)** - Create mockup data from live Redfish services
- **[Redfish-Service-Validator](https://github.com/DMTF/Redfish-Service-Validator)** - Validate Redfish service conformance
- **[Redfish-Mockup-Server](https://github.com/DMTF/Redfish-Mockup-Server)** - Original DMTF mockup server

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines for details:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the **BSD 3-Clause License** - see the [LICENSE.md](LICENSE.md) file for details.

Based on [DMTF Redfish-Mockup-Server](https://github.com/DMTF/Redfish-Mockup-Server)  
Copyright 2016-2020 DMTF. All rights reserved.

## 🙏 Acknowledgments

- **DMTF** - For the Redfish specification and original Mockup Server
- **Original Authors** - Paul Vancil and contributors to Redfish-Mockup-Server
- **Community** - All contributors and users of this project

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/microsoft/redfish-dev-server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/microsoft/redfish-dev-server/discussions)
- **Wiki**: [Project Wiki](WIKI.md)

## 🔄 Release Process

1. Go to the "Actions" page
2. Select the "Release and Publish" workflow
3. Click "Run workflow"
4. Fill out the form
5. Click "Run workflow"

---

**Version**: 2.0.0  
**Status**: Active Development  
**Last Updated**: November 2024
