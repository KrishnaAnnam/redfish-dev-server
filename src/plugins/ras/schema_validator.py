#!/usr/bin/env python3
"""
Schema Validation and Testing Utilities

Provides utilities for validating RAS plugin schemas and testing
schema-based resource generation.
"""

import json
from typing import Dict, Any, List, Optional


def validate_governance_metadata(governance: Dict[str, Any]) -> List[str]:
    """
    Validate governance metadata structure
    
    Args:
        governance: Governance metadata dictionary
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    required_fields = [
        "OwningWorkstream",
        "GoverningSpecification",
        "SpecificationVersion",
        "StandardizationIntent",
        "TargetNamespace",
        "ImplementationStatus",
        "ContractStability"
    ]
    
    for field in required_fields:
        if field not in governance:
            errors.append(f"Missing required field: {field}")
    
    # Validate enums
    if "ImplementationStatus" in governance:
        valid_statuses = ["Prototype", "Development", "Production", "Deprecated"]
        if governance["ImplementationStatus"] not in valid_statuses:
            errors.append(f"Invalid ImplementationStatus: {governance['ImplementationStatus']}")
    
    if "ContractStability" in governance:
        valid_stability = ["Experimental", "Stable", "Frozen", "Deprecated"]
        if governance["ContractStability"] not in valid_stability:
            errors.append(f"Invalid ContractStability: {governance['ContractStability']}")
    
    return errors


def validate_ras_service_resource(resource: Dict[str, Any]) -> List[str]:
    """
    Validate RASService resource structure
    
    Args:
        resource: RASService resource dictionary
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Required top-level fields
    required_fields = ["@odata.type", "@odata.id", "Id", "Name"]
    for field in required_fields:
        if field not in resource:
            errors.append(f"Missing required field: {field}")
    
    # Validate @odata.type
    if "@odata.type" in resource:
        if not resource["@odata.type"].startswith("#RasProto."):
            errors.append(f"Invalid @odata.type: {resource['@odata.type']}")
    
    # Validate Actions
    if "Actions" in resource:
        if "#RasProto.SubmitCPAD" not in resource["Actions"]:
            errors.append("Missing required action: #RasProto.SubmitCPAD")
        else:
            action = resource["Actions"]["#RasProto.SubmitCPAD"]
            if "target" not in action:
                errors.append("SubmitCPAD action missing 'target' property")
    
    # Validate governance if present
    if "Governance" in resource:
        gov_errors = validate_governance_metadata(resource["Governance"])
        errors.extend([f"Governance.{err}" for err in gov_errors])
    
    return errors


def validate_manager_extension(oem_extension: Dict[str, Any]) -> List[str]:
    """
    Validate Manager.Oem.RasProto extension structure
    
    Args:
        oem_extension: OEM extension dictionary
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if "@odata.type" not in oem_extension:
        errors.append("Missing @odata.type")
    elif not oem_extension["@odata.type"].startswith("#RasProto."):
        errors.append(f"Invalid @odata.type: {oem_extension['@odata.type']}")
    
    if "RASService" not in oem_extension:
        errors.append("Missing RASService link")
    elif "@odata.id" not in oem_extension["RASService"]:
        errors.append("RASService link missing @odata.id")
    
    return errors


def print_validation_results(resource_name: str, errors: List[str]) -> bool:
    """
    Print validation results
    
    Args:
        resource_name: Name of the resource being validated
        errors: List of validation errors
        
    Returns:
        True if valid (no errors), False otherwise
    """
    if not errors:
        print(f"✅ {resource_name}: VALID")
        return True
    else:
        print(f"❌ {resource_name}: INVALID")
        for error in errors:
            print(f"   - {error}")
        return False


if __name__ == "__main__":
    """Test schema validation"""
    from schema_registry import (
        build_ras_service_response,
        build_manager_oem_extension
    )
    
    print("=" * 60)
    print("RAS Plugin Schema Validation Tests")
    print("=" * 60)
    print()
    
    # Test 1: RASService resource
    print("Test 1: RASService Resource")
    print("-" * 60)
    ras_service = build_ras_service_response("BMC", service_enabled=True)
    errors = validate_ras_service_resource(ras_service)
    valid = print_validation_results("RASService", errors)
    
    if valid:
        print("\nGenerated Resource:")
        print(json.dumps(ras_service, indent=2))
    print()
    
    # Test 2: Manager OEM extension
    print("Test 2: Manager OEM Extension")
    print("-" * 60)
    manager_oem = build_manager_oem_extension("BMC")
    errors = validate_manager_extension(manager_oem)
    valid = print_validation_results("Manager.Oem.RasProto", errors)
    
    if valid:
        print("\nGenerated Extension:")
        print(json.dumps(manager_oem, indent=2))
    print()
    
    # Test 3: Governance metadata
    print("Test 3: Governance Metadata")
    print("-" * 60)
    if "Governance" in ras_service:
        errors = validate_governance_metadata(ras_service["Governance"])
        valid = print_validation_results("Governance", errors)
        
        if valid:
            print("\nGovernance Metadata:")
            print(json.dumps(ras_service["Governance"], indent=2))
    print()
    
    print("=" * 60)
    print("Schema validation tests complete")
    print("=" * 60)
