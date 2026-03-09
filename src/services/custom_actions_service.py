#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Custom Actions Service for BMC Redfish Simulator
================================================
Demonstrates how to create new Action handlers that integrate with the mockup tree.

This service shows how to:
1. Define action handlers for custom actions
2. Validate action parameters 
3. Perform action logic
4. Update mockup tree resources
5. Generate appropriate responses
6. Trigger EventService notifications
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from ..utils.file_utils import construct_path, get_cached_link

logger = logging.getLogger(__name__)


class CustomActionsService:
    """Service for handling custom Redfish actions"""
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.logger = logging.getLogger("CustomActions")
        
        # Register action handlers
        self.action_handlers = {
            # System Actions
            'ComputerSystem.Reset': self._handle_system_reset,
            'ComputerSystem.SetDefaultBootOrder': self._handle_set_boot_order,
            
            # Chassis Actions  
            'Chassis.Reset': self._handle_chassis_reset,
            
            # Manager Actions
            'Manager.Reset': self._handle_manager_reset,
            'Manager.ForceFailover': self._handle_manager_failover,
            
            # Custom Service Actions
            'TestService.Reset': self._handle_test_service_reset,
            'TestService.RunDiagnostic': self._handle_run_diagnostic,
            'TestService.UpdateFirmware': self._handle_firmware_update,
            
            # Battery Actions
            'Battery.SelfTest': self._handle_battery_self_test,
            'Battery.Calibrate': self._handle_battery_calibrate,
            
            # Custom OEM Actions
            'Oem.CustomDiagnostic': self._handle_custom_diagnostic,
            'Oem.ConfigureSettings': self._handle_configure_settings,
        }
    
    def handle_action(self, path: str, data_received: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """
        Main action handler that routes to specific action implementations
        
        :param path: Action path (e.g., '/redfish/v1/Systems/System1/Actions/ComputerSystem.Reset')
        :param data_received: Action parameters from POST body
        :param cached_links: Cache of loaded JSON resources
        :return: (status_code, headers, response_data)
        """
        try:
            # Parse action from path
            action_name = self._extract_action_name(path)
            if not action_name:
                return 404, {}, {"error": "Invalid action path"}
            
            # Check if we have a handler for this action
            if action_name not in self.action_handlers:
                return 404, {}, {"error": f"Action {action_name} not supported"}
            
            # Get the resource that owns this action
            resource_path = self._get_resource_path_from_action(path)
            resource_data = self._get_resource_data(resource_path, cached_links)
            
            if not resource_data:
                return 404, {}, {"error": "Resource not found"}
            
            # Validate that this action is supported by the resource
            if not self._validate_action_supported(resource_data, action_name, path):
                return 404, {}, {"error": f"Action {action_name} not supported by this resource"}
            
            # Call the specific action handler
            handler = self.action_handlers[action_name]
            return handler(path, resource_path, data_received, resource_data, cached_links)
            
        except Exception as e:
            self.logger.error(f"Error handling action {path}: {e}")
            return 500, {}, {"error": str(e)}
    
    def _extract_action_name(self, path: str) -> Optional[str]:
        """Extract action name from action path"""
        if '/Actions/' not in path:
            return None
        
        # Extract action name (e.g., 'ComputerSystem.Reset' from '/Actions/ComputerSystem.Reset')
        action_part = path.split('/Actions/')[-1]
        return action_part.split('?')[0]  # Remove query parameters
    
    def _get_resource_path_from_action(self, action_path: str) -> str:
        """Get resource path from action path"""
        # Remove '/Actions/...' part to get resource path
        return action_path.split('/Actions/')[0]
    
    def _get_resource_data(self, resource_path: str, cached_links: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get resource data from cache or file"""
        fpath = construct_path(
            self.server_config.mock_dir,
            resource_path,
            'index.json',
            self.server_config.short_form
        )
        
        success, data = get_cached_link(cached_links, fpath)
        return data if success else None
    
    def _validate_action_supported(self, resource_data: Dict[str, Any], action_name: str, action_path: str) -> bool:
        """Validate that the resource supports this action"""
        actions = resource_data.get('Actions', {})
        
        # Check if action is defined in the resource
        action_key = f"#{action_name}"
        if action_key in actions:
            target = actions[action_key].get('target', '')
            return action_path in target
        
        return False
    
    def _update_resource_data(self, resource_path: str, updated_data: Dict[str, Any], cached_links: Dict[str, Any]) -> bool:
        """Update resource data in mockup tree and cache"""
        try:
            fpath = construct_path(
                self.server_config.mock_dir,
                resource_path,
                'index.json',
                self.server_config.short_form
            )
            
            # Write to file
            with open(fpath, 'w') as f:
                json.dump(updated_data, f, indent=4, separators=(',', ': '))
            
            # Update cache
            cached_links[fpath] = updated_data
            
            return True
        except Exception as e:
            self.logger.error(f"Error updating resource {resource_path}: {e}")
            return False
    
    def _trigger_action_event(self, action_name: str, resource_path: str, parameters: Dict[str, Any], result: str):
        """Trigger EventService notification for action completion"""
        try:
            from .event_service import EventServiceHandler
            event_service = EventServiceHandler(self.server_config)
            
            event_data = {
                "EventType": "ActionCompleted",
                "EventId": f"Action.{action_name}.{int(time.time())}",
                "EventTimestamp": datetime.utcnow().isoformat() + 'Z',
                "Severity": "OK" if result == "Success" else "Warning",
                "Message": f"Action {action_name} completed with result: {result}",
                "MessageId": "Action.1.0.ActionCompleted",
                "MessageArgs": [action_name, result],
                "OriginOfCondition": {"@odata.id": resource_path}
            }
            
            # Submit event
            event_service.handle_eventing(
                "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent",
                event_data,
                {}
            )
            
        except Exception as e:
            self.logger.error(f"Error triggering action event: {e}")
    
    # =============================================================================
    # SPECIFIC ACTION HANDLERS
    # =============================================================================
    
    def _handle_system_reset(self, action_path: str, resource_path: str, data_received: Dict[str, Any], 
                           resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle ComputerSystem.Reset action"""
        reset_type = data_received.get('ResetType', 'GracefulRestart')
        
        # Validate ResetType
        valid_reset_types = ['On', 'ForceOff', 'GracefulShutdown', 'GracefulRestart', 'ForceRestart', 'PowerCycle']
        if reset_type not in valid_reset_types:
            return 400, {}, {
                "error": f"Invalid ResetType: {reset_type}",
                "validValues": valid_reset_types
            }
        
        # Update system PowerState
        if reset_type in ['On']:
            resource_data['PowerState'] = 'On'
        elif reset_type in ['ForceOff', 'GracefulShutdown']:
            resource_data['PowerState'] = 'Off'
        else:
            resource_data['PowerState'] = 'On'  # After restart
        
        # Update LastResetTime if present
        if 'LastResetTime' in resource_data:
            resource_data['LastResetTime'] = datetime.utcnow().isoformat() + 'Z'
        
        # Save updated resource
        self._update_resource_data(resource_path, resource_data, cached_links)
        
        # Trigger event
        self._trigger_action_event('ComputerSystem.Reset', resource_path, data_received, 'Success')
        
        return 204, {}, {}  # No content response for successful action
    
    def _handle_test_service_reset(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                                 resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle TestService.Reset action"""
        reset_type = data_received.get('ResetType', 'GracefulRestart')
        
        # Update resource status
        resource_data['Status'] = {
            "State": "Enabled",
            "Health": "OK",
            "HealthRollup": "OK"
        }
        
        # Add reset information
        resource_data['LastResetType'] = reset_type
        resource_data['LastResetTime'] = datetime.utcnow().isoformat() + 'Z'
        
        # Save updated resource
        self._update_resource_data(resource_path, resource_data, cached_links)
        
        # Trigger event
        self._trigger_action_event('TestService.Reset', resource_path, data_received, 'Success')
        
        return 200, {}, {
            "ResetType": reset_type,
            "CompletedTime": resource_data['LastResetTime'],
            "Status": "Success"
        }
    
    def _handle_run_diagnostic(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                             resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle TestService.RunDiagnostic action"""
        diagnostic_type = data_received.get('DiagnosticType', 'Full')
        timeout = data_received.get('Timeout', 300)
        
        # Validate parameters
        if diagnostic_type not in ['Quick', 'Extended', 'Full']:
            return 400, {}, {"error": "Invalid DiagnosticType"}
        
        if not isinstance(timeout, int) or timeout < 1 or timeout > 3600:
            return 400, {}, {"error": "Timeout must be between 1 and 3600 seconds"}
        
        # Simulate diagnostic execution
        diagnostic_result = {
            "DiagnosticId": f"diag_{int(time.time())}",
            "DiagnosticType": diagnostic_type,
            "Status": "Completed",
            "StartTime": datetime.utcnow().isoformat() + 'Z',
            "Duration": "PT30S",  # 30 seconds
            "Results": {
                "Overall": "Pass",
                "Tests": [
                    {"Name": "CPU Test", "Result": "Pass"},
                    {"Name": "Memory Test", "Result": "Pass"},
                    {"Name": "Storage Test", "Result": "Pass"}
                ]
            }
        }
        
        # Add diagnostic result to resource
        if 'DiagnosticResults' not in resource_data:
            resource_data['DiagnosticResults'] = []
        
        resource_data['DiagnosticResults'].append(diagnostic_result)
        
        # Keep only last 10 results
        if len(resource_data['DiagnosticResults']) > 10:
            resource_data['DiagnosticResults'] = resource_data['DiagnosticResults'][-10:]
        
        # Save updated resource
        self._update_resource_data(resource_path, resource_data, cached_links)
        
        # Trigger event
        self._trigger_action_event('TestService.RunDiagnostic', resource_path, data_received, 'Success')
        
        return 200, {}, diagnostic_result
    
    def _handle_battery_self_test(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                                resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle Battery.SelfTest action"""
        
        # Update battery test status
        test_result = {
            "TestType": "SelfTest",
            "TestId": f"test_{int(time.time())}",
            "StartTime": datetime.utcnow().isoformat() + 'Z',
            "Status": "Completed",
            "Result": "Pass",
            "Details": {
                "ChargeLevel": 98,
                "Voltage": "12.1V",
                "Temperature": "25°C",
                "CycleCount": 42
            }
        }
        
        # Add test result to battery resource
        if 'TestResults' not in resource_data:
            resource_data['TestResults'] = []
        
        resource_data['TestResults'].append(test_result)
        
        # Update battery status
        resource_data['Status']['Health'] = 'OK'
        resource_data['LastTestTime'] = test_result['StartTime']
        
        # Save updated resource
        self._update_resource_data(resource_path, resource_data, cached_links)
        
        # Trigger event  
        self._trigger_action_event('Battery.SelfTest', resource_path, data_received, 'Pass')
        
        return 200, {}, test_result
    
    def _handle_custom_diagnostic(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                                resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle custom OEM diagnostic action"""
        
        # Custom validation
        required_params = ['TargetComponent', 'TestLevel']
        missing = [p for p in required_params if p not in data_received]
        if missing:
            return 400, {}, {"error": f"Missing required parameters: {missing}"}
        
        target_component = data_received['TargetComponent']
        test_level = data_received['TestLevel']
        
        # Perform custom diagnostic logic
        diagnostic_result = {
            "DiagnosticId": f"oem_diag_{int(time.time())}",
            "TargetComponent": target_component,
            "TestLevel": test_level,
            "Status": "Completed",
            "StartTime": datetime.utcnow().isoformat() + 'Z',
            "Result": "Pass",
            "OemData": {
                "Vendor": "CustomOEM",
                "ComponentHealth": "Excellent",
                "Recommendations": []
            }
        }
        
        # Save result
        if 'OemDiagnostics' not in resource_data:
            resource_data['OemDiagnostics'] = []
        
        resource_data['OemDiagnostics'].append(diagnostic_result)
        self._update_resource_data(resource_path, resource_data, cached_links)
        
        # Trigger event
        self._trigger_action_event('Oem.CustomDiagnostic', resource_path, data_received, 'Pass')
        
        return 200, {}, diagnostic_result
    
    # Additional action handlers can be added here following the same pattern
    def _handle_set_boot_order(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                              resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle ComputerSystem.SetDefaultBootOrder action"""
        return 501, {}, {"error": "SetDefaultBootOrder not yet implemented"}
    
    def _handle_chassis_reset(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                            resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle Chassis.Reset action"""
        return 501, {}, {"error": "Chassis.Reset not yet implemented"}
    
    def _handle_manager_reset(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                            resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle Manager.Reset action"""
        return 501, {}, {"error": "Manager.Reset not yet implemented"}
    
    def _handle_manager_failover(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                                resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle Manager.ForceFailover action"""
        return 501, {}, {"error": "Manager.ForceFailover not yet implemented"}
    
    def _handle_firmware_update(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                              resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle TestService.UpdateFirmware action"""
        return 501, {}, {"error": "UpdateFirmware not yet implemented"}
    
    def _handle_battery_calibrate(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                                resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle Battery.Calibrate action"""
        return 501, {}, {"error": "Battery.Calibrate not yet implemented"}
    
    def _handle_configure_settings(self, action_path: str, resource_path: str, data_received: Dict[str, Any],
                                 resource_data: Dict[str, Any], cached_links: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle Oem.ConfigureSettings action"""
        return 501, {}, {"error": "ConfigureSettings not yet implemented"}