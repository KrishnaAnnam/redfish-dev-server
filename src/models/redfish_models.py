#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Data Models for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
=====================================

Provides Redfish-compliant data models for LogEntry, EventEntry, and related structures.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from enum import Enum

class LogEntryType(Enum):
    """Redfish LogEntryType enumeration"""
    EVENT = "Event"
    SEL = "SEL" 
    MULTIPLE = "Multiple"
    OEM = "Oem"

class EventType(Enum):
    """Redfish EventType enumeration"""
    STATUS_CHANGE = "StatusChange"
    RESOURCE_UPDATED = "ResourceUpdated"
    RESOURCE_ADDED = "ResourceAdded"
    RESOURCE_REMOVED = "ResourceRemoved"
    ALERT = "Alert"
    METRIC_REPORT = "MetricReport"

class SeverityType(Enum):
    """Redfish Severity levels"""
    OK = "OK"
    WARNING = "Warning"
    CRITICAL = "Critical"

class LogEntry:
    """Redfish LogEntry model"""
    
    def __init__(self, entry_id: str = None, message: str = None, 
                 severity: SeverityType = SeverityType.OK,
                 entry_type: LogEntryType = LogEntryType.EVENT,
                 message_id: str = None, message_args: List[str] = None,
                 additional_data: Dict[str, Any] = None):
        
        self.id = entry_id or str(uuid.uuid4())[:8]
        self.message = message or ""
        self.severity = severity
        self.entry_type = entry_type
        self.message_id = message_id
        self.message_args = message_args or []
        self.additional_data = additional_data or {}
        
        self.created = datetime.now(timezone.utc)
        self.entry_code = self._generate_entry_code()
        self.sensor_type = None
        self.sensor_number = None
        self.oem = {}
        
    def _generate_entry_code(self) -> str:
        """Generate entry code based on severity and type"""
        severity_codes = {
            SeverityType.OK: "Informational",
            SeverityType.WARNING: "Warning", 
            SeverityType.CRITICAL: "Critical"
        }
        return severity_codes.get(self.severity, "Unknown")
    
    def to_redfish_dict(self, base_path: str = "/redfish/v1") -> Dict[str, Any]:
        """Convert to Redfish LogEntry representation"""
        entry_data = {
            "@odata.type": "#LogEntry.v1_4_0.LogEntry",
            "@odata.id": f"{base_path}/Systems/system/LogServices/EventLog/Entries/{self.id}",
            "Id": self.id,
            "Name": f"Log Entry {self.id}",
            "EntryType": self.entry_type.value,
            "Severity": self.severity.value,
            "Created": self.created.isoformat(),
            "EntryCode": self.entry_code,
            "Message": self.message
        }
        
        if self.message_id:
            entry_data["MessageId"] = self.message_id
            
        if self.message_args:
            entry_data["MessageArgs"] = self.message_args
            
        if self.sensor_type:
            entry_data["SensorType"] = self.sensor_type
            
        if self.sensor_number is not None:
            entry_data["SensorNumber"] = self.sensor_number
            
        if self.additional_data:
            entry_data["AdditionalDataURI"] = f"{base_path}/Systems/system/LogServices/EventLog/Entries/{self.id}/AdditionalData"
            
        if self.oem:
            entry_data["Oem"] = self.oem
            
        return entry_data
    
    @classmethod
    def from_message(cls, message_id: str, message: str, 
                    severity: SeverityType = SeverityType.OK,
                    message_args: List[str] = None) -> 'LogEntry':
        """Create LogEntry from message information"""
        return cls(
            message=message,
            severity=severity,
            message_id=message_id,
            message_args=message_args or []
        )
    
    @classmethod
    def from_event(cls, event_data: Dict[str, Any]) -> 'LogEntry':
        """Create LogEntry from event data"""
        severity = SeverityType.OK
        if "Severity" in event_data:
            try:
                severity = SeverityType(event_data["Severity"])
            except ValueError:
                pass
                
        return cls(
            message=event_data.get("Message", ""),
            severity=severity,
            message_id=event_data.get("MessageId"),
            message_args=event_data.get("MessageArgs", []),
            additional_data=event_data.get("AdditionalData", {})
        )

