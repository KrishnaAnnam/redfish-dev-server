# RAS Plugin - Phase 1, 2, 3 Integration Complete

## Overview

Successfully integrated RasApi reference implementation into the BMC Redfish Simulator RAS plugin. This integration provides service-root OEM RAS capabilities aligned with the OCP RAS API Redfish Specification v0.7.

## Architecture

```
Service-Root OEM Placement (OCP RAS API v0.7):
/redfish/v1/Oem/OCPRASAPIWS/RASService
```

## Integration Phases Completed

### Phase 1: Core CPAD/Policy Logic ✅

**Files Created:**
- `src/plugins/ras/models/cpad_types.py` - CPAD data structures
- `src/plugins/ras/policy_engine.py` - Policy evaluation engine
- `src/plugins/ras/cpad_handler.py` - CPAD validation and processing

**Capabilities:**
- CPAD document validation
- Policy-based trust verification
- Action authorization
- Platform verification
- Confidence threshold checking

**Source:** Extracted from RasApi-main/policy.py and submit_cpad.py

### Phase 2: Service-Root OEM Integration ✅

**Resources:**
- `src/plugins/ras/discovery.py` - builds the RAS discovery tree dynamically (RASService, RASEndpoints, RASEndpoint, SubmitCPADActionInfo)
- `src/plugins/ras/handlers/submit_cpad_action.py` - SubmitCPAD action handler

**Capabilities:**
- Expose `Oem.OCPRASAPIWS.RASService` from the ServiceRoot
- Serve the RASService resource with RASEndpoints/CPERLogService/EventService links
- Handle SubmitCPAD POST action
- Generate OCPRAS messages for operations
- Track submission history and statistics

**Endpoints:**
- `GET /redfish/v1/Oem/OCPRASAPIWS/RASService`
- `GET /redfish/v1/Oem/OCPRASAPIWS/RASService/RASEndpoints`
- `GET /redfish/v1/Oem/OCPRASAPIWS/RASService/RASEndpoints/{EndpointId}`
- `GET /redfish/v1/Oem/OCPRASAPIWS/RASService/SubmitCPADActionInfo`
- `POST /redfish/v1/Oem/OCPRASAPIWS/RASService/Actions/RASService.SubmitCPAD`

### Phase 3: CPER Analysis (client-side)

CPER analysis is **not** performed by this plugin. The plugin only creates CPER
LogEntries in response to SubmitCPAD; decoding, repeat-detection, and SPPR
generation are done client-side by vendor analyzer plugins (see
`examples/ras_api_demo/analyzers/`). An earlier server-side `cper_analyzer.py`
engine was removed as unused.

## Example Files

Copied from RasApi reference:
- `examples/ras/SpprCpadExample.json` - SPPR (Soft Post Package Repair) CPAD
- `examples/ras/memErrorSpoofCpad.json` - Memory error spoof CPAD

## Policy Registries

Pre-configured with RasApi defaults:

**Trusted Creators:**
- `11111111-2222-3333-4444-555555555555` - Contoso

**Known Actions:**
- `e3b0c442-98fc-1c14-9afc-4c6fbc5a3f2d` - Memory Error Spoof (Low Risk)
- `6730c5e9-5aed-45a6-887d-cecb837403dc` - SPPR Memory Repair (Medium Risk)

**Known Platforms:**
- `990f8820-bd4d-5064-58cc-961a053dea79` - Demo Platform

## Testing the Integration

### 1. Start Server
```bash
# Ensure RAS plugin is enabled in platform config
python servers/redfishMockupServer_platform.py
```

### 2. Get ServiceRoot
```bash
curl -u demo:demo http://localhost:8000/redfish/v1
# Check for Oem.OCPRASAPIWS.RASService link
```

### 3. Get RASService
```bash
curl -u demo:demo http://localhost:8000/redfish/v1/Oem/OCPRASAPIWS/RASService
```

### 4. Submit CPAD
```bash
curl -u demo:demo -X POST http://localhost:8000/redfish/v1/Oem/OCPRASAPIWS/RASService/Actions/RASService.SubmitCPAD \
  -H "Content-Type: application/json" \
  -d @examples/ras/SpprCpadExample.json
```

Expected response:
- **202 Accepted** - CPAD approved by policy, task created
- **403 Forbidden** - CPAD denied by policy
- **400 Bad Request** - CPAD validation failed

## Message Registry Integration

All operations generate OCPRAS messages:
- `OCPRAS.1.0.CPADReceived`
- `OCPRAS.1.0.CPADValidated`
- `OCPRAS.1.0.PolicyEvaluationStarted`
- `OCPRAS.1.0.PolicyCheckPassed`
- `OCPRAS.1.0.PolicyCheckFailed`
- `OCPRAS.1.0.ActionAuthorized`
- `OCPRAS.1.0.ActionDenied`

## Code Structure

```
src/plugins/ras/
├── __init__.py                         # Updated with new imports
├── plugin.py                           # Updated with new handlers
├── models/
│   ├── __init__.py                     # NEW
│   └── cpad_types.py                   # NEW - CPAD data models
├── handlers/
│   ├── __init__.py                     # NEW
│   └── submit_cpad_action.py           # NEW - SubmitCPAD handler
├── policy_engine.py                    # NEW - Policy evaluation
├── cpad_handler.py                     # NEW - CPAD validation
├── schemas/
│   ├── OCPRAS.v1_0_0.json             # Existing
│   └── OCPRAS_v1.xml                  # Existing
├── registries/
│   └── OCPRAS.1.0.0.json              # Existing
├── message_utils.py                    # Existing
├── schema_registry.py                  # Existing
└── schema_validator.py                 # Existing

examples/ras/
├── SpprCpadExample.json                # NEW - SPPR CPAD
└── memErrorSpoofCpad.json              # NEW - Memory error CPAD
```

## Compatibility with RasApi Demo

The integration maintains compatibility with RasApi team's demo workflow:

1. **CPAD Submission** - Same JSON format, same validation
2. **Policy Evaluation** - Same trust/action/platform checks
3. **CPER Analysis** - Compatible with libcper tools (or mock fallback)
4. **Message Format** - OCPRAS message registry aligned

## Next Steps

### Server Integration (Phase 4)
- Wire plugin to server request routing
- Add Manager resource OEM injection hook
- Test end-to-end with real HTTP requests

### CPER Collection (Phase 5)
- Implement error queue management
- Add CPER download endpoints
- Integrate with LogService

### Standardization Work
- Document implementation for DMTF submission
- Create compliance test suite
- Generate API documentation

## Dependencies

**Required:**
- Python 3.8+
- Standard library only (json, pathlib, logging, datetime, dataclasses)

**Optional:**
- CPERgen/libcper - For real CPER analysis (graceful fallback to mock)

## Notes

- All code extracted from RasApi-main and adapted to plugin architecture
- No external Python dependencies added
- Mock CPER data available when libcper unavailable
- Policy registries can be extended via API calls
- Full OCPRAS message integration
- Manager-scoped for pre-standard transparency

## Authors

- Extracted from: OCP RAS API Reference Implementation (RasApi-main)
- Adapted by: BMC Redfish Simulator Team
- Integration Date: 2026-01-22
