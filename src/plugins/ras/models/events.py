#!/usr/bin/env python3
"""
RAS Event Model

Defines Redfish events emitted by the RAS plugin for:
- CPAD submission lifecycle
- CPER record creation
- Policy evaluation results
- Error detection events
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from enum import Enum


class RASEventType(Enum):
    """RAS Event Types"""
    CPAD_RECEIVED = "CPADReceived"
    CPAD_APPROVED = "CPADApproved"
    CPAD_DENIED = "CPADDenied"
    CPER_RECORD_CREATED = "CPERRecordCreated"
    POLICY_VIOLATION = "PolicyViolation"
    ERROR_DETECTED = "ErrorDetected"
    LOG_SERVICE_CLEARED = "LogServiceCleared"


class RASEventSeverity(Enum):
    """Event severity levels aligned with Redfish"""
    OK = "OK"
    WARNING = "Warning"
    CRITICAL = "Critical"


class RASEventMessage:
    """RAS Event Message Registry"""
    
    # Message registry following Redfish MessageRegistry format
    MESSAGES = {
        "CPADReceived": {
            "Description": "CPAD submission received",
            "Message": "CPAD %1 received from manager %2 for evaluation.",
            "Severity": "OK",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
            "Resolution": "None - informational event."
        },
        "CPADApproved": {
            "Description": "CPAD approved by policy",
            "Message": "CPAD %1 approved by policy. Action: %2. CPER record created.",
            "Severity": "OK",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
            "Resolution": "None - action will be executed."
        },
        "CPADDenied": {
            "Description": "CPAD denied by policy",
            "Message": "CPAD %1 denied by policy. Reason: %2.",
            "Severity": "Warning",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
            "Resolution": "Review policy configuration or CPAD parameters."
        },
        "CPERRecordCreated": {
            "Description": "CPER record created in LogService",
            "Message": "CPER record %1 created in RAS LogService. Severity: %2.",
            "Severity": "OK",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
            "Resolution": "None - record available for retrieval."
        },
        "PolicyViolation": {
            "Description": "Policy violation detected",
            "Message": "Policy violation detected for CPAD %1: %2.",
            "Severity": "Warning",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
            "Resolution": "Verify CPAD parameters and policy rules."
        },
        "ErrorDetected": {
            "Description": "Hardware error detected",
            "Message": "Error detected in %1: %2. Severity: %3.",
            "Severity": "Warning",
            "NumberOfArgs": 3,
            "ParamTypes": ["string", "string", "string"],
            "Resolution": "Review error details and initiate appropriate remediation."
        },
        "LogServiceCleared": {
            "Description": "RAS LogService cleared",
            "Message": "RAS LogService cleared. %1 entries removed.",
            "Severity": "OK",
            "NumberOfArgs": 1,
            "ParamTypes": ["number"],
            "Resolution": "None - log entries have been cleared."
        }
    }
    
    @staticmethod
    def get_message_id(event_type: RASEventType) -> str:
        """Get full message ID for event type"""
        return f"OCPRAS.1.0.0.{event_type.value}"
    
    @staticmethod
    def build_message(event_type: RASEventType, *args) -> str:
        """Build formatted message from template"""
        message_def = RASEventMessage.MESSAGES.get(event_type.value, {})
        message_template = message_def.get("Message", "")
        
        # Simple placeholder replacement
        result = message_template
        for i, arg in enumerate(args, 1):
            result = result.replace(f"%{i}", str(arg))
        
        return result


class RASEvent:
    """RAS Event builder"""
    
    @staticmethod
    def create_event(
        event_type: RASEventType,
        origin_of_condition: str,
        message_args: List[Any],
        severity: Optional[RASEventSeverity] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a Redfish event for RAS activity.
        
        Args:
            event_type: Type of RAS event
            origin_of_condition: Resource that triggered the event
            message_args: Arguments for message formatting
            severity: Event severity (uses default if not provided)
            additional_context: Additional context data
            
        Returns:
            dict: Redfish Event resource
        """
        message_id = RASEventMessage.get_message_id(event_type)
        message_def = RASEventMessage.MESSAGES.get(event_type.value, {})
        
        # Determine severity
        if severity is None:
            severity_str = message_def.get("Severity", "OK")
            severity = RASEventSeverity[severity_str.upper()]
        
        # Build message
        message_text = RASEventMessage.build_message(event_type, *message_args)
        
        # Create event structure
        event = {
            "@odata.type": "#Event.v1_7_0.Event",
            "Id": f"RAS-Event-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "Name": "RAS Event",
            "Events": [{
                "EventType": "Alert",
                "EventId": f"{event_type.value}-{datetime.now(timezone.utc).timestamp()}",
                "EventTimestamp": datetime.now(timezone.utc).isoformat(),
                "Severity": severity.value,
                "Message": message_text,
                "MessageId": message_id,
                "MessageArgs": [str(arg) for arg in message_args],
                "OriginOfCondition": {
                    "@odata.id": origin_of_condition
                },
                "Context": "RAS Plugin Event"
            }]
        }
        
        # Add OEM context if provided
        if additional_context:
            event["Events"][0]["Oem"] = {
                "OCPRASAPIWS": additional_context
            }
        
        return event
    
    @staticmethod
    def create_cpad_received_event(
        manager_id: str,
        cpad_id: str,
        submission_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create event for CPAD received"""
        origin = "/redfish/v1/Oem/OCPRASAPIWS/RASService"
        
        context = {
            "CPADId": cpad_id,
            "RecordId": submission_data.get("RecordId"),
            "RecordType": submission_data.get("RecordType"),
            "SubmissionTime": datetime.now(timezone.utc).isoformat()
        }
        
        return RASEvent.create_event(
            RASEventType.CPAD_RECEIVED,
            origin,
            [cpad_id, manager_id],
            RASEventSeverity.OK,
            context
        )
    
    @staticmethod
    def create_cpad_approved_event(
        manager_id: str,
        cpad_id: str,
        action_id: str,
        log_entry_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create event for CPAD approved"""
        origin = "/redfish/v1/Oem/OCPRASAPIWS/RASService"
        
        context = {
            "CPADId": cpad_id,
            "ActionId": action_id,
            "PolicyDecision": "Approved"
        }
        
        if log_entry_id:
            context["LogEntryId"] = log_entry_id
            context["LogEntryURI"] = f"/redfish/v1/Managers/{manager_id}/LogServices/CPER/Entries/{log_entry_id}"
        
        return RASEvent.create_event(
            RASEventType.CPAD_APPROVED,
            origin,
            [cpad_id, action_id],
            RASEventSeverity.OK,
            context
        )
    
    @staticmethod
    def create_cpad_denied_event(
        manager_id: str,
        cpad_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """Create event for CPAD denied"""
        origin = "/redfish/v1/Oem/OCPRASAPIWS/RASService"
        
        context = {
            "CPADId": cpad_id,
            "PolicyDecision": "Denied",
            "DenialReason": reason
        }
        
        return RASEvent.create_event(
            RASEventType.CPAD_DENIED,
            origin,
            [cpad_id, reason],
            RASEventSeverity.WARNING,
            context
        )
    
    @staticmethod
    def create_cper_created_event(
        manager_id: str,
        log_entry_id: str,
        severity: str,
        cper_data: Dict[str, Any],
        log_entry: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create event for CPER record created per §5.5.
        
        Uses OCPRAS MessageIds and includes DiagnosticData for Pattern A
        or AdditionalDataURI for Pattern B.
        """
        origin = f"/redfish/v1/Managers/{manager_id}/LogServices/CPER/Entries/{log_entry_id}"
        
        # §5.2 Map severity to OCPRAS MessageId
        message_id_map = {
            "Critical": "OCPRAS.1.0.0.FatalError",
            "Warning": "OCPRAS.1.0.0.CorrectedError",
            "OK": "OCPRAS.1.0.0.InformationalEvent",
        }
        # Check if this is a platform action event
        queue_type = None
        if log_entry:
            oem = log_entry.get("Oem", {}).get("OCPRASAPIWS", {})
            queue_type = oem.get("QueueType")
            if queue_type == "PlatformActionStatus":
                message_id = "OCPRAS.1.0.0.PlatformActionEvent"
            elif queue_type == "Recoverable":
                message_id = "OCPRAS.1.0.0.UncorrectedError"
            elif queue_type == "Fatal":
                message_id = "OCPRAS.1.0.0.FatalError"
            else:
                message_id = message_id_map.get(severity, "OCPRAS.1.0.0.InformationalEvent")
        else:
            message_id = message_id_map.get(severity, "OCPRAS.1.0.0.InformationalEvent")
        
        # Build message from log entry or default
        message = "CPER record created."
        if log_entry:
            message = log_entry.get("Message", message)
        
        # Build event record per §5.5
        event_record = {
            "EventType": "Alert",
            "EventId": f"CPER-{log_entry_id}",
            "EventTimestamp": datetime.now(timezone.utc).isoformat(),
            "Severity": severity,
            "Message": message,
            "MessageId": message_id,
            "MessageArgs": [],
            "OriginOfCondition": {
                "@odata.id": origin
            },
        }
        
        # Include inline DiagnosticData (Pattern A) or AdditionalDataURI (Pattern B)
        if log_entry:
            if "DiagnosticData" in log_entry:
                event_record["DiagnosticData"] = log_entry["DiagnosticData"]
                event_record["DiagnosticDataType"] = "CPER"
            elif "AdditionalDataURI" in log_entry:
                event_record["AdditionalDataURI"] = log_entry["AdditionalDataURI"]
            
            # Include OEM metadata
            oem = log_entry.get("Oem", {}).get("OCPRASAPIWS", {})
            if oem:
                event_record["Oem"] = {"OCPRASAPIWS": oem}
        
        event = {
            "@odata.type": "#Event.v1_7_0.Event",
            "Id": f"RAS-Event-{log_entry_id}",
            "Name": "RAS Event",
            "Events": [event_record]
        }
        
        return event
    
    @staticmethod
    def create_log_cleared_event(
        manager_id: str,
        entries_cleared: int
    ) -> Dict[str, Any]:
        """Create event for LogService cleared"""
        origin = f"/redfish/v1/Managers/{manager_id}/LogServices/CPER"
        
        context = {
            "EntriesCleared": entries_cleared,
            "ClearedTime": datetime.now(timezone.utc).isoformat()
        }
        
        return RASEvent.create_event(
            RASEventType.LOG_SERVICE_CLEARED,
            origin,
            [entries_cleared],
            RASEventSeverity.OK,
            context
        )


class EventSubscriptionFilter:
    """Filter events based on subscription criteria"""
    
    @staticmethod
    def matches_subscription(
        event: Dict[str, Any],
        subscription: Dict[str, Any]
    ) -> bool:
        """
        Check if event matches subscription criteria.
        
        Args:
            event: Event to check
            subscription: Subscription criteria
            
        Returns:
            bool: True if event matches subscription
        """
        if not event.get("Events"):
            return False
        
        event_detail = event["Events"][0]
        
        # Check EventTypes filter
        event_types = subscription.get("EventTypes", [])
        if event_types and event_detail.get("EventType") not in event_types:
            return False
        
        # Check MessageIds filter
        message_ids = subscription.get("MessageIds", [])
        if message_ids and event_detail.get("MessageId") not in message_ids:
            return False
        
        # Check OriginResources filter
        origin_resources = subscription.get("OriginResources", [])
        if origin_resources:
            origin = event_detail.get("OriginOfCondition", {}).get("@odata.id")
            # Check if origin matches any filter (support wildcards)
            if not any(EventSubscriptionFilter._matches_origin(origin, pattern) 
                      for pattern in origin_resources):
                return False
        
        # Check Severity filter (OEM extension)
        severities = subscription.get("Oem", {}).get("OCPRASAPIWS", {}).get("Severities", [])
        if severities and event_detail.get("Severity") not in severities:
            return False
        
        return True
    
    @staticmethod
    def _matches_origin(origin: str, pattern: str) -> bool:
        """Check if origin matches pattern (supports wildcards)"""
        if not origin or not pattern:
            return False
        
        # Simple wildcard support
        if pattern.endswith("*"):
            return origin.startswith(pattern[:-1])
        
        return origin == pattern
