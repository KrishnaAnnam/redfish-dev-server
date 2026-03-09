# BMC Redfish Simulator - Project Information

## Project Identity

**Project Name:** bmc-redfish-simulator  
**Version:** 2.0.0  
**Status:** Production Ready  
**License:** BSD 3-Clause (same as upstream)

## Origin and Attribution

This project is based on the DMTF Redfish-Mockup-Server:

- **Upstream Project:** [DMTF Redfish-Mockup-Server](https://github.com/DMTF/Redfish-Mockup-Server)
- **Original Copyright:** Copyright 2016-2024 DMTF. All rights reserved.
- **Original License:** BSD 3-Clause License
- **Upstream Version:** 1.2.4

## Project Scope

The BMC Redfish Simulator extends the original DMTF Redfish-Mockup-Server with comprehensive BMC-specific features for development and testing:

### Enhanced Features (Beyond Upstream)

1. **Comprehensive Message System**
   - DMTF Base Message Registry integration
   - Standardized ExtendedInfo responses
   - Dynamic message formatting with arguments
   - Related properties linking

2. **Advanced Logging System**
   - Multiple log types (Event, Audit, Security)
   - Persistent JSON-based storage
   - Operation tracking and audit trails
   - Property change tracking

3. **Enhanced Event System**
   - Real-time event subscriptions
   - Automatic event generation from operations
   - Background event delivery
   - Filtering and subscription management

4. **Platform Framework**
   - Multi-platform support
   - Platform auto-detection
   - Vendor-specific OEM extensions
   - Plugin architecture

5. **Client Library**
   - Comprehensive Python client
   - Monitoring client with alerting
   - Web-based dashboard
   - Interactive demo launcher

6. **Modular Architecture**
   - Clean separation of concerns
   - Service-oriented design
   - Handler-based request processing
   - Extensible plugin system

### Maintained Compatibility

All original DMTF Redfish-Mockup-Server functionality is preserved:

- ✅ Static mockup serving
- ✅ HTTP/HTTPS support
- ✅ SSDP discovery
- ✅ Query parameter support ($expand, $select)
- ✅ Command-line interface
- ✅ Docker container support
- ✅ ETag support
- ✅ Response timing simulation

## Architecture

### Source Code Attribution

The project maintains clear attribution for code origin:

1. **Original DMTF Code** (Inherited)
   - `redfishMockupServer.py` (with enhancements)
   - `rfSsdpServer.py`
   - Basic HTTP server framework
   - Mockup data structures

2. **Enhanced BMC Simulator Code** (New)
   - `src/` directory (all modules)
   - `redfish_client/` directory (client library)
   - Enhanced server implementations
   - Platform framework
   - Demo and test scripts

### File Headers

All files maintain proper attribution:

```python
#!/usr/bin/env python3
# BMC Redfish Simulator
# Based on DMTF Redfish-Mockup-Server
# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
```

## Relationship to Upstream

### Why a Separate Project?

1. **Extensive Extensions**: The enhanced features constitute a significant extension beyond the original scope
2. **Different Focus**: BMC-specific simulation vs. general Redfish mockup serving
3. **Independent Development**: Faster iteration on BMC-specific features
4. **Clear Identity**: Distinct project identity for BMC development community

### Upstream Contributions

Where appropriate, improvements that benefit the general Redfish community may be contributed back to the upstream DMTF project.

### Synchronization

The project tracks upstream changes and incorporates relevant updates while maintaining enhanced functionality.

## Documentation Structure

### Main Documentation

- `README.md` - Project overview and quick start
- `DEVELOPERS_GUIDE.md` - Comprehensive developer documentation
- `PROJECT_INFO.md` - This file (project identity and attribution)

### Feature Documentation

- `README_ENHANCED.md` - Enhanced features overview
- `README_MODULAR.md` - Modular architecture documentation
- `PLATFORM_ARCHITECTURE.md` - Platform framework details
- `PLATFORM_DEVELOPMENT.md` - Platform development guide
- `MIGRATION_GUIDE.md` - Migration from upstream
- `QUICK_START.md` - Quick start guide

### Client Library Documentation

- `redfish_client/README.md` - Client library documentation
- `REDFISH_CLIENT_README.md` - Detailed client guide
- `REDFISH_CLIENT_COMPLETE.md` - Complete client reference

### Implementation Documentation

- `ENHANCED_IMPLEMENTATION_SUMMARY.md` - Implementation details
- `ENHANCED_SYSTEM_SUMMARY.md` - System architecture
- `STANDALONE_IMPLEMENTATION_SUMMARY.md` - Standalone features
- `REFACTORING_SUMMARY.md` - Refactoring documentation

## Usage Scenarios

### Original Mockup Serving (DMTF Compatible)

```bash
# Standard DMTF Redfish-Mockup-Server usage
python3 redfishMockupServer.py -D mockups/public-rackmount1 -p 8000
```

### Enhanced BMC Simulation

```bash
# Enhanced server with full BMC features
python3 redfishMockupServer_enhanced.py -D mockup-directory --enhanced-responses

# Platform-aware server with auto-detection
python3 redfishMockupServer_platform.py -D mockup-directory -p 8000

# Modular server with improved architecture
python3 redfishMockupServer_modular.py -D mockup-directory -p 8000
```

### Client Library Usage

```python
from redfish_client.client import RedfishClient

client = RedfishClient("http://localhost:8000", "admin", "password")
if client.connect():
    systems = client.get_systems()
    # ... use client
```

## Version History

### Version 2.0.0 (Current)
- Complete rebranding as bmc-redfish-simulator
- Comprehensive BMC simulation features
- Enhanced message, logging, and event systems
- Platform framework with plugin support
- Full client library with monitoring
- Modular architecture with service layer

### Version 1.x (Upstream Base)
- Based on DMTF Redfish-Mockup-Server 1.2.4
- Standard mockup serving
- Basic HTTP/HTTPS support
- SSDP discovery

## Community and Support

### Project Repository
- Primary development location
- Issue tracking
- Feature requests
- Pull requests

### Upstream Community
- [DMTF Redfish Forum](https://www.dmtf.org/standards/feedback)
- [Redfish Developer Hub](https://www.dmtf.org/redfish)
- [Stack Overflow - Redfish](https://stackoverflow.com/questions/tagged/redfish)

## Contributing

We welcome contributions! Please ensure:

1. **Code Attribution**: Maintain proper copyright notices
2. **Upstream Compatibility**: Don't break compatibility with DMTF mockup format
3. **Documentation**: Update relevant documentation
4. **Testing**: Include tests for new features
5. **Style**: Follow existing code style

## License

This project maintains the same BSD 3-Clause License as the upstream DMTF Redfish-Mockup-Server.

See [LICENSE.md](LICENSE.md) for full license text.

## Acknowledgments

- **DMTF**: For the original Redfish-Mockup-Server foundation
- **Redfish Community**: For the Redfish specification and ecosystem
- **Contributors**: All developers who have contributed to this project

---

**Last Updated:** November 5, 2025  
**Project Maintainer:** BMC Simulator Development Team
