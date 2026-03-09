#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
BMC Redfish Simulator - Enhanced Server
========================================
Based on DMTF Redfish-Mockup-Server

Enhanced server with comprehensive message responses, logging, and event management.
Integrates MessageService, LogService, and EventService with existing mockup functionality.
"""

import sys
import os
import signal
import logging
from argparse import ArgumentParser

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import base server components
from redfishMockupServer_modular import main as base_main, parse_arguments as base_parse_arguments
from src.config.server_config import ServerConfig

# Import enhanced services
from src.services.message_service import init_message_service
from src.services.log_service import init_log_service  
from src.services.enhanced_event_service import init_enhanced_event_service

# Import enhanced handlers
from src.handlers.enhanced_handlers import (
    EnhancedPostHandler, EnhancedGetHandler, 
    EnhancedPatchHandler, EnhancedDeleteHandler
)

logger = logging.getLogger(__name__)

def create_enhanced_argument_parser():
    """Create argument parser with enhanced options"""
    parser = ArgumentParser(
        description="BMC Redfish Simulator - Enhanced server with comprehensive message responses and logging"
    )
    
    # Add base arguments (from original parser)
    parser.add_argument(
        "-H", "--host", dest="hostname", metavar="HOST",
        default="127.0.0.1", 
        help="hostname or IP address (default 127.0.0.1)"
    )
    parser.add_argument(
        "-p", "--port", dest="port", type=int, metavar="PORT",
        default=8000,
        help="host port (default 8000)"
    )
    parser.add_argument(
        "-D", "--dir", dest="mock_dir_path", metavar="PATH",
        default=None,
        help="path to mockup directory (may be relative to CWD)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="verbose level logging"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", 
        help="quiet mode, no logging"
    )
    parser.add_argument(
        "-s", "--ssl", action="store_true",
        help="place server in SSL (HTTPS) mode"
    )
    parser.add_argument(
        "--cert", dest="ssl_cert", metavar="FILE",
        help="the certificate for SSL"
    )
    parser.add_argument(
        "--key", dest="ssl_key", metavar="FILE", 
        help="the key for SSL"
    )
    parser.add_argument(
        "-P", "--ssdp", action="store_true",
        help="make mockup SSDP discoverable"
    )
    parser.add_argument(
        "-S", "--short-form", "--shortForm", dest="short_form", action="store_true",
        help="apply short form to mockup"
    )
    
    # Enhanced server specific arguments
    parser.add_argument(
        "--enhanced-responses", action="store_true", default=True,
        help="enable enhanced Redfish message responses (default: enabled)"
    )
    parser.add_argument(
        "--disable-logging", action="store_true",
        help="disable enhanced logging system"
    )
    parser.add_argument(
        "--disable-events", action="store_true", 
        help="disable enhanced event system"
    )
    parser.add_argument(
        "--log-storage-path", metavar="PATH",
        help="custom path for log storage (default: mockup_dir/logs)"
    )
    parser.add_argument(
        "--max-log-entries", type=int, default=1000,
        help="maximum log entries per service (default: 1000)"
    )
    parser.add_argument(
        "--event-delivery-interval", type=int, default=1,
        help="event delivery check interval in seconds (default: 1)"
    )
    
    return parser

def parse_enhanced_arguments():
    """Parse command line arguments with enhanced options"""
    parser = create_enhanced_argument_parser()
    args = parser.parse_args()
    
    # Create enhanced config
    config = ServerConfig()
    
    # Set base configuration
    config.hostname = args.hostname
    config.port = args.port
    config.mock_dir_path = args.mock_dir_path or os.path.join(os.getcwd(), "public-rackmount1")
    config.verbose = args.verbose
    config.quiet = args.quiet
    config.ssl = args.ssl
    config.ssl_cert = args.ssl_cert
    config.ssl_key = args.ssl_key
    config.ssdp = args.ssdp
    config.short_form = args.short_form
    
    # Set enhanced configuration
    config.enhanced_responses = args.enhanced_responses
    config.disable_logging = args.disable_logging
    config.disable_events = args.disable_events
    config.log_storage_path = args.log_storage_path
    config.max_log_entries = args.max_log_entries
    config.event_delivery_interval = args.event_delivery_interval
    
    return config

def initialize_enhanced_services(config):
    """Initialize enhanced services"""
    try:
        # Initialize message service (always enabled for enhanced responses)
        init_message_service(config)
        logger.info("MessageService initialized")
        
        # Initialize log service if not disabled
        if not getattr(config, 'disable_logging', False):
            init_log_service(config)
            logger.info("LogService initialized")
        
        # Initialize event service if not disabled
        if not getattr(config, 'disable_events', False):
            init_enhanced_event_service(config)
            logger.info("Enhanced EventService initialized")
        
        logger.info("All enhanced services initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize enhanced services: {e}")
        return False

def create_enhanced_handler_class():
    """Create enhanced handler class with all HTTP methods"""
    from src.handlers.base_handler import BaseRedfishHandler
    from src.handlers.get_handler import GetHandler
    from src.handlers.post_handler import PostHandler
    from src.handlers.patch_handler import PatchHandler
    from src.handlers.put_handler import PutHandler
    from src.handlers.delete_handler import DeleteHandler
    
    class EnhancedRedfishHandler(
        BaseRedfishHandler,
        EnhancedGetHandler,
        EnhancedPostHandler, 
        EnhancedPatchHandler,
        EnhancedDeleteHandler
    ):
        """Enhanced Redfish handler with all HTTP methods and enhanced responses"""
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            
        def do_GET(self):
            """Handle GET with enhanced response or fallback to original"""
            if getattr(self.server_config, 'enhanced_responses', True):
                return EnhancedGetHandler.do_GET(self)
            else:
                return GetHandler.do_GET(self)
        
        def do_POST(self):
            """Handle POST with enhanced response or fallback to original"""
            if getattr(self.server_config, 'enhanced_responses', True):
                return EnhancedPostHandler.do_POST(self)
            else:
                return PostHandler.do_POST(self)
        
        def do_PATCH(self):
            """Handle PATCH with enhanced response or fallback to original"""
            if getattr(self.server_config, 'enhanced_responses', True):
                return EnhancedPatchHandler.do_PATCH(self)
            else:
                return PatchHandler.do_PATCH(self)
        
        def do_DELETE(self):
            """Handle DELETE with enhanced response or fallback to original"""
            if getattr(self.server_config, 'enhanced_responses', True):
                return EnhancedDeleteHandler.do_DELETE(self)
            else:
                return DeleteHandler.do_DELETE(self)
    
    return EnhancedRedfishHandler

def setup_logging(config):
    """Set up logging configuration"""
    if getattr(config, 'quiet', False):
        log_level = logging.ERROR
    elif getattr(config, 'verbose', False):
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def enhanced_signal_handler(signum, frame, event_service=None):
    """Enhanced signal handler that properly cleans up services"""
    logger.info(f"Received signal {signum}: Shutting down enhanced server")
    
    # Stop event service if running
    if event_service:
        try:
            event_service.stop()
            logger.info("Event service stopped")
        except Exception as e:
            logger.error(f"Error stopping event service: {e}")
    
    sys.exit(0)

def main():
    """Enhanced server main entry point"""
    try:
        # Parse configuration
        config = parse_enhanced_arguments()
        config.validate()
        
        # Setup logging
        setup_logging(config)
        
        logger.info("🚀 Starting BMC Redfish Simulator (Enhanced Mode)")
        logger.info(f"Version: Enhanced v2.0 (based on modular architecture)")
        logger.info(f"Host: {config.hostname}")
        logger.info(f"Port: {config.port}")
        logger.info(f"Mockup directory: {config.mock_dir}")
        logger.info(f"Enhanced responses: {getattr(config, 'enhanced_responses', True)}")
        logger.info(f"Logging enabled: {not getattr(config, 'disable_logging', False)}")
        logger.info(f"Events enabled: {not getattr(config, 'disable_events', False)}")
        
        # Initialize enhanced services
        if not initialize_enhanced_services(config):
            logger.error("Failed to initialize enhanced services")
            return 1
        
        # Create enhanced handler
        handler_class = create_enhanced_handler_class()
        
        # Get event service for signal handler
        event_service = None
        if not getattr(config, 'disable_events', False):
            from src.services.enhanced_event_service import get_enhanced_event_service
            event_service = get_enhanced_event_service()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, lambda s, f: enhanced_signal_handler(s, f, event_service))
        signal.signal(signal.SIGTERM, lambda s, f: enhanced_signal_handler(s, f, event_service))
        
        # Start the server using modular base but with enhanced handler
        from http.server import HTTPServer
        import ssl
        
        # Create server
        mockup_server = HTTPServer((config.hostname, config.port), handler_class)
        mockup_server.server_config = config
        mockup_server.config = config  # For compatibility
        
        # Configure SSL if requested
        if config.ssl:
            if not config.ssl_cert or not config.ssl_key:
                logger.error("SSL enabled but certificate or key file not specified")
                return 1
            
            mockup_server.socket = ssl.wrap_socket(
                mockup_server.socket,
                certfile=config.ssl_cert,
                keyfile=config.ssl_key,
                server_side=True
            )
            logger.info("SSL/TLS enabled")
        
        # Start SSDP if requested
        ssdp_server = None
        if config.ssdp:
            try:
                from rfSsdpServer import RfSSDPServer
                ssdp_server = RfSSDPServer()
                ssdp_server.start_server()
                logger.info("SSDP discovery enabled")
            except Exception as e:
                logger.warning(f"Failed to start SSDP server: {e}")
        
        # Log startup completion
        protocol = "HTTPS" if config.ssl else "HTTP"
        logger.info(f"✅ BMC Redfish Simulator running on {protocol}://{config.hostname}:{config.port}")
        logger.info("Enhanced features:")
        logger.info("  • Standardized Redfish message responses with ExtendedInfo")
        logger.info("  • Comprehensive logging system (Event, Audit, Security logs)")
        logger.info("  • Enhanced event system with subscriptions and notifications")
        logger.info("  • Message registry integration for consistent error handling")
        logger.info("  • HTTP method integration with enhanced responses")
        logger.info("Press Ctrl+C to stop server")
        
        # Start serving
        try:
            mockup_server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Shutting down server...")
            mockup_server.server_close()
            if ssdp_server:
                ssdp_server.stop_server()
            if event_service:
                event_service.stop()
        
        return 0
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Server error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())