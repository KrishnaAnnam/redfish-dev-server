# Action Handlers - Complete Guide

## Overview

Action Handlers in the BMC Redfish Simulator provide a powerful way to implement Redfish actions that can:

1. **Execute Business Logic**: Perform specific operations like resets, diagnostics, firmware updates
2. **Validate Parameters**: Check action parameters against allowable values  
3. **Update Resource State**: Modify resource properties based on action results
4. **Persist Changes**: Save updated resource data to the mockup tree
5. **Trigger Events**: Generate EventService notifications for action completion
6. **Return Results**: Provide detailed action results and status

## Architecture

### Components

```
POST Request → PostHandler → CustomActionsService → Action Handler → Resource Update → Event Trigger
     ↓              ↓              ↓                    ↓               ↓              ↓
 Action Data → Route to Action → Validate & Execute → Update JSON → Save to File → Notify Subscribers
```

### Key Files

- **`src/services/custom_actions_service.py`**: Core action handling service
- **`src/handlers/post_handler.py`**: HTTP POST routing to actions
- **`mockups/public-rackmount1/**/*.json`**: Mockup resources with action definitions

## How to Create a New Action Handler

### Step 1: Define Action in Mockup Resource

Add the action definition to your resource's JSON file:

```json
{
    "@odata.type": "#ComputerSystem.v1_17_0.ComputerSystem",
    "Id": "System1",
    "Name": "Server System",
    "PowerState": "On",
    "Actions": {
        "#ComputerSystem.Reset": {
            "target": "/redfish/v1/Systems/System1/Actions/ComputerSystem.Reset",
            "ResetType@Redfish.AllowableValues": [
                "On", "ForceOff", "GracefulShutdown", "GracefulRestart", "ForceRestart", "PowerCycle"
            ]
        },
        "#ComputerSystem.MyCustomAction": {
            "target": "/redfish/v1/Systems/System1/Actions/ComputerSystem.MyCustomAction",
            "Parameter1@Redfish.AllowableValues": ["Mode1", "Mode2", "Mode3"],
            "Parameter2": {
                "Type": "Integer",
                "Minimum": 1,
                "Maximum": 100
            }
        }
    }
}
```

### Step 2: Implement Action Handler

Add your action handler to `CustomActionsService`:

```python
# In src/services/custom_actions_service.py

def __init__(self, server_config):
    # ... existing code ...
    self.action_handlers = {
        # ... existing handlers ...
        'ComputerSystem.MyCustomAction': self._handle_my_custom_action,
    }

def _handle_my_custom_action(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                           resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
    """Handle ComputerSystem.MyCustomAction"""
    
    # 1. Extract and validate parameters
    param1 = data_received.get('Parameter1')
    param2 = data_received.get('Parameter2', 50)  # Default value
    
    # Validate Parameter1
    if param1 not in ['Mode1', 'Mode2', 'Mode3']:
        return 400, {}, {
            "error": "Invalid Parameter1",
            "validValues": ['Mode1', 'Mode2', 'Mode3']
        }
    
    # Validate Parameter2  
    if not isinstance(param2, int) or param2 < 1 or param2 > 100:
        return 400, {}, {
            "error": "Parameter2 must be an integer between 1 and 100"
        }
    
    # 2. Perform action logic
    action_result = {
        "ActionId": f"custom_{int(time.time())}",
        "Status": "Completed",
        "ExecutedMode": param1,
        "ProcessedValue": param2,
        "StartTime": datetime.utcnow().isoformat() + 'Z',
        "Duration": "PT5S",  # 5 seconds
        "CustomResults": {
            "ProcessedItems": param2 * 2,
            "Mode": param1,
            "Success": True
        }
    }
    
    # 3. Update resource state
    resource_data['LastCustomAction'] = action_result
    resource_data['CustomActionCount'] = resource_data.get('CustomActionCount', 0) + 1
    
    # Update status if needed
    if param1 == 'Mode1':
        resource_data['CustomState'] = 'Enhanced'
    elif param1 == 'Mode2': 
        resource_data['CustomState'] = 'Standard'
    else:
        resource_data['CustomState'] = 'Basic'
    
    # 4. Save updated resource
    self._update_resource_data(resource_path, resource_data, cached_links)
    
    # 5. Trigger event notification
    self._trigger_action_event('ComputerSystem.MyCustomAction', resource_path, data_received, 'Success')
    
    # 6. Return success response
    return 200, {}, action_result
```

### Step 3: Test Your Action

```bash
# Test the new action
curl -X POST http://localhost:8000/redfish/v1/Systems/System1/Actions/ComputerSystem.MyCustomAction \
  -H "Content-Type: application/json" \
  -d '{
    "Parameter1": "Mode2",
    "Parameter2": 75
  }'
```

