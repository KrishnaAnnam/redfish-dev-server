# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Automatic platform detection and loading mechanism
"""

import os
import logging
from typing import Dict, Any, Optional, List
from .platform_config import PlatformDetector, PlatformConfig, PlatformDetectionMethod
from .registry import platform_registry
from .interfaces import BasePlatformProvider, PlatformType

logger = logging.getLogger(__name__)


class PlatformDiscovery:
    """Platform discovery and auto-loading system"""
    
    def __init__(self, mockup_dir: str):
        self.mockup_dir = mockup_dir
        self.detector = PlatformDetector(mockup_dir)
        self.loaded_platform: Optional[BasePlatformProvider] = None
        self.platform_config: Optional[PlatformConfig] = None
    
    def discover_and_load_platform(self, 
                                  platform_hint: Optional[str] = None,
                                  detection_method: PlatformDetectionMethod = PlatformDetectionMethod.AUTO_MOCKUP,
                                  skip_auto_discover: bool = False) -> Optional[BasePlatformProvider]:
        """Discover and load the appropriate platform"""
        
        # Step 1: Auto-discover available platform providers (unless skipped)
        if not skip_auto_discover:
            logger.info("Auto-discovering platform providers...")
            discovered_count = platform_registry.auto_discover_providers()
            logger.info(f"Discovered {discovered_count} platform providers")
        else:
            logger.info("Skipping auto-discovery (using explicit configuration)")
        
        # Step 2: Detect platform configuration
        logger.info(f"Detecting platform using method: {detection_method.value}")
        
        if platform_hint:
            # Use provided platform hint
            self.platform_config = self._create_config_from_hint(platform_hint)
        else:
            # Auto-detect platform
            self.platform_config = self.detector.detect_platform(detection_method)
        
        if not self.platform_config:
            logger.warning("Could not detect platform configuration, using generic")
            self.platform_config = self._create_generic_config()
        
        # Step 3: Load the appropriate platform provider
        platform_provider = self._load_platform_provider()
        
        if platform_provider:
            self.loaded_platform = platform_provider
            logger.info(f"Successfully loaded platform: {self.platform_config.display_name}")
        else:
            logger.warning("Failed to load platform provider, continuing with core functionality")
        
        return platform_provider
    
    def _create_config_from_hint(self, platform_hint: str) -> Optional[PlatformConfig]:
        """Create platform config from hint"""
        try:
            platform_type = PlatformType(platform_hint.lower())
            
            return PlatformConfig(
                platform_id=f"manual_{platform_hint}",
                platform_type=platform_type,
                display_name=f"Manual {platform_hint.title()} Platform",
                description=f"Manually specified {platform_hint} platform"
            )
        
        except ValueError:
            logger.error(f"Invalid platform hint: {platform_hint}")
            return None
    
    def _create_generic_config(self) -> PlatformConfig:
        """Create generic platform config"""
        return PlatformConfig(
            platform_id="generic",
            platform_type=PlatformType.GENERIC,
            display_name="Generic Redfish Platform",
            description="Generic Redfish implementation without platform-specific features"
        )
    
    def _load_platform_provider(self) -> Optional[BasePlatformProvider]:
        """Load the platform provider based on detected configuration"""
        
        # Try to find matching provider
        matching_providers = self._find_matching_providers()
        
        if not matching_providers:
            logger.warning(f"No provider found for platform type: {self.platform_config.platform_type.value}")
            return None
        
        # Use the first matching provider
        provider_id = matching_providers[0]
        logger.info(f"Loading platform provider: {provider_id}")
        
        # Convert platform config to dict for provider
        platform_config_dict = self.platform_config.to_dict()
        
        # Get provider instance
        platform_provider = platform_registry.get_provider(provider_id, platform_config_dict)
        
        if platform_provider:
            logger.info(f"Platform provider {provider_id} loaded successfully")
        else:
            logger.error(f"Failed to load platform provider: {provider_id}")
        
        return platform_provider
    
    def _find_matching_providers(self) -> List[str]:
        """Find providers that match the detected platform"""
        
        # First, try exact platform type match
        matching_providers = platform_registry.find_providers_by_type(self.platform_config.platform_type)
        
        if matching_providers:
            return matching_providers
        
        # Try platform ID pattern matching
        available_providers = platform_registry.list_providers()
        platform_name = self.platform_config.platform_type.value
        
        for provider_id in available_providers:
            if platform_name in provider_id.lower():
                matching_providers.append(provider_id)
        
        return matching_providers
    
    def get_platform_status(self) -> Dict[str, Any]:
        """Get current platform status"""
        status = {
            'platform_detected': self.platform_config is not None,
            'platform_loaded': self.loaded_platform is not None,
            'mockup_directory': self.mockup_dir
        }
        
        if self.platform_config:
            status.update({
                'platform_config': self.platform_config.to_dict(),
                'platform_type': self.platform_config.platform_type.value,
                'platform_id': self.platform_config.platform_id
            })
        
        if self.loaded_platform:
            status.update({
                'platform_info': self.loaded_platform.get_platform_info(),
                'platform_capabilities': [cap.value for cap in self.loaded_platform.get_all_capabilities()],
                'registered_services': list(self.loaded_platform.services.keys()),
                'registered_handlers': list(self.loaded_platform.handlers.keys())
            })
        
        # Add registry status
        status['registry'] = platform_registry.get_registry_status()
        
        return status
    
    def list_available_platforms(self) -> List[Dict[str, Any]]:
        """List all available platforms"""
        platforms = []
        
        for provider_id in platform_registry.list_providers():
            platform_info = platform_registry.get_platform_info(provider_id)
            if platform_info:
                platforms.append(platform_info)
            else:
                # Get basic info from provider class if instance not available
                try:
                    provider_class = platform_registry._providers[provider_id]
                    temp_instance = provider_class({})
                    platforms.append({
                        'platform_id': provider_id,
                        'platform_type': temp_instance.get_platform_type().value,
                        'display_name': provider_id.replace('_', ' ').title(),
                        'description': f"Platform provider: {provider_class.__name__}",
                        'status': 'available'
                    })
                except Exception as e:
                    logger.error(f"Error getting info for provider {provider_id}: {e}")
                    platforms.append({
                        'platform_id': provider_id,
                        'status': 'error',
                        'error': str(e)
                    })
        
        return platforms
    
    def reload_platform(self, platform_id: str = None) -> bool:
        """Reload the current or specified platform"""
        try:
            if platform_id:
                # Load specific platform
                platform_provider = platform_registry.get_provider(
                    platform_id, 
                    self.platform_config.to_dict() if self.platform_config else {}
                )
            else:
                # Reload current platform
                platform_provider = self.discover_and_load_platform()
            
            if platform_provider:
                self.loaded_platform = platform_provider
                logger.info("Platform reloaded successfully")
                return True
            else:
                logger.error("Failed to reload platform")
                return False
        except Exception as e:
            logger.error(f"Error reloading platform: {e}")
            return False
    
    def load_plugin_explicitly(self, plugin_name: str, plugin_config: Dict[str, Any] = None) -> Optional[Any]:
        """
        Explicitly load a plugin by name without auto-discovery
        
        Args:
            plugin_name: Name of the plugin to load (e.g., 'ras')
            plugin_config: Plugin-specific configuration
            
        Returns:
            Plugin handler instance or None if failed
        """
        try:
            logger.info(f"Explicitly loading plugin: {plugin_name}")
            
            # Import the plugin directly
            if plugin_name == 'ras':
                from src.plugins.ras.provider import RASHandler
                config = plugin_config or {'mockup_dir': self.mockup_dir}
                handler = RASHandler(config)
                logger.info(f"RAS plugin loaded successfully")
                return handler
            else:
                logger.error(f"Unknown plugin: {plugin_name}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}")
            import traceback
            traceback.print_exc()
            return None
