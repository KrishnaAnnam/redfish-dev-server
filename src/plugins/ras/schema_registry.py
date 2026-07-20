#!/usr/bin/env python3
"""
Schema Registry for RAS Plugin

Central registry for the OCP RAS (OCPRASAPIWS) schemas. Provides schema lookup,
validation support, and metadata management.
"""

from typing import Dict, Any, Optional
import json
import os


class SchemaRegistry:
    """Registry for OCP RAS OEM schemas"""
    
    # Schema namespace information
    NAMESPACE = "OCPRASService"
    VERSION = "v1_0_0"
    BASE_URI = "/redfish/v1/$metadata#OCPRASService"
    
    # Path to schema files
    SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')
    SCHEMA_FILE = os.path.join(SCHEMA_DIR, 'OCPRAS.v1_0_0.json')
    CSDL_FILE = os.path.join(SCHEMA_DIR, 'OCPRAS_v1.xml')
    
    _schema_cache = None
    
    @classmethod
    def _load_schema(cls) -> Dict[str, Any]:
        """Load JSON schema from file"""
        if cls._schema_cache is None:
            with open(cls.SCHEMA_FILE, 'r') as f:
                cls._schema_cache = json.load(f)
        return cls._schema_cache
    
    @classmethod
    def get_schema_file_path(cls, format: str = 'json') -> str:
        """Get path to schema file"""
        if format == 'json':
            return cls.SCHEMA_FILE
        elif format == 'csdl' or format == 'xml':
            return cls.CSDL_FILE
        else:
            raise ValueError(f"Unknown schema format: {format}")
    
    @classmethod
    def get_schema(cls, resource_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get schema definition
        
        Args:
            resource_type: Optional resource type (e.g., "RASService")
            
        Returns:
            Full schema or specific resource definition
        """
        schema = cls._load_schema()
        
        if resource_type:
            return schema.get('definitions', {}).get(resource_type, {})
        
        return schema
    
    @classmethod
    def get_action_info(cls, action_name: str) -> Dict[str, Any]:
        """
        Get ActionInfo for an action
        
        Args:
            action_name: Name of the action (e.g., "SubmitCPAD")
            
        Returns:
            ActionInfo dictionary
        """
        schema = cls._load_schema()
        action_def = schema.get('definitions', {}).get(action_name, {})
        
        # Build ActionInfo from schema definition
        return {
            "@odata.type": "#ActionInfo.v1_4_0.ActionInfo",
            "Id": f"{action_name}ActionInfo",
            "Name": f"{action_name} Action Info",
            "Description": action_def.get('description', f"Parameters for {action_name} action"),
            "Parameters": []  # TODO: Extract from schema if needed
        }
    
    @classmethod
    def get_odata_type(cls, resource_type: str) -> str:
        """
        Generate @odata.type value for a resource type
        
        Args:
            resource_type: Type name (e.g., "RASService", "Governance")
            
        Returns:
            Full @odata.type string
        """
        return f"#{cls.NAMESPACE}.{cls.VERSION}.{resource_type}"
    
    @classmethod
    def get_context(cls, resource_type: str) -> str:
        """
        Generate @odata.context value for a resource type
        
        Args:
            resource_type: Type name (e.g., "RASService")
            
        Returns:
            Full @odata.context string
        """
        return f"{cls.BASE_URI}.{resource_type}"
    
    @classmethod
    def list_schemas(cls) -> Dict[str, str]:
        """
        List all available schema definitions
        
        Returns:
            Dictionary mapping resource type to description
        """
        schema = cls._load_schema()
        definitions = schema.get('definitions', {})
        
        return {
            name: defn.get('description', 'No description')
            for name, defn in definitions.items()
        }
    
    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get metadata document for the OCP RAS namespace
        
        Returns:
            Metadata dictionary suitable for $metadata endpoint
        """
        return {
            "@odata.context": "/redfish/v1/$metadata",
            "@odata.type": "#ServiceRoot.v1_15_0.ServiceRoot",
            "Oem": {
                cls.NAMESPACE: {
                    "Namespace": cls.NAMESPACE,
                    "Version": cls.VERSION,
                    "Schemas": list(cls.SCHEMAS.keys()),
                    "Actions": list(cls.ACTION_INFO.keys())
                }
            }
        }