**Expected Response (200 OK):**
```json
{
  "ActionId": "custom_1699123456",
  "Status": "Completed",
  "ExecutedMode": "Mode2", 
  "ProcessedValue": 75,
  "StartTime": "2024-11-11T12:30:00Z",
  "Duration": "PT5S",
  "CustomResults": {
    "ProcessedItems": 150,
    "Mode": "Mode2",
    "Success": true
  }
}
```

## Built-in Action Handlers

The simulator includes several pre-implemented action handlers:

### System Actions

#### `ComputerSystem.Reset`
Resets a computer system with various reset types.

**Parameters:**
- `ResetType` (required): Type of reset to perform
  - Valid values: `On`, `ForceOff`, `GracefulShutdown`, `GracefulRestart`, `ForceRestart`, `PowerCycle`

**Example:**
```bash
curl -X POST http://localhost:8000/redfish/v1/Systems/System1/Actions/ComputerSystem.Reset \
  -H "Content-Type: application/json" \
  -d '{"ResetType": "GracefulRestart"}'
```

**Effects:**
- Updates system `PowerState`
- Sets `LastResetTime` timestamp
- Triggers `ActionCompleted` event

### TestService Actions

#### `TestService.Reset`
Resets the test service with custom behavior.

**Parameters:**
- `ResetType` (optional): Type of reset (default: `GracefulRestart`)

**Example:**
```bash
curl -X POST http://localhost:8000/redfish/v1/TestService/Actions/TestService.Reset \
  -H "Content-Type: application/json" \
  -d '{"ResetType": "PowerCycle"}'
```

#### `TestService.RunDiagnostic` 
Runs diagnostic tests on the service.

**Parameters:**
- `DiagnosticType` (required): Type of diagnostic
  - Valid values: `Quick`, `Extended`, `Full`
- `Timeout` (optional): Timeout in seconds (1-3600, default: 300)

**Example:**
```bash
curl -X POST http://localhost:8000/redfish/v1/TestService/Actions/TestService.RunDiagnostic \
  -H "Content-Type: application/json" \
  -d '{
    "DiagnosticType": "Full",
    "Timeout": 600
  }'
```

**Effects:**
- Adds diagnostic result to resource
- Updates resource status
- Returns detailed test results

### Battery Actions

#### `Battery.SelfTest`
Runs self-test on battery module.

**Parameters:** None

**Example:**
```bash
curl -X POST http://localhost:8000/redfish/v1/Chassis/1U/PowerSubsystem/Batteries/Module1/Actions/Battery.SelfTest
```

**Effects:**
- Adds test result to battery resource
- Updates battery health status
- Sets `LastTestTime`

### Custom OEM Actions

#### `Oem.CustomDiagnostic`
Performs custom OEM-specific diagnostic.

**Parameters:**
- `TargetComponent` (required): Component to test
- `TestLevel` (required): Level of testing

**Example:**
```bash
curl -X POST http://localhost:8000/redfish/v1/TestService/Actions/Oem.CustomDiagnostic \
  -H "Content-Type: application/json" \
  -d '{
    "TargetComponent": "PowerSupply",
    "TestLevel": "Comprehensive"
  }'
```

## Action Handler Patterns

### Parameter Validation Pattern

```python
def _handle_my_action(self, action_path, resource_path, data_received, resource_data, cached_links):
    # 1. Extract parameters
    param1 = data_received.get('RequiredParam')
    param2 = data_received.get('OptionalParam', 'default')
    
    # 2. Validate required parameters
    if param1 is None:
        return 400, {}, {"error": "RequiredParam is missing"}
    
    # 3. Validate parameter values
    if param1 not in ['Value1', 'Value2']:
        return 400, {}, {
            "error": f"Invalid RequiredParam: {param1}",
            "validValues": ['Value1', 'Value2']
        }
    
    # 4. Validate parameter ranges
    if isinstance(param2, int) and (param2 < 1 or param2 > 100):
        return 400, {}, {"error": "OptionalParam must be between 1 and 100"}
    
    # ... continue with action logic
```

### Resource Update Pattern

```python
def _handle_my_action(self, action_path, resource_path, data_received, resource_data, cached_links):
    # ... validation and logic ...
    
    # Update resource properties
    resource_data['Status']['Health'] = 'OK'
    resource_data['LastActionTime'] = datetime.utcnow().isoformat() + 'Z'
    resource_data['ActionHistory'] = resource_data.get('ActionHistory', [])
    
    # Add action to history
    action_record = {
        "ActionName": "MyAction",
        "Timestamp": resource_data['LastActionTime'],
        "Parameters": data_received,
        "Result": "Success"
    }
    resource_data['ActionHistory'].append(action_record)
    
    # Keep only last 10 actions
    if len(resource_data['ActionHistory']) > 10:
        resource_data['ActionHistory'] = resource_data['ActionHistory'][-10:]
    
    # Save changes
    self._update_resource_data(resource_path, resource_data, cached_links)
```

