# RASService Mockup - Plugin Model

This mockup is aligned with the RAS plugin implementation at `src/plugins/ras/`.

## Current Implementation

The plugin currently implements:

### ✅ Core Resources
- **RASService** - Main service resource with Governance metadata
- **SubmitCPAD Action** - CPAD submission endpoint
- **SubmitCPADActionInfo** - Action metadata

### 🚧 Future Features (in mockup but not yet in plugin)
- **Endpoints/** - RAS endpoint registration (Phase 5+)
- **Reporting/** - Error queue management (Phase 5+)

## Plugin Handlers

The mockup JSON structure matches these handlers:

1. **manager_extension.py**
   - `build_ras_service_resource()` → RASService/index.json
   - `build_submit_cpad_action_info()` → SubmitCPADActionInfo/index.json
   - `build_ras_service()` → Manager Oem injection

2. **submit_cpad_action.py**
   - `handle_post()` → Processes CPAD submissions
   - Returns Redfish messages (not static JSON)

## Schema Differences

**RAS API Team (GEN_10):**
- Uses `#RASService.v1_0_0.RASService` (official schema)
- Includes Endpoints and Reporting collections
- Action: `#RASService.SubmitCPAD`

**Our Plugin (RasProto):**
- Uses `#RasProto.v1_0_0.RASService` (pre-standard)
- Governance metadata for standardization transparency
- Action: `#RasProto.SubmitCPAD`
- Focus on CPAD/Policy/CPER (Phases 1-4)

## Testing

```bash
# Start server with plugin
cd /home/hari/Tools/bmc-redfish-simulator
python3 servers/redfishMockupServer_platform.py \
  -D mockups/ras_gen1/redfish \
  --enable-plugin ras

# Test RASService
curl http://localhost:8000/redfish/v1/Managers/System
curl http://localhost:8000/redfish/v1/Managers/System/Oem/RasProto/RASService

# Test SubmitCPAD
curl -X POST \
  http://localhost:8000/redfish/v1/Managers/System/Oem/RasProto/RASService/Actions/RasProto.SubmitCPAD \
  -H "Content-Type: application/json" \
  -d @examples/ras/sample_cpad.json
```

## Directory Structure

```
RASService/
├── index.json               # Main resource (matches plugin)
├── SubmitCPADActionInfo/    # Action metadata (matches plugin)
│   └── index.json
├── Endpoints/               # Future (not in plugin yet)
│   ├── index.json
│   └── Endpoint-1/
└── Reporting/               # Future (not in plugin yet)
    ├── index.json
    ├── Corrected/
    ├── Uncorrected/
    ├── Fatal/
    └── ...
```

## Migration Notes

When implementing Phases 5-7:
1. Plugin handlers will generate Endpoints and Reporting dynamically
2. Mockup structure provides reference for response format
3. Update this README when plugin implements these features
