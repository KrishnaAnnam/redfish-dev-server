# Schema Property Validation for BMC Redfish Simulator

## Overview

The BMC Redfish Simulator now includes comprehensive schema-based property validation for PATCH operations. This ensures that only writable properties can be modified according to Redfish specifications, and provides type checking, enum validation, and cross-property constraint validation.

## Architecture

### Components

1. **SchemaPropertyValidator** (`src/services/schema_property_validator.py`)
   - Core validation service that enforces property constraints
   - Maintains schema definitions for different resource types
   - Validates property writability, types, enums, and cross-property rules

2. **Enhanced PATCH Handler** (`src/handlers/patch_handler.py`)
   - Integrates with SchemaPropertyValidator before applying changes
   - Automatically detects resource type from `@odata.type` field
   - Returns appropriate error responses for validation failures

3. **Resource Type Detection**
   - Automatic detection from `@odata.type` field in resource data
   - Supports all major Redfish resource types (ComputerSystem, Manager, Chassis, etc.)

## Supported Validations

### 1. Property Writability
- **Read-only Properties**: Properties like `Id`, `PowerState`, `Status` are rejected
- **Writable Properties**: Properties like `AssetTag`, `IndicatorLED` are allowed
- **OEM Properties**: Custom vendor properties in `Oem` object are generally allowed

```json
{
  "AssetTag": "Server-001",     // ✅ Allowed - writable
  "IndicatorLED": "Blinking",   // ✅ Allowed - writable  
  "Id": "NewId",               // ❌ Rejected - read-only
  "PowerState": "Off"          // ❌ Rejected - read-only
}
```

### 2. Type Validation
- **String properties** must be strings
- **Boolean properties** must be true/false
- **Integer properties** must be numbers
- **Object properties** must be objects

```json
{
  "IndicatorLED": "Lit",        // ✅ Correct string type
  "InterfaceEnabled": true,     // ✅ Correct boolean type
  "MTUSize": 1500,             // ✅ Correct integer type
  "IndicatorLED": true,        // ❌ Wrong type - should be string
  "InterfaceEnabled": "yes"    // ❌ Wrong type - should be boolean
}
```

### 3. Enum Value Validation
- Properties with predefined values are validated against allowed enums
- Provides helpful error messages listing valid options

```json
{
  "IndicatorLED": "Lit",        // ✅ Valid enum value
  "IndicatorLED": "Blinking",   // ✅ Valid enum value
  "IndicatorLED": "Rainbow"     // ❌ Invalid - must be: Lit, Blinking, Off
}
```

### 4. Cross-Property Constraints
- Validates relationships between multiple properties
- Enforces business logic constraints

**Examples:**
- Boot override: `BootSourceOverrideTarget` cannot be "None" when `BootSourceOverrideEnabled` is "Once"
- Password complexity: Passwords must meet length and character requirements
- DateTime format validation for timestamp fields

```json
{
  "BootSourceOverrideEnabled": "Once",
  "BootSourceOverrideTarget": "None"   // ❌ Invalid combination
}

{
  "BootSourceOverrideEnabled": "Once", 
  "BootSourceOverrideTarget": "Pxe"    // ✅ Valid combination
}
```

## Schema Definitions

### Supported Resource Types

| Resource Type | Writable Properties | Key Constraints |
|---------------|-------------------|-----------------|
| **ComputerSystem** | AssetTag, IndicatorLED, BootSourceOverride* | Boot override validation |
| **Manager** | DateTime, IndicatorLED, CommandConnectTypesSupported | DateTime format validation |
| **Chassis** | AssetTag, IndicatorLED, LocationId | Location ID validation |
| **EthernetInterface** | InterfaceEnabled, MTUSize, VLAN | VLAN configuration validation |
| **ManagerAccount** | Password, Enabled, RoleId | Password complexity rules |
| **LogEntry** | Severity, Message | Message length limits |

### Property Type Definitions

