#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Monitoring Client
========================

A specialized client for monitoring BMC systems with real-time capabilities,
health checking, alerting, and dashboard functionality.
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from .client import RedfishClient, RedfishClientError

@dataclass
class SystemMetrics:
    """System metrics snapshot"""
    timestamp: datetime
    system_id: str
    power_state: str
    health_status: str
    cpu_count: int
    memory_gb: int
    temperature_celsius: Optional[float] = None
    power_watts: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

@dataclass
class HealthAlert:
    """Health alert information"""
    timestamp: datetime
    system_id: str
    component: str
    severity: str
    message: str
    resolved: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

class RedfishMonitoringClient:
    """
    Advanced Redfish monitoring client with real-time capabilities
    
    Features:
    - Continuous health monitoring
    - Real-time metrics collection
    - Alert generation and management
    - Event subscription handling
    - Dashboard data preparation
    - Historical data storage
    """
    
    def __init__(self, bmc_url: str, username: str, password: str, 
                 poll_interval: int = 30, alert_callback: Callable = None):
        """
        Initialize monitoring client
        
        Args:
            bmc_url: BMC URL to monitor
            username: Authentication username
            password: Authentication password
            poll_interval: Monitoring poll interval in seconds
            alert_callback: Callback function for alerts
        """
        self.bmc_url = bmc_url
        self.username = username
        self.password = password
        self.poll_interval = poll_interval
        self.alert_callback = alert_callback
        
        # Client and connection management
        self.client = RedfishClient(bmc_url, verify_ssl=False)
        self.connected = False
        self.monitoring_active = False
        
        # Data storage
        self.current_metrics: Dict[str, SystemMetrics] = {}
        self.historical_metrics: List[SystemMetrics] = []
        self.active_alerts: List[HealthAlert] = []
        self.resolved_alerts: List[HealthAlert] = []
        
        # Threading
        self.monitor_thread: Optional[threading.Thread] = None
        self.event_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Thresholds for alerting
        self.alert_thresholds = {
            'temperature_critical': 85.0,
            'temperature_warning': 75.0,
            'power_critical': 500.0,
            'power_warning': 400.0
        }
    
    def connect(self) -> bool:
        """Connect to BMC and authenticate"""
        try:
            if not self.client.connect():
                return False
            
            if not self.client.login(self.username, self.password):
                return False
            
            self.connected = True
            print(f"✅ Connected to {self.client.vendor} {self.client.product}")
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from BMC"""
        self.stop_monitoring()
        if self.connected:
            self.client.logout()
            self.connected = False
            print("👋 Disconnected from BMC")
    
    def collect_system_metrics(self) -> List[SystemMetrics]:
        """Collect current system metrics"""
        if not self.connected:
            return []
        
        metrics = []
        timestamp = datetime.now()
        
        try:
            systems = self.client.get_systems()
            
            for system in systems:
                data = system.data
                
                # Extract basic metrics
                power_state = data.get('PowerState', 'Unknown')
                health_status = data.get('Status', {}).get('Health', 'Unknown')
                
                # Memory info
                memory_summary = data.get('MemorySummary', {})
                memory_gb = memory_summary.get('TotalSystemMemoryGiB', 0)
                
                # CPU info
                cpu_summary = data.get('ProcessorSummary', {})
                cpu_count = cpu_summary.get('Count', 0)
                
                # Try to get thermal and power data (may not be available in simulator)
                temperature = self._get_system_temperature(system.id)
                power_consumption = self._get_power_consumption(system.id)
                
                metrics_obj = SystemMetrics(
                    timestamp=timestamp,
                    system_id=system.id,
                    power_state=power_state,
                    health_status=health_status,
                    cpu_count=cpu_count,
                    memory_gb=memory_gb,
                    temperature_celsius=temperature,
                    power_watts=power_consumption
                )
                
                metrics.append(metrics_obj)
                self.current_metrics[system.id] = metrics_obj
                
        except Exception as e:
            print(f"⚠️  Metrics collection failed: {e}")
        
        return metrics
    
    def _get_system_temperature(self, system_id: str) -> Optional[float]:
        """Get system temperature (if available)"""
        try:
            # Try to get thermal data
            thermal_url = f"/redfish/v1/Chassis/{system_id}/Thermal"
            thermal = self.client.get_resource(thermal_url)
            
            temperatures = thermal.data.get('Temperatures', [])
            if temperatures:
                # Get highest temperature
                temps = [t.get('ReadingCelsius') for t in temperatures if t.get('ReadingCelsius')]
                return max(temps) if temps else None
            
        except:
            pass  # Thermal data not available
        
        return None
    
    def _get_power_consumption(self, system_id: str) -> Optional[float]:
        """Get power consumption (if available)"""
        try:
            # Try to get power data
            power_url = f"/redfish/v1/Chassis/{system_id}/Power"
            power = self.client.get_resource(power_url)
            
            power_controls = power.data.get('PowerControl', [])
            if power_controls:
                # Get total power consumption
                consumption = power_controls[0].get('PowerConsumedWatts')
                return consumption
            
        except:
            pass  # Power data not available
        
        return None
    
    def check_health_alerts(self, metrics: List[SystemMetrics]):
        """Check for health alerts based on current metrics"""
        current_time = datetime.now()
        
        for metric in metrics:
            system_id = metric.system_id
            
            # Check health status alerts
            if metric.health_status not in ['OK', 'Warning']:
                self._create_alert(
                    system_id, 'Health', 'Critical',
                    f"System health is {metric.health_status}"
                )
            
            # Check power state alerts
            if metric.power_state == 'Off':
                self._create_alert(
                    system_id, 'Power', 'Warning',
                    "System is powered off"
                )
            
            # Check temperature alerts
            if metric.temperature_celsius:
                if metric.temperature_celsius >= self.alert_thresholds['temperature_critical']:
                    self._create_alert(
                        system_id, 'Temperature', 'Critical',
                        f"Temperature critical: {metric.temperature_celsius}°C"
                    )
                elif metric.temperature_celsius >= self.alert_thresholds['temperature_warning']:
                    self._create_alert(
                        system_id, 'Temperature', 'Warning',
                        f"Temperature high: {metric.temperature_celsius}°C"
                    )
            
            # Check power alerts
            if metric.power_watts:
                if metric.power_watts >= self.alert_thresholds['power_critical']:
                    self._create_alert(
                        system_id, 'Power', 'Critical',
                        f"Power consumption critical: {metric.power_watts}W"
                    )
                elif metric.power_watts >= self.alert_thresholds['power_warning']:
                    self._create_alert(
                        system_id, 'Power', 'Warning',
                        f"Power consumption high: {metric.power_watts}W"
                    )
    
    def _create_alert(self, system_id: str, component: str, severity: str, message: str):
        """Create a new health alert"""
        # Check if similar alert already exists
        for alert in self.active_alerts:
            if (alert.system_id == system_id and 
                alert.component == component and 
                alert.message == message and 
                not alert.resolved):
                return  # Alert already exists
        
        alert = HealthAlert(
            timestamp=datetime.now(),
            system_id=system_id,
            component=component,
            severity=severity,
            message=message
        )
        
        self.active_alerts.append(alert)
        
        print(f"🚨 ALERT [{severity}] {system_id}/{component}: {message}")
        
        # Call alert callback if provided
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                print(f"⚠️  Alert callback failed: {e}")
    
    def resolve_alert(self, alert_index: int):
        """Resolve an active alert"""
        if 0 <= alert_index < len(self.active_alerts):
            alert = self.active_alerts.pop(alert_index)
            alert.resolved = True
            self.resolved_alerts.append(alert)
            print(f"✅ Resolved alert: {alert.message}")
    
    def start_monitoring(self):
        """Start continuous monitoring"""
        if self.monitoring_active:
            return
        
        if not self.connected and not self.connect():
            print("❌ Cannot start monitoring: not connected")
            return
        
        self.monitoring_active = True
        self.stop_event.clear()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        # Start event subscription thread
        self.event_thread = threading.Thread(target=self._event_subscription_loop, daemon=True)
        self.event_thread.start()
        
        print(f"🎯 Started monitoring (interval: {self.poll_interval}s)")
    
    def stop_monitoring(self):
        """Stop continuous monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        self.stop_event.set()
        
        # Wait for threads to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        if self.event_thread and self.event_thread.is_alive():
            self.event_thread.join(timeout=5)
        
        print("⏹️  Stopped monitoring")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active and not self.stop_event.is_set():
            try:
                # Collect metrics
                metrics = self.collect_system_metrics()
                
                if metrics:
                    # Add to historical data
                    self.historical_metrics.extend(metrics)
                    
                    # Trim historical data (keep last 1000 entries)
                    if len(self.historical_metrics) > 1000:
                        self.historical_metrics = self.historical_metrics[-1000:]
                    
                    # Check for alerts
                    self.check_health_alerts(metrics)
                    
                    # Print summary
                    self._print_monitoring_summary(metrics)
                
                # Wait for next poll
                if not self.stop_event.wait(timeout=self.poll_interval):
                    continue
                else:
                    break  # Stop event was set
                    
            except Exception as e:
                print(f"⚠️  Monitoring error: {e}")
                time.sleep(5)  # Brief wait on error
    
    def _event_subscription_loop(self):
        """Handle event subscriptions"""
        try:
            # Create event subscription for real-time monitoring
            subscription = self.client.create_event_subscription(
                destination="http://localhost:9999/events",  # Placeholder
                event_types=["Alert", "ResourceUpdated"],
                context="MonitoringClient"
            )
            print(f"📡 Event subscription created: {subscription.id}")
            
            # Keep subscription alive while monitoring
            while self.monitoring_active and not self.stop_event.is_set():
                self.stop_event.wait(timeout=60)  # Check every minute
            
            # Cleanup subscription
            self.client.delete_event_subscription(subscription.id)
            print("📡 Event subscription cleaned up")
            
        except Exception as e:
            print(f"⚠️  Event subscription error: {e}")
    
    def _print_monitoring_summary(self, metrics: List[SystemMetrics]):
        """Print monitoring summary"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n⏰ [{timestamp}] Monitoring Summary:")
        for metric in metrics:
            status_icon = "🟢" if metric.health_status == "OK" else "🔴"
            power_icon = "⚡" if metric.power_state == "On" else "⚫"
            
            print(f"   {status_icon} {metric.system_id}: {power_icon} {metric.power_state}, "
                  f"Health: {metric.health_status}, CPU: {metric.cpu_count}, RAM: {metric.memory_gb}GB")
            
            if metric.temperature_celsius:
                print(f"      🌡️  Temperature: {metric.temperature_celsius}°C")
            
            if metric.power_watts:
                print(f"      ⚡ Power: {metric.power_watts}W")
        
        # Show active alerts
        if self.active_alerts:
            print(f"\n🚨 Active Alerts ({len(self.active_alerts)}):")
            for i, alert in enumerate(self.active_alerts[-5:]):  # Show last 5
                print(f"   {i}: [{alert.severity}] {alert.system_id}: {alert.message}")
    
    def get_dashboard_data(self) -> Dict:
        """Get data for dashboard display"""
        current_time = datetime.now()
        
        # System status summary
        system_summary = {
            'total_systems': len(self.current_metrics),
            'healthy_systems': len([m for m in self.current_metrics.values() if m.health_status == 'OK']),
            'powered_on_systems': len([m for m in self.current_metrics.values() if m.power_state == 'On']),
            'total_memory_gb': sum(m.memory_gb for m in self.current_metrics.values()),
            'total_cpus': sum(m.cpu_count for m in self.current_metrics.values())
        }
        
        # Alert summary
        alert_summary = {
            'total_active': len(self.active_alerts),
            'critical_alerts': len([a for a in self.active_alerts if a.severity == 'Critical']),
            'warning_alerts': len([a for a in self.active_alerts if a.severity == 'Warning']),
            'resolved_today': len([a for a in self.resolved_alerts 
                                 if a.timestamp.date() == current_time.date()])
        }
        
        # Recent metrics (last 24 hours)
        cutoff_time = current_time - timedelta(hours=24)
        recent_metrics = [m for m in self.historical_metrics if m.timestamp >= cutoff_time]
        
        return {
            'timestamp': current_time.isoformat(),
            'system_summary': system_summary,
            'alert_summary': alert_summary,
            'current_metrics': [m.to_dict() for m in self.current_metrics.values()],
            'recent_metrics': [m.to_dict() for m in recent_metrics[-100:]],  # Last 100 entries
            'active_alerts': [a.to_dict() for a in self.active_alerts],
            'monitoring_active': self.monitoring_active
        }
    
    def export_metrics(self, filename: str = None):
        """Export metrics to JSON file"""
        if not filename:
            filename = f"bmc_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'bmc_url': self.bmc_url,
            'historical_metrics': [m.to_dict() for m in self.historical_metrics],
            'resolved_alerts': [a.to_dict() for a in self.resolved_alerts],
            'alert_thresholds': self.alert_thresholds
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"📁 Metrics exported to: {filename}")

def main():
    """Example usage of monitoring client"""
    print("🎯 Redfish Monitoring Client Example")
    print("=" * 50)
    
    # Create monitoring client
    monitor = RedfishMonitoringClient(
        bmc_url="http://localhost:8000",
        username="admin", 
        password="admin",
        poll_interval=10,  # 10 second intervals for demo
        alert_callback=lambda alert: print(f"📧 Alert notification: {alert.message}")
    )
    
    try:
        # Connect to BMC
        if not monitor.connect():
            print("❌ Failed to connect to BMC")
            return
        
        # Collect initial metrics
        print("\n📊 Initial metrics collection...")
        initial_metrics = monitor.collect_system_metrics()
        
        for metric in initial_metrics:
            print(f"   System {metric.system_id}: {metric.health_status}, {metric.power_state}")
        
        # Start monitoring
        print(f"\n🎯 Starting continuous monitoring...")
        monitor.start_monitoring()
        
        # Run for demo duration
        demo_duration = 60  # 1 minute demo
        print(f"   Running monitoring for {demo_duration} seconds...")
        print("   (Press Ctrl+C to stop early)")
        
        start_time = time.time()
        try:
            while time.time() - start_time < demo_duration:
                time.sleep(5)
                
                # Print dashboard summary every 30 seconds
                if int(time.time() - start_time) % 30 == 0:
                    dashboard = monitor.get_dashboard_data()
                    print(f"\n📈 Dashboard Summary:")
                    print(f"   Systems: {dashboard['system_summary']['total_systems']} total, "
                          f"{dashboard['system_summary']['healthy_systems']} healthy")
                    print(f"   Alerts: {dashboard['alert_summary']['total_active']} active")
                
        except KeyboardInterrupt:
            print("\n⏹️  Monitoring stopped by user")
        
        # Export results
        print("\n📁 Exporting monitoring results...")
        monitor.export_metrics()
        
        # Show final dashboard
        final_dashboard = monitor.get_dashboard_data()
        print(f"\n📈 Final Dashboard Data:")
        print(f"   Total metrics collected: {len(monitor.historical_metrics)}")
        print(f"   Active alerts: {len(monitor.active_alerts)}")
        print(f"   Monitoring duration: {int(time.time() - start_time)} seconds")
        
    finally:
        monitor.disconnect()
        print("\n✅ Monitoring client demo completed")

if __name__ == "__main__":
    main()