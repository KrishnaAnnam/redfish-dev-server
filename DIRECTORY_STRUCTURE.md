# BMC Redfish Simulator - Directory Structure

This document outlines the organized directory structure of the BMC Redfish Simulator project.

## 📁 Root Directory Structure

```
bmc-redfish-simulator/
├── 📄 README.md                  # Main project documentation
├── 📄 AUTHORS.md                 # Project contributors
├── 📄 CHANGELOG.md               # Version history and changes
├── 📄 LICENSE.md                 # Project license
├── 📄 requirements.txt           # Main Python dependencies
├── 🐳 Dockerfile                 # Docker container configuration
│
├── 📁 config/                    # Configuration files
│   └── requirements_modular.txt  # Modular component dependencies
│
├── 📁 docs/                      # Documentation
│   ├── PROJECT_INFO.md           # Project overview and information
│   ├── README_ENHANCED.md        # Enhanced feature documentation
│   ├── README_MODULAR.md         # Modular architecture documentation
│   │
│   ├── 📁 guides/                # Development and user guides
│   │   ├── DEVELOPERS_GUIDE.md   # Developer setup and workflows
│   │   ├── MIGRATION_GUIDE.md    # Version migration instructions
│   │   ├── QUICK_START.md        # Quick start tutorial
│   │   └── STANDALONE_DEVELOPMENT.md # Standalone development guide
│   │
│   ├── 📁 specs/                 # Technical specifications
│   │   ├── ACTION_HANDLERS_SUMMARY.md       # Action handlers documentation
│   │   ├── LOGENTRY_IMPLEMENTATION_SUMMARY.md # Log entry implementation
│   │   ├── PLATFORM_ARCHITECTURE.md         # Platform architecture
│   │   ├── PLATFORM_DEVELOPMENT.md          # Platform development guide
│   │   └── SCHEMA_VALIDATION_GUIDE.md       # Schema validation guide
│   │
│   └── 📁 wiki/                  # Wiki and supplementary docs
│       ├── WIKI.md               # Main wiki content
│       ├── _Footer.md            # Wiki footer
│       └── _Sidebar.md           # Wiki sidebar navigation
│
├── 📁 examples/                  # Demo and example implementations
│   ├── action_handlers_demo.py   # Action handlers demonstration
│   ├── bmc_simulator_demo.py     # BMC simulator demo
│   ├── demo_enhanced_redfish_system.py # Enhanced system demo
│   ├── live_demo_presentation.py # Live presentation demo
│   ├── log_entry_demo.py         # Log entry demonstration
│   ├── redfish_message_compliance_demo.py # Message compliance demo
│   ├── schema_validation_demo.py # Schema validation demo
│   │
│   └── 📁 platform_configs/      # Platform configuration examples
│       ├── example_platform_config.json      # Example platform configuration
│       └── ras_enabled_platform_config.json  # RAS-enabled platform configuration
│
├── 📁 mockups/                   # Mock data and test fixtures
│   └── 📁 public-rackmount1/     # Sample rackmount system mockup
│       ├── explorer_config.json  # Explorer configuration
│       ├── index.json            # Main index
│       └── [various service directories...]
│
├── 📁 platforms/                 # Platform-specific implementations
│   └── 📁 example/               # Example platform implementation
│       ├── platform.py           # Platform logic
│       ├── README.md             # Platform documentation
│       ├── test_platform.py      # Platform tests
│       └── 📁 mock_data/         # Platform mock data
│
├── 📁 redfish_client/           # Redfish client implementation
│   ├── __init__.py              # Package initialization
│   ├── client.py                # Main client implementation
│   ├── monitoring.py            # Monitoring capabilities
│   ├── README.md                # Client documentation
│   │
│   ├── 📁 examples/             # Client usage examples
│   │   ├── __init__.py          # Package initialization
│   │   └── basic_examples.py    # Basic client examples
│   │
│   ├── 📁 tests/                # Client tests
│   │   ├── __init__.py          # Package initialization
│   │   ├── basic_test.py        # Basic functionality tests
│   │   └── test_suite.py        # Complete test suite
│   │
│   └── 📁 tools/                # Client tools and utilities
│       ├── __init__.py          # Package initialization
│       ├── launcher.py          # Tool launcher
│       └── web_dashboard.py     # Web-based dashboard
│
├── 📁 scripts/                  # Utility scripts and tools
│   ├── debug_mro.py             # Method Resolution Order debugging
│   ├── debug_mro_simple.py      # Simplified MRO debugging
│   ├── platform-cli             # Platform command-line interface
│   ├── redfish_client_launcher.py # Client launcher script
│   └── rfSsdpServer.py          # SSDP server implementation
│
├── 📁 servers/                  # Server implementations
│   ├── redfishMockupServer_enhanced.py # Enhanced server implementation
│   ├── redfishMockupServer_modular.py  # Modular server implementation
│   └── redfishMockupServer_platform.py # Platform-aware server
│
├── 📁 src/                      # Core source code
│   ├── __init__.py              # Package initialization
│   │
│   ├── 📁 config/               # Configuration management
│   ├── 📁 core/                 # Core functionality
│   ├── 📁 handlers/             # Request handlers
│   ├── 📁 models/               # Data models
│   ├── 📁 platform_framework/   # Platform framework
│   ├── 📁 plugins/              # Plugin system
│   ├── 📁 services/             # Service implementations
│   ├── 📁 standalone/           # Standalone utilities
│   └── 📁 utils/                # Utility functions
│
├── 📁 tests/                    # Test suite
│   ├── test_basic_ci.py         # Basic CI tests
│   ├── test_enhanced_server.py  # Enhanced server tests
│   ├── test_handler_debug.py    # Handler debugging tests
│   ├── test_modular_server.py   # Modular server tests
│   ├── test_patch_validation.py # PATCH validation tests
│   ├── test_property_conflict_minimal.py # Property conflict tests
│   ├── test_real_handlers.py    # Real handler tests
│   └── test_redfish_messages.py # Redfish message tests
│
├── 📁 training/                 # Training materials
│   ├── README.md                # Training overview
│   ├── 📁 exercises/            # Hands-on exercises
│   ├── 📁 labs/                 # Laboratory sessions
│   ├── 📁 reference/            # Reference materials
│   └── 📁 slides/               # Presentation slides
│
└── 📁 webui/                    # Web user interface
    ├── quickstart.sh            # Quick setup script
    ├── README_WEBUI.md          # Web UI documentation
    ├── requirements_webui.txt   # Web UI dependencies
    ├── WEBUI_IMPLEMENTATION.md  # Implementation details
    ├── webui_launcher.py        # Web UI launcher
    ├── 📁 client/               # Frontend client code
    └── 📁 server/               # Backend server code
```

