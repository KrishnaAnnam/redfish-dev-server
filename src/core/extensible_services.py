# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Enhanced core services with platform extensibility
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from .interfaces import BasePlatformProvider, BasePlatformService, ServiceCapability
from ..services.event_service import EventServiceHandler as BaseEventService
from ..services.telemetry_service import TelemetryServiceHandler as BaseTelemetryService

logger = logging.getLogger(__name__)


class ExtensibleEventService(BaseEventService):
    """Enhanced EventService with platform extensibility"""
    
    def __init__(self, server_config, platform_provider: Optional[BasePlatformProvider] = None):
        super().__init__(server_config)
        self.platform_provider = platform_provider
        self.platform_service = None
        
        if platform_provider:
            self.platform_service = platform_provider.get_service('event_service')
    
    def handle_adding_subscriptions(self, path, data_received, cached_links):
        """Handle subscription creation with platform extensions"""
        # Check if platform wants to handle this
        if self.platform_service and hasattr(self.platform_service, 'handle_subscription_creation'):
            try:
                status, response = self.platform_service.handle_subscription_creation(
                    path, data_received, cached_links
                )
                if status != 501:  # Platform handled it
                    return status
            except Exception as e:
                logger.error(f"Platform subscription handler failed: {e}")
        
        # Fall back to base implementation
        return super().handle_adding_subscriptions(path, data_received, cached_links)
    
    def handle_eventing(self, path, data_received, cached_links):
        """Handle event submission with platform extensions"""
        # Pre-process with platform if available
        if self.platform_service and hasattr(self.platform_service, 'preprocess_event'):
            try:
                data_received = self.platform_service.preprocess_event(data_received)
            except Exception as e:
                logger.error(f"Platform event preprocessing failed: {e}")
        
        # Check if platform wants to handle this completely
        if self.platform_service and hasattr(self.platform_service, 'handle_event_submission'):
            try:
                status, response = self.platform_service.handle_event_submission(
                    path, data_received, cached_links
                )
                if status != 501:  # Platform handled it
                    return status
            except Exception as e:
                logger.error(f"Platform event handler failed: {e}")
        
        # Use base implementation
        result = super().handle_eventing(path, data_received, cached_links)
        
        # Post-process with platform if available
        if self.platform_service and hasattr(self.platform_service, 'postprocess_event'):
            try:
                self.platform_service.postprocess_event(data_received, result)
            except Exception as e:
                logger.error(f"Platform event postprocessing failed: {e}")
        
        return result
    
    def get_supported_event_types(self) -> List[str]:
        """Get supported event types including platform-specific ones"""
        base_types = ['Event', 'Alert', 'ResourceAdded', 'ResourceRemoved', 'ResourceUpdated']
        
        if self.platform_service and hasattr(self.platform_service, 'get_supported_event_types'):
            try:
                platform_types = self.platform_service.get_supported_event_types()
                base_types.extend(platform_types)
            except Exception as e:
                logger.error(f"Error getting platform event types: {e}")
        
        return list(set(base_types))


class ExtensibleTelemetryService(BaseTelemetryService):
    """Enhanced TelemetryService with platform extensibility"""
    
    def __init__(self, server_config, platform_provider: Optional[BasePlatformProvider] = None):
        super().__init__(server_config)
        self.platform_provider = platform_provider
        self.platform_service = None
        
        if platform_provider:
            self.platform_service = platform_provider.get_service('telemetry_service')
    
    def handle_telemetry(self, path, data_received, cached_links):
        """Handle telemetry with platform extensions"""
        # Pre-process with platform if available
        if self.platform_service and hasattr(self.platform_service, 'preprocess_telemetry'):
            try:
                data_received = self.platform_service.preprocess_telemetry(data_received)
            except Exception as e:
                logger.error(f"Platform telemetry preprocessing failed: {e}")
        
        # Check if platform wants to handle this completely
        if self.platform_service and hasattr(self.platform_service, 'handle_telemetry_submission'):
            try:
                status, response = self.platform_service.handle_telemetry_submission(
                    path, data_received, cached_links
                )
                if status != 501:  # Platform handled it
                    return status
            except Exception as e:
                logger.error(f"Platform telemetry handler failed: {e}")
        
        # Use base implementation
        result = super().handle_telemetry(path, data_received, cached_links)
        
        # Post-process with platform if available
        if self.platform_service and hasattr(self.platform_service, 'postprocess_telemetry'):
            try:
                self.platform_service.postprocess_telemetry(data_received, result)
            except Exception as e:
                logger.error(f"Platform telemetry postprocessing failed: {e}")
        
        return result


class ServiceManager:
    """Manager for core and platform services"""
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.platform_provider: Optional[BasePlatformProvider] = None
        self.services: Dict[str, Any] = {}
        self.hooks: Dict[str, List[Callable]] = {}
    
    def set_platform_provider(self, platform_provider: BasePlatformProvider):
        """Set the platform provider and reinitialize services"""
        self.platform_provider = platform_provider
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize all services with platform provider"""
        self.services = {
            'event_service': ExtensibleEventService(self.server_config, self.platform_provider),
            'telemetry_service': ExtensibleTelemetryService(self.server_config, self.platform_provider),
        }
        
        # Register platform services if available
        if self.platform_provider:
            for service_name, service_instance in self.platform_provider.services.items():
                if service_name not in self.services:
                    self.services[service_name] = service_instance
    
    def get_service(self, service_name: str) -> Optional[Any]:
        """Get a service by name"""
        return self.services.get(service_name)
    
    def register_hook(self, hook_name: str, callback: Callable):
        """Register a hook callback"""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        self.hooks[hook_name].append(callback)
    
    def execute_hooks(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Execute all callbacks for a hook"""
        results = []
        for callback in self.hooks.get(hook_name, []):
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook_name} callback failed: {e}")
        return results
    
    def get_service_capabilities(self) -> Dict[str, List[ServiceCapability]]:
        """Get capabilities of all services"""
        capabilities = {}
        
        # Add platform service capabilities
        if self.platform_provider:
            for service_name, service in self.platform_provider.services.items():
                if hasattr(service, 'get_supported_capabilities'):
                    capabilities[service_name] = service.get_supported_capabilities()
        
        return capabilities