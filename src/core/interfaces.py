# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Abstract base classes for platform-specific implementations
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum


class PlatformType(Enum):
    """Platform types for different BMC implementations"""
    GENERIC = "generic"
    VENDOR1 = "vendor1"  # Example vendor platform type 1
    VENDOR2 = "vendor2"  # Example vendor platform type 2
    SUPERMICRO = "supermicro"
    LENOVO_XCC = "lenovo_xcc"
    IBM_BMC = "ibm_bmc"
    CISCO_CIMC = "cisco_cimc"
    CUSTOM = "custom"


class ServiceCapability(Enum):
    """Service capabilities that platforms can support"""
    EVENT_SERVICE = "EventService"
    TELEMETRY_SERVICE = "TelemetryService"
    UPDATE_SERVICE = "UpdateService"
    TASK_SERVICE = "TaskService"
    SESSION_SERVICE = "SessionService"
    ACCOUNT_SERVICE = "AccountService"
    CERTIFICATE_SERVICE = "CertificateService"
    LICENSE_SERVICE = "LicenseService"
    RAS_SERVICE = "RASService"
    COMPOSABILITY = "Composability"
    SECURE_BOOT = "SecureBoot"
    BIOS_CONFIG = "BiosConfig"
    NETWORK_ADAPTER = "NetworkAdapter"
    STORAGE = "Storage"
    POWER_THERMAL = "PowerThermal"
    OEM_ACTIONS = "OemActions"


class BasePlatformService(ABC):
    """Abstract base class for platform-specific services"""
    
    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_config = platform_config
        self.capabilities = set()
    
    @abstractmethod
    def get_service_name(self) -> str:
        """Return the service name"""
        pass
    
    @abstractmethod
    def get_supported_capabilities(self) -> List[ServiceCapability]:
        """Return list of capabilities this service supports"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the service. Return True if successful."""
        pass
    
    def supports_capability(self, capability: ServiceCapability) -> bool:
        """Check if service supports a specific capability"""
        return capability in self.get_supported_capabilities()
    
    def handle_request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None, 
                      cached_links: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Handle service-specific requests. Return (status_code, response_data)"""
        return 501, {"error": "Not implemented"}


class BasePlatformHandler(ABC):
    """Abstract base class for platform-specific HTTP handlers"""
    
    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_config = platform_config
    
    @abstractmethod
    def get_handler_name(self) -> str:
        """Return the handler name"""
        pass
    
    @abstractmethod
    def get_supported_paths(self) -> List[str]:
        """Return list of path patterns this handler supports"""
        pass
    
    def can_handle_path(self, path: str) -> bool:
        """Check if this handler can handle the given path"""
        supported_paths = self.get_supported_paths()
        for pattern in supported_paths:
            if self._match_path_pattern(path, pattern):
                return True
        return False
    
    def _match_path_pattern(self, path: str, pattern: str) -> bool:
        """Match path against pattern (supports wildcards)"""
        import re
        # Convert pattern to regex (simple wildcard support)
        regex_pattern = pattern.replace('*', '[^/]*').replace('**', '.*')
        regex_pattern = f"^{regex_pattern}$"
        return bool(re.match(regex_pattern, path))
    
    @abstractmethod
    def handle_get(self, path: str, query_params: Dict[str, Any] = None, 
                   cached_links: Dict[str, Any] = None) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Handle GET requests"""
        pass
    
    def handle_post(self, path: str, data: Dict[str, Any], 
                    cached_links: Dict[str, Any] = None) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Handle POST requests"""
        return 405, None  # Method not allowed by default
    
    def handle_patch(self, path: str, data: Dict[str, Any], 
                     cached_links: Dict[str, Any] = None) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Handle PATCH requests"""
        return 405, None  # Method not allowed by default
    
    def handle_delete(self, path: str, 
                      cached_links: Dict[str, Any] = None) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Handle DELETE requests"""
        return 405, None  # Method not allowed by default


class BasePlatformProvider(ABC):
    """Abstract base class for platform providers"""
    
    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_config = platform_config
        self.services: Dict[str, BasePlatformService] = {}
        self.handlers: Dict[str, BasePlatformHandler] = {}
    
    @abstractmethod
    def get_platform_info(self) -> Dict[str, Any]:
        """Return platform identification information"""
        pass
    
    @abstractmethod
    def get_platform_type(self) -> PlatformType:
        """Return the platform type"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the platform provider"""
        pass
    
    @abstractmethod
    def register_services(self) -> None:
        """Register all platform-specific services"""
        pass
    
    @abstractmethod
    def register_handlers(self) -> None:
        """Register all platform-specific handlers"""
        pass
    
    def add_service(self, service: BasePlatformService) -> None:
        """Add a service to this platform"""
        self.services[service.get_service_name()] = service
    
    def add_handler(self, handler: BasePlatformHandler) -> None:
        """Add a handler to this platform"""
        self.handlers[handler.get_handler_name()] = handler
    
    def get_service(self, service_name: str) -> Optional[BasePlatformService]:
        """Get a service by name"""
        return self.services.get(service_name)
    
    def get_handler_for_path(self, path: str) -> Optional[BasePlatformHandler]:
        """Get the appropriate handler for a path"""
        for handler in self.handlers.values():
            if handler.can_handle_path(path):
                return handler
        return None
    
    def get_all_capabilities(self) -> List[ServiceCapability]:
        """Get all capabilities supported by this platform"""
        capabilities = set()
        for service in self.services.values():
            capabilities.update(service.get_supported_capabilities())
        return list(capabilities)


class OemActionHandler(ABC):
    """Abstract base class for OEM action handlers"""
    
    @abstractmethod
    def get_action_name(self) -> str:
        """Return the OEM action name"""
        pass
    
    @abstractmethod
    def get_supported_targets(self) -> List[str]:
        """Return list of target URIs this action supports"""
        pass
    
    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate action parameters. Return (is_valid, error_message)"""
        pass
    
    @abstractmethod
    def execute_action(self, target_uri: str, parameters: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Execute the OEM action. Return (status_code, response_data)"""
        pass