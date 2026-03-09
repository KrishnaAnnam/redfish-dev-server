# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Platform configuration and detection system
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from ..core.interfaces import PlatformType, ServiceCapability

logger = logging.getLogger(__name__)


class PlatformDetectionMethod(Enum):
    """Methods for detecting platform type"""
    MANUAL = "manual"
    AUTO_MOCKUP = "auto_mockup"  # Detect from mockup data structure
    AUTO_MANIFEST = "auto_manifest"  # Detect from platform manifest file
    AUTO_DMI = "auto_dmi"  # Detect from system DMI/SMBIOS info (if available)
    AUTO_CONFIG = "auto_config"  # Detect from configuration hints


@dataclass
class PlatformConfig:
    """Configuration for a platform"""
    platform_id: str
    platform_type: PlatformType
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    
    # Service configuration
    enabled_services: List[ServiceCapability] = field(default_factory=list)
    service_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # OEM extensions
    oem_namespace: str = ""
    oem_actions: List[str] = field(default_factory=list)
    oem_properties: Dict[str, Any] = field(default_factory=dict)
    
    # Hardware simulation
    system_info: Dict[str, Any] = field(default_factory=dict)
    manager_info: Dict[str, Any] = field(default_factory=dict)
    chassis_info: Dict[str, Any] = field(default_factory=dict)
    
    # Network configuration
    network_interfaces: List[Dict[str, Any]] = field(default_factory=list)
    
    # Security settings
    authentication: Dict[str, Any] = field(default_factory=dict)
    certificates: Dict[str, Any] = field(default_factory=dict)
    
    # Custom properties
    custom_properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'platform_id': self.platform_id,
            'platform_type': self.platform_type.value,
            'display_name': self.display_name,
            'version': self.version,
            'description': self.description,
            'enabled_services': [s.value for s in self.enabled_services],
            'service_configs': self.service_configs,
            'oem_namespace': self.oem_namespace,
            'oem_actions': self.oem_actions,
            'oem_properties': self.oem_properties,
            'system_info': self.system_info,
            'manager_info': self.manager_info,
            'chassis_info': self.chassis_info,
            'network_interfaces': self.network_interfaces,
            'authentication': self.authentication,
            'certificates': self.certificates,
            'custom_properties': self.custom_properties
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlatformConfig':
        """Create from dictionary"""
        # Convert string enums back to enum objects
        platform_type = PlatformType(data.get('platform_type', 'generic'))
        enabled_services = [ServiceCapability(s) for s in data.get('enabled_services', [])]
        
        return cls(
            platform_id=data['platform_id'],
            platform_type=platform_type,
            display_name=data['display_name'],
            version=data.get('version', '1.0.0'),
            description=data.get('description', ''),
            enabled_services=enabled_services,
            service_configs=data.get('service_configs', {}),
            oem_namespace=data.get('oem_namespace', ''),
            oem_actions=data.get('oem_actions', []),
            oem_properties=data.get('oem_properties', {}),
            system_info=data.get('system_info', {}),
            manager_info=data.get('manager_info', {}),
            chassis_info=data.get('chassis_info', {}),
            network_interfaces=data.get('network_interfaces', []),
            authentication=data.get('authentication', {}),
            certificates=data.get('certificates', {}),
            custom_properties=data.get('custom_properties', {})
        )


