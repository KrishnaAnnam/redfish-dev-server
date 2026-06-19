#!/usr/bin/env python3
"""
OCPRAS Message Registry Utilities

Helper functions for using the OCPRAS message registry in RAS plugin operations.
Provides message generation, formatting, and integration with LogService/EventService.
"""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


class OCPRASMessages:
    """Helper class for OCPRAS message registry operations"""
    
    REGISTRY_PREFIX = "OCPRAS"
    REGISTRY_VERSION = "1.0.0"
    REGISTRY_FILE = os.path.join(os.path.dirname(__file__), 'registries', 'OCPRAS.1.0.0.json')
    
    _registry_cache = None
    
    @classmethod
    def _load_registry(cls) -> Dict[str, Any]:
        """Load message registry from file"""
        if cls._registry_cache is None:
            with open(cls.REGISTRY_FILE, 'r') as f:
                cls._registry_cache = json.load(f)
        return cls._registry_cache
    
    @classmethod
    def get_message(cls, message_name: str) -> Optional[Dict[str, Any]]:
        """
        Get message definition from registry
        
        Args:
            message_name: Name of the message (e.g., "CPERRecordCreated")
            
        Returns:
            Message definition dictionary or None if not found
        """
        registry = cls._load_registry()
        return registry.get('Messages', {}).get(message_name)
    
    @classmethod
    def format_message(cls, message_name: str, *args) -> Dict[str, Any]:
        """
        Format a message with arguments
        
        Args:
            message_name: Name of the message
            *args: Message arguments in order
            
        Returns:
            Formatted message object suitable for LogEntry or Event
        """
        message_def = cls.get_message(message_name)
        if not message_def:
            raise ValueError(f"Unknown message: {message_name}")
        
        # Format the message text
        message_text = message_def['Message']
        for i, arg in enumerate(args, 1):
            message_text = message_text.replace(f'%{i}', str(arg))
        
        return {
            "MessageId": f"{cls.REGISTRY_PREFIX}.{cls.REGISTRY_VERSION}.{message_name}",
            "Message": message_text,
            "MessageArgs": list(args),
            "Severity": message_def.get('Severity', 'OK'),
            "MessageSeverity": message_def.get('MessageSeverity', 'OK'),
            "Resolution": message_def.get('Resolution', 'None.')
        }
    
    @classmethod
    def create_log_entry(cls, message_name: str, *args, **kwargs) -> Dict[str, Any]:
        """
        Create a complete LogEntry resource with OCPRAS message
        
        Args:
            message_name: Name of the message
            *args: Message arguments
            **kwargs: Additional LogEntry properties (EntryType, EventTimestamp, etc.)
            
        Returns:
            Complete LogEntry resource dictionary
        """
        message = cls.format_message(message_name, *args)
        
        entry = {
            "@odata.type": "#LogEntry.v1_16_0.LogEntry",
            "EntryType": kwargs.get("EntryType", "Event"),
            "Created": kwargs.get("Created", datetime.now(timezone.utc).isoformat()),
            "EventTimestamp": kwargs.get("EventTimestamp", datetime.now(timezone.utc).isoformat()),
            **message
        }
        
        # Add optional properties if provided
        for key in ["SensorType", "SensorNumber", "EventId", "EventType", "EventGroupId"]:
            if key in kwargs:
                entry[key] = kwargs[key]
        
        return entry
    
    @classmethod
    def list_messages(cls) -> Dict[str, str]:
        """
        List all available messages
        
        Returns:
            Dictionary mapping message name to description
        """
        registry = cls._load_registry()
        return {
            name: msg.get('Description', 'No description')
            for name, msg in registry.get('Messages', {}).items()
        }
    
    @classmethod
    def get_registry_info(cls) -> Dict[str, Any]:
        """
        Get registry metadata
        
        Returns:
            Registry information dictionary
        """
        registry = cls._load_registry()
        return {
            "RegistryPrefix": registry.get("RegistryPrefix"),
            "RegistryVersion": registry.get("RegistryVersion"),
            "OwningEntity": registry.get("OwningEntity"),
            "Language": registry.get("Language"),
            "MessageCount": len(registry.get("Messages", {}))
        }


