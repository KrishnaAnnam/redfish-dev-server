#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Enhanced Event Service for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
===============================================

Extends the existing EventService with proper event entries, correlation with logs,
standardized event generation, and comprehensive event management.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path

from ..models.redfish_models import EventEntry, LogEntry, SeverityType, EventType
from .message_service import MessageService, get_message_service
from .log_service import LogService, get_log_service, LogServiceType

logger = logging.getLogger(__name__)

class EventSubscription:
    """Represents an event subscription"""
    
    def __init__(self, subscription_id: str, destination: str, protocol: str = "Redfish",
                 context: str = None, event_types: List[str] = None,
                 message_ids: List[str] = None, registry_prefixes: List[str] = None):
        self.id = subscription_id
        self.destination = destination
        self.protocol = protocol
        self.context = context or f"Context-{subscription_id}"
        self.event_types = event_types or ["Alert", "ResourceAdded", "ResourceRemoved", "ResourceUpdated"]
        self.message_ids = message_ids or []
        self.registry_prefixes = registry_prefixes or ["Base"]
        self.created = datetime.now(timezone.utc)
        self.delivery_retry_policy = "RetryForever"
        self.delivery_retry_attempts = 3
        self.delivery_retry_interval_seconds = 30
        
    def to_redfish_dict(self) -> Dict[str, Any]:
        """Convert to Redfish EventDestination format"""
        return {
            "@odata.type": "#EventDestination.v1_7_0.EventDestination",
            "@odata.id": f"/redfish/v1/EventService/Subscriptions/{self.id}",
            "Id": self.id,
            "Name": f"Event Subscription {self.id}",
            "Destination": self.destination,
            "Context": self.context,
            "Protocol": self.protocol,
            "EventTypes": self.event_types,
            "MessageIds": self.message_ids,
            "RegistryPrefixes": self.registry_prefixes,
            "DeliveryRetryPolicy": self.delivery_retry_policy,
            "Status": {
                "State": "Enabled",
                "Health": "OK"
            }
        }
    
    def matches_event(self, event: EventEntry) -> bool:
        """Check if subscription matches event"""
        # Check event type
        if event.event_type.value not in self.event_types:
            return False
            
        # Check message ID if specified
        if self.message_ids and event.message_id not in self.message_ids:
            return False
            
        # Check registry prefix
        if self.registry_prefixes:
            event_prefix = event.message_id.split('.')[0] if '.' in event.message_id else ""
            if not any(prefix in event_prefix for prefix in self.registry_prefixes):
                return False
        
        return True

