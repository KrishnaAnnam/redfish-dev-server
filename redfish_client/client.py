#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Client for BMC Simulator
================================

A comprehensive Redfish client library for interacting with the BMC Simulator.
Provides authentication, resource management, event handling, and utilities
for Redfish client development.

Usage:
    client = RedfishClient("https://bmc.example.com")
    client.login("admin", "password")
    systems = client.get_systems()
    client.logout()
"""

import json
import time
import logging
import requests
import threading
from typing import Dict, List, Optional, Any, Callable
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# Disable SSL warnings for development
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RedfishClientError(Exception):
    """Base exception for Redfish client errors"""
    pass

class AuthenticationError(RedfishClientError):
    """Authentication related errors"""
    pass

class ResourceNotFoundError(RedfishClientError):
    """Resource not found errors"""
    pass

class OperationError(RedfishClientError):
    """Operation execution errors"""
    pass

class SessionState(Enum):
    """Session state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"

@dataclass
class RedfishResource:
    """Represents a Redfish resource"""
    odata_id: str
    odata_type: str
    id: str
    name: str
    data: Dict[str, Any]
    
    @property
    def resource_type(self) -> str:
        """Get the resource type from @odata.type"""
        return self.odata_type.split('.')[-1].split('#')[-1]

@dataclass
class EventSubscription:
    """Represents an event subscription"""
    id: str
    destination: str
    context: str
    protocol: str
    event_types: List[str]
    subscription_type: str = "RedfishEvent"

