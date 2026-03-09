#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
BMC Redfish Simulator - Server Web UI
Provides a comprehensive web interface for configuring, monitoring, and controlling the Redfish simulator server.
"""

import os
import sys
import json
import logging
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

# Add parent directory to path to import server modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
server_process = None
server_config = {}
server_logs = []
max_log_entries = 1000

class ServerManager:
    """Manages the Redfish simulator server process"""
    
    def __init__(self):
        self.process = None
        self.config = {}
        self.base_path = Path(__file__).parent.parent.parent
        self.is_running = False
        self.start_time = None
        self.stats = {
            'requests_total': 0,
            'requests_success': 0,
            'requests_error': 0,
            'uptime': 0
        }
    
    def start_server(self, config: Dict) -> Dict:
        """Start the Redfish simulator server"""
        if self.is_running:
            return {'success': False, 'message': 'Server is already running'}
        
        try:
            # Build command
            cmd = [
                sys.executable,
                str(self.base_path / 'redfishMockupServer_enhanced.py')
            ]
            
            # Add configuration parameters
            if config.get('host'):
                cmd.extend(['-H', config['host']])
            if config.get('port'):
                cmd.extend(['-p', str(config['port'])])
            if config.get('mockup_dir'):
                cmd.extend(['-D', config['mockup_dir']])
            if config.get('ssl'):
                cmd.append('--ssl')
            if config.get('platform_type'):
                cmd.extend(['--platform', config['platform_type']])
            
            # Start process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.is_running = True
            self.config = config
            self.start_time = datetime.now()
            
            # Start log capture thread
            log_thread = threading.Thread(target=self._capture_logs, daemon=True)
            log_thread.start()
            
            logger.info(f"Server started with PID {self.process.pid}")
            add_log('info', f'Server started on {config.get("host", "0.0.0.0")}:{config.get("port", 8000)}')
            
            return {
                'success': True,
                'message': 'Server started successfully',
                'pid': self.process.pid,
                'config': self.config
            }
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return {'success': False, 'message': str(e)}
    
    def stop_server(self) -> Dict:
        """Stop the Redfish simulator server"""
        if not self.is_running or not self.process:
            return {'success': False, 'message': 'Server is not running'}
        
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.is_running = False
            self.process = None
            
            add_log('info', 'Server stopped')
            logger.info("Server stopped")
            
            return {'success': True, 'message': 'Server stopped successfully'}
            
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.is_running = False
            self.process = None
            return {'success': True, 'message': 'Server forcefully killed'}
        except Exception as e:
            logger.error(f"Failed to stop server: {e}")
            return {'success': False, 'message': str(e)}
    
    def restart_server(self) -> Dict:
        """Restart the server"""
        stop_result = self.stop_server()
        if not stop_result['success']:
            return stop_result
        
        import time
        time.sleep(2)
        
        return self.start_server(self.config)
    
    def get_status(self) -> Dict:
        """Get server status"""
        uptime = None
        if self.start_time and self.is_running:
            uptime = (datetime.now() - self.start_time).total_seconds()
            self.stats['uptime'] = uptime
        
        return {
            'running': self.is_running,
            'pid': self.process.pid if self.process else None,
            'config': self.config,
            'uptime': uptime,
            'stats': self.stats,
            'start_time': self.start_time.isoformat() if self.start_time else None
        }
    
    def _capture_logs(self):
        """Capture server logs in background thread"""
        if not self.process:
            return
        
        for line in self.process.stdout:
            line = line.strip()
            if line:
                # Parse log level from line
                level = 'info'
                if 'ERROR' in line or 'Error' in line:
                    level = 'error'
                    self.stats['requests_error'] += 1
                elif 'WARNING' in line or 'Warning' in line:
                    level = 'warning'
                elif 'GET' in line or 'POST' in line or 'PATCH' in line or 'DELETE' in line:
                    level = 'success'
                    self.stats['requests_total'] += 1
                    self.stats['requests_success'] += 1
                
                add_log(level, line)

# Initialize server manager
server_manager = ServerManager()

def add_log(level: str, message: str):
    """Add log entry"""
    global server_logs
    entry = {
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message
    }
    server_logs.append(entry)
    
    # Keep only last N entries
    if len(server_logs) > max_log_entries:
        server_logs = server_logs[-max_log_entries:]

# Routes
@app.route('/')
def index():
    """Main dashboard"""
    return render_template('server_index.html')

@app.route('/api/status')
def get_status():
    """Get server status"""
    return jsonify(server_manager.get_status())

@app.route('/api/start', methods=['POST'])
def start_server():
    """Start the server"""
    config = request.json or {}
    result = server_manager.start_server(config)
    return jsonify(result)

@app.route('/api/stop', methods=['POST'])
def stop_server():
    """Stop the server"""
    result = server_manager.stop_server()
    return jsonify(result)

@app.route('/api/restart', methods=['POST'])
def restart_server():
    """Restart the server"""
    result = server_manager.restart_server()
    return jsonify(result)

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Get or update server configuration"""
    if request.method == 'GET':
        return jsonify(server_manager.config)
    else:
        config = request.json
        server_manager.config = config
        return jsonify({'success': True, 'config': config})

@app.route('/api/logs')
def get_logs():
    """Get server logs"""
    limit = request.args.get('limit', 100, type=int)
    level = request.args.get('level', None)
    
    logs = server_logs[-limit:]
    
    if level:
        logs = [log for log in logs if log['level'] == level]
    
    return jsonify(logs)

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Clear server logs"""
    global server_logs
    server_logs = []
    return jsonify({'success': True, 'message': 'Logs cleared'})

@app.route('/api/mockups')
def list_mockups():
    """List available mockup directories"""
    base_path = Path(__file__).parent.parent.parent
    mockup_dirs = []
    
    # Look for directories with index.json
    for item in base_path.iterdir():
        if item.is_dir() and (item / 'index.json').exists():
            mockup_dirs.append({
                'name': item.name,
                'path': str(item),
                'size': sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
            })
    
    return jsonify(mockup_dirs)

@app.route('/api/platforms')
def list_platforms():
    """List available platform types"""
    platforms = [
        {'id': 'generic', 'name': 'Generic Redfish Server'},
        {'id': 'vendor1', 'name': 'Vendor1 Platform'},
        {'id': 'vendor2', 'name': 'Vendor2 Platform'}
    ]
    return jsonify(platforms)

@app.route('/api/stats')
def get_stats():
    """Get server statistics"""
    return jsonify(server_manager.stats)

@app.route('/api/system')
def get_system_info():
    """Get system information"""
    import platform
    import psutil
    
    info = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'cpu_count': psutil.cpu_count(),
        'memory': {
            'total': psutil.virtual_memory().total,
            'available': psutil.virtual_memory().available,
            'percent': psutil.virtual_memory().percent
        }
    }
    
    if server_manager.process:
        try:
            proc = psutil.Process(server_manager.process.pid)
            info['server_process'] = {
                'memory_info': proc.memory_info().rss,
                'cpu_percent': proc.cpu_percent(interval=0.1),
                'num_threads': proc.num_threads()
            }
        except:
            pass
    
    return jsonify(info)

def main():
    """Run the web UI"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BMC Redfish Simulator - Server Web UI')
    parser.add_argument('-H', '--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('-p', '--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║   BMC Redfish Simulator - Server Web UI                     ║
╠══════════════════════════════════════════════════════════════╣
║   Access the web interface at:                              ║
║   http://{args.host}:{args.port}/                                      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()
