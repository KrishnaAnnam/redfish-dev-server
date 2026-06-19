#!/usr/bin/env python3
"""
RAS Health Monitoring Service

Provides real-time health monitoring and alerting for RAS system.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Overall health status levels"""
    HEALTHY = "Healthy"
    DEGRADED = "Degraded"
    CRITICAL = "Critical"
    UNKNOWN = "Unknown"


class RASHealthMonitor:
    """
    Health monitoring service for RAS system.
    
    Monitors:
    - Component health scores
    - Error rates and trends
    - Queue health
    - Remediation effectiveness
    """
    
    def __init__(
        self,
        analytics_engine=None,
        queue_manager=None,
        remediation_engine=None
    ):
        """
        Initialize health monitor.
        
        Args:
            analytics_engine: RAS analytics engine
            queue_manager: CPER queue manager
            remediation_engine: Remediation engine
        """
        self.analytics = analytics_engine
        self.queue_manager = queue_manager
        self.remediation = remediation_engine
        
        # Health thresholds
        self.thresholds = {
            "component_health_min": 70.0,
            "error_rate_max_per_hour": 50,
            "queue_utilization_max": 0.8,
            "failed_remediation_rate_max": 0.3
        }
        
        # Alert history
        self.alerts: List[Dict[str, Any]] = []
        self.max_alerts = 100
        
        logger.info("RAS Health Monitor initialized")
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        health_checks = []
        
        # Check component health
        if self.analytics:
            component_health = self._check_component_health()
            health_checks.append(component_health)
        
        # Check error rates
        if self.analytics:
            error_rate_health = self._check_error_rates()
            health_checks.append(error_rate_health)
        
        # Check queue health
        if self.queue_manager:
            queue_health = self._check_queue_health()
            health_checks.append(queue_health)
        
        # Check remediation effectiveness
        if self.remediation:
            remediation_health = self._check_remediation_health()
            health_checks.append(remediation_health)
        
        # Determine overall status
        if not health_checks:
            overall_status = HealthStatus.UNKNOWN
        elif any(check["status"] == HealthStatus.CRITICAL.value for check in health_checks):
            overall_status = HealthStatus.CRITICAL
        elif any(check["status"] == HealthStatus.DEGRADED.value for check in health_checks):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        return {
            "overall_status": overall_status.value,
            "health_checks": health_checks,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "active_alerts": len([a for a in self.alerts if not a.get("resolved", False)])
        }
    
    def _check_component_health(self) -> Dict[str, Any]:
        """Check component health scores"""
        try:
            health_data = self.analytics.get_component_health_scores()
            
            if "error" in health_data:
                return {
                    "check": "component_health",
                    "status": HealthStatus.UNKNOWN.value,
                    "message": health_data["error"]
                }
            
            overall_health = health_data.get("overall_health", 100.0)
            components = health_data.get("components", {})
            
            # Find unhealthy components
            unhealthy = [
                comp for comp, data in components.items()
                if data["health_score"] < self.thresholds["component_health_min"]
            ]
            
            if unhealthy:
                if any(components[c]["health_score"] < 50 for c in unhealthy):
                    status = HealthStatus.CRITICAL
                else:
                    status = HealthStatus.DEGRADED
                
                message = f"Unhealthy components: {', '.join(unhealthy[:3])}"
                if len(unhealthy) > 3:
                    message += f" (+{len(unhealthy)-3} more)"
            else:
                status = HealthStatus.HEALTHY
                message = f"All components healthy (avg score: {overall_health:.1f})"
            
            return {
                "check": "component_health",
                "status": status.value,
                "message": message,
                "overall_health": overall_health,
                "unhealthy_count": len(unhealthy)
            }
        
        except Exception as e:
            logger.error(f"Component health check failed: {e}")
            return {
                "check": "component_health",
                "status": HealthStatus.UNKNOWN.value,
                "message": f"Check failed: {e}"
            }
    
    def _check_error_rates(self) -> Dict[str, Any]:
        """Check error rates and trends"""
        try:
            trends = self.analytics.analyze_error_trends(time_window_hours=1)
            
            if "error" in trends:
                return {
                    "check": "error_rates",
                    "status": HealthStatus.UNKNOWN.value,
                    "message": trends["error"]
                }
            
            total_errors = trends.get("total_errors", 0)
            trend = trends.get("trend", "stable")
            
            # Check against threshold
            threshold = self.thresholds["error_rate_max_per_hour"]
            
            if total_errors > threshold * 2:
                status = HealthStatus.CRITICAL
                message = f"Critical error rate: {total_errors}/hour (threshold: {threshold})"
            elif total_errors > threshold:
                status = HealthStatus.DEGRADED
                message = f"Elevated error rate: {total_errors}/hour (threshold: {threshold})"
            else:
                status = HealthStatus.HEALTHY
                message = f"Error rate normal: {total_errors}/hour, trend: {trend}"
            
            return {
                "check": "error_rates",
                "status": status.value,
                "message": message,
                "errors_per_hour": total_errors,
                "trend": trend
            }
        
        except Exception as e:
            logger.error(f"Error rate check failed: {e}")
            return {
                "check": "error_rates",
                "status": HealthStatus.UNKNOWN.value,
                "message": f"Check failed: {e}"
            }
    
    def _check_queue_health(self) -> Dict[str, Any]:
        """Check CPER queue health"""
        try:
            queue_status = self.queue_manager.get_queue_status()
            
            main_queue = queue_status["main_queue"]
            utilization = main_queue["size"] / main_queue["max_size"]
            
            threshold = self.thresholds["queue_utilization_max"]
            
            if utilization > 0.95:
                status = HealthStatus.CRITICAL
                message = f"Queue nearly full: {utilization*100:.0f}% utilization"
            elif utilization > threshold:
                status = HealthStatus.DEGRADED
                message = f"Queue filling up: {utilization*100:.0f}% utilization"
            else:
                status = HealthStatus.HEALTHY
                message = f"Queue healthy: {utilization*100:.0f}% utilization"
            
            return {
                "check": "queue_health",
                "status": status.value,
                "message": message,
                "utilization": f"{utilization*100:.1f}%",
                "queue_size": main_queue["size"]
            }
        
        except Exception as e:
            logger.error(f"Queue health check failed: {e}")
            return {
                "check": "queue_health",
                "status": HealthStatus.UNKNOWN.value,
                "message": f"Check failed: {e}"
            }
    
    def _check_remediation_health(self) -> Dict[str, Any]:
        """Check remediation effectiveness"""
        try:
            stats = self.remediation.get_stats()
            
            total_executed = stats.get("total_executed", 0)
            total_failed = stats.get("total_failed", 0)
            
            if total_executed == 0:
                status = HealthStatus.HEALTHY
                message = "No remediation actions executed"
                failure_rate = 0.0
            else:
                failure_rate = total_failed / total_executed
                threshold = self.thresholds["failed_remediation_rate_max"]
                
                if failure_rate > threshold * 2:
                    status = HealthStatus.CRITICAL
                    message = f"High remediation failure rate: {failure_rate*100:.0f}%"
                elif failure_rate > threshold:
                    status = HealthStatus.DEGRADED
                    message = f"Elevated remediation failures: {failure_rate*100:.0f}%"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"Remediation effective: {(1-failure_rate)*100:.0f}% success rate"
            
            return {
                "check": "remediation_health",
                "status": status.value,
                "message": message,
                "success_rate": f"{(1-failure_rate)*100:.1f}%",
                "total_executed": total_executed
            }
        
        except Exception as e:
            logger.error(f"Remediation health check failed: {e}")
            return {
                "check": "remediation_health",
                "status": HealthStatus.UNKNOWN.value,
                "message": f"Check failed: {e}"
            }
    
    def create_alert(
        self,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a health alert"""
        import uuid
        
        alert = {
            "alert_id": str(uuid.uuid4()),
            "severity": severity,
            "message": message,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
            "resolved_at": None
        }
        
        self.alerts.append(alert)
        
        # Trim alerts if needed
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        logger.warning(f"Health alert created: {message}")
        return alert["alert_id"]
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve a health alert"""
        for alert in self.alerts:
            if alert["alert_id"] == alert_id and not alert["resolved"]:
                alert["resolved"] = True
                alert["resolved_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(f"Alert resolved: {alert_id}")
                return True
        return False
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active (unresolved) alerts"""
        return [a for a in self.alerts if not a.get("resolved", False)]
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary"""
        overall = self.get_overall_health()
        
        return {
            "summary": {
                "status": overall["overall_status"],
                "active_alerts": len(self.get_active_alerts()),
                "checked_at": overall["checked_at"]
            },
            "details": overall,
            "recent_alerts": self.alerts[-10:] if self.alerts else []
        }
