#!/usr/bin/env python3
"""
RAS LogService Handler

Manages the RAS LogService for storing CPER error records as Redfish LogEntry resources.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

from ..models.log_entry import CPERToLogEntry
from .event_service import RASEventServiceHandler


logger = logging.getLogger(__name__)


class RASLogServiceHandler:
    """Handler for RAS LogService operations"""
    
    def __init__(self, mockup_dir: str, manager_id: str = "System", event_handler: Optional[RASEventServiceHandler] = None):
        """
        Initialize RAS CPER LogService handler.
        
        Args:
            mockup_dir: Path to mockup directory root
            manager_id: Manager ID (default: System)
            event_handler: Optional event handler for emitting events
        """
        self.mockup_dir = mockup_dir
        self.manager_id = manager_id
        self.event_handler = event_handler
        self.log_service_path = f"/redfish/v1/Managers/{manager_id}/LogServices/CPER"
        self.entries_path = f"{self.log_service_path}/Entries"
        
        # File system paths
        self.log_service_fs_path = Path(mockup_dir) / "redfish/v1/Managers" / manager_id / "LogServices/CPER"
        self.entries_fs_path = self.log_service_fs_path / "Entries"
        
        # Ensure directories exist
        self.entries_fs_path.mkdir(parents=True, exist_ok=True)

        # BMC-assigned CPER recordID counter.  A real RAS API endpoint assigns
        # the recordID as it logs each CPER; this demo has no such endpoint, so
        # the BMC assigns sequential recordIDs starting at 1 (see next_record_id).
        self._record_id_counter = 0

        # Initialize LogService resource if not present
        self._ensure_log_service_resource()

        logger.info(f"CPER LogService initialized for Manager: {manager_id}")

    def next_record_id(self) -> int:
        """Assign the next sequential CPER recordID.

        The recordID is BMC-assigned (a stand-in for the RAS API endpoint) and
        starts at 1, incrementing for every new CPER the BMC emits.  It resets
        on server restart, which is fine for the demo.
        """
        self._record_id_counter += 1
        return self._record_id_counter
    
    def add_cper_log_entry(self, cper_data: Dict[str, Any], binary_cper_path: str = None) -> Tuple[int, str]:
        """
        Add a CPER record as a LogEntry per OCP RAS API §4.
        
        Uses Pattern A (inline DiagnosticData) for small CPERs,
        Pattern B (AdditionalDataURI) for large CPERs.
        
        Args:
            cper_data: CPER record data (JSON)
            binary_cper_path: Optional path to binary .cper file
            
        Returns:
            tuple: (HTTP status, entry_id)
        """
        try:
            # Generate entry ID
            entry_id = self._generate_entry_id(cper_data)
            
            # Read binary CPER if available
            binary_cper = None
            if binary_cper_path and os.path.exists(binary_cper_path):
                with open(binary_cper_path, 'rb') as f:
                    binary_cper = f.read()
            
            # Convert CPER to LogEntry format (handles Pattern A vs B internally)
            log_entry = CPERToLogEntry.convert(cper_data, self.manager_id, entry_id, binary_cper)
            
            # Save LogEntry
            self._save_log_entry(entry_id, log_entry)
            
            # Save attachment for Pattern B (large CPERs or when binary is available)
            if binary_cper and "AdditionalDataURI" in log_entry:
                self._save_binary_attachment(entry_id, binary_cper)
            elif not binary_cper and "AdditionalDataURI" in log_entry:
                # Fallback: save JSON-serialized CPER as binary attachment
                self._save_binary_attachment(entry_id, json.dumps(cper_data).encode('utf-8'))
            
            # Update collection
            self._update_collection(entry_id)
            
            # Emit CPER created event
            if self.event_handler:
                try:
                    severity = log_entry.get("Severity", "OK")
                    self.event_handler.emit_cper_created(
                        self.manager_id,
                        entry_id,
                        severity,
                        cper_data,
                        log_entry
                    )
                except Exception as e:
                    logger.error(f"Failed to emit CPER created event: {e}")
            
            logger.info(f"Created RAS LogEntry: {entry_id}")
            return (201, entry_id)
            
        except Exception as e:
            logger.error(f"Failed to create RAS LogEntry: {e}")
            return (500, None)
    
    def get_log_entry(self, entry_id: str) -> Tuple[int, Optional[Dict[str, Any]]]:
        """
        Get a specific LogEntry.
        
        Args:
            entry_id: Entry ID
            
        Returns:
            tuple: (HTTP status, log_entry data or None)
        """
        entry_file = self.entries_fs_path / entry_id / "index.json"
        
        if not entry_file.exists():
            return (404, None)
        
        try:
            with open(entry_file, 'r') as f:
                log_entry = json.load(f)
            return (200, log_entry)
        except Exception as e:
            logger.error(f"Failed to read LogEntry {entry_id}: {e}")
            return (500, None)
    
    def get_log_entries(self, filter_params: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
        """
        Get LogEntry collection with optional filtering.
        
        Args:
            filter_params: Optional filter parameters (severity, timestamp, etc.)
            
        Returns:
            tuple: (HTTP status, collection data)
        """
        try:
            collection_file = self.entries_fs_path / "index.json"
            
            if not collection_file.exists():
                # Return empty collection
                return (200, {
                    "@odata.type": "#LogEntryCollection.LogEntryCollection",
                    "@odata.id": self.entries_path,
                    "Name": "CPER Log Entries",
                    "Members@odata.count": 0,
                    "Members": []
                })
            
            with open(collection_file, 'r') as f:
                collection = json.load(f)
            
            # Apply filters if provided
            if filter_params:
                collection = self._apply_filters(collection, filter_params)
            
            return (200, collection)
            
        except Exception as e:
            logger.error(f"Failed to get LogEntry collection: {e}")
            return (500, {"error": str(e)})
    
    def get_attachment(self, entry_id: str) -> Tuple[int, Optional[bytes]]:
        """
        Get full CPER attachment for a LogEntry.
        
        Args:
            entry_id: Entry ID
            
        Returns:
            tuple: (HTTP status, attachment data or None)
        """
        attachment_file = self.entries_fs_path / entry_id / "Attachment"
        
        if not attachment_file.exists():
            return (404, None)
        
        try:
            with open(attachment_file, 'rb') as f:
                data = f.read()
            return (200, data)
        except Exception as e:
            logger.error(f"Failed to read attachment for {entry_id}: {e}")
            return (500, None)
    
    def clear_logs(self) -> Tuple[int, Dict[str, Any]]:
        """
        Clear all RAS log entries.
        
        Returns:
            tuple: (HTTP status, response message)
        """
        try:
            # Count entries before clearing
            entries_count = sum(1 for d in self.entries_fs_path.iterdir() 
                              if d.is_dir() and d.name != "__pycache__")
            
            # Remove all entry directories
            for entry_dir in self.entries_fs_path.iterdir():
                if entry_dir.is_dir() and entry_dir.name != "__pycache__":
                    for file in entry_dir.iterdir():
                        file.unlink()
                    entry_dir.rmdir()
            
            # Reset collection
            collection = {
                "@odata.type": "#LogEntryCollection.LogEntryCollection",
                "@odata.id": self.entries_path,
                "Name": "CPER Log Entries",
                "Members@odata.count": 0,
                "Members": []
            }
            
            collection_file = self.entries_fs_path / "index.json"
            with open(collection_file, 'w') as f:
                json.dump(collection, f, indent=2)
            
            # Emit log cleared event
            if self.event_handler:
                try:
                    self.event_handler.emit_log_cleared(self.manager_id, entries_count)
                except Exception as e:
                    logger.error(f"Failed to emit log cleared event: {e}")
            
            logger.info(f"Cleared all RAS log entries ({entries_count} entries)")
            return (200, {"Message": f"RAS logs cleared successfully. {entries_count} entries removed."})
            
        except Exception as e:
            logger.error(f"Failed to clear RAS logs: {e}")
            return (500, {"error": str(e)})
    
    def _generate_entry_id(self, cper_data: Dict[str, Any]) -> str:
        """Generate unique entry ID from CPER data"""
        # Try simple format first
        if "RecordId" in cper_data:
            return str(cper_data["RecordId"]).replace("0x", "")
        
        # Try full CPER format
        header = cper_data.get("header", {})
        record_id = header.get("recordID")
        
        if record_id:
            return str(record_id)
        
        # Fallback: generate from timestamp + random component
        import random
        timestamp = header.get("timestamp", datetime.now(timezone.utc).isoformat())
        ts_part = timestamp.replace(":", "").replace("-", "").replace(".", "")[:14]
        random_part = f"{random.randint(0, 9999):04d}"
        return f"{ts_part}{random_part}"
    
    def _save_log_entry(self, entry_id: str, log_entry: Dict[str, Any]):
        """Save LogEntry to file system"""
        entry_dir = self.entries_fs_path / entry_id
        entry_dir.mkdir(exist_ok=True)
        
        entry_file = entry_dir / "index.json"
        with open(entry_file, 'w') as f:
            json.dump(log_entry, f, indent=2)
    
    def _save_binary_attachment(self, entry_id: str, binary_cper: bytes):
        """Save raw binary CPER as attachment for Pattern B."""
        entry_dir = self.entries_fs_path / entry_id
        attachment_file = entry_dir / "Attachment"
        with open(attachment_file, 'wb') as f:
            f.write(binary_cper)
        logger.info(f"Stored binary CPER attachment for entry {entry_id} ({len(binary_cper)} bytes)")

    def _ensure_log_service_resource(self):
        """Create the CPER LogService resource file if not present."""
        log_service_file = self.log_service_fs_path / "index.json"
        if not log_service_file.exists():
            resource = {
                "@odata.type": "#LogService.v1_8_0.LogService",
                "@odata.id": self.log_service_path,
                "Id": "CPER",
                "Name": "CPER Log Service",
                "Description": "Persistent Common Platform Error Record storage",
                "OverWritePolicy": "WrapsWhenFull",
                "MaxNumberOfRecords": 1000,
                "Entries": {
                    "@odata.id": self.entries_path
                },
                "Actions": {
                    "#LogService.ClearLog": {
                        "target": f"{self.log_service_path}/Actions/LogService.ClearLog"
                    }
                },
                "Status": {
                    "State": "Enabled",
                    "Health": "OK"
                }
            }
            self.log_service_fs_path.mkdir(parents=True, exist_ok=True)
            with open(log_service_file, 'w') as f:
                json.dump(resource, f, indent=2)
            logger.info(f"Created CPER LogService resource at {self.log_service_path}")

    def delete_entry(self, entry_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        Delete a specific CPER LogEntry (§4.8).
        
        Args:
            entry_id: Entry ID to delete
            
        Returns:
            tuple: (HTTP status, response)
        """
        entry_dir = self.entries_fs_path / entry_id
        if not entry_dir.exists():
            return (404, {"error": f"Entry {entry_id} not found"})
        
        try:
            # Remove entry directory and contents
            for file in entry_dir.iterdir():
                file.unlink()
            entry_dir.rmdir()
            
            # Update collection to remove the entry
            collection_file = self.entries_fs_path / "index.json"
            if collection_file.exists():
                with open(collection_file, 'r') as f:
                    collection = json.load(f)
                
                member_uri = f"{self.entries_path}/{entry_id}"
                collection["Members"] = [
                    m for m in collection.get("Members", [])
                    if m.get("@odata.id") != member_uri
                ]
                collection["Members@odata.count"] = len(collection["Members"])
                
                with open(collection_file, 'w') as f:
                    json.dump(collection, f, indent=2)
            
            logger.info(f"Deleted CPER LogEntry: {entry_id}")
            return (200, {"Message": f"Entry {entry_id} deleted successfully."})
            
        except Exception as e:
            logger.error(f"Failed to delete entry {entry_id}: {e}")
            return (500, {"error": str(e)})
    
    def _update_collection(self, entry_id: str):
        """Update LogEntry collection to include new entry"""
        collection_file = self.entries_fs_path / "index.json"
        
        # Read existing collection or create new
        if collection_file.exists():
            with open(collection_file, 'r') as f:
                collection = json.load(f)
        else:
            collection = {
                "@odata.type": "#LogEntryCollection.LogEntryCollection",
                "@odata.id": self.entries_path,
                "Name": "CPER Log Entries",
                "Members": []
            }
        
        # Add new member if not already present
        new_member = {"@odata.id": f"{self.entries_path}/{entry_id}"}
        if new_member not in collection.get("Members", []):
            collection["Members"].append(new_member)
            collection["Members@odata.count"] = len(collection["Members"])
        
        # Save updated collection
        with open(collection_file, 'w') as f:
            json.dump(collection, f, indent=2)
    
    def _apply_filters(self, collection: Dict[str, Any], 
                      filter_params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply filter parameters to collection"""
        # This is a simplified filter implementation
        # In production, would support OData query parameters
        
        filtered_members = collection.get("Members", [])
        
        # Filter by severity if provided
        if "severity" in filter_params:
            severity = filter_params["severity"]
            filtered_members = [
                m for m in filtered_members
                if self._check_severity(m["@odata.id"], severity)
            ]
        
        collection["Members"] = filtered_members
        collection["Members@odata.count"] = len(filtered_members)
        
        return collection
    
    def _check_severity(self, entry_uri: str, severity: str) -> bool:
        """Check if entry matches severity filter"""
        # Extract entry ID from URI
        entry_id = entry_uri.split("/")[-1]
        
        # Read entry and check severity
        status, entry = self.get_log_entry(entry_id)
        if status == 200 and entry:
            return entry.get("Severity") == severity
        
        return False
    
    def handle_get(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """
        Handle GET requests to CPER LogService paths.
        
        Args:
            path: Request path
            
        Returns:
            tuple: (status, response)
        """
        if path.endswith("/LogServices/CPER"):
            # Return LogService resource
            log_service_file = self.log_service_fs_path / "index.json"
            if log_service_file.exists():
                with open(log_service_file, 'r') as f:
                    return (200, json.load(f))
            return (404, {"error": "LogService not found"})
        
        elif path.endswith("/LogServices/CPER/Entries"):
            # Return collection
            return self.get_log_entries()
        
        elif "/LogServices/CPER/Entries/" in path:
            # Get specific entry or attachment
            parts = path.split("/")
            entry_id = parts[-1] if not path.endswith("/Attachment") else parts[-2]
            
            if path.endswith("/Attachment"):
                status, data = self.get_attachment(entry_id)
                if status == 200:
                    # Return the raw CPER bytes; the transport layer sends them
                    # as application/octet-stream.  The attachment is binary
                    # (CPER signature + register dumps) and must not be decoded
                    # as UTF-8.
                    return (status, data)
                return (status, {"error": "Attachment not found"})
            else:
                return self.get_log_entry(entry_id)
        
        return (404, {"error": "Resource not found"})
    
    def handle_post(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """
        Handle POST requests (ClearLog action).
        
        Args:
            path: Request path
            data: Request body
            
        Returns:
            tuple: (status, response)
        """
        if path.endswith("/Actions/LogService.ClearLog"):
            return self.clear_logs()
        
        return (404, {"error": "Action not found"})
    
    def handle_delete(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """
        Handle DELETE requests (individual entry deletion per §4.8).
        
        Args:
            path: Request path
            
        Returns:
            tuple: (status, response)
        """
        if "/LogServices/CPER/Entries/" in path:
            entry_id = path.split("/")[-1]
            return self.delete_entry(entry_id)
        
        return (405, {"error": "DELETE not supported on this resource"})
