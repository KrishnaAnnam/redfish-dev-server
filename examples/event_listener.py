#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Simple HTTP Event Listener for Redfish Events
Receives and displays events from the BMC EventService
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EventListenerHandler(BaseHTTPRequestHandler):
    """HTTP handler for receiving Redfish events"""
    
    events_received = []
    
    def log_message(self, format, *args):
        """Override to use logger instead of stderr"""
        logger.info("%s - %s" % (self.address_string(), format % args))
    
    def do_POST(self):
        """Handle POST requests (event notifications)"""
        try:
            # Read the event data
            content_length = int(self.headers.get('Content-Length', 0))
            event_data = self.rfile.read(content_length)
            
            # Parse JSON
            event_json = json.loads(event_data.decode('utf-8'))
            
            # Store event
            EventListenerHandler.events_received.append({
                'timestamp': datetime.now().isoformat(),
                'data': event_json
            })
            
            # Display event
            self._display_event(event_json)
            
            # Send 204 No Content response
            self.send_response(204)
            self.end_headers()
            
        except Exception as e:
            logger.error(f"Error processing event: {e}")
            self.send_response(400)
            self.end_headers()
    
    def _display_event(self, event_data):
        """Display event in formatted output"""
        print("\n" + "=" * 80)
        print("🔔 EVENT RECEIVED")
        print("=" * 80)
        print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Event details
        events = event_data.get('Events', [])
        for idx, event in enumerate(events, 1):
            print(f"\n📋 Event {idx}/{len(events)}:")
            print(f"   Event Type: {event.get('EventType', 'Unknown')}")
            print(f"   Event ID: {event.get('EventId', 'N/A')}")
            print(f"   Timestamp: {event.get('EventTimestamp', 'N/A')}")
            print(f"   Severity: {event.get('Severity', 'N/A')}")
            print(f"   Message: {event.get('Message', 'N/A')}")
            
            # Message details
            message_args = event.get('MessageArgs', [])
            if message_args:
                print(f"   Arguments: {', '.join(str(arg) for arg in message_args)}")
            
            # Origin of condition
            origin = event.get('OriginOfCondition', {})
            if origin:
                origin_id = origin.get('@odata.id', 'N/A')
                print(f"   Origin: {origin_id}")
            
            # OEM data
            oem = event.get('Oem', {})
            if oem:
                ras_proto = oem.get('OCPRASAPIWS', {})
                if ras_proto:
                    print(f"\n   🔧 RAS Plugin Data:")
                    for key, value in ras_proto.items():
                        if key != '@odata.type':
                            print(f"      {key}: {value}")
        
        print("=" * 80)
        print(f"Total events received: {len(EventListenerHandler.events_received)}\n")
    
    def do_GET(self):
        """Handle GET requests (for testing)"""
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            status = {
                'status': 'listening',
                'events_received': len(EventListenerHandler.events_received),
                'endpoint': f'http://localhost:{self.server.server_port}/'
            }
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Event Listener Ready\n')


class EventListener:
    """Event listener server"""
    
    def __init__(self, host='0.0.0.0', port=8888):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
    
    def start(self):
        """Start the event listener server"""
        self.server = HTTPServer((self.host, self.port), EventListenerHandler)
        
        print("\n" + "=" * 80)
        print("🎧 REDFISH EVENT LISTENER")
        print("=" * 80)
        print(f"Listening on: http://{self.host}:{self.port}/")
        print(f"Status endpoint: http://localhost:{self.port}/status")
        print("\nWaiting for events... (Press Ctrl+C to stop)")
        print("=" * 80 + "\n")
        
        # Start server in thread
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """Stop the event listener server"""
        if self.server:
            print("\n\nShutting down event listener...")
            self.server.shutdown()
            self.server.server_close()
            print("Event listener stopped.")
    
    def run_blocking(self):
        """Run the server in blocking mode"""
        self.server = HTTPServer((self.host, self.port), EventListenerHandler)
        
        print("\n" + "=" * 80)
        print("🎧 REDFISH EVENT LISTENER")
        print("=" * 80)
        print(f"Listening on: http://{self.host}:{self.port}/")
        print(f"Status endpoint: http://localhost:{self.port}/status")
        print("\nWaiting for events... (Press Ctrl+C to stop)")
        print("=" * 80 + "\n")
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\n\nShutting down event listener...")
            self.server.shutdown()
            self.server.server_close()
            
            # Display summary
            print("\n" + "=" * 80)
            print("📊 EVENT SUMMARY")
            print("=" * 80)
            print(f"Total events received: {len(EventListenerHandler.events_received)}")
            
            if EventListenerHandler.events_received:
                print("\nEvents by type:")
                event_types = {}
                for evt in EventListenerHandler.events_received:
                    for e in evt['data'].get('Events', []):
                        evt_type = e.get('EventType', 'Unknown')
                        event_types[evt_type] = event_types.get(evt_type, 0) + 1
                
                for evt_type, count in event_types.items():
                    print(f"  - {evt_type}: {count}")
            
            print("=" * 80)


if __name__ == '__main__':
    listener = EventListener(host='0.0.0.0', port=8888)
    listener.run_blocking()
