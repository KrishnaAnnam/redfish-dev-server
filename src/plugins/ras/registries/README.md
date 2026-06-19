# OCPRAS Message Registry

This directory contains the Redfish Message Registry for OCP RAS operations.

## Registry File

**`OCPRAS.1.0.0.json`** - Redfish MessageRegistry v1.6.2 format

- **RegistryPrefix**: OCPRAS
- **RegistryVersion**: 1.0.0
- **OwningEntity**: OCP (Open Compute Project)
- **Messages**: 31 RAS-specific messages

## Message Categories

### Error Detection (4 messages)
- CorrectedMemoryError
- CorrectedPCIeError
- DeferredError
- FatalError

### CPER Lifecycle (5 messages)
- CPERRecordCreated
- CPERRecordAvailable
- CPERRecordRetrieved
- CPERRecordDeleted
- CPERQueueFull

### CPAD Actions (6 messages)
- CPADReceived
- CPADValidated
- CPADValidationFailed
- CPADActionStarted
- CPADActionCompleted
- CPADActionFailed

### Repair Operations (6 messages)
- PPRInitiated
- PPRCompleted
- SPPRInitiated
- SPPRCompleted
- MemorySpared
- ComponentIsolated

### Policy & Trust (5 messages)
- PolicyCheckPassed
- PolicyCheckFailed
- UntrustedCreator
- UnauthorizedPlatform
- PolicyOverride

### Endpoint/Initiator (5 messages)
- EndpointRegistered
- EndpointRemoved
- EndpointUnresponsive
- InitiatorConnected
- InitiatorDisconnected

## Usage

### Python API

```python
from message_utils import OCPRASMessages, cper_created, cpad_received

# Format a message
msg = cper_created("CPER-001", "Corrected")
# Returns: {
#   "MessageId": "OCPRAS.1.0.0.CPERRecordCreated",
#   "Message": "CPER record CPER-001 created in Corrected queue.",
#   "Severity": "OK",
#   ...
# }

# Create a LogEntry
entry = OCPRASMessages.create_log_entry(
    "CPADActionCompleted",
    "MemoryRepair"
)
```

### EventService Integration

Clients can subscribe to OCPRAS messages:

```json
{
  "Destination": "https://listener.example.com/events",
  "RegistryPrefixes": ["OCPRAS"],
  "MessageIds": [
    "OCPRAS.1.0.0.CPADReceived",
    "OCPRAS.1.0.0.CPADActionCompleted"
  ]
}
```

### Serving the Registry

The registry should be available at:

```
GET /redfish/v1/Registries/OCPRAS/OCPRAS.1.0.0
```

Returns the complete message registry JSON.

## Relationship to DMTF Registries

OCPRAS complements standard DMTF registries:

- **Platform.1.3.x** - Hardware error detection
- **ResourceEvent.1.4.x** - Resource state changes
- **Base.1.x.x** - General Redfish operations

Use OCPRAS for RAS workflow events (CPER/CPAD lifecycle, policy, repair operations).
Use DMTF registries for hardware events and resource state.

## Standards Alignment

- Follows Redfish MessageRegistry v1.6.2 schema
- Compatible with Redfish LogService and EventService
- Designed for OCP Hardware Management RAS standardization path
