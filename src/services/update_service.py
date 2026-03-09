#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Update Service Handler Implementation

Handles UpdateService-specific operations including:
- Firmware updates with multipart support
- Simple update actions
- Update progress tracking
- File upload handling
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional


class UpdateServiceHandler:
    """Handler for UpdateService operations"""
    
    def __init__(self, config):
        """Initialize UpdateService handler"""
        self.config = config
        self.logger = logging.getLogger("UpdateService")
        self.update_sessions = {}  # Track update sessions
        
    def handle_update_service_post(self, path: str, data_received: Dict[str, Any], 
                                  multipart_data: bool = False, uploaded_files: Dict[str, str] = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle UpdateService POST requests"""
        
        if "UpdateService/Actions/UpdateService.SimpleUpdate" in path:
            return self._handle_simple_update(data_received)
        elif "UpdateService/FirmwareInventory" in path:
            return self._handle_firmware_inventory_create(data_received)
        elif "UpdateService" in path and multipart_data:
            return self._handle_multipart_update(data_received, uploaded_files)
        elif "UpdateService" in path:
            return self._handle_generic_update(data_received)
        else:
            return 404, {}, {"error": "UpdateService action not found"}
    
    def _handle_simple_update(self, data_received: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle SimpleUpdate action"""
        image_uri = data_received.get('ImageURI')
        targets = data_received.get('Targets', [])
        transfer_protocol = data_received.get('TransferProtocol', 'HTTP')
        
        if not image_uri:
            return 400, {}, {
                'error': {
                    'code': 'Base.1.4.ActionParameterMissing',
                    'message': 'The action SimpleUpdate requires ImageURI parameter.'
                }
            }
        
        # Create update task
        task_id = str(uuid.uuid4())
        update_response = {
            '@odata.type': '#Task.v1_4_3.Task',
            'Id': task_id,
            'Name': 'Simple Update Task',
            'TaskState': 'Running',
            'StartTime': datetime.now(timezone.utc).isoformat(),
            'TaskStatus': 'OK',
            'Messages': [],
            'Payload': {
                'ImageURI': image_uri,
                'Targets': targets,
                'TransferProtocol': transfer_protocol
            }
        }
        
        # Store task for tracking
        self.update_sessions[task_id] = update_response
        
        return 202, {'Location': f'/redfish/v1/TaskService/Tasks/{task_id}'}, update_response
    
    def _handle_firmware_inventory_create(self, data_received: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle creation of firmware inventory entry"""
        
        required_fields = ['Name', 'Version']
        for field in required_fields:
            if field not in data_received:
                return 400, {}, {
                    'error': {
                        'code': 'Base.1.4.PropertyMissing',
                        'message': f'The property {field} is required.'
                    }
                }
        
        # Create firmware inventory entry
        firmware_id = data_received.get('Id', str(uuid.uuid4()))
        firmware_entry = {
            '@odata.type': '#SoftwareInventory.v1_1_0.SoftwareInventory',
            '@odata.id': f'/redfish/v1/UpdateService/FirmwareInventory/{firmware_id}',
            'Id': firmware_id,
            'Name': data_received['Name'],
            'Version': data_received['Version'],
            'Description': data_received.get('Description', 'Firmware component'),
            'Status': {
                'State': 'Enabled',
                'Health': 'OK'
            },
            'Updateable': data_received.get('Updateable', True),
            'SoftwareId': data_received.get('SoftwareId', firmware_id),
            'LowestSupportedVersion': data_received.get('LowestSupportedVersion'),
            'Manufacturer': data_received.get('Manufacturer'),
            'ReleaseDate': data_received.get('ReleaseDate')
        }
        
        return 201, {'Location': firmware_entry['@odata.id']}, firmware_entry
    
    def _handle_multipart_update(self, data_received: Dict[str, Any], 
                                uploaded_files: Dict[str, str]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle multipart firmware update"""
        
        self.logger.info("Processing multipart update request")
        self.logger.info(f"JSON data: {data_received}")
        self.logger.info(f"Uploaded files: {uploaded_files}")
        
        # Validate uploaded files
        if not uploaded_files:
            return 400, {}, {
                'error': {
                    'code': 'Base.1.4.ActionParameterMissing',
                    'message': 'Firmware file is required for multipart update.'
                }
            }
        
        # Create update task
        task_id = str(uuid.uuid4())
        update_response = {
            '@odata.type': '#Task.v1_4_3.Task',
            'Id': task_id,
            'Name': 'Multipart Update Task',
            'TaskState': 'Running',
            'StartTime': datetime.now(timezone.utc).isoformat(),
            'TaskStatus': 'OK',
            'Messages': [{
                'MessageId': 'Update.1.0.FirmwareUpdateStarted',
                'Message': 'Firmware update started successfully.',
                'Severity': 'OK'
            }],
            'Payload': {
                'UpdateParameters': data_received,
                'UploadedFiles': list(uploaded_files.keys())
            }
        }
        
        # Store task for tracking
        self.update_sessions[task_id] = update_response
        
        return 202, {'Location': f'/redfish/v1/TaskService/Tasks/{task_id}'}, update_response
    
    def _handle_generic_update(self, data_received: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle generic UpdateService actions"""
        
        self.logger.info("Update Service processing ...")
        
        # Create generic update response
        update_response = {
            '@odata.type': '#Message.v1_0_8.Message',
            'MessageId': 'Update.1.0.OperationStarted',
            'Message': 'The update operation has been started.',
            'MessageArgs': [],
            'Severity': 'OK',
            'Resolution': 'Check the task monitor for update progress.'
        }
        
        return 202, {}, update_response
    
    def get_update_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get update task by ID"""
        return self.update_sessions.get(task_id)
    
    def update_task_status(self, task_id: str, status: str, state: str = None, 
                          message: str = None) -> bool:
        """Update task status"""
        if task_id not in self.update_sessions:
            return False
        
        task = self.update_sessions[task_id]
        task['TaskStatus'] = status
        
        if state:
            task['TaskState'] = state
        
        if message:
            task['Messages'].append({
                'MessageId': 'Update.1.0.StatusUpdate',
                'Message': message,
                'Severity': 'OK',
                'Created': datetime.now(timezone.utc).isoformat()
            })
        
        if state in ['Completed', 'Exception', 'Killed', 'Cancelled']:
            task['EndTime'] = datetime.now(timezone.utc).isoformat()
        
        return True
    
    def list_update_tasks(self) -> Dict[str, Dict[str, Any]]:
        """List all update tasks"""
        return self.update_sessions.copy()