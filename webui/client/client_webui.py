#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
BMC Redfish Simulator - Client Web UI
Provides a comprehensive web interface for interacting with and analyzing Redfish servers.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import time

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# Add parent directory to path to import client modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from redfish_client.redfish_client import RedfishClient
except ImportError:
    # Fallback if client not available
    RedfishClient = None

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
active_connections = {}
request_history = []
max_history_entries = 100

class ClientManager:
    """Manages Redfish client connections and operations"""
    
    def __init__(self):
        self.connections = {}
        self.history = []
        
    def create_connection(self, name: str, config: Dict) -> Dict:
        """Create a new Redfish connection"""
        try:
            if not RedfishClient:
                return {'success': False, 'message': 'RedfishClient not available'}
            
            client = RedfishClient(
                base_url=config['url'],
                username=config.get('username'),
                password=config.get('password'),
                verify_ssl=config.get('verify_ssl', False)
            )
            
            # Test connection
            root = client.get_root()
            
            self.connections[name] = {
                'client': client,
                'config': config,
                'created_at': datetime.now(),
                'connected': True,
                'root': root
            }
            
            self.add_history('info', f'Connected to {config["url"]}', {'connection': name})
            
            return {
                'success': True,
                'message': 'Connection established',
                'name': name,
                'root': root
            }
            
        except Exception as e:
            logger.error(f"Failed to create connection: {e}")
            return {'success': False, 'message': str(e)}
    
    def get_connection(self, name: str):
        """Get a connection by name"""
        conn = self.connections.get(name)
        return conn['client'] if conn else None
    
    def list_connections(self) -> List[Dict]:
        """List all connections"""
        result = []
        for name, conn in self.connections.items():
            result.append({
                'name': name,
                'url': conn['config']['url'],
                'created_at': conn['created_at'].isoformat(),
                'connected': conn['connected']
            })
        return result
    
    def close_connection(self, name: str) -> Dict:
        """Close a connection"""
        if name in self.connections:
            del self.connections[name]
            self.add_history('info', f'Connection {name} closed', {})
            return {'success': True, 'message': 'Connection closed'}
        return {'success': False, 'message': 'Connection not found'}
    
    def add_history(self, level: str, message: str, data: Dict):
        """Add entry to request history"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
            'data': data
        }
        self.history.append(entry)
        
        if len(self.history) > max_history_entries:
            self.history = self.history[-max_history_entries:]

# Initialize client manager
client_manager = ClientManager()

# Routes
@app.route('/')
def index():
    """Main dashboard"""
    return render_template('client_index.html')

@app.route('/api/connections', methods=['GET', 'POST', 'DELETE'])
def handle_connections():
    """Manage connections"""
    if request.method == 'GET':
        return jsonify(client_manager.list_connections())
    
    elif request.method == 'POST':
        data = request.json
        result = client_manager.create_connection(data['name'], data['config'])
        return jsonify(result)
    
    elif request.method == 'DELETE':
        name = request.args.get('name')
        result = client_manager.close_connection(name)
        return jsonify(result)

@app.route('/api/get', methods=['POST'])
def redfish_get():
    """Perform GET operation"""
    try:
        data = request.json
        conn_name = data['connection']
        path = data['path']
        
        client = client_manager.get_connection(conn_name)
        if not client:
            return jsonify({'success': False, 'message': 'Connection not found'})
        
        start_time = time.time()
        response = client.get(path)
        elapsed = time.time() - start_time
        
        client_manager.add_history('success', f'GET {path}', {
            'connection': conn_name,
            'path': path,
            'elapsed': elapsed
        })
        
        return jsonify({
            'success': True,
            'data': response,
            'elapsed': elapsed
        })
        
    except Exception as e:
        client_manager.add_history('error', f'GET failed: {str(e)}', {'error': str(e)})
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/post', methods=['POST'])
def redfish_post():
    """Perform POST operation"""
    try:
        data = request.json
        conn_name = data['connection']
        path = data['path']
        payload = data.get('payload', {})
        
        client = client_manager.get_connection(conn_name)
        if not client:
            return jsonify({'success': False, 'message': 'Connection not found'})
        
        start_time = time.time()
        response = client.post(path, payload)
        elapsed = time.time() - start_time
        
        client_manager.add_history('success', f'POST {path}', {
            'connection': conn_name,
            'path': path,
            'elapsed': elapsed
        })
        
        return jsonify({
            'success': True,
            'data': response,
            'elapsed': elapsed
        })
        
    except Exception as e:
        client_manager.add_history('error', f'POST failed: {str(e)}', {'error': str(e)})
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/patch', methods=['POST'])
def redfish_patch():
    """Perform PATCH operation"""
    try:
        data = request.json
        conn_name = data['connection']
        path = data['path']
        payload = data.get('payload', {})
        
        client = client_manager.get_connection(conn_name)
        if not client:
            return jsonify({'success': False, 'message': 'Connection not found'})
        
        start_time = time.time()
        response = client.patch(path, payload)
        elapsed = time.time() - start_time
        
        client_manager.add_history('success', f'PATCH {path}', {
            'connection': conn_name,
            'path': path,
            'elapsed': elapsed
        })
        
        return jsonify({
            'success': True,
            'data': response,
            'elapsed': elapsed
        })
        
    except Exception as e:
        client_manager.add_history('error', f'PATCH failed: {str(e)}', {'error': str(e)})
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/delete', methods=['POST'])
def redfish_delete():
    """Perform DELETE operation"""
    try:
        data = request.json
        conn_name = data['connection']
        path = data['path']
        
        client = client_manager.get_connection(conn_name)
        if not client:
            return jsonify({'success': False, 'message': 'Connection not found'})
        
        start_time = time.time()
        response = client.delete(path)
        elapsed = time.time() - start_time
        
        client_manager.add_history('success', f'DELETE {path}', {
            'connection': conn_name,
            'path': path,
            'elapsed': elapsed
        })
        
        return jsonify({
            'success': True,
            'data': response,
            'elapsed': elapsed
        })
        
    except Exception as e:
        client_manager.add_history('error', f'DELETE failed: {str(e)}', {'error': str(e)})
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/discover', methods=['POST'])
def discover_resources():
    """Discover all resources on a Redfish server"""
    try:
        data = request.json
        conn_name = data['connection']
        
        client = client_manager.get_connection(conn_name)
        if not client:
            return jsonify({'success': False, 'message': 'Connection not found'})
        
        # Get service root
        root = client.get_root()
        
        # Discover common resources
        resources = {
            'ServiceRoot': root,
            'Systems': [],
            'Chassis': [],
            'Managers': [],
            'SessionService': None,
            'AccountService': None,
            'EventService': None,
            'UpdateService': None,
            'TaskService': None
        }
        
        # Get Systems
        if 'Systems' in root:
            systems_collection = client.get(root['Systems']['@odata.id'])
            if 'Members' in systems_collection:
                for member in systems_collection['Members']:
                    system = client.get(member['@odata.id'])
                    resources['Systems'].append(system)
        
        # Get Chassis
        if 'Chassis' in root:
            chassis_collection = client.get(root['Chassis']['@odata.id'])
            if 'Members' in chassis_collection:
                for member in chassis_collection['Members']:
                    chassis = client.get(member['@odata.id'])
                    resources['Chassis'].append(chassis)
        
        # Get Managers
        if 'Managers' in root:
            managers_collection = client.get(root['Managers']['@odata.id'])
            if 'Members' in managers_collection:
                for member in managers_collection['Members']:
                    manager = client.get(member['@odata.id'])
                    resources['Managers'].append(manager)
        
        # Get other services
        for service in ['SessionService', 'AccountService', 'EventService', 'UpdateService', 'TaskService']:
            if service in root:
                try:
                    resources[service] = client.get(root[service]['@odata.id'])
                except:
                    pass
        
        client_manager.add_history('success', 'Resource discovery completed', {
            'connection': conn_name,
            'systems': len(resources['Systems']),
            'chassis': len(resources['Chassis']),
            'managers': len(resources['Managers'])
        })
        
        return jsonify({
            'success': True,
            'resources': resources
        })
        
    except Exception as e:
        client_manager.add_history('error', f'Discovery failed: {str(e)}', {'error': str(e)})
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/analyze', methods=['POST'])
def analyze_server():
    """Analyze server capabilities and features"""
    try:
        data = request.json
        conn_name = data['connection']
        
        client = client_manager.get_connection(conn_name)
        if not client:
            return jsonify({'success': False, 'message': 'Connection not found'})
        
        root = client.get_root()
        
        analysis = {
            'redfish_version': root.get('RedfishVersion', 'Unknown'),
            'uuid': root.get('UUID', 'Unknown'),
            'product': root.get('Product', 'Unknown'),
            'protocol_features': root.get('ProtocolFeaturesSupported', {}),
            'available_services': [],
            'oem_extensions': 'Oem' in root,
            'links': {}
        }
        
        # Check available services
        services = ['Systems', 'Chassis', 'Managers', 'SessionService', 'AccountService',
                   'EventService', 'UpdateService', 'TaskService', 'CertificateService',
                   'TelemetryService', 'CompositionService']
        
        for service in services:
            if service in root:
                analysis['available_services'].append(service)
                analysis['links'][service] = root[service].get('@odata.id', '')
        
        # Count resources
        resource_counts = {}
        for service in ['Systems', 'Chassis', 'Managers']:
            if service in root:
                try:
                    collection = client.get(root[service]['@odata.id'])
                    resource_counts[service] = collection.get('Members@odata.count', len(collection.get('Members', [])))
                except:
                    resource_counts[service] = 0
        
        analysis['resource_counts'] = resource_counts
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/history')
def get_history():
    """Get request history"""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(client_manager.history[-limit:])

@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """Clear request history"""
    client_manager.history = []
    return jsonify({'success': True, 'message': 'History cleared'})

def main():
    """Run the web UI"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BMC Redfish Simulator - Client Web UI')
    parser.add_argument('-H', '--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('-p', '--port', type=int, default=5001, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║   BMC Redfish Simulator - Client Web UI                     ║
╠══════════════════════════════════════════════════════════════╣
║   Access the web interface at:                              ║
║   http://{args.host}:{args.port}/                                      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()
