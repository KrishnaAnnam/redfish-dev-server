#!/usr/bin/env python3

# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Modular Redfish Mockup Server
A modular implementation of the DMTF Redfish Mockup Server with enhanced extensibility.
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

# Add project root to path so src/ and scripts/ are importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(1, os.path.join(_project_root, 'scripts'))

from src.config.settings import parse_arguments, ServerConfig
from src.handlers.main_handler import RedfishMockupHandler
from rfSsdpServer import RfSSDPServer

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.ERROR)
logger.addHandler(ch)

# Global variables for cleanup
mockup_server = None
ssdp_server = None


class RedfishMockupHTTPServer(HTTPServer):
    """Extended HTTPServer with configuration support"""
    
    def __init__(self, server_address, request_handler, config):
        super().__init__(server_address, request_handler)
        self.config = config


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
    global mockup_server, ssdp_server
    
    # Parse configuration
    try:
        config = parse_arguments()
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    logger.info(f"Redfish Mockup Server (Modular), version {config.tool_version}")
    logger.info(f'Hostname: {config.hostname}')
    logger.info(f'Port: {config.port}')
    logger.info(f"Mockup directory path: {config.mock_dir_path}")
    logger.info(f"Serving Mockup in absolute path: {config.mock_dir}")
    logger.info(f"Response time: {config.response_time} seconds")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Create HTTP server
        mockup_server = RedfishMockupHTTPServer(
            (config.hostname, config.port), 
            RedfishMockupHandler,
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
        
        logger.info(f"Serving Redfish mockup on port: {config.port}")
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