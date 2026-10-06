#!/usr/bin/env python3

# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Enhanced Redfish Mockup Server with Platform Support
A platform-aware implementation of the DMTF Redfish Mockup Server with auto-detection and extensibility.
"""

import sys
import os
import ssl
import json
import shutil
import signal
import logging
import threading
from http.server import HTTPServer
from urllib.parse import parse_qs, urlparse

# Add project root directory to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.config.settings import parse_arguments, ServerConfig
from src.core.discovery import PlatformDiscovery
from src.core.platform_config import (
    PlatformDetectionMethod,
    load_platform_config,
)
from src.core.extensible_services import ServiceManager
from src.handlers.main_handler import RedfishMockupHandler
from src.plugins import shutdown_plugins
from src.plugins.loader import normalize_plugin_specs

# Add scripts directory to path for rfSsdpServer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from rfSsdpServer import RfSSDPServer

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Global variables for cleanup
mockup_server = None
ssdp_server = None
platform_discovery = None
service_manager = None


class PlatformAwareRedfishHandler(RedfishMockupHandler):
    """Enhanced Redfish handler with platform support"""
    
    def __init__(self, request, client_address, server):
        # Initialize service manager with platform provider
        self.service_manager = server.service_manager
        self.platform_provider = server.platform_provider
        
        super().__init__(request, client_address, server)
    
    def do_GET(self):
        """Enhanced GET handler with platform and plugin support"""
        parsed = urlparse(self.path)
        try:
            plugin_response = self.plugin_loader.handle_get(
                parsed.path,
                parse_qs(parsed.query, keep_blank_values=True),
                self.cached_links,
            )
        except Exception:
            logger.exception("Plugin GET handler failed for %s", parsed.path)
            self._send_plugin_error()
            return

        if plugin_response is not None:
            self._send_plugin_response(plugin_response)
            return

        # Check if platform provider can handle this path
        if self.platform_provider:
            handler = self.platform_provider.get_handler_for_path(self.path)
            if handler:
                try:
                    status, response_data = handler.handle_get(self.path, {}, self.cached_links)
                    if status != 405:  # Platform handled it
                        self._send_platform_response(status, response_data)
                        return
                except Exception as e:
                    logger.error(f"Platform GET handler error: {e}")
        
        # Fall back to standard GET handling
        super().do_GET()
    
    def do_POST(self):
        """Enhanced POST handler with platform and plugin support"""
        import io
        
        # Get request data first
        data_received = None
        raw_body = b''
        
        if "content-length" in self.headers:
            lenn = int(self.headers["content-length"])
            if lenn > 0:
                raw_body = self.rfile.read(lenn)
                try:
                    data_received = json.loads(raw_body.decode("utf-8"))
                except (ValueError, json.JSONDecodeError):
                    logger.error('Decoding JSON has failed')
                    self.send_response(400)
                    self.end_headers()
                    return

        request_path = urlparse(self.path).path
        try:
            plugin_response = self.plugin_loader.handle_post(
                request_path,
                data_received or {},
                self.cached_links,
            )
        except Exception:
            logger.exception("Plugin POST handler failed for %s", request_path)
            self._send_plugin_error()
            return

        if plugin_response is not None:
            self._send_plugin_response(plugin_response)
            return
        
        # Check if platform provider can handle this path
        if self.platform_provider and data_received:
            handler = self.platform_provider.get_handler_for_path(self.path)
            if handler:
                try:
                    status, response_data = handler.handle_post(self.path, data_received, self.cached_links)
                    if status != 405:  # Platform handled it
                        self._send_platform_response(status, response_data)
                        return
                except Exception as e:
                    logger.error(f"Platform POST handler error: {e}")
        
        # Restore the body for the parent handler by wrapping in BytesIO
        # This allows super().do_POST() to re-read the body
        self.rfile = io.BytesIO(raw_body)
        
        # Fall back to standard POST handling
        super().do_POST()
    
    def _send_platform_response(self, status: int, response_data: dict = None):
        """Send platform handler response"""
        self.send_response(status)
        
        if response_data:
            encoded_data = json.dumps(response_data, sort_keys=True, indent=4, separators=(",", ": ")).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)
        else:
            self.end_headers()


class PlatformAwareRedfishServer(HTTPServer):
    """Enhanced HTTPServer with platform and service management"""
    
    def __init__(self, server_address, request_handler, config):
        super().__init__(server_address, request_handler)
        self.config = config
        self.platform_provider = None
        self.service_manager = ServiceManager(config)
        
        # Initialize platform discovery and loading
        self._initialize_platform()
    
    def _initialize_platform(self):
        """Initialize platform discovery and loading"""
        try:
            # Create platform discovery
            discovery = PlatformDiscovery(self.config.mock_dir)
            
            # Propagate plugin configuration through the server configuration.
            platform_config_path = os.path.join(self.config.mock_dir, 'platform_config.json')
            if os.path.exists(platform_config_path):
                platform_config = load_platform_config(platform_config_path)
                self.config.extensions = platform_config.extensions
                normalize_plugin_specs(self.config.extensions)
                logger.info(
                    "Configured extensions: %s",
                    self.config.extensions
                )
            
            # Determine detection method
            detection_method = PlatformDetectionMethod.AUTO_MOCKUP
            platform_hint = getattr(self.config, 'platform_hint', None)
            
            # Discover and load platform providers independently of plugins.
            self.platform_provider = discovery.discover_and_load_platform(
                platform_hint=platform_hint,
                detection_method=detection_method
            )
            
            # Set platform provider in service manager
            if self.platform_provider:
                self.service_manager.set_platform_provider(self.platform_provider)
                logger.info(f"Platform loaded: {self.platform_provider.get_platform_info()['display_name']}")
                
                # Log platform capabilities
                capabilities = self.platform_provider.get_all_capabilities()
                if capabilities:
                    logger.info(f"Platform capabilities: {[cap.value for cap in capabilities]}")
            else:
                logger.info("Running in generic mode without platform-specific features")
            
            # Store discovery for later use
            global platform_discovery
            platform_discovery = discovery
            
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            raise
        except Exception as e:
            logger.error(f"Platform initialization failed: {e}")
            logger.info("Continuing with generic functionality")


def enhanced_parse_arguments():
    """Enhanced argument parsing with platform options"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Serve a static Redfish mockup with platform support.')
    
    # Standard arguments
    parser.add_argument('-H', '--host', '--Host', default='127.0.0.1',
                        help='hostname or IP address (default 127.0.0.1)')
    parser.add_argument('-p', '--port', '--Port', default=8000, type=int,
                        help='host port (default 8000)')
    parser.add_argument('-D', '--dir', '--Dir',
                        help='path to mockup dir (may be relative to CWD)')
    parser.add_argument('-E', '--test-etag', '--TestEtag',
                        action='store_true',
                        help='(unimplemented) etag testing')
    parser.add_argument('-X', '--headers', action='store_true',
                        help='load headers from headers.json files in mockup')
    parser.add_argument('-t', '--time', default=0,
                        help='delay in seconds added to responses (float or int)')
    parser.add_argument('-T', action='store_true',
                        help='delay response based on times in time.json files in mockup')
    parser.add_argument('-s', '--ssl', action='store_true',
                        help='place server in SSL (HTTPS) mode; requires a cert and key')
    parser.add_argument('--cert', help='the certificate for SSL')
    parser.add_argument('--key', help='the key for SSL')
    parser.add_argument('-S', '--short-form', '--shortForm', action='store_true',
                        help='apply short form to mockup (omit filepath /redfish/v1)')
    parser.add_argument('-P', '--ssdp', action='store_true',
                        help='make mockup SSDP discoverable')
    
    # Platform-specific arguments
    parser.add_argument('--platform', dest='platform_hint',
                        choices=['dell', 'hpe', 'supermicro', 'lenovo', 'generic'],
                        help='specify platform type for enhanced features')
    parser.add_argument('--list-platforms', action='store_true',
                        help='list available platform providers and exit')
    parser.add_argument('--platform-info', action='store_true',
                        help='show detected platform information and exit')
    
    args = parser.parse_args()
    
    # Handle special actions
    if args.list_platforms:
        _list_platforms()
        sys.exit(0)
    
    if args.platform_info:
        _show_platform_info(args)
        sys.exit(0)
    
    # Create enhanced config
    config = ServerConfig(
        hostname=args.host,
        port=args.port,
        mock_dir_path=args.dir,
        test_etag=args.test_etag,
        headers=args.headers,
        response_time=float(args.time),
        time_from_json=args.T,
        ssl_mode=args.ssl,
        ssl_cert=args.cert,
        ssl_key=args.key,
        short_form=args.short_form,
        ssdp_start=args.ssdp
    )
    
    # Add platform hint
    config.platform_hint = args.platform_hint
    
    return config