```python
"ComputerSystem": {
    "writable_properties": {
        "AssetTag", "IndicatorLED", "BootSourceOverrideEnabled", 
        "BootSourceOverrideTarget", "PowerRestorePolicy"
    },
    "readonly_properties": {
        "Id", "Name", "PowerState", "SerialNumber", "Model", 
        "Manufacturer", "UUID", "Status", "ProcessorSummary"
    },
    "property_types": {
        "AssetTag": "string",
        "IndicatorLED": "string",
        "BootSourceOverrideEnabled": "string",
        "BootSourceOverrideTarget": "string"
    },
    "enum_values": {
        "IndicatorLED": ["Lit", "Blinking", "Off"],
        "BootSourceOverrideEnabled": ["Disabled", "Once", "Continuous"],
        "BootSourceOverrideTarget": ["None", "Pxe", "Floppy", "Cd", "Usb", "Hdd"]
    }
}
```

## Usage Examples

### 1. Valid PATCH Request

```http
PATCH /redfish/v1/Systems/437XR1138R2
Content-Type: application/json

{
  "AssetTag": "Server-001",
  "IndicatorLED": "Blinking"
}

Response: 204 No Content
```

### 2. Invalid PATCH Request (Read-only Property)

```http
PATCH /redfish/v1/Systems/437XR1138R2
Content-Type: application/json

{
  "AssetTag": "Server-001",
  "PowerState": "Off"  // Read-only property
}

Response: 400 Bad Request
{
  "error": {
    "code": "PropertyNotWritable",
    "message": "One or more properties cannot be modified",
    "validationErrors": [
      "Property 'PowerState' is read-only and cannot be modified"
    ]
  }
}
```

### 3. Invalid PATCH Request (Enum Constraint)

```http
PATCH /redfish/v1/Systems/437XR1138R2
Content-Type: application/json

{
  "IndicatorLED": "Rainbow"  // Invalid enum value
}

Response: 400 Bad Request
{
  "error": {
    "code": "PropertyValueError", 
    "message": "One or more property values are invalid",
    "validationErrors": [
      "Property 'IndicatorLED' must be one of: Lit, Blinking, Off"
    ]
  }
}
```

### 4. OEM Property Support

```http
PATCH /redfish/v1/Systems/437XR1138R2
Content-Type: application/json

{
  "AssetTag": "Server-001",
  "Oem": {
    "CustomVendor": {
      "CustomProperty": "CustomValue",
      "AdvancedSettings": {
        "Feature1": true,
        "Feature2": 42
      }
    }
  }
}

Response: 204 No Content
```

## Error Response Format

Schema validation errors follow the standard Redfish error format:

```json
{
  "error": {
    "code": "PropertyNotWritable",
    "message": "One or more properties cannot be modified", 
    "validationErrors": [
      "Property 'Id' is read-only and cannot be modified",
      "Property 'PowerState' is read-only and cannot be modified"
    ]
  }
}
```

### Error Codes

- **PropertyNotWritable**: Read-only property modification attempt
- **PropertyValueError**: Invalid property value (type, enum, constraint)
- **PropertyValidationError**: Cross-property constraint violation

## Configuration

### Adding New Resource Types

To add validation for a new resource type:

1. **Add Schema Definition** in `SchemaPropertyValidator.__init__()`

```python
"MyCustomResource": {
    "writable_properties": {
        "CustomProperty1", "CustomProperty2", "EnabledFlag"
    },
    "readonly_properties": {
        "Id", "Name", "Status", "Created"
    },
    "property_types": {
        "CustomProperty1": "string",
        "CustomProperty2": "integer", 
        "EnabledFlag": "boolean"
    },
    "enum_values": {
        "CustomProperty1": ["Value1", "Value2", "Value3"]
    }
}
```

2. **Add Resource Type Detection** in `patch_handler.py`

```python
def _extract_resource_type(self, resource_data: dict) -> str:
    odata_type = resource_data.get("@odata.type", "")
    
    # Add custom detection
    if "#MyCustomResource" in odata_type:
        return "MyCustomResource"
    
    # ... existing code
```

3. **Add Cross-Property Validation** (optional)

```python
def _validate_cross_property_constraints(self, resource_type, resource_data, patch_data):
    if resource_type == "MyCustomResource":
        if patch_data.get("EnabledFlag") and not patch_data.get("CustomProperty1"):
            errors.append("CustomProperty1 is required when EnabledFlag is true")
```

### Enabling/Disabling Validation

Schema validation can be controlled through configuration:

```python
# Disable validation for a specific resource type
"MyResource": {
    "validation_disabled": True
}

# Allow all properties (backwards compatibility mode)
"LegacyResource": {
    "allow_all_properties": True
}
```