class EventEntry:
    """Redfish Event model for notifications"""
    
    def __init__(self, event_type: EventType, message_id: str,
                 message: str, severity: SeverityType = SeverityType.OK,
                 origin_of_condition: str = None, message_args: List[str] = None):
        
        self.event_id = str(uuid.uuid4())[:8] 
        self.event_type = event_type
        self.message_id = message_id
        self.message = message
        self.severity = severity
        self.message_args = message_args or []
        self.origin_of_condition = origin_of_condition
        
        self.timestamp = datetime.now(timezone.utc)
        self.event_group_id = None
        self.additional_data = {}
        self.oem = {}
        
    def to_redfish_dict(self) -> Dict[str, Any]:
        """Convert to Redfish Event representation"""
        event_data = {
            "@odata.type": "#Event.v1_3_0.Event",
            "Id": self.event_id,
            "Name": "Event",
            "Context": f"Event-{self.event_id}",
            "Events": [{
                "EventType": self.event_type.value,
                "EventId": self.event_id,
                "EventTimestamp": self.timestamp.isoformat(),
                "Severity": self.severity.value,
                "Message": self.message,
                "MessageId": self.message_id,
                "MessageArgs": self.message_args
            }]
        }
        
        if self.origin_of_condition:
            event_data["Events"][0]["OriginOfCondition"] = {
                "@odata.id": self.origin_of_condition
            }
            
        if self.event_group_id:
            event_data["Events"][0]["EventGroupId"] = self.event_group_id
            
        if self.additional_data:
            event_data["Events"][0]["AdditionalData"] = self.additional_data
            
        if self.oem:
            event_data["Events"][0]["Oem"] = self.oem
            
        return event_data
    
    def to_log_entry(self) -> LogEntry:
        """Convert event to LogEntry for logging"""
        return LogEntry.from_message(
            message_id=self.message_id,
            message=self.message,
            severity=self.severity,
            message_args=self.message_args
        )
    
    @classmethod
    def resource_created(cls, resource_path: str, resource_type: str = "Resource") -> 'EventEntry':
        """Create resource added event"""
        return cls(
            event_type=EventType.RESOURCE_ADDED,
            message_id="ResourceEvent.1.0.0.ResourceCreated",
            message=f"{resource_type} has been created.",
            severity=SeverityType.OK,
            origin_of_condition=resource_path,
            message_args=[resource_type, resource_path]
        )
    
    @classmethod
    def resource_updated(cls, resource_path: str, resource_type: str = "Resource") -> 'EventEntry':
        """Create resource updated event"""
        return cls(
            event_type=EventType.RESOURCE_UPDATED,
            message_id="ResourceEvent.1.0.0.ResourceModified", 
            message=f"{resource_type} has been modified.",
            severity=SeverityType.OK,
            origin_of_condition=resource_path,
            message_args=[resource_type, resource_path]
        )
    
    @classmethod
    def resource_deleted(cls, resource_path: str, resource_type: str = "Resource") -> 'EventEntry':
        """Create resource removed event"""
        return cls(
            event_type=EventType.RESOURCE_REMOVED,
            message_id="ResourceEvent.1.0.0.ResourceRemoved",
            message=f"{resource_type} has been removed.",
            severity=SeverityType.OK,
            origin_of_condition=resource_path,
            message_args=[resource_type, resource_path]
        )
    
    @classmethod
    def status_change(cls, resource_path: str, old_status: str, new_status: str) -> 'EventEntry':
        """Create status change event"""
        return cls(
            event_type=EventType.STATUS_CHANGE,
            message_id="ResourceEvent.1.0.0.ResourceStatusChanged",
            message=f"Resource status changed from {old_status} to {new_status}.",
            severity=SeverityType.WARNING if new_status in ["Critical", "Warning"] else SeverityType.OK,
            origin_of_condition=resource_path,
            message_args=[old_status, new_status]
        )
    
    @classmethod  
    def alert_event(cls, resource_path: str, alert_message: str, 
                   severity: SeverityType = SeverityType.WARNING) -> 'EventEntry':
        """Create alert event"""
        return cls(
            event_type=EventType.ALERT,
            message_id="Base.1.5.0.GeneralError",
            message=alert_message,
            severity=severity,
            origin_of_condition=resource_path
        )

class TaskEventEntry(EventEntry):
    """Task-specific event entry"""
    
    def __init__(self, task_id: str, task_state: str, message: str,
                 severity: SeverityType = SeverityType.OK):
        super().__init__(
            event_type=EventType.STATUS_CHANGE,
            message_id="TaskEvent.1.0.0.TaskStateChanged",
            message=message,
            severity=severity,
            origin_of_condition=f"/redfish/v1/TaskService/Tasks/{task_id}",
            message_args=[task_id, task_state]
        )
        self.task_id = task_id
        self.task_state = task_state

class LogEntryCollection:
    """Collection of LogEntries with pagination support"""
    
    def __init__(self, base_path: str = "/redfish/v1/Systems/system/LogServices/EventLog"):
        self.base_path = base_path
        self.entries: Dict[str, LogEntry] = {}
        self.max_entries = 1000  # Default max entries
        
    def add_entry(self, entry: LogEntry) -> str:
        """Add log entry to collection"""
        self.entries[entry.id] = entry
        
        # Handle overflow
        if len(self.entries) > self.max_entries:
            # Remove oldest entry
            oldest_id = min(self.entries.keys(), 
                          key=lambda k: self.entries[k].created)
            del self.entries[oldest_id]
            
        return entry.id
    
    def get_entry(self, entry_id: str) -> Optional[LogEntry]:
        """Get specific log entry"""
        return self.entries.get(entry_id)
    
    def get_entries(self, start: int = 0, count: int = None) -> List[LogEntry]:
        """Get entries with pagination"""
        sorted_entries = sorted(self.entries.values(), 
                              key=lambda e: e.created, reverse=True)
        
        if count is None:
            return sorted_entries[start:]
        else:
            return sorted_entries[start:start + count]
    
    def to_redfish_collection(self, start: int = 0, count: int = 50) -> Dict[str, Any]:
        """Convert to Redfish collection format"""
        entries = self.get_entries(start, count)
        
        return {
            "@odata.type": "#LogEntryCollection.LogEntryCollection",
            "@odata.id": f"{self.base_path}/Entries",
            "Name": "Log Entry Collection",
            "Description": "Collection of Log Entries",
            "Members@odata.count": len(self.entries),
            "Members": [
                {"@odata.id": f"{self.base_path}/Entries/{entry.id}"}
                for entry in entries
            ]
        }
    
    def clear_entries(self):
        """Clear all log entries"""
        self.entries.clear()
    
    def delete_entry(self, entry_id: str) -> bool:
        """Delete specific log entry"""
        if entry_id in self.entries:
            del self.entries[entry_id]
            return True
        return False