def _list_platforms():
    """List available platform providers"""
    print("\nAvailable Platform Providers:")
    print("=" * 50)
    
    # Create dummy discovery to get providers
    try:
        from src.core.registry import platform_registry
        
        # Discover providers
        discovered = platform_registry.auto_discover_providers()
        
        if discovered == 0:
            print("No platform providers found.")
            return
        
        providers = platform_registry.list_providers()
        for provider_id in providers:
            try:
                info = platform_registry.get_platform_info(provider_id)
                if info:
                    print(f"  {provider_id}:")
                    print(f"    Name: {info.get('display_name', 'Unknown')}")
                    print(f"    Type: {info.get('platform_type', 'Unknown')}")
                    print(f"    Description: {info.get('description', 'No description')}")
                    print()
                else:
                    print(f"  {provider_id}: (Information not available)")
            except Exception as e:
                print(f"  {provider_id}: (Error: {e})")
    
    except Exception as e:
        print(f"Error listing platforms: {e}")


def _show_platform_info(args):
    """Show platform detection information"""
    print("\nPlatform Detection Information:")
    print("=" * 50)
    
    # Determine mockup directory
    mock_dir_path = args.dir or 'public-rackmount1'
    mock_dir = os.path.realpath(mock_dir_path)
    
    if not os.path.exists(mock_dir):
        print(f"Mockup directory not found: {mock_dir}")
        return
    
    try:
        # Create discovery instance
        discovery = PlatformDiscovery(mock_dir)
        
        # Get platform status
        status = discovery.get_platform_status()
        
        print(f"Mockup Directory: {mock_dir}")
        print(f"Platform Detected: {status.get('platform_detected', False)}")
        
        if status.get('platform_config'):
            config = status['platform_config']
            print(f"Platform Type: {config.get('platform_type', 'Unknown')}")
            print(f"Platform ID: {config.get('platform_id', 'Unknown')}")
            print(f"Display Name: {config.get('display_name', 'Unknown')}")
            print(f"OEM Namespace: {config.get('oem_namespace', 'None')}")
            
            enabled_services = config.get('enabled_services', [])
            if enabled_services:
                print(f"Detected Services: {', '.join(enabled_services)}")
        
        # Show available platforms
        print(f"\nRegistry Status:")
        registry_status = status.get('registry', {})
        print(f"  Registered Providers: {registry_status.get('registered_providers', 0)}")
        print(f"  Available Providers: {', '.join(registry_status.get('provider_list', []))}")
        
    except Exception as e:
        print(f"Error detecting platform: {e}")


