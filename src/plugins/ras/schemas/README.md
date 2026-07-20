# OCPRAS OEM Schemas

This directory contains the schema definitions for the OCP RAS API OEM namespace
(`Oem.OCPRASAPIWS`), aligned with the OCP RAS API Redfish Specification v0.7.

## Files

### `OCPRAS.v1_0_0.json`
JSON Schema format - used for validation and can be served via HTTP at:
- `/redfish/v1/schemas/OCPRAS.v1_0_0.json`

### `OCPRAS_v1.xml`
CSDL (Common Schema Definition Language) format - DMTF standard format:
- Used by OData/Redfish metadata endpoints
- Can be served at `/redfish/v1/$metadata` 

## Schema Contents

The OCPRAS schema defines:

1. **RASService** - Main RAS coordination service
   - Location: `/redfish/v1/Oem/OCPRASAPIWS/RASService`
   - Purpose: Service-root RAS orchestration and error coordination
   - Type: `#OCPRASService.v1_0_0.RASService`

2. **ServiceRootExtension** - OEM extension for the ServiceRoot resource
   - Adds the `RASService` link to `ServiceRoot.Oem.OCPRASAPIWS`
   - Type: `#OCPRASServiceRoot.v1_0_0.ServiceRootExtension`

3. **RASEndpoints** - Collection of RAS endpoints (error sources)
   - Location: `/redfish/v1/Oem/OCPRASAPIWS/RASService/RASEndpoints`
   - Members type: `#OCPRASEndpoint.v1_0_0.RASEndpoint`

4. **SubmitCPAD** - Action for submitting CPAD records
   - Target: `/redfish/v1/Oem/OCPRASAPIWS/RASService/Actions/RASService.SubmitCPAD`
   - Converts CPAD to CPER and creates a LogEntry

## Usage

```python
from schema_registry import SchemaRegistry

# Get full schema
schema = SchemaRegistry.get_schema()

# Get specific definition
ras_service_def = SchemaRegistry.get_schema('RASService')

# Get schema file path
json_path = SchemaRegistry.get_schema_file_path('json')
csdl_path = SchemaRegistry.get_schema_file_path('csdl')
```

## Specification

Aligned with the OCP RAS API Redfish Specification v0.7. The RAS service and its
resources live under the service-root OEM namespace `/redfish/v1/Oem/OCPRASAPIWS`.