# Convenience functions for common RAS operations
def cper_created(record_id: str, queue_name: str) -> Dict[str, Any]:
    """Generate CPERRecordCreated message"""
    return OCPRASMessages.format_message("CPERRecordCreated", record_id, queue_name)


def cpad_received(record_id: str, action_id: str) -> Dict[str, Any]:
    """Generate CPADReceived message"""
    return OCPRASMessages.format_message("CPADReceived", record_id, action_id)


def cpad_validated(record_id: str) -> Dict[str, Any]:
    """Generate CPADValidated message"""
    return OCPRASMessages.format_message("CPADValidated", record_id)


def policy_check_passed(check_name: str, value: str) -> Dict[str, Any]:
    """Generate PolicyCheckPassed message"""
    return OCPRASMessages.format_message("PolicyCheckPassed", check_name, value)


def policy_check_failed(check_name: str, reason: str) -> Dict[str, Any]:
    """Generate PolicyCheckFailed message"""
    return OCPRASMessages.format_message("PolicyCheckFailed", check_name, reason)


def cpad_action_completed(action_type: str) -> Dict[str, Any]:
    """Generate CPADActionCompleted message"""
    return OCPRASMessages.format_message("CPADActionCompleted", action_type)


def cpad_action_failed(action_type: str, reason: str) -> Dict[str, Any]:
    """Generate CPADActionFailed message"""
    return OCPRASMessages.format_message("CPADActionFailed", action_type, reason)


def ppr_initiated(device_id: str) -> Dict[str, Any]:
    """Generate PPRInitiated message"""
    return OCPRASMessages.format_message("PPRInitiated", device_id)


def ppr_completed(device_id: str, rows_repaired: int) -> Dict[str, Any]:
    """Generate PPRCompleted message"""
    return OCPRASMessages.format_message("PPRCompleted", device_id, rows_repaired)


if __name__ == "__main__":
    """Test message registry"""
    print("=" * 60)
    print("OCPRAS Message Registry Test")
    print("=" * 60)
    
    # Test 1: Registry info
    info = OCPRASMessages.get_registry_info()
    print(f"\nRegistry: {info['RegistryPrefix']} v{info['RegistryVersion']}")
    print(f"Owner: {info['OwningEntity']}")
    print(f"Messages: {info['MessageCount']}")
    
    # Test 2: Format some messages
    print("\n" + "=" * 60)
    print("Sample Messages")
    print("=" * 60)
    
    msg1 = cper_created("CPER-12345", "Corrected")
    print(f"\n✅ {msg1['MessageId']}")
    print(f"   Message: {msg1['Message']}")
    print(f"   Severity: {msg1['Severity']}")
    
    msg2 = cpad_received("OS-Agent-1", "SPPR")
    print(f"\n✅ {msg2['MessageId']}")
    print(f"   Message: {msg2['Message']}")
    
    msg3 = ppr_completed("DIMM-A1", 5)
    print(f"\n✅ {msg3['MessageId']}")
    print(f"   Message: {msg3['Message']}")
    
    # Test 3: Create LogEntry
    print("\n" + "=" * 60)
    print("LogEntry Generation")
    print("=" * 60)
    
    log_entry = OCPRASMessages.create_log_entry(
        "CPADActionFailed",
        "MemoryRepair",
        "Insufficient spare rows available"
    )
    print(f"\n@odata.type: {log_entry['@odata.type']}")
    print(f"MessageId: {log_entry['MessageId']}")
    print(f"Message: {log_entry['Message']}")
    print(f"Severity: {log_entry['Severity']}")
    print(f"Created: {log_entry['Created']}")
    
    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