def setup_ssdp_server(config):
    """Set up SSDP server if enabled"""
    if not config.ssdp_start:
        return None
    
    try:
        from gevent import monkey
        monkey.patch_all()
        
        # Load service root data
        service_root_path = os.path.join(
            config.mock_dir, 
            'index.json' if config.short_form else 'redfish/v1/index.json'
        )
        
        json_data = None
        if os.path.isfile(service_root_path):
            with open(service_root_path) as f:
                json_data = json.load(f)
        
        protocol = 'https' if config.ssl_mode else 'http'
        location = f"{protocol}://{config.hostname}:{config.port}/redfish/v1"
        
        return RfSSDPServer(json_data, location, config.hostname)
        
    except ImportError:
        logger.error("gevent not available for SSDP support")
        return None
    except Exception as e:
        logger.error(f"Failed to setup SSDP server: {e}")
        return None


def setup_ssl_context(config, server):
    """Set up SSL context if SSL is enabled"""
    if config.ssl_mode:
        logger.info(f"Using SSL with certfile: {config.ssl_cert}")
        server.socket = ssl.wrap_socket(
            server.socket, 
            certfile=config.ssl_cert, 
            keyfile=config.ssl_key, 
            server_side=True
        )


def clear_subscriptions(mock_dir):
    """Clear all event subscriptions on server shutdown"""
    sub_path = os.path.join(mock_dir, 'redfish', 'v1', 'EventService', 'Subscriptions', 'index.json')
    
    if not os.path.isfile(sub_path):
        return
    
    try:
        with open(sub_path) as f:
            sub_payload = json.load(f)
        
        # Remove subscription directories
        for member in sub_payload.get('Members', []):
            member_path = os.path.join(mock_dir, member['@odata.id'].lstrip('/'))
            if os.path.exists(member_path):
                shutil.rmtree(member_path)
        
        # Reset subscription collection
        sub_payload['Members'] = []
        sub_payload['Members@odata.count'] = 0
        
        with open(sub_path, "w") as outfile:
            json.dump(sub_payload, outfile, indent=4, separators=(',', ':'))
            
        logger.info("Event subscriptions cleared")
        
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error clearing subscriptions: {e}")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}: Shutting down server")
    
    # Clear subscriptions
    if mockup_server and mockup_server.config:
        clear_subscriptions(mockup_server.config.mock_dir)
    
    # Stop servers
    if mockup_server:
        mockup_server.server_close()
    shutdown_plugins()
    
    sys.exit(0)


