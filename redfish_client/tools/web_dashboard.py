#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Web Dashboard
====================

Simple web dashboard for monitoring BMC systems using the Redfish client library.
Provides real-time system status, metrics, and alert management.
"""

import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from monitoring import RedfishMonitoringClient

app = Flask(__name__)

# Global monitoring client
monitor_client = None
dashboard_data = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BMC Dashboard - Redfish Monitor</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .card h3 {
            margin: 0 0 15px 0;
            color: #333;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }
        .metric-row {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .status-ok { color: #28a745; font-weight: bold; }
        .status-warning { color: #ffc107; font-weight: bold; }
        .status-critical { color: #dc3545; font-weight: bold; }
        .status-unknown { color: #6c757d; font-weight: bold; }
        .system-card {
            border-left: 4px solid #667eea;
        }
        .alert-card {
            border-left: 4px solid #dc3545;
        }
        .metrics-card {
            border-left: 4px solid #28a745;
        }
        .alert-item {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
            padding: 10px;
            margin: 5px 0;
        }
        .alert-critical {
            background: #f8d7da;
            border-color: #f5c6cb;
        }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
        .btn:hover {
            background: #5a67d8;
        }
        .timestamp {
            font-size: 0.9em;
            color: #666;
            text-align: right;
        }
        #status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .connected { background-color: #28a745; }
        .disconnected { background-color: #dc3545; }
        .chart-container {
            height: 200px;
            margin: 15px 0;
            background: #f8f9fa;
            border-radius: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🖥️ BMC System Dashboard</h1>
        <p>
            <span id="status-indicator" class="disconnected"></span>
            <span id="connection-status">Connecting...</span>
            <span class="timestamp" id="last-update">Last Update: Never</span>
        </p>
    </div>

    <div class="dashboard-grid">
        <div class="card system-card">
            <h3>🏗️ System Overview</h3>
            <div id="system-overview">
                <div class="metric-row">
                    <span>Loading system data...</span>
                </div>
            </div>
        </div>

        <div class="card alert-card">
            <h3>🚨 Active Alerts</h3>
            <div id="alerts-container">
                <div class="metric-row">
                    <span>Loading alerts...</span>
                </div>
            </div>
        </div>

        <div class="card metrics-card">
            <h3>📊 System Metrics</h3>
            <div id="metrics-container">
                <div class="chart-container">
                    Metrics Chart Placeholder
                </div>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>🖥️ Systems Detail</h3>
        <div id="systems-detail">
            Loading system details...
        </div>
    </div>

    <div class="card">
        <h3>📈 Recent Activity</h3>
        <div id="recent-activity">
            Loading activity...
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    updateConnectionStatus(data);
                    updateSystemOverview(data.system_summary);
                    updateAlerts(data.active_alerts, data.alert_summary);
                    updateSystemsDetail(data.current_metrics);
                    updateRecentActivity(data.recent_metrics);
                    
                    document.getElementById('last-update').textContent = 
                        'Last Update: ' + new Date().toLocaleTimeString();
                })
                .catch(error => {
                    console.error('Dashboard update failed:', error);
                    document.getElementById('connection-status').textContent = 'Connection Error';
                    document.getElementById('status-indicator').className = 'disconnected';
                });
        }

        function updateConnectionStatus(data) {
            const indicator = document.getElementById('status-indicator');
            const status = document.getElementById('connection-status');
            
            if (data.monitoring_active) {
                indicator.className = 'connected';
                status.textContent = 'Connected & Monitoring';
            } else {
                indicator.className = 'disconnected';
                status.textContent = 'Disconnected';
            }
        }

        function updateSystemOverview(summary) {
            const container = document.getElementById('system-overview');
            container.innerHTML = `
                <div class="metric-row">
                    <span>Total Systems:</span>
                    <span class="status-ok">${summary.total_systems}</span>
                </div>
                <div class="metric-row">
                    <span>Healthy Systems:</span>
                    <span class="status-ok">${summary.healthy_systems}</span>
                </div>
                <div class="metric-row">
                    <span>Powered On:</span>
                    <span class="status-ok">${summary.powered_on_systems}</span>
                </div>
                <div class="metric-row">
                    <span>Total Memory:</span>
                    <span>${summary.total_memory_gb} GB</span>
                </div>
                <div class="metric-row">
                    <span>Total CPUs:</span>
                    <span>${summary.total_cpus}</span>
                </div>
            `;
        }

        function updateAlerts(alerts, summary) {
            const container = document.getElementById('alerts-container');
            
            if (alerts.length === 0) {
                container.innerHTML = '<div class="metric-row"><span class="status-ok">No active alerts</span></div>';
                return;
            }

            let html = `
                <div class="metric-row">
                    <span>Critical:</span>
                    <span class="status-critical">${summary.critical_alerts}</span>
                </div>
                <div class="metric-row">
                    <span>Warning:</span>
                    <span class="status-warning">${summary.warning_alerts}</span>
                </div>
            `;

            alerts.forEach((alert, index) => {
                const alertClass = alert.severity === 'Critical' ? 'alert-critical' : '';
                html += `
                    <div class="alert-item ${alertClass}">
                        <strong>${alert.severity}</strong> - ${alert.system_id}<br>
                        ${alert.message}<br>
                        <small>${new Date(alert.timestamp).toLocaleString()}</small>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function updateSystemsDetail(metrics) {
            const container = document.getElementById('systems-detail');
            
            if (metrics.length === 0) {
                container.innerHTML = '<div class="metric-row"><span>No system metrics available</span></div>';
                return;
            }

            let html = '';
            metrics.forEach(metric => {
                const healthClass = getStatusClass(metric.health_status);
                const powerIcon = metric.power_state === 'On' ? '🟢' : '🔴';
                
                html += `
                    <div class="metric-row">
                        <div>
                            <strong>${metric.system_id}</strong> ${powerIcon}<br>
                            <small>Power: ${metric.power_state} | Health: <span class="${healthClass}">${metric.health_status}</span></small>
                        </div>
                        <div>
                            CPU: ${metric.cpu_count} | RAM: ${metric.memory_gb}GB<br>
                            <small>${new Date(metric.timestamp).toLocaleTimeString()}</small>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function updateRecentActivity(recentMetrics) {
            const container = document.getElementById('recent-activity');
            
            if (recentMetrics.length === 0) {
                container.innerHTML = '<div class="metric-row"><span>No recent activity</span></div>';
                return;
            }

            let html = '';
            recentMetrics.slice(-10).reverse().forEach(metric => {
                html += `
                    <div class="metric-row">
                        <span>${new Date(metric.timestamp).toLocaleTimeString()}</span>
                        <span>${metric.system_id}: ${metric.power_state}, ${metric.health_status}</span>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function getStatusClass(status) {
            switch(status.toLowerCase()) {
                case 'ok': return 'status-ok';
                case 'warning': return 'status-warning';
                case 'critical': return 'status-critical';
                default: return 'status-unknown';
            }
        }

        // Auto-refresh dashboard
        setInterval(updateDashboard, 5000);  // Update every 5 seconds
        updateDashboard();  // Initial load
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Serve the main dashboard page"""
    return HTML_TEMPLATE