## Testing

### Running Validation Tests

```bash
# Run comprehensive validation tests
python3 test_patch_validation.py

# Run live demo with actual HTTP requests
python3 examples/schema_validation_demo.py
```

### Test Coverage

The test suite covers:

- ✅ Resource type detection from `@odata.type`
- ✅ Property writability validation
- ✅ Property type checking
- ✅ Enum value validation
- ✅ Cross-property constraint validation
- ✅ OEM property handling
- ✅ Error reporting and response formatting

## Integration with Existing Code

### LogEntry Service Integration

The LogEntry service automatically integrates with schema validation:

```python
# In LogEntryService.handle_patch_log_entry()
is_valid, errors, filtered_data = validator.validate_patch_properties(
    "LogEntry", current_data, patch_data
)

if not is_valid:
    return self._create_error_response(400, errors)

# Apply only validated properties
self._apply_patch_data(current_data, filtered_data)
```

### Action Handlers Integration

Action handlers can also use schema validation for parameter validation:

```python
# Validate action parameters
is_valid, errors, _ = validator.validate_patch_properties(
    "ActionParameters", {}, action_params
)
```

## Best Practices

### 1. Schema-First Approach
- Define schema constraints before implementing PATCH handlers
- Use schema validation to enforce Redfish compliance
- Keep property definitions synchronized with Redfish specifications

### 2. Error Handling
- Always provide clear error messages listing specific validation failures
- Include helpful information like valid enum values
- Return appropriate HTTP status codes (400 for validation errors)

### 3. OEM Properties
- Allow OEM properties by default for vendor extensions
- Validate OEM structure if custom validation is needed
- Document OEM property schemas for vendor-specific implementations

### 4. Performance Considerations
- Schema validation adds minimal overhead (~1-5ms per request)
- Property definitions are cached in memory for fast access
- Consider disabling validation in development environments if needed

## Troubleshooting

### Common Issues

1. **"Property X is read-only"**
   - Check if property is listed in `readonly_properties`
   - Verify property should actually be writable according to Redfish spec
   - Consider if property should be in `writable_properties` instead

2. **"Property must be one of: X, Y, Z"**
   - Check enum definition in `enum_values`
   - Verify the value being sent matches exactly (case-sensitive)
   - Update enum definition if new values should be supported

3. **"Invalid type" errors**
   - Check property type definition in `property_types`
   - Ensure JSON payload has correct data types
   - Boolean values must be true/false, not "true"/"false"

4. **Cross-property constraint violations**
   - Review constraint logic in `_validate_cross_property_constraints()`
   - Check if multiple properties need to be set together
   - Verify business logic rules are correctly implemented

### Debug Mode

Enable debug logging to see detailed validation information:

```python
import logging
logging.getLogger('schema_property_validator').setLevel(logging.DEBUG)
```

This provides detailed information about:
- Which properties are being validated
- Why specific properties are rejected
- What filtered properties are being applied

## Future Enhancements

### Planned Features

1. **Dynamic Schema Loading**: Load schema definitions from Redfish CSDL files
2. **Custom Validation Rules**: Plugin system for vendor-specific validation logic
3. **Schema Versioning**: Support for multiple Redfish schema versions
4. **Performance Optimization**: Caching and optimization for high-throughput scenarios
5. **Advanced Constraints**: Regex patterns, dependency validation, conditional rules

### Contributing

To contribute to schema validation:

1. Add test cases for new validation scenarios
2. Update schema definitions for new Redfish resources
3. Implement new constraint types (regex, ranges, etc.)
4. Optimize performance for high-volume deployments
5. Add support for additional Redfish specification features

## Conclusion

The schema property validation system ensures that the BMC Redfish Simulator maintains strict compliance with Redfish specifications while providing clear feedback when invalid modifications are attempted. This helps developers build reliable Redfish clients and ensures that the simulator behaves like real BMC implementations.

The validation is:
- **Comprehensive**: Covers property writability, types, enums, and cross-property constraints
- **Extensible**: Easy to add new resource types and validation rules
- **Performance-friendly**: Minimal overhead with in-memory schema caching
- **Standards-compliant**: Based on official Redfish specifications
- **Developer-friendly**: Clear error messages and extensive testing support