def main():
    """Main server entry point"""
    global mockup_server, ssdp_server, platform_discovery
    
    # Parse configuration
    try:
        config = enhanced_parse_arguments()
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    logger.info(f"BMC Redfish Simulator with Platform Support, version {config.tool_version}")
    logger.info(f'Hostname: {config.hostname}')
    logger.info(f'Port: {config.port}')
    logger.info(f"Mockup directory path: {config.mock_dir_path}")
    logger.info(f"Serving Mockup in absolute path: {config.mock_dir}")
    
    if hasattr(config, 'platform_hint') and config.platform_hint:
        logger.info(f"Platform hint: {config.platform_hint}")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Create HTTP server with platform support
        mockup_server = PlatformAwareRedfishServer(
            (config.hostname, config.port), 
            PlatformAwareRedfishHandler,
            config
        )
        
        # Set up SSL if enabled
        setup_ssl_context(config, mockup_server)
        
        # Set up SSDP server if enabled
        ssdp_server = setup_ssdp_server(config)
        if ssdp_server:
            ssdp_thread = threading.Thread(target=ssdp_server.start)
            ssdp_thread.daemon = True
            ssdp_thread.start()
            logger.info("SSDP server started")
        
        # Log platform status
        if mockup_server.platform_provider:
            platform_info = mockup_server.platform_provider.get_platform_info()
            logger.info(f"Platform: {platform_info['display_name']} v{platform_info.get('version', 'Unknown')}")
        
        logger.info(f"Serving Enhanced Redfish mockup on port: {config.port}")
        logger.info('Server started. Press Ctrl+C to stop.')
        
        # Start the server
        mockup_server.serve_forever()
        
    except KeyboardInterrupt:
        logger.info("\nReceived interrupt signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Cleanup
        if mockup_server:
            clear_subscriptions(config.mock_dir)
            mockup_server.server_close()
        shutdown_plugins()
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    main()