class PlatformDetector:
    """Detects platform type from various sources"""
    
    def __init__(self, mockup_dir: str):
        self.mockup_dir = mockup_dir
    
    def detect_platform(self, method: PlatformDetectionMethod = PlatformDetectionMethod.AUTO_MOCKUP) -> Optional[PlatformConfig]:
        """Detect platform configuration using specified method"""
        
        if method == PlatformDetectionMethod.AUTO_MOCKUP:
            return self._detect_from_mockup()
        elif method == PlatformDetectionMethod.AUTO_MANIFEST:
            return self._detect_from_manifest()
        elif method == PlatformDetectionMethod.AUTO_CONFIG:
            return self._detect_from_config()
        else:
            logger.warning(f"Detection method {method} not implemented")
            return None
    
    def _detect_from_mockup(self) -> Optional[PlatformConfig]:
        """Detect platform from mockup data structure"""
        try:
            # Look for service root to get basic info
            service_root_path = os.path.join(self.mockup_dir, 'redfish', 'v1', 'index.json')
            if not os.path.exists(service_root_path):
                # Try short form
                service_root_path = os.path.join(self.mockup_dir, 'index.json')
            
            if not os.path.exists(service_root_path):
                return None
            
            with open(service_root_path, 'r') as f:
                service_root = json.load(f)
            
            # Extract OEM information
            oem_info = service_root.get('Oem', {})
            
            # Detect platform type from OEM namespace
            platform_type = PlatformType.GENERIC
            oem_namespace = ""
            
            if 'Vendor1' in oem_info:
                platform_type = PlatformType.VENDOR1
                oem_namespace = "Vendor1"
            elif 'Vendor2' in oem_info:
                platform_type = PlatformType.VENDOR2
                oem_namespace = "Vendor2"
            elif 'Supermicro' in oem_info:
                platform_type = PlatformType.SUPERMICRO
                oem_namespace = "Supermicro"
            elif 'Lenovo' in oem_info:
                platform_type = PlatformType.LENOVO_XCC
                oem_namespace = "Lenovo"
            
            # Detect available services
            enabled_services = []
            if 'EventService' in service_root:
                enabled_services.append(ServiceCapability.EVENT_SERVICE)
            if 'TelemetryService' in service_root:
                enabled_services.append(ServiceCapability.TELEMETRY_SERVICE)
            if 'UpdateService' in service_root:
                enabled_services.append(ServiceCapability.UPDATE_SERVICE)
            if 'TaskService' in service_root:
                enabled_services.append(ServiceCapability.TASK_SERVICE)
            if 'SessionService' in service_root:
                enabled_services.append(ServiceCapability.SESSION_SERVICE)
            if 'AccountService' in service_root:
                enabled_services.append(ServiceCapability.ACCOUNT_SERVICE)
            if 'CertificateService' in service_root:
                enabled_services.append(ServiceCapability.CERTIFICATE_SERVICE)
            if 'RASService' in service_root:
                enabled_services.append(ServiceCapability.RAS_SERVICE)
            
            # Get system information
            system_info = self._get_system_info()
            manager_info = self._get_manager_info()
            chassis_info = self._get_chassis_info()
            
            platform_config = PlatformConfig(
                platform_id=f"auto_detected_{platform_type.value}",
                platform_type=platform_type,
                display_name=f"Auto-detected {platform_type.value.title()} Platform",
                description=f"Automatically detected from mockup data",
                enabled_services=enabled_services,
                oem_namespace=oem_namespace,
                system_info=system_info,
                manager_info=manager_info,
                chassis_info=chassis_info
            )
            
            logger.info(f"Detected platform: {platform_type.value}")
            return platform_config
            
        except Exception as e:
            logger.error(f"Error detecting platform from mockup: {e}")
            return None
    
    def _detect_from_manifest(self) -> Optional[PlatformConfig]:
        """Detect platform from manifest file"""
        manifest_paths = [
            os.path.join(self.mockup_dir, 'platform_manifest.json'),
            os.path.join(self.mockup_dir, '.platform'),
            os.path.join(self.mockup_dir, 'redfish', 'v1', 'platform_manifest.json')
        ]
        
        for manifest_path in manifest_paths:
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r') as f:
                        manifest_data = json.load(f)
                    
                    return PlatformConfig.from_dict(manifest_data)
                    
                except Exception as e:
                    logger.error(f"Error loading platform manifest {manifest_path}: {e}")
        
        return None
    
    def _detect_from_config(self) -> Optional[PlatformConfig]:
        """Detect platform from configuration file"""
        config_paths = [
            os.path.join(self.mockup_dir, 'platform_config.json'),
            os.path.join(os.path.dirname(self.mockup_dir), 'platform_config.json')
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config_data = json.load(f)
                    
                    return PlatformConfig.from_dict(config_data)
                    
                except Exception as e:
                    logger.error(f"Error loading platform config {config_path}: {e}")
        
        return None
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Extract system information from mockup"""
        system_info = {}
        
        try:
            systems_path = os.path.join(self.mockup_dir, 'redfish', 'v1', 'Systems', 'index.json')
            if not os.path.exists(systems_path):
                systems_path = os.path.join(self.mockup_dir, 'Systems', 'index.json')
            
            if os.path.exists(systems_path):
                with open(systems_path, 'r') as f:
                    systems_data = json.load(f)
                
                members = systems_data.get('Members', [])
                if members:
                    # Get first system details
                    first_system_path = members[0].get('@odata.id', '').lstrip('/')
                    system_detail_path = os.path.join(self.mockup_dir, first_system_path, 'index.json')
                    
                    if os.path.exists(system_detail_path):
                        with open(system_detail_path, 'r') as f:
                            system_detail = json.load(f)
                        
                        system_info = {
                            'Manufacturer': system_detail.get('Manufacturer', ''),
                            'Model': system_detail.get('Model', ''),
                            'SerialNumber': system_detail.get('SerialNumber', ''),
                            'PartNumber': system_detail.get('PartNumber', ''),
                            'SystemType': system_detail.get('SystemType', ''),
                            'BiosVersion': system_detail.get('BiosVersion', '')
                        }
        
        except Exception as e:
            logger.error(f"Error extracting system info: {e}")
        
        return system_info
    
    def _get_manager_info(self) -> Dict[str, Any]:
        """Extract manager information from mockup"""
        manager_info = {}
        
        try:
            managers_path = os.path.join(self.mockup_dir, 'redfish', 'v1', 'Managers', 'index.json')
            if not os.path.exists(managers_path):
                managers_path = os.path.join(self.mockup_dir, 'Managers', 'index.json')
            
            if os.path.exists(managers_path):
                with open(managers_path, 'r') as f:
                    managers_data = json.load(f)
                
                members = managers_data.get('Members', [])
                if members:
                    # Get first manager details
                    first_manager_path = members[0].get('@odata.id', '').lstrip('/')
                    manager_detail_path = os.path.join(self.mockup_dir, first_manager_path, 'index.json')
                    
                    if os.path.exists(manager_detail_path):
                        with open(manager_detail_path, 'r') as f:
                            manager_detail = json.load(f)
                        
                        manager_info = {
                            'ManagerType': manager_detail.get('ManagerType', ''),
                            'FirmwareVersion': manager_detail.get('FirmwareVersion', ''),
                            'Model': manager_detail.get('Model', ''),
                            'Manufacturer': manager_detail.get('Manufacturer', '')
                        }
        
        except Exception as e:
            logger.error(f"Error extracting manager info: {e}")
        
        return manager_info
    
    def _get_chassis_info(self) -> Dict[str, Any]:
        """Extract chassis information from mockup"""
        chassis_info = {}
        
        try:
            chassis_path = os.path.join(self.mockup_dir, 'redfish', 'v1', 'Chassis', 'index.json')
            if not os.path.exists(chassis_path):
                chassis_path = os.path.join(self.mockup_dir, 'Chassis', 'index.json')
            
            if os.path.exists(chassis_path):
                with open(chassis_path, 'r') as f:
                    chassis_data = json.load(f)
                
                members = chassis_data.get('Members', [])
                if members:
                    # Get first chassis details
                    first_chassis_path = members[0].get('@odata.id', '').lstrip('/')
                    chassis_detail_path = os.path.join(self.mockup_dir, first_chassis_path, 'index.json')
                    
                    if os.path.exists(chassis_detail_path):
                        with open(chassis_detail_path, 'r') as f:
                            chassis_detail = json.load(f)
                        
                        chassis_info = {
                            'ChassisType': chassis_detail.get('ChassisType', ''),
                            'Manufacturer': chassis_detail.get('Manufacturer', ''),
                            'Model': chassis_detail.get('Model', ''),
                            'SerialNumber': chassis_detail.get('SerialNumber', ''),
                            'PartNumber': chassis_detail.get('PartNumber', '')
                        }
        
        except Exception as e:
            logger.error(f"Error extracting chassis info: {e}")
        
        return chassis_info