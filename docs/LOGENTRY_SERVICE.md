# LogEntry Service - POST/PATCH with EventService Integration

## Overview

The BMC Redfish Simulator now supports dynamic creation and modification of LogEntry resources through POST and PATCH operations. When LogEntry resources are created or modified, the system automatically:

1. **Persists to Mockup Tree**: New/modified LogEntry resources are written to the appropriate directory structure
2. **Triggers EventService Notifications**: Automatically generates and sends events to subscribed clients
3. **Maintains Collections**: Updates LogEntry collections with proper member counts

## Supported Operations

### POST - Create LogEntry

**Endpoint**: `POST /redfish/v1/Managers/{ManagerId}/LogServices/{LogServiceId}/Entries`

**Required Fields**:
- `Message` (string): The log message
- `Severity` (string): Log severity (Critical, Warning, OK, etc.)

**Optional Fields**:
- `EntryType` (string): Type of entry (default: "Event")
- `MessageId` (string): Standardized message identifier
- `MessageArgs` (array): Arguments for the message template
- `Resolution` (string): Recommended resolution
- `Resolved` (boolean): Whether the issue is resolved
- `SensorNumber` (integer): Associated sensor number
- `SensorType` (string): Type of sensor
- `OriginOfCondition` (string): URI of the resource that caused the log entry
- `AdditionalDataURI` (string): URI to additional data

**Example Request**:
```json
POST /redfish/v1/Managers/BMC/LogServices/Log/Entries
{
    "Message": "System temperature exceeded critical threshold",
    "Severity": "Critical",
    "EntryType": "Event",
    "MessageId": "Thermal.1.0.TempCritical",
    "MessageArgs": ["88°C", "CPU1"],
    "OriginOfCondition": "/redfish/v1/Chassis/1U/Thermal/Temperatures/1"
}
```

**Response** (201 Created):
```json
{
    "Created": "/redfish/v1/Managers/BMC/LogServices/Log/Entries/2",
    "LogEntry": {
        "@odata.context": "/redfish/v1/$metadata#LogEntry.LogEntry",
        "@odata.type": "#LogEntry.v1_14_0.LogEntry",
        "@odata.id": "/redfish/v1/Managers/BMC/LogServices/Log/Entries/2",
        "Id": "2",
        "Name": "Log Entry 2",
        "Created": "2024-11-11T10:30:00Z",
        "EntryType": "Event",
        "Message": "System temperature exceeded critical threshold",
        "Severity": "Critical",
        "MessageId": "Thermal.1.0.TempCritical",
        "MessageArgs": ["88°C", "CPU1"],
        "Links": {
            "OriginOfCondition": {
                "@odata.id": "/redfish/v1/Chassis/1U/Thermal/Temperatures/1"
            },
            "Oem": {}
        },
        "Oem": {}
    }
}
```

### PATCH - Modify LogEntry

**Endpoint**: `PATCH /redfish/v1/Managers/{ManagerId}/LogServices/{LogServiceId}/Entries/{EntryId}`

**Modifiable Fields**:
- `Message`: Update the log message
- `Severity`: Change severity level
- `Resolution`: Add/update resolution text
- `Resolved`: Mark entry as resolved/unresolved

**Example Request**:
```json
PATCH /redfish/v1/Managers/BMC/LogServices/Log/Entries/2
{
    "Severity": "OK",
    "Resolution": "Temperature returned to normal range",
    "Resolved": true,
    "Message": "System temperature critical condition resolved"
}
```

**Response** (200 OK):
```json
{
    "Updated": "/redfish/v1/Managers/BMC/LogServices/Log/Entries/2",
    "ModifiedFields": ["Severity", "Resolution", "Resolved", "Message"],
    "LogEntry": {
        "@odata.context": "/redfish/v1/$metadata#LogEntry.LogEntry",
        "@odata.type": "#LogEntry.v1_14_0.LogEntry",
        "@odata.id": "/redfish/v1/Managers/BMC/LogServices/Log/Entries/2",
        "Id": "2",
        "Name": "Log Entry 2",
        "Created": "2024-11-11T10:30:00Z",
        "Modified": "2024-11-11T10:35:00Z",
        "EntryType": "Event",
        "Message": "System temperature critical condition resolved",
        "Severity": "OK",
        "Resolution": "Temperature returned to normal range",
        "Resolved": true,
        "MessageId": "Thermal.1.0.TempCritical",
        "MessageArgs": ["88°C", "CPU1"],
        "Links": {
            "OriginOfCondition": {
                "@odata.id": "/redfish/v1/Chassis/1U/Thermal/Temperatures/1"
            },
            "Oem": {}
        },
        "Oem": {}
    }
}
```

## EventService Integration

