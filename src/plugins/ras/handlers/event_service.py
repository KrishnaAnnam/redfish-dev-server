#!/usr/bin/env python3
"""
RAS Event Service Handler

Manages event emission and delivery for RAS plugin events.
Integrates with Redfish EventService for subscription management.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from pathlib import Path
import threading
import queue

from ..models.events import (
    RASEvent,
    RASEventType,
    EventSubscriptionFilter
)

logger = logging.getLogger(__name__)


class RASEventServiceHandler:
    """
    Handler for RAS event emission and delivery.
    
    Responsibilities:
    - Emit events for RAS activities
    - Manage in-memory event queue
    - Deliver events to subscribers
    - Filter events based on subscriptions
    """
    
    def __init__(self, mockup_dir: Optional[str] = None):
        """
        Initialize RAS EventService handler.
        
        Args:
            mockup_dir: Optional mockup directory for persistence
        """
        self.mockup_dir = mockup_dir
        self.event_queue = queue.Queue(maxsize=1000)
        self.subscribers = {}  # {subscription_id: subscription_data}
        self.event_callbacks = []  # List of callback functions
        self.event_history = []  # Recent events (limited size)
        self.max_history = 100
        
        # Statistics
        self.stats = {
            "events_emitted": 0,
            "events_delivered": 0,
            "events_filtered": 0
        }
        
        logger.info("RAS EventService handler initialized")
    
    def emit_event(self, event: Dict[str, Any]) -> bool:
        """
        Emit a RAS event.
        
        Args:
            event: Event data structure
            
        Returns:
            bool: True if event was emitted successfully
        """
        try:
            # Add to queue
            try:
                self.event_queue.put_nowait(event)
            except queue.Full:
                logger.warning("Event queue full, dropping oldest event")
                try:
                    self.event_queue.get_nowait()
                    self.event_queue.put_nowait(event)
                except:
                    pass
            
            # Add to history
            self.event_history.append(event)
            if len(self.event_history) > self.max_history:
                self.event_history.pop(0)
            
            # Update stats
            self.stats["events_emitted"] += 1
            
            # Deliver to subscribers
            self._deliver_event(event)
            
            # Invoke callbacks
            for callback in self.event_callbacks:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Event callback error: {e}")
            
            logger.info(f"Event emitted: {event.get('Id')} - {event.get('Events', [{}])[0].get('MessageId')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            return False
    
    def _deliver_event(self, event: Dict[str, Any]):
        """Deliver event to matching subscribers"""
        for sub_id, subscription in self.subscribers.items():
            try:
                if EventSubscriptionFilter.matches_subscription(event, subscription):
                    self._send_to_subscriber(subscription, event)
                    self.stats["events_delivered"] += 1
                else:
                    self.stats["events_filtered"] += 1
            except Exception as e:
                logger.error(f"Failed to deliver event to {sub_id}: {e}")
    
    def _send_to_subscriber(self, subscription: Dict[str, Any], event: Dict[str, Any]):
        """
        Send event to subscriber.
        
        In a real implementation, this would make HTTP POST to the Destination URL.
        For simulation, we log the delivery.
        """
        destination = subscription.get("Destination")
        protocol = subscription.get("Protocol", "Redfish")
        
        logger.info(f"[EVENT DELIVERY] to {destination} ({protocol})")
        logger.debug(f"Event: {json.dumps(event, indent=2)}")
        
        # TODO: Implement actual HTTP delivery if needed
        # For now, just log the event
    
    def add_subscription(self, subscription_data: Dict[str, Any]) -> str:
        """
        Add an event subscription.
        
        Args:
            subscription_data: Subscription configuration
            
        Returns:
            str: Subscription ID
        """
        sub_id = subscription_data.get("Id") or f"RAS-Sub-{len(self.subscribers) + 1}"
        self.subscribers[sub_id] = subscription_data
        
        logger.info(f"Added event subscription: {sub_id}")
        return sub_id
    
    def remove_subscription(self, subscription_id: str) -> bool:
        """
        Remove an event subscription.
        
        Args:
            subscription_id: Subscription ID to remove
            
        Returns:
            bool: True if removed
        """
        if subscription_id in self.subscribers:
            del self.subscribers[subscription_id]
            logger.info(f"Removed event subscription: {subscription_id}")
            return True
        return False
    
    def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription by ID"""
        return self.subscribers.get(subscription_id)
    
    def get_subscriptions(self) -> List[Dict[str, Any]]:
        """Get all subscriptions"""
        return list(self.subscribers.values())
    
    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Register a callback function to be invoked when events are emitted.
        
        Args:
            callback: Function that takes event dict as parameter
        """
        self.event_callbacks.append(callback)
        logger.info(f"Registered event callback: {callback.__name__}")
    
    def get_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent events from history.
        
        Args:
            count: Number of recent events to return
            
        Returns:
            List of recent events
        """
        return self.event_history[-count:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event statistics"""
        return {
            **self.stats,
            "queue_size": self.event_queue.qsize(),
            "subscribers_count": len(self.subscribers),
            "callbacks_count": len(self.event_callbacks),
            "history_size": len(self.event_history)
        }
    
    def clear_history(self):
        """Clear event history"""
        self.event_history.clear()
        logger.info("Event history cleared")
    
    # Convenience methods for emitting specific event types
    
    def emit_cpad_received(
        self,
        manager_id: str,
        cpad_id: str,
        submission_data: Dict[str, Any]
    ) -> bool:
        """Emit CPAD received event"""
        event = RASEvent.create_cpad_received_event(manager_id, cpad_id, submission_data)
        return self.emit_event(event)
    
    def emit_cpad_approved(
        self,
        manager_id: str,
        cpad_id: str,
        action_id: str,
        log_entry_id: Optional[str] = None
    ) -> bool:
        """Emit CPAD approved event"""
        event = RASEvent.create_cpad_approved_event(manager_id, cpad_id, action_id, log_entry_id)
        return self.emit_event(event)
    
    def emit_cpad_denied(
        self,
        manager_id: str,
        cpad_id: str,
        reason: str
    ) -> bool:
        """Emit CPAD denied event"""
        event = RASEvent.create_cpad_denied_event(manager_id, cpad_id, reason)
        return self.emit_event(event)
    
    def emit_cper_created(
        self,
        manager_id: str,
        log_entry_id: str,
        severity: str,
        cper_data: Dict[str, Any]
    ) -> bool:
        """Emit CPER record created event"""
        event = RASEvent.create_cper_created_event(manager_id, log_entry_id, severity, cper_data)
        return self.emit_event(event)
    
    def emit_log_cleared(
        self,
        manager_id: str,
        entries_cleared: int
    ) -> bool:
        """Emit LogService cleared event"""
        event = RASEvent.create_log_cleared_event(manager_id, entries_cleared)
        return self.emit_event(event)


class EventServiceIntegration:
    """
    Integration with main Redfish EventService.
    
    This class provides methods to integrate RAS events with the
    server's main EventService if available.
    """
    
    @staticmethod
    def register_with_event_service(
        event_service: Any,
        ras_event_handler: RASEventServiceHandler
    ):
        """
        Register RAS event handler with main EventService.
        
        Args:
            event_service: Main EventService handler
            ras_event_handler: RAS EventService handler
        """
        # Register callback to forward events
        def forward_to_event_service(event: Dict[str, Any]):
            try:
                if hasattr(event_service, 'emit_event'):
                    event_service.emit_event(event)
                elif hasattr(event_service, 'add_event'):
                    event_service.add_event(event)
            except Exception as e:
                logger.error(f"Failed to forward event to EventService: {e}")
        
        ras_event_handler.register_callback(forward_to_event_service)
        logger.info("RAS EventService integrated with main EventService")
    
    @staticmethod
    def create_ras_subscription_template() -> Dict[str, Any]:
        """
        Create a template subscription for RAS events.
        
        Returns:
            dict: Subscription template
        """
        return {
            "Name": "RAS Events Subscription",
            "Destination": "https://example.com/ras-events",
            "Protocol": "Redfish",
            "Context": "RAS Plugin Events",
            "EventTypes": ["Alert"],
            "MessageIds": [
                "RasProto.1.0.0.CPADReceived",
                "RasProto.1.0.0.CPADApproved",
                "RasProto.1.0.0.CPADDenied",
                "RasProto.1.0.0.CPERRecordCreated",
                "RasProto.1.0.0.LogServiceCleared"
            ],
            "OriginResources": [
                "/redfish/v1/Managers/*/Oem/RasProto/RASService",
                "/redfish/v1/Managers/*/LogServices/RAS/*"
            ],
            "Oem": {
                "RasProto": {
                    "Severities": ["OK", "Warning", "Critical"],
                    "IncludeCPERData": True
                }
            }
        }
