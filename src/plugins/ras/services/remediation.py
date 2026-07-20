#!/usr/bin/env python3
"""
RAS Automated Remediation Framework

Provides policy-based automated remediation for RAS errors.
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RemediationAction(Enum):
    """Types of automated remediation actions"""
    LOG_ONLY = "LogOnly"
    NOTIFY = "Notify"
    DISABLE_COMPONENT = "DisableComponent"
    RESET_COMPONENT = "ResetComponent"
    FAILOVER = "Failover"
    RESTART_SERVICE = "RestartService"
    CUSTOM = "Custom"


class RemediationStatus(Enum):
    """Status of remediation execution"""
    PENDING = "Pending"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SKIPPED = "Skipped"


@dataclass
class RemediationRule:
    """Rule for automated remediation"""
    rule_id: str
    name: str
    description: str
    condition: Callable[[Dict[str, Any]], bool]
    action: RemediationAction
    action_params: Dict[str, Any]
    enabled: bool = True
    max_executions_per_hour: int = 10
    cooldown_minutes: int = 15


@dataclass
class RemediationRecord:
    """Record of remediation execution"""
    record_id: str
    rule_id: str
    trigger_event: Dict[str, Any]
    action: RemediationAction
    status: RemediationStatus
    started_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AutomatedRemediationEngine:
    """
    Engine for automated remediation of RAS errors.
    
    Features:
    - Policy-based remediation rules
    - Execution tracking and history
    - Rate limiting and cooldown
    - Custom action handlers
    """
    
    def __init__(self, event_handler=None):
        """
        Initialize remediation engine.
        
        Args:
            event_handler: RAS event handler for notifications
        """
        self.event_handler = event_handler
        
        # Remediation rules
        self.rules: Dict[str, RemediationRule] = {}
        
        # Remediation history
        self.history: List[RemediationRecord] = []
        self.max_history_size = 1000
        
        # Execution tracking
        self.execution_counts: Dict[str, List[float]] = {}
        self.last_execution: Dict[str, float] = {}
        
        # Custom action handlers
        self.action_handlers: Dict[str, Callable] = {}
        
        # Statistics
        self.stats = {
            "total_evaluated": 0,
            "total_executed": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "rules_triggered": {}
        }
        
        # Register default rules
        self._register_default_rules()
        
        logger.info("Automated Remediation Engine initialized")
    
    def _register_default_rules(self):
        """Register default remediation rules"""
        
        # Rule 1: Log critical errors
        self.add_rule(RemediationRule(
            rule_id="rule_001",
            name="Log Critical Errors",
            description="Log all critical errors for audit",
            condition=lambda event: event.get("Severity") == "Critical",
            action=RemediationAction.LOG_ONLY,
            action_params={"log_level": "ERROR"},
            max_executions_per_hour=1000
        ))
        
        # Rule 2: Notify on repeated errors
        self.add_rule(RemediationRule(
            rule_id="rule_002",
            name="Notify on Repeated Errors",
            description="Send notification when same component fails multiple times",
            condition=lambda event: self._check_repeated_failures(event, threshold=3),
            action=RemediationAction.NOTIFY,
            action_params={"notification_type": "email"},
            max_executions_per_hour=10,
            cooldown_minutes=60
        ))
        
        # Rule 3: Disable failing component
        self.add_rule(RemediationRule(
            rule_id="rule_003",
            name="Disable Failing Component",
            description="Disable component after 5 critical failures",
            condition=lambda event: (
                event.get("Severity") == "Critical" and
                self._check_repeated_failures(event, threshold=5)
            ),
            action=RemediationAction.DISABLE_COMPONENT,
            action_params={},
            max_executions_per_hour=5,
            cooldown_minutes=120,
            enabled=False  # Disabled by default for safety
        ))
    
    def add_rule(self, rule: RemediationRule):
        """Add a remediation rule"""
        self.rules[rule.rule_id] = rule
        self.stats["rules_triggered"][rule.rule_id] = 0
        logger.info(f"Added remediation rule: {rule.name} (id={rule.rule_id})")
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a remediation rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"Removed remediation rule: {rule_id}")
            return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        """Enable a remediation rule"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True
            logger.info(f"Enabled rule: {rule_id}")
            return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Disable a remediation rule"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
            logger.info(f"Disabled rule: {rule_id}")
            return True
        return False
    
    def register_action_handler(
        self,
        action_type: str,
        handler: Callable[[Dict[str, Any], RemediationRecord], Dict[str, Any]]
    ):
        """
        Register a custom action handler.
        
        Args:
            action_type: Action type name
            handler: Handler function(action_params, record) -> result
        """
        self.action_handlers[action_type] = handler
        logger.info(f"Registered action handler: {action_type}")
    
    def evaluate_event(self, event: Dict[str, Any]) -> List[RemediationRecord]:
        """
        Evaluate event against remediation rules.
        
        Args:
            event: Event or CPER data to evaluate
            
        Returns:
            list: Remediation records for triggered rules
        """
        self.stats["total_evaluated"] += 1
        triggered_records = []
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            try:
                # Check if condition matches
                if not rule.condition(event):
                    continue
                
                # Check rate limiting
                if not self._check_rate_limit(rule):
                    logger.debug(f"Rule {rule.rule_id} rate limited")
                    self.stats["total_skipped"] += 1
                    continue
                
                # Check cooldown
                if not self._check_cooldown(rule):
                    logger.debug(f"Rule {rule.rule_id} in cooldown")
                    self.stats["total_skipped"] += 1
                    continue
                
                # Execute remediation
                record = self._execute_remediation(rule, event)
                triggered_records.append(record)
                
                # Update statistics
                self.stats["rules_triggered"][rule.rule_id] += 1
                
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.rule_id}: {e}")
        
        return triggered_records
    
    def _execute_remediation(
        self,
        rule: RemediationRule,
        event: Dict[str, Any]
    ) -> RemediationRecord:
        """Execute remediation action"""
        import uuid
        
        record = RemediationRecord(
            record_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            trigger_event=event,
            action=rule.action,
            status=RemediationStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc).isoformat()
        )
        
        try:
            # Execute action based on type
            if rule.action == RemediationAction.LOG_ONLY:
                result = self._action_log_only(event, rule.action_params)
            elif rule.action == RemediationAction.NOTIFY:
                result = self._action_notify(event, rule.action_params)
            elif rule.action == RemediationAction.DISABLE_COMPONENT:
                result = self._action_disable_component(event, rule.action_params)
            elif rule.action == RemediationAction.CUSTOM:
                action_name = rule.action_params.get("handler")
                if action_name in self.action_handlers:
                    result = self.action_handlers[action_name](rule.action_params, record)
                else:
                    raise ValueError(f"Unknown custom action: {action_name}")
            else:
                result = {"status": "not_implemented", "action": rule.action.value}
            
            record.status = RemediationStatus.COMPLETED
            record.result = result
            self.stats["total_executed"] += 1
            
        except Exception as e:
            logger.error(f"Remediation failed for rule {rule.rule_id}: {e}")
            record.status = RemediationStatus.FAILED
            record.error = str(e)
            self.stats["total_failed"] += 1
        
        finally:
            record.completed_at = datetime.now(timezone.utc).isoformat()
            self._add_to_history(record)
            self._update_execution_tracking(rule)
        
        return record
    
    def _action_log_only(
        self,
        event: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Log-only remediation action"""
        log_level = params.get("log_level", "INFO")
        message = f"RAS Event: {event.get('MessageId', 'Unknown')} - {event.get('Message', '')}"
        
        if log_level == "ERROR":
            logger.error(message)
        elif log_level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
        
        return {"action": "logged", "level": log_level}
    
    def _action_notify(
        self,
        event: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notification remediation action"""
        notification_type = params.get("notification_type", "log")
        
        # In real implementation, would send email/SMS/etc
        logger.warning(f"NOTIFICATION ({notification_type}): {event.get('Message', '')}")
        
        # Emit event if handler available
        if self.event_handler:
            try:
                self.event_handler.emit_event({
                    "Events": [{
                        "EventType": "Alert",
                        "MessageId": "OCPRAS.1.0.0.RemediationNotification",
                        "Message": f"Remediation notification: {event.get('Message', '')}",
                        "Severity": "Warning"
                    }]
                })
            except Exception as e:
                logger.error(f"Failed to emit notification event: {e}")
        
        return {"action": "notified", "type": notification_type}
    
    def _action_disable_component(
        self,
        event: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Disable component remediation action"""
        # Extract component ID
        component_id = event.get("Oem", {}).get("OCPRASAPIWS", {}).get("FRUId", "Unknown")
        
        logger.warning(f"Would disable component: {component_id} (simulated)")
        
        # In real implementation, would interface with BMC to disable component
        return {
            "action": "component_disabled",
            "component": component_id,
            "simulated": True
        }
    
    def _check_rate_limit(self, rule: RemediationRule) -> bool:
        """Check if rule execution is within rate limit"""
        import time
        
        current_time = time.time()
        hour_ago = current_time - 3600
        
        # Get executions in last hour
        if rule.rule_id not in self.execution_counts:
            self.execution_counts[rule.rule_id] = []
        
        # Remove old executions
        self.execution_counts[rule.rule_id] = [
            t for t in self.execution_counts[rule.rule_id]
            if t > hour_ago
        ]
        
        # Check limit
        return len(self.execution_counts[rule.rule_id]) < rule.max_executions_per_hour
    
    def _check_cooldown(self, rule: RemediationRule) -> bool:
        """Check if rule is past cooldown period"""
        import time
        
        if rule.rule_id not in self.last_execution:
            return True
        
        current_time = time.time()
        last_exec = self.last_execution[rule.rule_id]
        cooldown_seconds = rule.cooldown_minutes * 60
        
        return (current_time - last_exec) >= cooldown_seconds
    
    def _update_execution_tracking(self, rule: RemediationRule):
        """Update execution tracking for rate limiting"""
        import time
        
        current_time = time.time()
        
        if rule.rule_id not in self.execution_counts:
            self.execution_counts[rule.rule_id] = []
        
        self.execution_counts[rule.rule_id].append(current_time)
        self.last_execution[rule.rule_id] = current_time
    
    def _check_repeated_failures(
        self,
        event: Dict[str, Any],
        threshold: int = 3
    ) -> bool:
        """Check if component has repeated failures"""
        component_id = event.get("Oem", {}).get("OCPRASAPIWS", {}).get("FRUId")
        if not component_id:
            return False
        
        # Count recent failures for this component
        recent_failures = sum(
            1 for record in self.history[-100:]  # Last 100 records
            if (record.trigger_event.get("Oem", {}).get("OCPRASAPIWS", {}).get("FRUId") == component_id)
        )
        
        return recent_failures >= threshold
    
    def _add_to_history(self, record: RemediationRecord):
        """Add record to history"""
        self.history.append(record)
        
        # Trim history if needed
        if len(self.history) > self.max_history_size:
            self.history = self.history[-self.max_history_size:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get remediation statistics"""
        return {
            **self.stats,
            "active_rules": len([r for r in self.rules.values() if r.enabled]),
            "total_rules": len(self.rules),
            "history_size": len(self.history)
        }
    
    def get_recent_remediations(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent remediation records"""
        recent = self.history[-count:] if count > 0 else self.history
        
        return [
            {
                "record_id": r.record_id,
                "rule_id": r.rule_id,
                "action": r.action.value,
                "status": r.status.value,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "result": r.result,
                "error": r.error
            }
            for r in reversed(recent)
        ]
    
    def get_rule_summary(self) -> Dict[str, Any]:
        """Get summary of all rules"""
        return {
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "description": rule.description,
                    "action": rule.action.value,
                    "enabled": rule.enabled,
                    "triggered_count": self.stats["rules_triggered"].get(rule.rule_id, 0)
                }
                for rule in self.rules.values()
            ],
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules.values() if r.enabled])
        }