### Async Action Pattern (for long-running operations)

```python
def _handle_long_action(self, action_path, resource_path, data_received, resource_data, cached_links):
    # Create task for long-running operation
    task_id = f"task_{int(time.time())}"
    
    # Add task to resource
    resource_data['ActiveTasks'] = resource_data.get('ActiveTasks', [])
    task = {
        "TaskId": task_id,
        "Status": "Running",
        "StartTime": datetime.utcnow().isoformat() + 'Z',
        "Action": "LongRunningAction",
        "Progress": 0
    }
    resource_data['ActiveTasks'].append(task)
    
    # Save initial state
    self._update_resource_data(resource_path, resource_data, cached_links)
    
    # Return 202 Accepted with task location
    return 202, {
        "Location": f"{resource_path}/Tasks/{task_id}"
    }, {
        "TaskId": task_id,
        "Status": "Running",
        "Message": "Long running action started"
    }
```

## Error Handling

### Standard Error Responses

```python
# 400 Bad Request - Invalid parameters
return 400, {}, {
    "error": "Invalid parameter value",
    "parameter": "ResetType", 
    "validValues": ["On", "ForceOff", "GracefulRestart"]
}

# 404 Not Found - Action not supported
return 404, {}, {
    "error": "Action not supported by this resource",
    "action": "ComputerSystem.NonExistentAction"
}

# 409 Conflict - Resource state conflict  
return 409, {}, {
    "error": "Cannot reset system while firmware update is in progress",
    "currentState": "FirmwareUpdating"
}

# 500 Internal Server Error - Unexpected error
return 500, {}, {
    "error": "Internal server error during action execution",
    "details": str(exception)
}
```

## EventService Integration

Actions automatically trigger EventService notifications:

```python
# Automatic event generation
self._trigger_action_event('ComputerSystem.Reset', resource_path, data_received, 'Success')
```

**Generated Event:**
```json
{
    "EventType": "ActionCompleted",
    "EventId": "Action.ComputerSystem.Reset.1699123456",
    "EventTimestamp": "2024-11-11T12:30:00Z", 
    "Severity": "OK",
    "Message": "Action ComputerSystem.Reset completed with result: Success",
    "MessageId": "Action.1.0.ActionCompleted",
    "MessageArgs": ["ComputerSystem.Reset", "Success"],
    "OriginOfCondition": {
        "@odata.id": "/redfish/v1/Systems/System1"
    }
}
```

## Testing Actions

### Using curl

```bash
# Basic action test
curl -X POST http://localhost:8000/redfish/v1/Systems/System1/Actions/ComputerSystem.Reset \
  -H "Content-Type: application/json" \
  -d '{"ResetType": "GracefulRestart"}'

# Action with complex parameters
curl -X POST http://localhost:8000/redfish/v1/TestService/Actions/TestService.RunDiagnostic \
  -H "Content-Type: application/json" \
  -d '{
    "DiagnosticType": "Full",
    "Timeout": 300,
    "Components": ["CPU", "Memory", "Storage"]
  }'

# Test invalid parameters (should return 400)
curl -X POST http://localhost:8000/redfish/v1/Systems/System1/Actions/ComputerSystem.Reset \
  -H "Content-Type: application/json" \
  -d '{"ResetType": "InvalidType"}'
```

### Using Python

```python
import requests

def test_action():
    url = "http://localhost:8000/redfish/v1/Systems/System1/Actions/ComputerSystem.Reset"
    data = {"ResetType": "GracefulRestart"}
    
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    if response.text:
        print(f"Response: {response.json()}")
```

## Best Practices

### 1. **Follow Redfish Conventions**
- Use standard action names when possible
- Follow Redfish parameter naming conventions
- Use appropriate HTTP status codes

### 2. **Comprehensive Validation**  
- Validate all required parameters
- Check parameter types and ranges
- Provide clear error messages

### 3. **Resource State Management**
- Update resource properties appropriately
- Maintain action history
- Keep resource state consistent

### 4. **Error Handling**
- Return appropriate HTTP status codes
- Provide detailed error information
- Log errors for debugging

### 5. **Event Integration**
- Always trigger events for action completion
- Include relevant action details in events
- Use appropriate event types and severity

### 6. **Documentation**
- Document action parameters and behavior
- Provide examples for each action
- Include error conditions and responses

## Integration with Existing Services

Action handlers integrate seamlessly with existing BMC Redfish Simulator services:

- **EventService**: Automatic event generation and delivery
- **LogService**: Action results can create log entries  
- **TaskService**: Support for long-running actions
- **UpdateService**: Integration with firmware updates
- **TelemetryService**: Action metrics and monitoring

This comprehensive action handling system provides the foundation for implementing any Redfish action while maintaining consistency with the simulator's mockup-driven architecture.