## 🎯 Organization Benefits

### 1. **Clear Separation of Concerns**
- **Documentation** (`docs/`) - All project documentation in one place
- **Source Code** (`src/`) - Core implementation
- **Tests** (`tests/`) - All test files centralized
- **Examples** (`examples/`) - Demo and sample code
- **Scripts** (`scripts/`) - Utility and helper scripts

### 2. **Logical Grouping**
- **Specifications** (`docs/specs/`) - Technical specs and architecture
- **Guides** (`docs/guides/`) - User and developer guides
- **Servers** (`servers/`) - Different server implementations
- **Configuration** (`config/`) - All configuration files

### 3. **Easy Navigation**
- Related files are grouped together
- Clear naming conventions
- Hierarchical organization
- README files provide context in each directory

### 4. **Scalability**
- Easy to add new components
- Clear placement guidelines for new files
- Modular structure supports future growth

## 📋 Quick Reference

| Need to find... | Look in... |
|-----------------|------------|
| Getting started | `docs/guides/QUICK_START.md` |
| API documentation | `docs/specs/` |
| Code examples | `examples/` |
| Test files | `tests/` |
| Server implementations | `servers/` |
| Utility scripts | `scripts/` |
| Configuration files | `config/` |
| Core source code | `src/` |

## 🔄 Migration Notes

If you have existing scripts or documentation that reference the old file locations, you may need to update the paths. The files have been moved as follows:

- Documentation files → `docs/` (with subcategorization)
- Test files → `tests/`
- Demo files → `examples/`
- Debug scripts → `scripts/`
- Server implementations → `servers/`
- Configuration files → `config/`