class RedfishClient:
    """
    Comprehensive Redfish client for BMC interaction
    
    Features:
    - Session-based authentication
    - Resource discovery and management
    - Event subscription handling
    - Asynchronous operations
    - Error handling and retry logic
    - Logging and debugging support
    """
    
    def __init__(self, base_url: str, verify_ssl: bool = False, timeout: int = 30):
        """
        Initialize Redfish client
        
        Args:
            base_url: Base URL of the Redfish service (e.g., https://bmc.example.com)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        
        # Session management
        self.session = requests.Session()
        self.session_token = None
        self.session_location = None
        self.session_state = SessionState.DISCONNECTED
        self.session_expiry = None
        
        # Service root information
        self.service_root = None
        self.redfish_version = None
        self.vendor = None
        self.product = None
        
        # Event handling
        self.event_subscriptions: Dict[str, EventSubscription] = {}
        self.event_callbacks: List[Callable] = []
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        
        # Setup session defaults
        self.session.verify = verify_ssl
        self.session.timeout = timeout
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'RedFish-Client/1.0'
        })
    
    def connect(self) -> bool:
        """
        Connect to the Redfish service and retrieve service root
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.session_state = SessionState.CONNECTING
            self.logger.info(f"Connecting to Redfish service at {self.base_url}")
            
            # Get service root
            response = self._request('GET', '/redfish/v1/')
            if response.status_code != 200:
                raise RedfishClientError(f"Failed to get service root: {response.status_code}")
            
            self.service_root = response.json()
            self.redfish_version = self.service_root.get('RedfishVersion', 'Unknown')
            
            # Extract vendor/product information if available
            oem = self.service_root.get('Oem', {})
            self.vendor = oem.get('Vendor', 'Unknown')
            self.product = oem.get('Product', 'Unknown')
            
            self.session_state = SessionState.DISCONNECTED
            self.logger.info(f"Connected to {self.vendor} {self.product} (Redfish {self.redfish_version})")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.session_state = SessionState.DISCONNECTED
            return False
    
    def login(self, username: str, password: str) -> bool:
        """
        Authenticate with the Redfish service using session-based auth
        
        Args:
            username: Username for authentication
            password: Password for authentication
            
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            if not self.service_root:
                if not self.connect():
                    return False
            
            self.logger.info(f"Authenticating user: {username}")
            
            # Get session service endpoint
            session_service = self.service_root.get('SessionService', {})
            sessions_url = session_service.get('Sessions', {}).get('@odata.id')
            
            if not sessions_url:
                # Fallback to basic auth
                self.session.auth = (username, password)
                self.session_state = SessionState.AUTHENTICATED
                self.logger.info("Using basic authentication")
                return True
            
            # Create session
            session_data = {
                "UserName": username,
                "Password": password
            }
            
            response = self._request('POST', sessions_url, json=session_data)
            
            if response.status_code in [200, 201]:
                # Extract session token and location
                self.session_token = response.headers.get('X-Auth-Token')
                self.session_location = response.headers.get('Location')
                
                if self.session_token:
                    self.session.headers['X-Auth-Token'] = self.session_token
                
                # Calculate session expiry (default 30 minutes)
                session_timeout = session_service.get('SessionTimeout', 1800)
                self.session_expiry = datetime.now() + timedelta(seconds=session_timeout)
                
                self.session_state = SessionState.AUTHENTICATED
                self.logger.info("Authentication successful (session-based)")
                return True
            else:
                raise AuthenticationError(f"Authentication failed: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            self.session_state = SessionState.DISCONNECTED
            return False
    
    def logout(self) -> bool:
        """
        Logout and cleanup session
        
        Returns:
            True if logout successful, False otherwise
        """
        try:
            if self.session_location and self.session_state == SessionState.AUTHENTICATED:
                # Delete session
                response = self._request('DELETE', self.session_location)
                if response.status_code in [200, 204]:
                    self.logger.info("Session deleted successfully")
                else:
                    self.logger.warning(f"Session deletion returned: {response.status_code}")
            
            # Cleanup
            self.session_token = None
            self.session_location = None
            self.session_expiry = None
            self.session_state = SessionState.DISCONNECTED
            
            if 'X-Auth-Token' in self.session.headers:
                del self.session.headers['X-Auth-Token']
            
            self.session.auth = None
            
            return True
            
        except Exception as e:
            self.logger.error(f"Logout failed: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if client is authenticated and session is valid"""
        if self.session_state != SessionState.AUTHENTICATED:
            return False
        
        if self.session_expiry and datetime.now() > self.session_expiry:
            self.session_state = SessionState.EXPIRED
            return False
        
        return True
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with proper URL handling and error checking
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            url: URL path or full URL
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
        """
        # Handle both relative and absolute URLs
        if url.startswith(('http://', 'https://')):
            full_url = url
        else:
            full_url = urljoin(self.base_url, url.lstrip('/'))
        
        self.logger.debug(f"{method} {full_url}")
        
        try:
            response = self.session.request(method, full_url, **kwargs)
            
            # Log response details
            self.logger.debug(f"Response: {response.status_code}")
            if response.headers.get('content-type', '').startswith('application/json'):
                self.logger.debug(f"Body: {response.text[:500]}")
            
            return response
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            raise RedfishClientError(f"Request failed: {e}")
    
    def get_resource(self, url: str) -> RedfishResource:
        """
        Get a Redfish resource by URL
        
        Args:
            url: Resource URL (relative or absolute)
            
        Returns:
            RedfishResource object
        """
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")
        
        response = self._request('GET', url)
        
        if response.status_code == 404:
            raise ResourceNotFoundError(f"Resource not found: {url}")
        elif response.status_code != 200:
            raise OperationError(f"Failed to get resource: {response.status_code}")
        
        data = response.json()
        
        return RedfishResource(
            odata_id=data.get('@odata.id', url),
            odata_type=data.get('@odata.type', ''),
            id=data.get('Id', ''),
            name=data.get('Name', ''),
            data=data
        )
    
    def get_collection(self, url: str) -> List[RedfishResource]:
        """
        Get all members of a Redfish collection
        
        Args:
            url: Collection URL
            
        Returns:
            List of RedfishResource objects
        """
        collection = self.get_resource(url)
        members = collection.data.get('Members', [])
        
        resources = []
        for member in members:
            member_url = member.get('@odata.id')
            if member_url:
                try:
                    resource = self.get_resource(member_url)
                    resources.append(resource)
                except Exception as e:
                    self.logger.warning(f"Failed to get member {member_url}: {e}")
        
        return resources
    
    def create_resource(self, collection_url: str, resource_data: Dict[str, Any]) -> RedfishResource:
        """
        Create a new resource in a collection
        
        Args:
            collection_url: Collection URL to create resource in
            resource_data: Resource data to create
            
        Returns:
            Created RedfishResource object
        """
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")
        
        response = self._request('POST', collection_url, json=resource_data)
        
        if response.status_code not in [200, 201]:
            raise OperationError(f"Failed to create resource: {response.status_code}")
        
        # Get location of created resource
        location = response.headers.get('Location')
        if location:
            return self.get_resource(location)
        else:
            # Return response data as resource
            data = response.json() if response.content else {}
            return RedfishResource(
                odata_id=data.get('@odata.id', collection_url),
                odata_type=data.get('@odata.type', ''),
                id=data.get('Id', ''),
                name=data.get('Name', ''),
                data=data
            )
    
    def update_resource(self, url: str, updates: Dict[str, Any]) -> RedfishResource:
        """
        Update a Redfish resource
        
        Args:
            url: Resource URL
            updates: Dictionary of properties to update
            
        Returns:
            Updated RedfishResource object
        """
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")
        
        response = self._request('PATCH', url, json=updates)
        
        if response.status_code not in [200, 202, 204]:
            raise OperationError(f"Failed to update resource: {response.status_code}")
        
        # Get updated resource
        return self.get_resource(url)
    
    def delete_resource(self, url: str) -> bool:
        """
        Delete a Redfish resource
        
        Args:
            url: Resource URL
            
        Returns:
            True if deletion successful
        """
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")
        
        response = self._request('DELETE', url)
        
        if response.status_code not in [200, 202, 204]:
            raise OperationError(f"Failed to delete resource: {response.status_code}")
        
        return True
    
    def invoke_action(self, action_url: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Invoke a Redfish action
        
        Args:
            action_url: Action URL
            parameters: Action parameters
            
        Returns:
            Action response data
        """
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")
        
        response = self._request('POST', action_url, json=parameters or {})
        
        if response.status_code not in [200, 202, 204]:
            raise OperationError(f"Action failed: {response.status_code}")
        
        return response.json() if response.content else {}
    
    # Convenience methods for common resources
    
    def get_systems(self) -> List[RedfishResource]:
        """Get all computer systems"""
        systems_url = self.service_root.get('Systems', {}).get('@odata.id')
        if systems_url:
            return self.get_collection(systems_url)
        return []
    
    def get_chassis(self) -> List[RedfishResource]:
        """Get all chassis"""
        chassis_url = self.service_root.get('Chassis', {}).get('@odata.id')
        if chassis_url:
            return self.get_collection(chassis_url)
        return []
    
    def get_managers(self) -> List[RedfishResource]:
        """Get all managers (BMCs)"""
        managers_url = self.service_root.get('Managers', {}).get('@odata.id')
        if managers_url:
            return self.get_collection(managers_url)
        return []
    
    def get_system_by_id(self, system_id: str) -> RedfishResource:
        """Get specific system by ID"""
        systems_url = self.service_root.get('Systems', {}).get('@odata.id')
        if systems_url:
            system_url = f"{systems_url.rstrip('/')}/{system_id}"
            return self.get_resource(system_url)
        raise ResourceNotFoundError(f"System {system_id} not found")
    
    def power_on_system(self, system_id: str) -> Dict[str, Any]:
        """Power on a system"""
        system = self.get_system_by_id(system_id)
        actions = system.data.get('Actions', {})
        reset_action = actions.get('#ComputerSystem.Reset', {})
        target = reset_action.get('target')
        
        if target:
            return self.invoke_action(target, {"ResetType": "On"})
        raise OperationError("Reset action not available")
    
    def power_off_system(self, system_id: str) -> Dict[str, Any]:
        """Power off a system"""
        system = self.get_system_by_id(system_id)
        actions = system.data.get('Actions', {})
        reset_action = actions.get('#ComputerSystem.Reset', {})
        target = reset_action.get('target')
        
        if target:
            return self.invoke_action(target, {"ResetType": "ForceOff"})
        raise OperationError("Reset action not available")
    
    def reboot_system(self, system_id: str) -> Dict[str, Any]:
        """Reboot a system"""
        system = self.get_system_by_id(system_id)
        actions = system.data.get('Actions', {})
        reset_action = actions.get('#ComputerSystem.Reset', {})
        target = reset_action.get('target')
        
        if target:
            return self.invoke_action(target, {"ResetType": "ForceRestart"})
        raise OperationError("Reset action not available")
    
    # Event subscription methods
    
    def create_event_subscription(self, destination: str, event_types: List[str] = None, 
                                context: str = None, protocol: str = "Redfish") -> EventSubscription:
        """
        Create an event subscription
        
        Args:
            destination: Event destination URL
            event_types: List of event types to subscribe to
            context: Client context string
            protocol: Protocol for event delivery
            
        Returns:
            EventSubscription object
        """
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")
        
        event_service = self.service_root.get('EventService', {})
        subscriptions_url = event_service.get('Subscriptions', {}).get('@odata.id')
        
        if not subscriptions_url:
            raise OperationError("Event subscriptions not supported")
        
        subscription_data = {
            "Destination": destination,
            "Protocol": protocol,
            "Context": context or f"Client-{int(time.time())}"
        }
        
        if event_types:
            subscription_data["EventTypes"] = event_types
        
        resource = self.create_resource(subscriptions_url, subscription_data)
        
        subscription = EventSubscription(
            id=resource.id,
            destination=destination,
            context=subscription_data["Context"],
            protocol=protocol,
            event_types=event_types or []
        )
        
        self.event_subscriptions[resource.id] = subscription
        return subscription
    
    def delete_event_subscription(self, subscription_id: str) -> bool:
        """Delete an event subscription"""
        event_service = self.service_root.get('EventService', {})
        subscriptions_url = event_service.get('Subscriptions', {}).get('@odata.id')
        
        if subscriptions_url:
            subscription_url = f"{subscriptions_url.rstrip('/')}/{subscription_id}"
            success = self.delete_resource(subscription_url)
            
            if success and subscription_id in self.event_subscriptions:
                del self.event_subscriptions[subscription_id]
            
            return success
        
        return False
    
    def get_event_subscriptions(self) -> List[EventSubscription]:
        """Get all event subscriptions"""
        event_service = self.service_root.get('EventService', {})
        subscriptions_url = event_service.get('Subscriptions', {}).get('@odata.id')
        
        if subscriptions_url:
            subscriptions = self.get_collection(subscriptions_url)
            result = []
            
            for sub in subscriptions:
                data = sub.data
                event_sub = EventSubscription(
                    id=sub.id,
                    destination=data.get('Destination', ''),
                    context=data.get('Context', ''),
                    protocol=data.get('Protocol', 'Redfish'),
                    event_types=data.get('EventTypes', [])
                )
                result.append(event_sub)
            
            return result
        
        return []
    
    def submit_test_event(self, event_type: str = "Alert", message: str = "Test event", 
                         severity: str = "OK") -> Dict[str, Any]:
        """Submit a test event"""
        event_service = self.service_root.get('EventService', {})
        actions = event_service.get('Actions', {})
        test_event_action = actions.get('#EventService.SubmitTestEvent', {})
        target = test_event_action.get('target')
        
        if target:
            parameters = {
                "EventType": event_type,
                "Message": message,
                "Severity": severity
            }
            return self.invoke_action(target, parameters)
        
        raise OperationError("SubmitTestEvent action not available")
    
    # Utility methods
    
    def wait_for_task(self, task_url: str, timeout: int = 300, poll_interval: int = 5) -> Dict[str, Any]:
        """
        Wait for a task to complete
        
        Args:
            task_url: Task URL to monitor
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
            
        Returns:
            Final task data
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            task = self.get_resource(task_url)
            state = task.data.get('TaskState', 'Unknown')
            
            if state in ['Completed', 'Exception', 'Killed', 'Cancelled']:
                return task.data
            
            time.sleep(poll_interval)
        
        raise OperationError(f"Task timeout after {timeout} seconds")
    
    def get_health_status(self) -> Dict[str, str]:
        """Get overall system health status"""
        health_status = {
            'systems': 'Unknown',
            'chassis': 'Unknown', 
            'managers': 'Unknown'
        }
        
        try:
            systems = self.get_systems()
            if systems:
                statuses = [s.data.get('Status', {}).get('Health', 'Unknown') for s in systems]
                health_status['systems'] = 'OK' if all(s == 'OK' for s in statuses) else 'Warning'
        except:
            pass
        
        try:
            chassis = self.get_chassis()
            if chassis:
                statuses = [c.data.get('Status', {}).get('Health', 'Unknown') for c in chassis]
                health_status['chassis'] = 'OK' if all(s == 'OK' for s in statuses) else 'Warning'
        except:
            pass
        
        try:
            managers = self.get_managers()
            if managers:
                statuses = [m.data.get('Status', {}).get('Health', 'Unknown') for m in managers]
                health_status['managers'] = 'OK' if all(s == 'OK' for s in statuses) else 'Warning'
        except:
            pass
        
        return health_status
    
    def close(self):
        """Close the client and cleanup resources"""
        self.logout()
        self.session.close()