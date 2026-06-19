"""
RAS Services Package

Advanced services for RAS plugin:
- Queue Manager: Priority-based CPER processing
- Analytics: Error trends and health monitoring
- Remediation: Automated error remediation
- Health Monitor: System health monitoring
"""

from .queue_manager import CPERQueueManager, CPERQueueItem, CPERPriority
from .analytics import RASAnalyticsEngine
from .remediation import (
    AutomatedRemediationEngine,
    RemediationAction,
    RemediationStatus,
    RemediationRule,
    RemediationRecord
)
from .health_monitor import RASHealthMonitor, HealthStatus

__all__ = [
    'CPERQueueManager',
    'CPERQueueItem',
    'CPERPriority',
    'RASAnalyticsEngine',
    'AutomatedRemediationEngine',
    'RemediationAction',
    'RemediationStatus',
    'RemediationRule',
    'RemediationRecord',
    'RASHealthMonitor',
    'HealthStatus'
]
