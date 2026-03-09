#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
LogEntry Service for BMC Redfish Simulator
==========================================
Handles POST/PATCH operations for LogEntry resources and triggers EventService notifications.
"""

import os
import json
import logging
import threading
from datetime import datetime
from ..utils.file_utils import construct_path, get_cached_link
from .event_service import EventServiceHandler

logger = logging.getLogger(__name__)


class LogEntryService:
    """Service to handle LogEntry creation, modification, and event notification"""
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.event_service = EventServiceHandler(server_config)
        self.log_entry_counter = {}  # Track log entry IDs per service
        
    def handle_post_log_entry(self, path, data_received, cached_links):
        """
        Handle POST request to create a new LogEntry
        
        :param path: Request path (e.g., /redfish/v1/Managers/BMC/LogServices/Log/Entries)
        :param data_received: JSON data from POST request
        :param cached_links: Cache of loaded JSON files
        :return: HTTP status code and response data
        """
        try:
            # Validate this is a LogEntries collection
            if not path.endswith('/Entries'):
                return 404, {"error": "Not a LogEntries collection"}
            
            # Get the collection data
            fpath = construct_path(
                self.server_config.mock_dir,
                path,
                'index.json',
                self.server_config.short_form
            )
            
            success, collection_payload = get_cached_link(cached_links, fpath)
            if not success:
                return 404, {"error": "LogEntries collection not found"}
            
            # Validate required fields
            required_fields = ['Message', 'Severity']
            missing_fields = [field for field in required_fields if field not in data_received]
            if missing_fields:
                return 400, {"error": f"Missing required fields: {missing_fields}"}
            
            # Generate new log entry
            log_entry = self._create_log_entry(path, data_received, collection_payload)
            
            # Save log entry to mockup tree
            entry_path = log_entry['@odata.id']
            entry_fpath = construct_path(
                self.server_config.mock_dir,
                entry_path,
                'index.json',
                self.server_config.short_form
            )
            
            # Create directory structure
            os.makedirs(os.path.dirname(entry_fpath), exist_ok=True)
            
            # Write log entry file
            with open(entry_fpath, 'w') as f:
                json.dump(log_entry, f, indent=4, separators=(',', ': '))
            
            # Update collection
            collection_payload['Members'].append({
                "@odata.id": entry_path
            })
            collection_payload['Members@odata.count'] = len(collection_payload['Members'])
            
            # Save updated collection
            with open(fpath, 'w') as f:
                json.dump(collection_payload, f, indent=4, separators=(',', ': '))
            
            # Update cache
            cached_links[fpath] = collection_payload
            cached_links[entry_fpath] = log_entry
            
            # Trigger event notification
            self._trigger_log_entry_event(log_entry, cached_links)
            
            logger.info(f"Created new LogEntry: {entry_path}")
            
            return 201, {
                "Created": entry_path,
                "LogEntry": log_entry
            }
            
        except Exception as e:
            logger.error(f"Error creating LogEntry: {e}")
            return 500, {"error": str(e)}
    
    def handle_patch_log_entry(self, path, data_received, cached_links):
        """
        Handle PATCH request to modify an existing LogEntry
        
        :param path: Request path (e.g., /redfish/v1/Managers/BMC/LogServices/Log/Entries/1)
        :param data_received: JSON data from PATCH request  
        :param cached_links: Cache of loaded JSON files
        :return: HTTP status code and response data
        """
        try:
            # Get existing log entry
            fpath = construct_path(
                self.server_config.mock_dir,
                path,
                'index.json',
                self.server_config.short_form
            )
            
            success, log_entry = get_cached_link(cached_links, fpath)
            if not success:
                return 404, {"error": "LogEntry not found"}
            
            # Store original values for event
            original_entry = log_entry.copy()
            
            # Apply PATCH updates (only allow certain fields to be modified)
            modifiable_fields = ['Message', 'Severity', 'Resolution', 'Resolved']
            updated_fields = []
            
            for field in modifiable_fields:
                if field in data_received:
                    if log_entry.get(field) != data_received[field]:
                        log_entry[field] = data_received[field]
                        updated_fields.append(field)
            
            if not updated_fields:
                return 200, {"message": "No changes made"}
            
            # Update Modified timestamp
            log_entry['Modified'] = datetime.utcnow().isoformat() + 'Z'
            
            # Save updated log entry
            with open(fpath, 'w') as f:
                json.dump(log_entry, f, indent=4, separators=(',', ': '))
            
            # Update cache
            cached_links[fpath] = log_entry
            
            # Trigger event notification for modification
            self._trigger_log_entry_modified_event(original_entry, log_entry, updated_fields, cached_links)
            
            logger.info(f"Updated LogEntry: {path}, fields: {updated_fields}")
            
            return 200, {
                "Updated": path,
                "ModifiedFields": updated_fields,
                "LogEntry": log_entry
            }
            
        except Exception as e:
            logger.error(f"Error updating LogEntry: {e}")
            return 500, {"error": str(e)}
    
    def _create_log_entry(self, collection_path, data_received, collection_payload):
        """Create a new LogEntry object"""
        # Generate unique ID
        service_path = collection_path.replace('/Entries', '')
        if service_path not in self.log_entry_counter:
            # Initialize counter based on existing entries
            self.log_entry_counter[service_path] = collection_payload.get('Members@odata.count', 0)
        
        self.log_entry_counter[service_path] += 1
        entry_id = str(self.log_entry_counter[service_path])
        
        # Create log entry
        log_entry = {
            "@odata.context": "/redfish/v1/$metadata#LogEntry.LogEntry",
            "@odata.type": "#LogEntry.v1_14_0.LogEntry",
            "@odata.id": f"{collection_path}/{entry_id}",
            "Id": entry_id,
            "Name": f"Log Entry {entry_id}",
            "Created": datetime.utcnow().isoformat() + 'Z',
            "EntryType": data_received.get("EntryType", "Event"),
            "Message": data_received["Message"],
            "Severity": data_received["Severity"]
        }
        
        # Optional fields
        optional_fields = [
            "MessageId", "MessageArgs", "Resolution", "Resolved",
            "SensorNumber", "SensorType", "AdditionalDataURI"
        ]
        
        for field in optional_fields:
            if field in data_received:
                log_entry[field] = data_received[field]
        
        # Handle Links
        if "OriginOfCondition" in data_received:
            log_entry["Links"] = {
                "OriginOfCondition": {"@odata.id": data_received["OriginOfCondition"]},
                "Oem": {}
            }
        
        log_entry["Oem"] = {}
        
        return log_entry
    
    def _trigger_log_entry_event(self, log_entry, cached_links):
        """Trigger EventService notification for new LogEntry"""
        try:
            event_data = {
                "EventType": "Alert",
                "EventId": f"LogEntry.Created.{log_entry['Id']}",
                "EventTimestamp": log_entry['Created'],
                "Severity": log_entry['Severity'],
                "Message": f"New log entry created: {log_entry['Message']}",
                "MessageId": "LogEntry.1.0.LogEntryCreated",
                "MessageArgs": [log_entry['Id'], log_entry['Message']],
                "OriginOfCondition": {
                    "@odata.id": log_entry["@odata.id"]
                }
            }
            
            # Submit event
            self.event_service.handle_eventing(
                "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent",
                event_data,
                cached_links
            )
            
        except Exception as e:
            logger.error(f"Error triggering LogEntry creation event: {e}")
    
    def _trigger_log_entry_modified_event(self, original_entry, updated_entry, updated_fields, cached_links):
        """Trigger EventService notification for modified LogEntry"""
        try:
            event_data = {
                "EventType": "ResourceUpdated", 
                "EventId": f"LogEntry.Modified.{updated_entry['Id']}",
                "EventTimestamp": updated_entry.get('Modified', datetime.utcnow().isoformat() + 'Z'),
                "Severity": updated_entry['Severity'],
                "Message": f"Log entry modified: {', '.join(updated_fields)}",
                "MessageId": "LogEntry.1.0.LogEntryModified", 
                "MessageArgs": [updated_entry['Id'], ', '.join(updated_fields)],
                "OriginOfCondition": {
                    "@odata.id": updated_entry["@odata.id"]
                }
            }
            
            # Submit event
            self.event_service.handle_eventing(
                "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent",
                event_data, 
                cached_links
            )
            
        except Exception as e:
            logger.error(f"Error triggering LogEntry modification event: {e}")