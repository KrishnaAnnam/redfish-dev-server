#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Log Service for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
=====================================

Provides comprehensive log entry management with different log types,
persistence, CRUD operations, and Redfish compliance.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from threading import Lock

from ..models.redfish_models import LogEntry, LogEntryCollection, SeverityType, LogEntryType
from .message_service import MessageService, get_message_service

logger = logging.getLogger(__name__)

class LogServiceType:
    """Log service types"""
    EVENT = "Event"
    SEL = "SEL"
    IPMI = "IPMI" 
    BIOS = "BIOS"
    AUDIT = "Audit"
    SECURITY = "Security"

class LogStorage:
    """Handles persistent storage of log entries"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
    
    def save_log_collection(self, service_name: str, collection: LogEntryCollection):
        """Save log collection to file"""
        with self._lock:
            try:
                file_path = self.storage_path / f"{service_name}_logs.json"
                
                # Convert to serializable format
                entries_data = {}
                for entry_id, entry in collection.entries.items():
                    entries_data[entry_id] = {
                        "id": entry.id,
                        "message": entry.message,
                        "severity": entry.severity.value,
                        "entry_type": entry.entry_type.value,
                        "message_id": entry.message_id,
                        "message_args": entry.message_args,
                        "additional_data": entry.additional_data,
                        "created": entry.created.isoformat(),
                        "entry_code": entry.entry_code,
                        "sensor_type": entry.sensor_type,
                        "sensor_number": entry.sensor_number,
                        "oem": entry.oem
                    }
                
                with open(file_path, 'w') as f:
                    json.dump(entries_data, f, indent=2)
                    
            except Exception as e:
                logger.error(f"Failed to save logs for {service_name}: {e}")
    
    def load_log_collection(self, service_name: str) -> LogEntryCollection:
        """Load log collection from file"""
        collection = LogEntryCollection()
        
        with self._lock:
            try:
                file_path = self.storage_path / f"{service_name}_logs.json"
                
                if not file_path.exists():
                    return collection
                
                with open(file_path, 'r') as f:
                    entries_data = json.load(f)
                
                for entry_id, entry_data in entries_data.items():
                    # Reconstruct LogEntry
                    entry = LogEntry(
                        entry_id=entry_data["id"],
                        message=entry_data["message"],
                        severity=SeverityType(entry_data["severity"]),
                        entry_type=LogEntryType(entry_data["entry_type"]),
                        message_id=entry_data.get("message_id"),
                        message_args=entry_data.get("message_args", []),
                        additional_data=entry_data.get("additional_data", {})
                    )
                    
                    # Restore timestamps and other fields
                    entry.created = datetime.fromisoformat(entry_data["created"])
                    entry.entry_code = entry_data.get("entry_code", "")
                    entry.sensor_type = entry_data.get("sensor_type")
                    entry.sensor_number = entry_data.get("sensor_number")
                    entry.oem = entry_data.get("oem", {})
                    
                    collection.entries[entry_id] = entry
                    
            except Exception as e:
                logger.error(f"Failed to load logs for {service_name}: {e}")
        
        return collection

class LogService:
    """Core log service for managing multiple log types"""
    
    def __init__(self, config, message_service: MessageService = None):
        self.config = config
        self.message_service = message_service or get_message_service(config)
        
        # Initialize storage
        storage_dir = Path(config.mock_dir if config else ".") / "logs"
        self.storage = LogStorage(storage_dir)
        
        # Log collections by service type
        self.log_collections: Dict[str, LogEntryCollection] = {}
        
        # Initialize default log services
        self._initialize_log_services()
        
        # Load existing logs
        self._load_existing_logs()
    
    def _initialize_log_services(self):
        """Initialize default log services"""
        default_services = [
            LogServiceType.EVENT,
            LogServiceType.SEL, 
            LogServiceType.AUDIT,
            LogServiceType.SECURITY
        ]
        
        for service_type in default_services:
            base_path = f"/redfish/v1/Systems/system/LogServices/{service_type}"
            self.log_collections[service_type] = LogEntryCollection(base_path)
    
    def _load_existing_logs(self):
        """Load existing logs from storage"""
        for service_name in self.log_collections.keys():
            loaded_collection = self.storage.load_log_collection(service_name)
            if loaded_collection.entries:
                self.log_collections[service_name] = loaded_collection
                logger.info(f"Loaded {len(loaded_collection.entries)} entries for {service_name}")
    
    def add_log_entry(self, service_type: str, entry: LogEntry) -> str:
        """Add log entry to specified service"""
        if service_type not in self.log_collections:
            # Create new log collection for unknown service types
            base_path = f"/redfish/v1/Systems/system/LogServices/{service_type}"
            self.log_collections[service_type] = LogEntryCollection(base_path)
        
        entry_id = self.log_collections[service_type].add_entry(entry)
        
        # Save to persistent storage
        self.storage.save_log_collection(service_type, self.log_collections[service_type])
        
        logger.debug(f"Added log entry {entry_id} to {service_type} service")
        return entry_id
    
    def create_and_log_entry(self, service_type: str, message_id: str, 
                           message: str, severity: SeverityType = SeverityType.OK,
                           message_args: List[str] = None,
                           additional_data: Dict[str, Any] = None) -> str:
        """Create and add log entry from message data"""
        entry = LogEntry(
            message=message,
            severity=severity,
            message_id=message_id,
            message_args=message_args or [],
            additional_data=additional_data or {}
        )
        
        return self.add_log_entry(service_type, entry)
    
    def log_operation(self, operation: str, resource_path: str, 
                     success: bool = True, details: str = None) -> str:
        """Log an operation with automatic message generation"""
        if success:
            message_id = "Base.1.5.0.Success" if operation != "CREATE" else "Base.1.5.0.Created"
            message = f"{operation} operation completed successfully on {resource_path}"
            severity = SeverityType.OK
        else:
            message_id = "Base.1.5.0.GeneralError"
            message = f"{operation} operation failed on {resource_path}"
            severity = SeverityType.CRITICAL
            if details:
                message += f": {details}"
        
        return self.create_and_log_entry(
            LogServiceType.EVENT,
            message_id,
            message,
            severity,
            message_args=[operation, resource_path]
        )
    
    def log_property_change(self, resource_path: str, property_name: str,
                          old_value: Any, new_value: Any) -> str:
        """Log property change"""
        message = f"Property '{property_name}' changed from '{old_value}' to '{new_value}'"
        
        return self.create_and_log_entry(
            LogServiceType.AUDIT,
            "Base.1.5.0.PropertyValueChanged",
            message,
            SeverityType.OK,
            message_args=[property_name, str(old_value), str(new_value)],
            additional_data={
                "ResourcePath": resource_path,
                "PropertyName": property_name,
                "OldValue": str(old_value),
                "NewValue": str(new_value)
            }
        )
    
    def log_authentication_event(self, username: str, success: bool, 
                               source_ip: str = None) -> str:
        """Log authentication event"""
        if success:
            message = f"User '{username}' successfully authenticated"
            severity = SeverityType.OK
            message_id = "Security.1.0.0.AuthenticationSuccessful"
        else:
            message = f"Authentication failed for user '{username}'"
            severity = SeverityType.WARNING
            message_id = "Security.1.0.0.AuthenticationFailed"
        
        additional_data = {"Username": username}
        if source_ip:
            additional_data["SourceIP"] = source_ip
            message += f" from {source_ip}"
        
        return self.create_and_log_entry(
            LogServiceType.SECURITY,
            message_id,
            message,
            severity,
            message_args=[username],
            additional_data=additional_data
        )
    
    def get_log_service_info(self, service_type: str) -> Dict[str, Any]:
        """Get log service information"""
        if service_type not in self.log_collections:
            return {}
        
        collection = self.log_collections[service_type]
        
        return {
            "@odata.type": "#LogService.v1_1_0.LogService",
            "@odata.id": f"/redfish/v1/Systems/system/LogServices/{service_type}",
            "Id": service_type,
            "Name": f"{service_type} Log Service",
            "Description": f"Log Service for {service_type} entries",
            "ServiceEnabled": True,
            "MaxNumberOfRecords": collection.max_entries,
            "OverWritePolicy": "WrapsWhenFull",
            "Status": {
                "State": "Enabled",
                "Health": "OK"
            },
            "Entries": {
                "@odata.id": f"/redfish/v1/Systems/system/LogServices/{service_type}/Entries"
            },
            "Actions": {
                "#LogService.ClearLog": {
                    "target": f"/redfish/v1/Systems/system/LogServices/{service_type}/Actions/LogService.ClearLog"
                }
            }
        }
    
    def get_log_services_collection(self) -> Dict[str, Any]:
        """Get collection of all log services"""
        members = []
        for service_type in self.log_collections.keys():
            members.append({
                "@odata.id": f"/redfish/v1/Systems/system/LogServices/{service_type}"
            })
        
        return {
            "@odata.type": "#LogServiceCollection.LogServiceCollection",
            "@odata.id": "/redfish/v1/Systems/system/LogServices",
            "Name": "Log Service Collection",
            "Description": "Collection of Log Services",
            "Members@odata.count": len(members),
            "Members": members
        }
    
    def get_log_entries(self, service_type: str, start: int = 0, 
                       count: int = 50) -> Optional[Dict[str, Any]]:
        """Get log entries collection for service"""
        if service_type not in self.log_collections:
            return None
        
        return self.log_collections[service_type].to_redfish_collection(start, count)
    
    def get_log_entry(self, service_type: str, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get specific log entry"""
        if service_type not in self.log_collections:
            return None
        
        entry = self.log_collections[service_type].get_entry(entry_id)
        if entry:
            base_path = f"/redfish/v1/Systems/system/LogServices/{service_type}"
            return entry.to_redfish_dict(base_path)
        
        return None
    
    def clear_log_service(self, service_type: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Clear all entries from log service"""
        if service_type not in self.log_collections:
            return self.message_service.create_not_found_response("LogService", service_type)
        
        self.log_collections[service_type].clear_entries()
        self.storage.save_log_collection(service_type, self.log_collections[service_type])
        
        # Log the clear operation
        self.log_operation("CLEAR", f"/redfish/v1/Systems/system/LogServices/{service_type}")
        
        return self.message_service.create_success_response()
    
    def delete_log_entry(self, service_type: str, entry_id: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Delete specific log entry"""
        if service_type not in self.log_collections:
            return self.message_service.create_not_found_response("LogService", service_type)
        
        if not self.log_collections[service_type].delete_entry(entry_id):
            return self.message_service.create_not_found_response("LogEntry", entry_id)
        
        self.storage.save_log_collection(service_type, self.log_collections[service_type])
        
        return self.message_service.create_success_response()
    
    def handle_log_service_get(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle GET requests to LogService endpoints"""
        parts = path.strip('/').split('/')
        
        try:
            if 'LogServices' not in parts:
                return 404, {}, {"error": "Not found"}
            
            log_services_index = parts.index('LogServices')
            
            # /redfish/v1/Systems/system/LogServices
            if log_services_index == len(parts) - 1:
                return 200, {}, self.get_log_services_collection()
            
            # /redfish/v1/Systems/system/LogServices/{service}
            elif log_services_index + 1 < len(parts):
                service_type = parts[log_services_index + 1]
                
                # /redfish/v1/Systems/system/LogServices/{service}
                if log_services_index + 1 == len(parts) - 1:
                    service_info = self.get_log_service_info(service_type)
                    if service_info:
                        return 200, {}, service_info
                    else:
                        return self.message_service.create_not_found_response("LogService", service_type)
                
                # /redfish/v1/Systems/system/LogServices/{service}/Entries
                elif parts[log_services_index + 2] == "Entries":
                    if log_services_index + 2 == len(parts) - 1:
                        # Entries collection
                        entries = self.get_log_entries(service_type)
                        if entries:
                            return 200, {}, entries
                        else:
                            return self.message_service.create_not_found_response("LogService", service_type)
                    
                    # /redfish/v1/Systems/system/LogServices/{service}/Entries/{entry_id}
                    elif log_services_index + 3 < len(parts):
                        entry_id = parts[log_services_index + 3]
                        entry = self.get_log_entry(service_type, entry_id)
                        if entry:
                            return 200, {}, entry
                        else:
                            return self.message_service.create_not_found_response("LogEntry", entry_id)
            
            return 404, {}, {"error": "Not found"}
            
        except Exception as e:
            logger.error(f"Error handling LogService GET request: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")
    
    def handle_log_service_post(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle POST requests to LogService endpoints (actions)"""
        parts = path.strip('/').split('/')
        
        try:
            if 'Actions' in parts and 'LogService.ClearLog' in parts:
                # Find service type
                log_services_index = parts.index('LogServices')
                if log_services_index + 1 < len(parts):
                    service_type = parts[log_services_index + 1]
                    return self.clear_log_service(service_type)
            
            return 404, {}, {"error": "Action not found"}
            
        except Exception as e:
            logger.error(f"Error handling LogService POST request: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")
    
    def handle_log_service_delete(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle DELETE requests to LogService endpoints"""
        parts = path.strip('/').split('/')
        
        try:
            if 'Entries' in parts:
                log_services_index = parts.index('LogServices')
                entries_index = parts.index('Entries')
                
                if log_services_index + 1 < len(parts) and entries_index + 1 < len(parts):
                    service_type = parts[log_services_index + 1]
                    entry_id = parts[entries_index + 1]
                    return self.delete_log_entry(service_type, entry_id)
            
            return 404, {}, {"error": "Not found"}
            
        except Exception as e:
            logger.error(f"Error handling LogService DELETE request: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")

# Global log service instance
_log_service_instance = None

def get_log_service(config=None) -> LogService:
    """Get global log service instance"""
    global _log_service_instance
    if _log_service_instance is None:
        _log_service_instance = LogService(config)
    return _log_service_instance

def init_log_service(config):
    """Initialize global log service"""
    global _log_service_instance
    _log_service_instance = LogService(config)