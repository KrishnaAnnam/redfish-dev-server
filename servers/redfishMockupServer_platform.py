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

# Add project root directory to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.config.settings import parse_arguments, ServerConfig
from src.core.discovery import PlatformDiscovery
from src.core.platform_config import PlatformDetectionMethod
from src.core.extensible_services import ServiceManager
from src.handlers.main_handler import RedfishMockupHandler

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
        self.plugin_handlers = getattr(server, 'plugin_handlers', {})
        
        super().__init__(request, client_address, server)
    
    def do_GET(self):
        """Enhanced GET handler with platform and plugin support"""
        # Check if a plugin can handle this path
        for plugin_name, plugin_handler in self.plugin_handlers.items():
            if plugin_handler.can_handle_path(self.path):
                try:
                    status, response_data = plugin_handler.handle_get(self.path, {}, self.cached_links)
                    if status != 405:  # Plugin handled it
                        self._send_platform_response(status, response_data)
                        return
                except Exception as e:
                    logger.error(f"Plugin {plugin_name} GET handler error: {e}")
        
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
        
        # Check if a plugin can handle this path
        for plugin_name, plugin_handler in self.plugin_handlers.items():
            if plugin_handler.can_handle_path(self.path):
                try:
                    # Forward to the plugin and return its real status code.
                    # For SubmitCPAD the plugin runs the acceptance checks
                    # (PlatformID / PartitionID / well-formed) and returns
                    # 202 (Accepted) on success or a 4xx on rejection — the
                    # client must be told which (spec §6.5).  Do not send a
                    # premature status before the handler has decided.
                    status, response_data = plugin_handler.handle_post(
                        self.path, data_received or {}, self.cached_links)
                    if status != 405:  # Plugin handled it
                        self._send_platform_response(status, response_data)

                        # Bridge: notify core EventService subscribers only when
                        # the CPAD was accepted for processing (2xx).
                        if 'SubmitCPAD' in self.path and 200 <= status < 300:
                            self._dispatch_ras_cpad_events(data_received or {})

                        return
                except Exception as e:
                    logger.error(f"Plugin {plugin_name} POST handler error: {e}")
        
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
    
    def _dispatch_ras_cpad_events(self, data_received):
        """After a SubmitCPAD, notify core EventService subscribers.

        The RAS plugin creates LogEntries but does not push events to
        Redfish EventService subscribers.  This bridge scans for recently
        created entries and fires OCPRAS events (§5.5) so that subscription
        listeners (e.g. SDK RedfishEventListener) receive push notifications.
        """
        try:
            import re
            import time
            from datetime import datetime, timezone

            manager_match = re.search(r'/Managers/([^/]+)/', self.path)
            manager_id = manager_match.group(1) if manager_match else "System"

            entries_dir = os.path.join(
                self.server.config.mock_dir,
                "redfish", "v1", "Managers", manager_id,
                "LogServices", "CPER", "Entries"
            )

            if not os.path.isdir(entries_dir):
                logger.info(f"EventBridge: entries_dir not found: {entries_dir}")
                return

            # Find entry directories with index.json modified in the last 10 seconds
            now = time.time()
            all_dirs = [
                name for name in os.listdir(entries_dir)
                if os.path.isdir(os.path.join(entries_dir, name))
                and name != "__pycache__"
            ]
            recent_entries = []
            for name in all_dirs:
                index_file = os.path.join(entries_dir, name, "index.json")
                if os.path.exists(index_file):
                    age = now - os.path.getmtime(index_file)
                    if age < 10:
                        recent_entries.append(name)

            for entry_id in recent_entries:
                # Read the LogEntry to get severity, MessageId, DiagnosticData
                entry_file = os.path.join(entries_dir, entry_id, "index.json")
                log_entry = {}
                if os.path.exists(entry_file):
                    with open(entry_file, 'r') as f:
                        log_entry = json.load(f)

                severity = log_entry.get("Severity", "Warning")
                message_id = log_entry.get("MessageId", "OCPRAS.1.0.0.CorrectedError")
                message = log_entry.get("Message", "CPER record created.")
                oem = log_entry.get("Oem", {}).get("OCPRASAPIWS", {})

                event_data = {
                    "EventType": "Alert",
                    "EventId": f"CPER-{entry_id}",
                    "EventTimestamp": datetime.now(timezone.utc).isoformat(),
                    "Severity": severity,
                    "Message": message,
                    "MessageId": message_id,
                    "MessageArgs": [],
                    "OriginOfCondition": {
                        "@odata.id": f"/redfish/v1/Managers/{manager_id}/LogServices/CPER/Entries/{entry_id}"
                    },
                }

                # Pattern A: include inline DiagnosticData; Pattern B: include AdditionalDataURI
                if "DiagnosticData" in log_entry:
                    event_data["DiagnosticData"] = log_entry["DiagnosticData"]
                    event_data["DiagnosticDataType"] = "CPER"
                elif "AdditionalDataURI" in log_entry:
                    event_data["AdditionalDataURI"] = log_entry["AdditionalDataURI"]

                # Include OEM metadata
                if oem:
                    event_data["Oem"] = {"OCPRASAPIWS": oem}

                self.event_service.handle_eventing(
                    "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent",
                    event_data,
                    self.cached_links,
                )

            if recent_entries:
                logger.info(f"EventBridge: dispatched {len(recent_entries)} OCPRAS events for CPER LogEntries")

        except Exception as e:
            logger.error(f"EventBridge: failed to dispatch RAS events: {e}")

    def _send_platform_response(self, status: int, response_data=None):
        """Send platform handler response.

        Accepts either a dict (sent as JSON) or raw bytes (sent as
        application/octet-stream, e.g. a binary CPER attachment).
        """
        self.send_response(status)

        if isinstance(response_data, (bytes, bytearray)):
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", len(response_data))
            self.end_headers()
            self.wfile.write(response_data)
        elif response_data:
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
            
            # Check for platform_config.json for explicit plugin configuration
            platform_config_path = os.path.join(self.config.mock_dir, 'platform_config.json')
            explicit_plugins = []
            
            if os.path.exists(platform_config_path):
                try:
                    with open(platform_config_path) as f:
                        platform_config = json.load(f)
                        explicit_plugins = platform_config.get('plugins', [])
                        if explicit_plugins:
                            logger.info(f"Found explicit plugin configuration: {explicit_plugins}")
                except Exception as e:
                    logger.warning(f"Could not read platform_config.json: {e}")
            
            # Determine detection method
            detection_method = PlatformDetectionMethod.AUTO_MOCKUP
            platform_hint = getattr(self.config, 'platform_hint', None)
            
            # Discover and load platform (skip auto-discovery if explicit plugins configured)
            self.platform_provider = discovery.discover_and_load_platform(
                platform_hint=platform_hint,
                detection_method=detection_method,
                skip_auto_discover=bool(explicit_plugins)
            )
            
            # Load explicit plugins if configured
            if explicit_plugins:
                logger.info("Loading explicitly configured plugins...")
                print(f"DEBUG: Loading {len(explicit_plugins)} plugins")
                for plugin_spec in explicit_plugins:
                    if isinstance(plugin_spec, str):
                        plugin_name = plugin_spec
                        plugin_config = {}
                    elif isinstance(plugin_spec, dict):
                        plugin_name = plugin_spec.get('name')
                        plugin_config = plugin_spec.get('config', {})
                    else:
                        continue
                    
                    if plugin_name and plugin_spec.get('enabled', True) if isinstance(plugin_spec, dict) else True:
                        print(f"DEBUG: Loading plugin: {plugin_name}")
                        plugin_config['mockup_dir'] = self.config.mock_dir
                        plugin_handler = discovery.load_plugin_explicitly(plugin_name, plugin_config)
                        print(f"DEBUG: Plugin handler result: {plugin_handler}")
                        if plugin_handler:
                            # Store plugin handler for request routing
                            if not hasattr(self, 'plugin_handlers'):
                                self.plugin_handlers = {}
                            self.plugin_handlers[plugin_name] = plugin_handler
                            print(f"DEBUG: ✅ Plugin {plugin_name} stored in plugin_handlers")
                            logger.info(f"Plugin {plugin_name} loaded and registered")
                        else:
                            print(f"DEBUG: ❌ Plugin {plugin_name} returned None")

            
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
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    main()
