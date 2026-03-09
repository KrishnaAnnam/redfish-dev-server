# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Platform registry system for managing platform providers
"""

import os
import sys
import importlib
import importlib.util
import logging
from typing import Dict, List, Optional, Type, Any
from .interfaces import BasePlatformProvider, PlatformType, ServiceCapability

logger = logging.getLogger(__name__)


class PlatformRegistry:
    """Registry for managing platform providers and their capabilities"""
    
    def __init__(self):
        self._providers: Dict[str, Type[BasePlatformProvider]] = {}
        self._instances: Dict[str, BasePlatformProvider] = {}
        self._platform_metadata: Dict[str, Dict[str, Any]] = {}
    
    def register_provider(self, provider_class: Type[BasePlatformProvider], 
                         platform_id: str = None) -> str:
        """Register a platform provider class"""
        if platform_id is None:
            # Create platform ID from class name
            platform_id = provider_class.__name__.lower().replace('provider', '')
        
        if platform_id in self._providers:
            logger.warning(f"Platform provider {platform_id} already registered, overriding")
        
        self._providers[platform_id] = provider_class
        logger.info(f"Registered platform provider: {platform_id}")
        return platform_id
    
    def unregister_provider(self, platform_id: str) -> bool:
        """Unregister a platform provider"""
        if platform_id in self._providers:
            del self._providers[platform_id]
            if platform_id in self._instances:
                del self._instances[platform_id]
            if platform_id in self._platform_metadata:
                del self._platform_metadata[platform_id]
            logger.info(f"Unregistered platform provider: {platform_id}")
            return True
        return False
    
    def get_provider(self, platform_id: str, platform_config: Dict[str, Any] = None) -> Optional[BasePlatformProvider]:
        """Get or create platform provider instance"""
        if platform_id not in self._providers:
            logger.error(f"Platform provider {platform_id} not found")
            return None
        
        if platform_id not in self._instances:
            # Create new instance
            provider_class = self._providers[platform_id]
            config = platform_config or {}
            try:
                instance = provider_class(config)
                if instance.initialize():
                    self._instances[platform_id] = instance
                    # Cache platform metadata
                    self._platform_metadata[platform_id] = instance.get_platform_info()
                    logger.info(f"Initialized platform provider: {platform_id}")
                else:
                    logger.error(f"Failed to initialize platform provider: {platform_id}")
                    return None
            except Exception as e:
                logger.error(f"Error creating platform provider {platform_id}: {e}")
                return None
        
        return self._instances.get(platform_id)
    
    def list_providers(self) -> List[str]:
        """List all registered platform provider IDs"""
        return list(self._providers.keys())
    
    def get_platform_info(self, platform_id: str) -> Optional[Dict[str, Any]]:
        """Get platform information"""
        return self._platform_metadata.get(platform_id)
    
    def find_providers_by_type(self, platform_type: PlatformType) -> List[str]:
        """Find providers by platform type"""
        matching_providers = []
        for platform_id in self._instances:
            provider = self._instances[platform_id]
            if provider.get_platform_type() == platform_type:
                matching_providers.append(platform_id)
        return matching_providers
    
    def find_providers_by_capability(self, capability: ServiceCapability) -> List[str]:
        """Find providers that support a specific capability"""
        matching_providers = []
        for platform_id in self._instances:
            provider = self._instances[platform_id]
            if capability in provider.get_all_capabilities():
                matching_providers.append(platform_id)
        return matching_providers
    
    def auto_discover_providers(self, search_paths: List[str] = None) -> int:
        """Auto-discover platform providers from search paths"""
        if search_paths is None:
            search_paths = [
                os.path.join(os.path.dirname(__file__), '..', 'plugins'),
                os.path.join(os.path.dirname(__file__), '..', 'platform'),
            ]
        
        discovered_count = 0
        
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
                
            logger.info(f"Searching for platform providers in: {search_path}")
            
            # Add search path to sys.path temporarily
            if search_path not in sys.path:
                sys.path.insert(0, search_path)
            
            try:
                discovered_count += self._discover_in_path(search_path)
            except Exception as e:
                logger.error(f"Error discovering providers in {search_path}: {e}")
            finally:
                # Remove from sys.path
                if search_path in sys.path:
                    sys.path.remove(search_path)
        
        logger.info(f"Auto-discovered {discovered_count} platform providers")
        return discovered_count
    
    def _discover_in_path(self, search_path: str) -> int:
        """Discover providers in a specific path"""
        discovered_count = 0
        
        for item in os.listdir(search_path):
            item_path = os.path.join(search_path, item)
            
            if os.path.isfile(item_path) and item.endswith('.py') and not item.startswith('_'):
                # Single Python file
                try:
                    discovered_count += self._load_provider_from_file(item_path, item[:-3])
                except Exception as e:
                    logger.error(f"Error loading provider from {item_path}: {e}")
            
            elif os.path.isdir(item_path) and not item.startswith('_'):
                # Package directory
                init_file = os.path.join(item_path, '__init__.py')
                if os.path.exists(init_file):
                    try:
                        discovered_count += self._load_provider_from_package(item_path, item)
                    except Exception as e:
                        logger.error(f"Error loading provider from package {item_path}: {e}")
        
        return discovered_count
    
    def _load_provider_from_file(self, file_path: str, module_name: str) -> int:
        """Load provider from a single Python file"""
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return 0
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        return self._extract_providers_from_module(module, module_name)
    
    def _load_provider_from_package(self, package_path: str, package_name: str) -> int:
        """Load provider from a package"""
        try:
            module = importlib.import_module(package_name)
            return self._extract_providers_from_module(module, package_name)
        except ImportError as e:
            logger.error(f"Failed to import package {package_name}: {e}")
            return 0
    
    def _extract_providers_from_module(self, module: Any, module_name: str) -> int:
        """Extract platform providers from a loaded module"""
        discovered_count = 0
        
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            # Check if it's a class that inherits from BasePlatformProvider
            if (isinstance(attr, type) and 
                issubclass(attr, BasePlatformProvider) and 
                attr is not BasePlatformProvider):
                
                platform_id = f"{module_name}_{attr_name.lower()}"
                self.register_provider(attr, platform_id)
                discovered_count += 1
                logger.debug(f"Discovered provider: {platform_id} from {module_name}")
        
        return discovered_count
    
    def get_registry_status(self) -> Dict[str, Any]:
        """Get registry status information"""
        return {
            'registered_providers': len(self._providers),
            'initialized_instances': len(self._instances),
            'provider_list': list(self._providers.keys()),
            'instance_list': list(self._instances.keys()),
            'platform_types': {
                pid: self._instances[pid].get_platform_type().value 
                for pid in self._instances
            },
            'capabilities': {
                pid: [cap.value for cap in self._instances[pid].get_all_capabilities()] 
                for pid in self._instances
            }
        }


# Global registry instance
platform_registry = PlatformRegistry()