@app.route('/api/dashboard')
def api_dashboard():
    """API endpoint for dashboard data"""
    global monitor_client, dashboard_data
    
    if monitor_client and monitor_client.connected:
        try:
            dashboard_data = monitor_client.get_dashboard_data()
        except Exception as e:
            print(f"Error getting dashboard data: {e}")
    
    return jsonify(dashboard_data)

@app.route('/api/start_monitoring', methods=['POST'])
def api_start_monitoring():
    """Start monitoring"""
    global monitor_client
    
    try:
        if monitor_client and not monitor_client.monitoring_active:
            monitor_client.start_monitoring()
            return jsonify({"status": "success", "message": "Monitoring started"})
        else:
            return jsonify({"status": "error", "message": "Already monitoring or no client"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/stop_monitoring', methods=['POST'])
def api_stop_monitoring():
    """Stop monitoring"""
    global monitor_client
    
    try:
        if monitor_client and monitor_client.monitoring_active:
            monitor_client.stop_monitoring()
            return jsonify({"status": "success", "message": "Monitoring stopped"})
        else:
            return jsonify({"status": "error", "message": "Not monitoring"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/export_metrics', methods=['POST'])
def api_export_metrics():
    """Export metrics"""
    global monitor_client
    
    try:
        if monitor_client:
            filename = f"dashboard_metrics_{int(time.time())}.json"
            monitor_client.export_metrics(filename)
            return jsonify({"status": "success", "filename": filename})
        else:
            return jsonify({"status": "error", "message": "No monitoring client"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def initialize_monitor(bmc_url="http://localhost:8000", username="admin", password="admin"):
    """Initialize the monitoring client"""
    global monitor_client, dashboard_data
    
    monitor_client = RedfishMonitoringClient(
        bmc_url=bmc_url,
        username=username,
        password=password,
        poll_interval=10,
        alert_callback=lambda alert: print(f"🚨 Dashboard Alert: {alert.message}")
    )
    
    # Initialize with empty data
    dashboard_data = {
        'timestamp': datetime.now().isoformat(),
        'system_summary': {
            'total_systems': 0,
            'healthy_systems': 0,
            'powered_on_systems': 0,
            'total_memory_gb': 0,
            'total_cpus': 0
        },
        'alert_summary': {
            'total_active': 0,
            'critical_alerts': 0,
            'warning_alerts': 0,
            'resolved_today': 0
        },
        'current_metrics': [],
        'recent_metrics': [],
        'active_alerts': [],
        'monitoring_active': False
    }
    
    # Try to connect
    def connect_background():
        try:
            if monitor_client.connect():
                print("✅ Connected to BMC for dashboard")
                monitor_client.start_monitoring()
                print("🎯 Started monitoring for dashboard")
            else:
                print("❌ Failed to connect to BMC")
        except Exception as e:
            print(f"❌ Dashboard connection error: {e}")
    
    # Start connection in background
    connection_thread = threading.Thread(target=connect_background, daemon=True)
    connection_thread.start()

def main():
    """Run the web dashboard"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Redfish Web Dashboard')
    parser.add_argument('--bmc-url', default='http://localhost:8000',
                       help='BMC URL to monitor')
    parser.add_argument('--username', default='admin',
                       help='BMC username')
    parser.add_argument('--password', default='admin',
                       help='BMC password')
    parser.add_argument('--host', default='127.0.0.1',
                       help='Dashboard host address')
    parser.add_argument('--port', default=5000, type=int,
                       help='Dashboard port')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    
    args = parser.parse_args()
    
    print("🌐 Starting Redfish Web Dashboard")
    print(f"   BMC URL: {args.bmc_url}")
    print(f"   Dashboard: http://{args.host}:{args.port}")
    print()
    
    # Initialize monitoring
    initialize_monitor(args.bmc_url, args.username, args.password)
    
    try:
        # Start Flask app
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=False  # Disable reloader to avoid threading issues
        )
    
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped by user")
    
    finally:
        # Cleanup
        global monitor_client
        if monitor_client:
            monitor_client.disconnect()

if __name__ == "__main__":
    main()