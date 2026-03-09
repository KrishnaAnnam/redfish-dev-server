# Quick Start Guide - BMC Redfish Simulator

**Project:** bmc-redfish-simulator  
**Based on:** DMTF Redfish-Mockup-Server

## Installation and Setup

### Prerequisites
- Python 3.10 or later
- pip package manager

### Install Dependencies
```bash
pip install -r requirements.txt
```

## Quick Usage

### Basic Server (Original Functionality)
```bash
# Use the original monolithic server
python servers/redfishMockupServer.py -D mockups/public-rackmount1

# Use the modular server (drop-in replacement)
python servers/redfishMockupServer_modular.py -D mockups/public-rackmount1
```

### Platform-Aware Server (Enhanced)
```bash
# Auto-detect platform and run
python servers/redfishMockupServer_platform.py -D mockups/public-rackmount1

# Specify platform explicitly
python servers/redfishMockupServer_platform.py --platform dell -D mockups/public-rackmount1

# List available platforms
python servers/redfishMockupServer_platform.py --list-platforms

# Show platform detection info
python servers/redfishMockupServer_platform.py --platform-info -D mockups/public-rackmount1
```

## Common Use Cases

### 1. Testing Redfish Clients
```bash
# Start server for testing
python servers/redfishMockupServer_platform.py -D mockups/public-rackmount1 -p 8000

# Access service root
curl http://localhost:8000/redfish/v1/

# Test authentication (Basic auth with any credentials)
curl -u admin:admin http://localhost:8000/redfish/v1/Systems/
```

### 2. Developing Platform-Specific Features
```bash
# Use RAS-enabled platform for error testing
python servers/redfishMockupServer_platform.py --platform generic -D mockups/public-rackmount1/

# Use generic platform for basic testing  
python servers/redfishMockupServer_platform.py --platform generic -D mockups/public-rackmount1/

# Enable debug logging for development
python servers/redfishMockupServer_platform.py -D mockups/public-rackmount1/ --platform generic -v
```

### 3. Creating Custom Mockups
```bash
# Start with existing mockup and modify responses
python servers/redfishMockupServer_platform.py -D mockups/base-mockup/ -p 8001

# Add platform manifest for auto-detection
echo '{"platform_id": "custom", "platform_type": "custom"}' > mockups/custom-mockup/platform_manifest.json
```

## Server Options

### Common Arguments
- `-D, --Dir`: Mockup directory path (required)
- `-p, --port`: Port number (default: 8000)
- `-H, --Host`: Host IP address (default: all interfaces)
- `-v, --verbose`: Enable verbose logging
- `-q, --quiet`: Suppress output

### Platform-Specific Arguments
- `--platform`: Force specific platform (generic, custom, etc.)
- `--list-platforms`: Show available platforms
- `--platform-info`: Show platform detection information
- `--config`: Use platform configuration file

### Advanced Options
- `--ssl`: Enable SSL/TLS
- `--cert`: SSL certificate file
- `--key`: SSL private key file
- `-S, --ssdp`: Enable SSDP discovery

## Testing the Setup

### 1. Verify Server is Running
```bash
curl http://localhost:8000/redfish/v1/
```
Expected response:
```json
{
    "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
    "@odata.id": "/redfish/v1/", 
    "Id": "RootService",
    "Name": "Root Service"
}
```

### 2. Check Platform Detection
```bash
python servers/redfishMockupServer_platform.py --platform-info -D mockups/public-rackmount1
```

### 3. Test Platform-Specific Features
For Dell platform:
```bash
# Check OEM namespace
curl http://localhost:8000/redfish/v1/Systems/437XR1138R2/Oem/Dell/

# Test OEM actions (if available)
curl -X POST -H "Content-Type: application/json" \
     -d '{}' http://localhost:8000/redfish/v1/Systems/437XR1138R2/Actions/Oem/Dell.ExportSystemConfiguration
```

## Configuration Examples

### Platform Manifest (Auto-Detection)
Create `platform_manifest.json` in your mockup directory:
```json
{
    "platform_id": "my_platform",
    "platform_type": "custom",
    "display_name": "My Custom Platform", 
    "enabled_services": ["EventService", "UpdateService"],
    "oem_namespace": "MyVendor"
}
```

### Platform Configuration File
Create detailed configuration (see `config/examples/` for templates):
```bash
python servers/redfishMockupServer_platform.py --config config/examples/dell_r750_config.json -D mockups/public-rackmount1/
```

## Development Workflow

### 1. Start with Basic Server
```bash
# Test basic functionality first
python servers/redfishMockupServer_modular.py -D mockups/your-mockup/
```

### 2. Add Platform Detection
```bash
# Check what platform is detected
python servers/redfishMockupServer_platform.py --platform-info -D mockups/your-mockup/
```

### 3. Customize Platform Behavior
```bash
# Create platform manifest or configuration
# Add custom platform provider if needed
# Test platform-specific features
```

## Troubleshooting

### Server Won't Start
- Check Python version: `python --version`
- Install dependencies: `pip install -r requirements.txt`
- Verify mockup directory exists and contains `index.json`
- Check port availability: `netstat -ln | grep :8000`

### Platform Not Detected
- Add platform manifest: `{"platform_id": "custom", "platform_type": "custom"}`
- Use explicit platform: `--platform custom`
- Enable verbose logging: `-v`

### OEM Features Not Working
- Verify platform supports the feature
- Check OEM namespace in platform configuration
- Ensure platform provider is correctly implemented

### Performance Issues
- Use smaller mockup directories for development
- Disable verbose logging in production
- Consider using modular server for better performance

## Next Steps

### Learn More
- Read [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for detailed architecture
- Check [PLATFORM_DEVELOPMENT.md](PLATFORM_DEVELOPMENT.md) for creating custom platforms
- Review example configurations in `config/examples/`

### Extend the Server  
- Create custom platform providers
- Add new services and handlers
- Implement vendor-specific OEM actions
- Contribute new platform implementations

### Integration
- Use with Redfish client libraries
- Integrate into test suites
- Deploy in containerized environments
- Set up CI/CD testing workflows

## Support

### Getting Help
- Check existing documentation in the repository
- Review example configurations and platforms
- Enable verbose logging for debugging
- Check GitHub issues for known problems

### Contributing
- Fork the repository
- Create feature branches
- Add tests for new functionality
- Submit pull requests with clear descriptions

This enhanced server provides a solid foundation for Redfish development and testing while maintaining compatibility with existing workflows.