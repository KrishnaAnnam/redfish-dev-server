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
        if not resource["@odata.type"].startswith("#OCPRASService."):
            errors.append(f"Invalid @odata.type: {resource['@odata.type']}")
    
    # Validate Actions
    if "Actions" in resource:
        if "#RASService.SubmitCPAD" not in resource["Actions"]:
            errors.append("Missing required action: #RASService.SubmitCPAD")
        else:
            action = resource["Actions"]["#RASService.SubmitCPAD"]
            if "target" not in action:
                errors.append("SubmitCPAD action missing 'target' property")
    
    # Validate governance if present
    if "Governance" in resource:
        gov_errors = validate_governance_metadata(resource["Governance"])
        errors.extend([f"Governance.{err}" for err in gov_errors])
    
    return errors


def validate_service_root_extension(oem_extension: Dict[str, Any]) -> List[str]:
    """
    Validate ServiceRoot.Oem.OCPRASAPIWS extension structure
    
    Args:
        oem_extension: OEM extension dictionary
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if "@odata.type" not in oem_extension:
        errors.append("Missing @odata.type")
    elif not oem_extension["@odata.type"].startswith("#OCPRASServiceRoot."):
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
    from discovery import RASDiscoveryHandler

    discovery = RASDiscoveryHandler("System")

    print("=" * 60)
    print("RAS Plugin Schema Validation Tests")
    print("=" * 60)
    print()
    
    # Test 1: RASService resource
    print("Test 1: RASService Resource")
    print("-" * 60)
    _, ras_service = discovery.ras_service()
    errors = validate_ras_service_resource(ras_service)
    valid = print_validation_results("RASService", errors)
    
    if valid:
        print("\nGenerated Resource:")
        print(json.dumps(ras_service, indent=2))
    print()
    
    # Test 2: ServiceRoot OEM extension
    print("Test 2: ServiceRoot OEM Extension")
    print("-" * 60)
    service_root_oem = discovery.service_root_extension()
    errors = validate_service_root_extension(service_root_oem)
    valid = print_validation_results("ServiceRoot.Oem.OCPRASAPIWS", errors)
    
    if valid:
        print("\nGenerated Extension:")
        print(json.dumps(service_root_oem, indent=2))
    print()
    
    print("=" * 60)
    print("Schema validation tests complete")
    print("=" * 60)
