# RasProto OEM Schemas

This directory contains the schema definitions for the RasProto OEM namespace.

## Files

### `RasProto.v1_0_0.json`
JSON Schema format - used for validation and can be served via HTTP at:
- `/redfish/v1/schemas/RasProto.v1_0_0.json`

### `RasProto_v1.xml`
CSDL (Common Schema Definition Language) format - DMTF standard format:
- Used by OData/Redfish metadata endpoints
- Can be served at `/redfish/v1/$metadata` 

## Schema Contents

The RasProto schema defines:

1. **RASService** - Main RAS coordination service
   - Location: `/redfish/v1/Managers/{ManagerId}/Oem/RasProto/RASService`
   - Purpose: Manager-scoped RAS orchestration and error coordination

2. **Governance** - Pre-standard governance metadata
   - Ownership, specification version, standardization intent
   - Provides transparency about experimental status

3. **ManagerExtension** - OEM extension for Manager resource
   - Adds RASService link to Manager.Oem.RasProto

4. **SubmitCPAD** - Action for submitting CPAD records
   - Converts CPAD to CPER and creates LogEntry

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

## Standardization Path

Current: `/redfish/v1/Managers/{ManagerId}/Oem/RasProto/RASService`  
Target:  `/redfish/v1/Managers/{ManagerId}/RASService` (after DMTF acceptance)
