# Migration Guide - BMC Redfish Simulator

**Project:** bmc-redfish-simulator  
**Based on:** DMTF Redfish-Mockup-Server

## Overview

This guide helps you migrate from the original DMTF Redfish-Mockup-Server to the enhanced BMC Redfish Simulator architecture. The migration path is designed to be gradual and backward-compatible.

## Migration Paths

### Path 1: Drop-in Replacement (Modular Server)

The modular server is a direct replacement for the original server with identical functionality but improved code organization.

**Original Command:**
```bash
python redfishMockupServer.py -D public-rackmount1 -p 8000
```

**Modular Replacement:**
```bash
python redfishMockupServer_modular.py -D public-rackmount1 -p 8000
```

**Benefits:**
- ✅ Identical API and behavior
- ✅ Improved code maintainability
- ✅ Better performance
- ✅ Enhanced logging
- ✅ No configuration changes needed

### Path 2: Platform-Aware Server (Enhanced)

The platform-aware server adds automatic platform detection and vendor-specific features while maintaining full backward compatibility.

**Enhanced Command:**
```bash
python redfishMockupServer_platform.py -D public-rackmount1 -p 8000
```

**Benefits:**
- ✅ All modular server benefits
- ✅ Automatic platform detection
- ✅ Vendor-specific OEM extensions
- ✅ Enhanced services (EventService, TelemetryService)
- ✅ Plugin architecture for customization
- ✅ Still backward compatible

## Migration Steps

### Step 1: Backup and Test

```bash
# Backup your current setup
cp -r your-mockup-directory your-mockup-directory.backup

# Test original server still works
python redfishMockupServer.py -D your-mockup-directory -p 8001

# Test basic connectivity
curl http://localhost:8001/redfish/v1/
```

### Step 2: Test Modular Server

```bash
# Test modular server with same mockup
python redfishMockupServer_modular.py -D your-mockup-directory -p 8002

# Compare responses (should be identical)
curl http://localhost:8002/redfish/v1/
curl http://localhost:8002/redfish/v1/Systems/
```

### Step 3: Test Platform-Aware Server

```bash
# Test platform-aware server
python redfishMockupServer_platform.py -D your-mockup-directory -p 8003

# Check platform detection
python redfishMockupServer_platform.py --platform-info -D your-mockup-directory

# Test enhanced features
curl http://localhost:8003/redfish/v1/
curl http://localhost:8003/redfish/v1/Systems/*/Oem/  # Check for OEM extensions
```

### Step 4: Gradual Feature Adoption

```bash
# Enable verbose logging to see platform features
python redfishMockupServer_platform.py -D your-mockup-directory -v

# Add platform manifest for explicit platform support
echo '{"platform_id": "custom", "platform_type": "custom"}' > your-mockup-directory/platform_manifest.json
```

## Compatibility Matrix

| Feature | Original | Modular | Platform-Aware |
|---------|----------|---------|----------------|
| Basic Redfish API | ✅ | ✅ | ✅ |
| Authentication | ✅ | ✅ | ✅ |
| Static Responses | ✅ | ✅ | ✅ |
| SSDP Discovery | ✅ | ✅ | ✅ |
| SSL Support | ✅ | ✅ | ✅ |
| Code Organization | ❌ | ✅ | ✅ |
| Enhanced Logging | ❌ | ✅ | ✅ |
| Platform Detection | ❌ | ❌ | ✅ |
| OEM Extensions | ❌ | ❌ | ✅ |
| Plugin Architecture | ❌ | ❌ | ✅ |
| Enhanced Services | ❌ | ❌ | ✅ |

## Configuration Migration

### Original Configuration

The original server used command-line arguments only:

```bash
python redfishMockupServer.py \
    -D /path/to/mockup \
    -p 8000 \
    -H 0.0.0.0 \
    --ssl \
    --cert server.crt \
    --key server.key
```

### Enhanced Configuration

The platform-aware server supports the same arguments plus new features:

```bash
python redfishMockupServer_platform.py \
    -D /path/to/mockup \
    -p 8000 \
    -H 0.0.0.0 \
    --ssl \
    --cert server.crt \
    --key server.key \
    --platform dell \
    --config platform_config.json
```

### Configuration Files

Create optional configuration files for enhanced features:

**Platform Manifest (auto-detection):**
```json
{
    "platform_id": "my_platform",
    "platform_type": "dell_idrac",
    "display_name": "Dell PowerEdge Server",
    "enabled_services": ["EventService", "UpdateService"]
}
```

**Platform Configuration (advanced):**
```json
{
    "platform_id": "dell_r750",
    "system_info": {
        "Manufacturer": "Dell Inc.",
        "Model": "PowerEdge R750"
    },
    "oem_namespace": "Dell",
    "enabled_services": ["EventService", "UpdateService", "TelemetryService"]
}
```

## Migrating Custom Modifications

### If You Modified the Original Server

**Original Modifications:**
```python
# Changes to redfishMockupServer.py
def custom_handler(self, path):
    # Your custom logic
    pass
```

**Modular Migration:**
```python
# Create src/handlers/custom_handler.py
from .base_handler import BaseHandler

class CustomHandler(BaseHandler):
    def handle_request(self, path, method, data=None):
        # Your custom logic
        pass
```

**Platform Migration:**
```python
# Create src/plugins/custom/platform.py
from src.core.interfaces import BasePlatformProvider

class CustomProvider(BasePlatformProvider):
    def register_handlers(self):
        from .handlers import CustomHandler
        self.platform_handlers["custom"] = CustomHandler()
```

### Common Migration Scenarios

#### Custom Authentication
**Before:**
```python
# Modified redfishMockupServer.py
def do_GET(self):
    if not self.custom_auth():
        self.send_error(401)
        return
    # Rest of handler
```

**After:**
```python
# src/handlers/auth_handler.py
class AuthHandler(BaseHandler):
    def authenticate_request(self, headers):
        # Your custom auth logic
        return True
```

#### Custom Responses
**Before:**
```python
# Modified response generation
def send_response_data(self, data):
    data["CustomField"] = "CustomValue"
    # Send response
```

**After:**
```python
# src/plugins/custom/services.py
class CustomResponseService(BasePlatformService):
    def postprocess_response(self, response_data):
        response_data["CustomField"] = "CustomValue"
        return response_data
```

#### Custom Endpoints
**Before:**
```python
# Added endpoints to main server
if path.startswith("/custom/"):
    self.handle_custom_endpoint(path)
```

**After:**
```python
# src/plugins/custom/handlers.py
class CustomEndpointHandler(BasePlatformHandler):
    def get_supported_paths(self):
        return ["/custom/*"]
    
    def handle_get(self, path, query_params=None, cached_links=None):
        # Handle custom endpoint
        return 200, {"Custom": "Response"}
```

## Testing Migration

### Automated Testing Script

```python
#!/usr/bin/env python3
"""Migration testing script"""

import requests
import subprocess
import time
import sys

def start_server(script, port, mockup_dir):
    """Start a server and return the process"""
    cmd = [sys.executable, script, "-D", mockup_dir, "-p", str(port)]
    return subprocess.Popen(cmd)

def test_endpoint(port, endpoint):
    """Test an endpoint and return response"""
    try:
        response = requests.get(f"http://localhost:{port}{endpoint}")
        return response.status_code, response.json()
    except Exception as e:
        return None, str(e)

def compare_responses(original_resp, new_resp, endpoint):
    """Compare responses between servers"""
    if original_resp[0] != new_resp[0]:
        print(f"❌ {endpoint}: Status code mismatch ({original_resp[0]} vs {new_resp[0]})")
        return False
    
    # Compare essential fields (ignore timestamps, etc.)
    essential_fields = ["@odata.id", "@odata.type", "Id", "Name", "Members"]
    
    orig_data = original_resp[1] if original_resp[1] else {}
    new_data = new_resp[1] if new_resp[1] else {}
    
    for field in essential_fields:
        if field in orig_data and field in new_data:
            if orig_data[field] != new_data[field]:
                print(f"❌ {endpoint}: Field {field} mismatch")
                return False
    
    print(f"✅ {endpoint}: Responses match")
    return True

def main():
    mockup_dir = sys.argv[1] if len(sys.argv) > 1 else "public-rackmount1"
    
    # Test endpoints
    endpoints = [
        "/redfish/v1/",
        "/redfish/v1/Systems/",
        "/redfish/v1/Managers/",
        "/redfish/v1/Chassis/",
        "/redfish/v1/EventService/"
    ]
    
    # Start servers
    original = start_server("redfishMockupServer.py", 8001, mockup_dir)
    modular = start_server("redfishMockupServer_modular.py", 8002, mockup_dir)
    platform = start_server("redfishMockupServer_platform.py", 8003, mockup_dir)
    
    time.sleep(3)  # Let servers start
    
    try:
        print("Testing migration compatibility...\n")
        
        for endpoint in endpoints:
            print(f"Testing {endpoint}:")
            
            # Get responses
            orig_resp = test_endpoint(8001, endpoint)
            mod_resp = test_endpoint(8002, endpoint)
            plat_resp = test_endpoint(8003, endpoint)
            
            # Compare
            compare_responses(orig_resp, mod_resp, f"  Original vs Modular")
            compare_responses(orig_resp, plat_resp, f"  Original vs Platform")
            
            print()
    
    finally:
        # Cleanup
        original.terminate()
        modular.terminate()
        platform.terminate()

if __name__ == "__main__":
    main()
```

