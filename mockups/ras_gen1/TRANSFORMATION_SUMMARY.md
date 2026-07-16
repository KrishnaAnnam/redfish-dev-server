# RAS GEN_10 Mockup Transformation Summary

## Overview
This mockup was inherited from the official RAS API team's GEN_10 reference implementation and transformed to match our BMC simulator's Manager OEM architecture.

## Source
- **Original Location**: `references/RasApi-main/GEN_10`
- **Developed By**: RAS API team (official reference implementation)
- **Transformation Date**: January 22, 2026

## Transformation Applied

### 1. Directory Structure Change
**Before (Standalone):**
```
redfish/v1/RASService/
```

**After (Manager OEM):**
```
redfish/v1/Managers/System/Oem/RasProto/RASService/
```

### 2. Path Transformations
All JSON files were updated to replace:
- **Old**: `/redfish/v1/RASService`
- **New**: `/redfish/v1/Managers/System/Oem/RasProto/RASService`

**Files Transformed**: 11 JSON files
- Main RASService resource
- Endpoints collection and members
- Reporting queues (Corrected, Uncorrected, Fatal, Deferred, Informational, OOB_UncorrectedFatal)
- ErrorRecord samples

### 3. Manager Resource Update
Added RasProto OEM extension to `/redfish/v1/Managers/System/index.json`:

```json
"Oem": {
  "RasProto": {
    "@odata.type": "#RasProto.v1_0_0.ManagerExtension",
    "RASService": {
      "@odata.id": "/redfish/v1/Managers/System/Oem/RasProto/RASService"
    }
  }
}
```

## Directory Structure

```
ras_gen1/redfish/v1/
├── Managers/
│   └── System/
│       ├── index.json (updated with RasProto OEM)
│       └── Oem/
│           └── RasProto/
│               └── RASService/
│                   ├── index.json
│                   ├── Endpoints/
│                   │   ├── index.json
│                   │   └── Endpoint-1/
│                   │       └── index.json
│                   └── Reporting/
│                       ├── index.json
│                       ├── Corrected/index.json
│                       ├── Uncorrected/index.json
│                       ├── Fatal/index.json
│                       ├── Deferred/index.json
│                       ├── Informational/index.json
│                       ├── OOB_UncorrectedFatal/index.json
│                       └── ErrorRecord-001/index.json
└── [Other GEN_10 resources: Systems, Chassis, etc.]
```

## Usage with Simulator

### Starting the Server
```bash
cd /home/hari/Tools/bmc-redfish-simulator
python3 servers/redfishMockupServer_platform.py -D mockups/ras_gen1/redfish
```

### Accessing RASService
```bash
# Get RASService resource
curl http://localhost:8000/redfish/v1/Managers/System/Oem/RasProto/RASService

# Get Endpoints
curl http://localhost:8000/redfish/v1/Managers/System/Oem/RasProto/RASService/Endpoints

# Get Reporting queues
curl http://localhost:8000/redfish/v1/Managers/System/Oem/RasProto/RASService/Reporting

# Submit CPAD action
curl -X POST http://localhost:8000/redfish/v1/Managers/System/Oem/RasProto/RASService/Actions/RASService.SubmitCPAD \
  -H "Content-Type: application/json" \
  -d @cpad_payload.json
```

## Key Features Inherited

### RASService Resource
- Service discovery and status
- Endpoints management
- Reporting queues (multiple severity levels)
- CPAD submission action

### Endpoints Collection
- Endpoint registration
- Endpoint-1 example with full configuration
- CollectionCapabilities for dynamic creation

### Reporting Queues
- **Corrected**: Correctable errors
- **Uncorrected**: Uncorrectable non-fatal errors
- **Fatal**: Fatal errors
- **Deferred**: Deferred error handling
- **Informational**: Informational events
- **OOB_UncorrectedFatal**: Out-of-band fatal errors

### Error Records
- CPER-compliant error record format
- Sample ErrorRecord-001 for reference

## Integration with Plugin

The transformed mockup aligns with our RAS plugin implementation:
- Manager OEM injection pattern
- SubmitCPAD action handler
- RASService resource builder
- Path routing under `/redfish/v1/Managers/*/Oem/RasProto/*`

## Maintenance Notes

- **Upstream Updates**: When RAS API team releases new GEN_10 versions, re-run transformation
- **Transformation Script**: `mockups/transform_ras_paths.py`
- **Manager ID**: Currently uses "System" - can be adapted for other Manager IDs (BMC, etc.)
- **Compatibility**: Mockup structure matches RAS API v1.0.0 specification

## Verification

All paths verified to use Manager OEM structure:
```bash
grep -r '"/redfish/v1/RASService' mockups/ras_gen1/
# Should return no results - all transformed
```

## Related Files
- Plugin implementation: `src/plugins/ras/`
- Integration tests: `examples/ras/test_server_integration.py`
- Transformation script: `mockups/transform_ras_paths.py`