When LogEntry resources are created or modified, the system automatically generates events and sends them to all active EventService subscriptions.

### LogEntry Creation Event

```json
{
    "EventType": "Alert",
    "EventId": "LogEntry.Created.2",
    "EventTimestamp": "2024-11-11T10:30:00Z",
    "Severity": "Critical",
    "Message": "New log entry created: System temperature exceeded critical threshold",
    "MessageId": "LogEntry.1.0.LogEntryCreated",
    "MessageArgs": ["2", "System temperature exceeded critical threshold"],
    "OriginOfCondition": {
        "@odata.id": "/redfish/v1/Managers/BMC/LogServices/Log/Entries/2"
    }
}
```

### LogEntry Modification Event

```json
{
    "EventType": "ResourceUpdated",
    "EventId": "LogEntry.Modified.2", 
    "EventTimestamp": "2024-11-11T10:35:00Z",
    "Severity": "OK",
    "Message": "Log entry modified: Severity, Resolution, Resolved, Message",
    "MessageId": "LogEntry.1.0.LogEntryModified",
    "MessageArgs": ["2", "Severity, Resolution, Resolved, Message"],
    "OriginOfCondition": {
        "@odata.id": "/redfish/v1/Managers/BMC/LogServices/Log/Entries/2"
    }
}
```

## Mockup Tree Structure

The LogEntry service automatically maintains the proper file system structure:

```
mockups/public-rackmount1/
├── Managers/
│   └── BMC/
│       └── LogServices/
│           └── Log/
│               ├── index.json                    # LogService resource
│               └── Entries/
│                   ├── index.json               # LogEntryCollection (updated)
│                   ├── 1/
│                   │   └── index.json           # LogEntry 1
│                   ├── 2/                       # Created dynamically
│                   │   └── index.json           # LogEntry 2 (NEW)
│                   └── 3/                       # Created dynamically  
│                       └── index.json           # LogEntry 3 (NEW)
```

## Usage Examples

### Basic LogEntry Creation

```bash
# Create a simple error log
curl -X POST http://localhost:8000/redfish/v1/Managers/BMC/LogServices/Log/Entries \
  -H "Content-Type: application/json" \
  -d '{
    "Message": "Power supply failure detected",
    "Severity": "Critical",
    "MessageId": "Power.1.0.PSUFailure"
  }'
```

### Resolve a LogEntry

```bash
# Mark a log entry as resolved
curl -X PATCH http://localhost:8000/redfish/v1/Managers/BMC/LogServices/Log/Entries/2 \
  -H "Content-Type: application/json" \
  -d '{
    "Resolved": true,
    "Resolution": "Power supply replaced",
    "Severity": "OK"
  }'
```

### EventService Subscription

```bash
# Create subscription to receive LogEntry events
curl -X POST http://localhost:8000/redfish/v1/EventService/Subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "Destination": "http://my-server:8080/events",
    "Protocol": "Redfish",
    "EventTypes": ["Alert", "ResourceUpdated"]
  }'
```

## Key Features

### ✅ **Dynamic Resource Creation**
- LogEntry resources are created in real-time
- File system structure is maintained automatically
- Collections are updated with proper member counts

### ✅ **Event Integration** 
- Automatic event generation for LogEntry operations
- Events sent to all active EventService subscriptions
- Configurable event types and message formats

### ✅ **Standards Compliance**
- Follows Redfish LogEntry schema v1.14.0
- Proper HTTP status codes and responses
- Validation of required fields

### ✅ **Persistence**
- All LogEntry resources persist to the mockup tree
- Survives server restarts
- Can be manually edited via JSON files

### ✅ **Flexibility**
- Support for multiple LogService instances
- Configurable message formats and severity levels
- Extensible for custom OEM properties

## Error Handling

The service provides comprehensive error handling:

### 400 Bad Request
- Missing required fields (`Message`, `Severity`)
- Invalid JSON in request body

### 404 Not Found  
- LogService or LogEntry resource doesn't exist
- Invalid collection path

### 405 Method Not Allowed
- PATCH on LogEntry collections (only individual entries)

### 500 Internal Server Error
- File system errors
- JSON serialization issues

## Implementation Notes

1. **Thread Safety**: LogEntry operations are thread-safe for concurrent requests
2. **ID Generation**: LogEntry IDs are automatically generated and unique per LogService
3. **Caching**: Updated resources are cached for improved performance  
4. **Event Delivery**: Events are delivered asynchronously to avoid blocking responses
5. **File Permissions**: Ensure the simulator has write permissions to the mockup directory

This implementation demonstrates the power of the BMC Redfish Simulator's architecture where the mockup tree serves as both the data store and API structure, enabling dynamic resource management with full EventService integration.