class EnhancedEventService:
    """Enhanced EventService with comprehensive event management"""
    
    def __init__(self, config, message_service: MessageService = None, log_service: LogService = None):
        self.config = config
        self.message_service = message_service or get_message_service(config)
        self.log_service = log_service or get_log_service(config)
        
        # Event management
        self.subscriptions: Dict[str, EventSubscription] = {}
        self.event_queue: List[EventEntry] = []
        self.subscription_counter = 1
        self.event_counter = 1
        
        # Threading for event delivery
        self._lock = threading.Lock()
        self._delivery_thread = None
        self._stop_delivery = False
        
        # Start event delivery thread
        self._start_delivery_thread()
    
    def _start_delivery_thread(self):
        """Start event delivery thread"""
        if not self._delivery_thread or not self._delivery_thread.is_alive():
            self._stop_delivery = False
            self._delivery_thread = threading.Thread(target=self._event_delivery_worker, daemon=True)
            self._delivery_thread.start()
            logger.info("Event delivery thread started")
    
    def _event_delivery_worker(self):
        """Worker thread for event delivery"""
        while not self._stop_delivery:
            try:
                with self._lock:
                    events_to_deliver = self.event_queue.copy()
                    self.event_queue.clear()
                
                for event in events_to_deliver:
                    self._deliver_event(event)
                
                time.sleep(1)  # Check for events every second
                
            except Exception as e:
                logger.error(f"Error in event delivery thread: {e}")
    
    def _deliver_event(self, event: EventEntry):
        """Deliver event to subscriptions"""
        for subscription in self.subscriptions.values():
            if subscription.matches_event(event):
                try:
                    self._send_event_to_destination(event, subscription)
                except Exception as e:
                    logger.error(f"Failed to deliver event to {subscription.destination}: {e}")
    
    def _send_event_to_destination(self, event: EventEntry, subscription: EventSubscription):
        """Send event to specific destination"""
        # This is a simplified implementation - in real scenarios, 
        # you would make HTTP POST requests to the destination
        
        event_data = event.to_redfish_dict()
        event_data["Context"] = subscription.context
        
        logger.info(f"Delivering event {event.event_id} to {subscription.destination}")
        logger.debug(f"Event data: {json.dumps(event_data, indent=2)}")
        
        # In a real implementation, you would send:
        # requests.post(subscription.destination, json=event_data, ...)
    
    def create_subscription(self, destination: str, protocol: str = "Redfish",
                          context: str = None, event_types: List[str] = None,
                          message_ids: List[str] = None, 
                          registry_prefixes: List[str] = None) -> EventSubscription:
        """Create new event subscription"""
        with self._lock:
            subscription_id = str(self.subscription_counter)
            self.subscription_counter += 1
            
            subscription = EventSubscription(
                subscription_id=subscription_id,
                destination=destination,
                protocol=protocol,
                context=context,
                event_types=event_types,
                message_ids=message_ids,
                registry_prefixes=registry_prefixes
            )
            
            self.subscriptions[subscription_id] = subscription
            
            # Log subscription creation
            self.log_service.log_operation(
                "CREATE",
                f"/redfish/v1/EventService/Subscriptions/{subscription_id}",
                success=True
            )
            
            logger.info(f"Created event subscription {subscription_id} for {destination}")
            return subscription
    
    def delete_subscription(self, subscription_id: str) -> bool:
        """Delete event subscription"""
        with self._lock:
            if subscription_id in self.subscriptions:
                del self.subscriptions[subscription_id]
                
                # Log subscription deletion
                self.log_service.log_operation(
                    "DELETE",
                    f"/redfish/v1/EventService/Subscriptions/{subscription_id}",
                    success=True
                )
                
                logger.info(f"Deleted event subscription {subscription_id}")
                return True
            return False
    
    def get_subscription(self, subscription_id: str) -> Optional[EventSubscription]:
        """Get event subscription by ID"""
        return self.subscriptions.get(subscription_id)
    
    def get_subscriptions_collection(self) -> Dict[str, Any]:
        """Get subscriptions collection"""
        members = []
        for subscription_id in self.subscriptions.keys():
            members.append({
                "@odata.id": f"/redfish/v1/EventService/Subscriptions/{subscription_id}"
            })
        
        return {
            "@odata.type": "#EventDestinationCollection.EventDestinationCollection",
            "@odata.id": "/redfish/v1/EventService/Subscriptions",
            "Name": "Event Subscriptions Collection",
            "Description": "Collection of Event Subscriptions",
            "Members@odata.count": len(members),
            "Members": members
        }
    
    def publish_event(self, event: EventEntry, log_to_service: bool = True):
        """Publish event to subscribers and optionally log"""
        with self._lock:
            # Assign event ID
            event.event_id = f"Event-{self.event_counter}"
            self.event_counter += 1
            
            # Add to delivery queue
            self.event_queue.append(event)
            
            # Convert to log entry and log it
            if log_to_service:
                log_entry = event.to_log_entry()
                self.log_service.add_log_entry(LogServiceType.EVENT, log_entry)
            
            logger.debug(f"Published event {event.event_id}: {event.message}")
    
    def publish_resource_event(self, operation: str, resource_path: str, 
                             resource_type: str = "Resource"):
        """Publish resource lifecycle event"""
        if operation == "CREATE":
            event = EventEntry.resource_created(resource_path, resource_type)
        elif operation == "UPDATE":
            event = EventEntry.resource_updated(resource_path, resource_type)
        elif operation == "DELETE":
            event = EventEntry.resource_deleted(resource_path, resource_type)
        else:
            return  # Unknown operation
        
        self.publish_event(event)
    
    def publish_status_change_event(self, resource_path: str, old_status: str, new_status: str):
        """Publish status change event"""
        event = EventEntry.status_change(resource_path, old_status, new_status)
        self.publish_event(event)
    
    def publish_alert_event(self, resource_path: str, alert_message: str,
                          severity: SeverityType = SeverityType.WARNING):
        """Publish alert event"""
        event = EventEntry.alert_event(resource_path, alert_message, severity)
        self.publish_event(event)
    
    def submit_test_event(self, event_type: str = "Alert", 
                         message: str = "Test event message",
                         severity: str = "Warning") -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Submit test event"""
        try:
            # Convert severity string to enum
            severity_enum = SeverityType.WARNING
            try:
                severity_enum = SeverityType(severity)
            except ValueError:
                pass
            
            # Convert event type string to enum
            event_type_enum = EventType.ALERT
            try:
                event_type_enum = EventType(event_type)
            except ValueError:
                pass
            
            # Create test event
            event = EventEntry(
                event_type=event_type_enum,
                message_id="Base.1.5.0.TestMessage",
                message=message,
                severity=severity_enum,
                origin_of_condition="/redfish/v1/EventService",
                message_args=[message]
            )
            
            # Publish event
            self.publish_event(event)
            
            response_data = {
                "Message": f"Test event submitted successfully",
                "EventId": event.event_id,
                "EventType": event_type,
                "Severity": severity
            }
            
            return self.message_service.create_success_response(response_data)
            
        except Exception as e:
            logger.error(f"Error submitting test event: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")
    
    def get_event_service_info(self) -> Dict[str, Any]:
        """Get EventService root information"""
        return {
            "@odata.type": "#EventService.v1_5_0.EventService",
            "@odata.id": "/redfish/v1/EventService",
            "Id": "EventService",
            "Name": "Event Service",
            "Description": "Event Service for managing event subscriptions and notifications",
            "Status": {
                "State": "Enabled",
                "Health": "OK"
            },
            "ServiceEnabled": True,
            "DeliveryRetryAttempts": 3,
            "DeliveryRetryIntervalSeconds": 30,
            "EventTypesForSubscription": [
                "StatusChange",
                "ResourceUpdated", 
                "ResourceAdded",
                "ResourceRemoved",
                "Alert",
                "MetricReport"
            ],
            "RegistryPrefixes": ["Base", "Platform"],
            "ResourceTypes": ["Chassis", "EventService", "Managers", "Systems", "Task"],
            "Subscriptions": {
                "@odata.id": "/redfish/v1/EventService/Subscriptions"
            },
            "Actions": {
                "#EventService.SubmitTestEvent": {
                    "target": "/redfish/v1/EventService/Actions/EventService.SubmitTestEvent",
                    "@Redfish.ActionInfo": "/redfish/v1/EventService/SubmitTestEventActionInfo"
                }
            },
            "SMTP": {
                "ServiceEnabled": False
            }
        }
    
    def handle_event_service_get(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle GET requests to EventService endpoints"""
        parts = path.strip('/').split('/')
        
        try:
            # /redfish/v1/EventService
            if path.endswith('/EventService') or path.endswith('/EventService/'):
                return 200, {}, self.get_event_service_info()
            
            # /redfish/v1/EventService/Subscriptions
            elif 'Subscriptions' in parts:
                subscriptions_index = parts.index('Subscriptions')
                
                # Collection
                if subscriptions_index == len(parts) - 1:
                    return 200, {}, self.get_subscriptions_collection()
                
                # Individual subscription
                elif subscriptions_index + 1 < len(parts):
                    subscription_id = parts[subscriptions_index + 1]
                    subscription = self.get_subscription(subscription_id)
                    if subscription:
                        return 200, {}, subscription.to_redfish_dict()
                    else:
                        return self.message_service.create_not_found_response("EventSubscription", subscription_id)
            
            return 404, {}, {"error": "Not found"}
            
        except Exception as e:
            logger.error(f"Error handling EventService GET request: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")
    
    def handle_event_service_post(self, path: str, data: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle POST requests to EventService endpoints"""
        try:
            # Submit test event action
            if 'SubmitTestEvent' in path:
                event_type = data.get("EventType", "Alert")
                message = data.get("Message", "Test event message")
                severity = data.get("Severity", "Warning")
                return self.submit_test_event(event_type, message, severity)
            
            # Create subscription
            elif 'Subscriptions' in path and not any(action in path for action in ['Actions', 'SubmitTestEvent']):
                destination = data.get("Destination")
                if not destination:
                    return self.message_service.create_action_error_response(
                        "CreateSubscription", "Destination", "ActionParameterMissing"
                    )
                
                protocol = data.get("Protocol", "Redfish")
                context = data.get("Context")
                event_types = data.get("EventTypes")
                message_ids = data.get("MessageIds")
                registry_prefixes = data.get("RegistryPrefixes")
                
                subscription = self.create_subscription(
                    destination=destination,
                    protocol=protocol,
                    context=context,
                    event_types=event_types,
                    message_ids=message_ids,
                    registry_prefixes=registry_prefixes
                )
                
                location = f"/redfish/v1/EventService/Subscriptions/{subscription.id}"
                return self.message_service.create_created_response(
                    subscription.to_redfish_dict(), location
                )
            
            return 404, {}, {"error": "Action not found"}
            
        except Exception as e:
            logger.error(f"Error handling EventService POST request: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")
    
    def handle_event_service_delete(self, path: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """Handle DELETE requests to EventService endpoints"""
        parts = path.strip('/').split('/')
        
        try:
            if 'Subscriptions' in parts:
                subscriptions_index = parts.index('Subscriptions')
                if subscriptions_index + 1 < len(parts):
                    subscription_id = parts[subscriptions_index + 1]
                    if self.delete_subscription(subscription_id):
                        return self.message_service.create_success_response()
                    else:
                        return self.message_service.create_not_found_response("EventSubscription", subscription_id)
            
            return 404, {}, {"error": "Not found"}
            
        except Exception as e:
            logger.error(f"Error handling EventService DELETE request: {e}")
            return self.message_service.create_error_response("Base.1.5.0.GeneralError")
    
    def stop(self):
        """Stop the event service"""
        self._stop_delivery = True
        if self._delivery_thread and self._delivery_thread.is_alive():
            self._delivery_thread.join(timeout=5)
        logger.info("Event service stopped")

# Global enhanced event service instance
_enhanced_event_service_instance = None

def get_enhanced_event_service(config=None) -> EnhancedEventService:
    """Get global enhanced event service instance"""
    global _enhanced_event_service_instance
    if _enhanced_event_service_instance is None:
        _enhanced_event_service_instance = EnhancedEventService(config)
    return _enhanced_event_service_instance

def init_enhanced_event_service(config):
    """Initialize global enhanced event service"""
    global _enhanced_event_service_instance
    _enhanced_event_service_instance = EnhancedEventService(config)