### Run Migration Tests

```bash
# Make script executable
chmod +x scripts/test_migration.py

# Run migration tests
python scripts/test_migration.py your-mockup-directory
```

## Troubleshooting Migration

### Common Issues

#### Port Conflicts
**Problem:** Server won't start on desired port
**Solution:**
```bash
# Check what's using the port
netstat -ln | grep :8000

# Use different port
python redfishMockupServer_platform.py -D mockup/ -p 8080
```

#### Platform Not Detected
**Problem:** Platform-aware server doesn't detect platform
**Solution:**
```bash
# Check platform detection
python redfishMockupServer_platform.py --platform-info -D mockup/

# Add explicit platform manifest
echo '{"platform_id": "generic", "platform_type": "generic"}' > mockup/platform_manifest.json

# Or specify platform explicitly
python redfishMockupServer_platform.py --platform generic -D mockup/
```

#### Response Differences
**Problem:** Responses differ between servers
**Solution:**
```bash
# Enable debug logging
python redfishMockupServer_platform.py -D mockup/ -v

# Compare specific endpoints
curl http://localhost:8000/redfish/v1/ | jq .
curl http://localhost:8001/redfish/v1/ | jq .
```

#### Performance Issues
**Problem:** New server is slower
**Solution:**
```bash
# Disable verbose logging
python redfishMockupServer_platform.py -D mockup/ -q

# Use modular server if platform features not needed
python redfishMockupServer_modular.py -D mockup/
```

## Rollback Plan

### Emergency Rollback

If issues arise, you can immediately rollback:

```bash
# Stop new server
pkill -f redfishMockupServer_platform

# Start original server
python redfishMockupServer.py -D your-mockup-directory -p 8000
```

### Gradual Rollback

```bash
# Step 1: Move to modular server (keeps improvements, removes platform features)
python redfishMockupServer_modular.py -D mockup/ -p 8000

# Step 2: If still issues, use original
python redfishMockupServer.py -D mockup/ -p 8000
```

## Migration Timeline

### Week 1: Testing Phase
- Deploy modular server in test environment
- Run compatibility tests
- Verify all existing functionality works

### Week 2: Staging Deployment  
- Deploy platform-aware server in staging
- Test platform detection with your mockup data
- Verify enhanced features work as expected

### Week 3: Production Migration
- Deploy to production with monitoring
- Keep original server as backup
- Monitor for any issues or performance changes

### Week 4: Optimization
- Enable platform-specific features
- Add custom platform providers if needed
- Optimize configuration for your use case

## Best Practices for Migration

### Before Migration
- ✅ Document your current configuration
- ✅ Test all existing endpoints
- ✅ Backup mockup directories
- ✅ Note any custom modifications

### During Migration
- ✅ Test in non-production first
- ✅ Run both servers in parallel initially
- ✅ Monitor logs for errors
- ✅ Validate critical endpoints

### After Migration  
- ✅ Monitor performance metrics
- ✅ Enable new features gradually
- ✅ Update documentation
- ✅ Train team on new capabilities

This migration guide ensures a smooth transition while preserving all existing functionality and enabling new platform-aware features.