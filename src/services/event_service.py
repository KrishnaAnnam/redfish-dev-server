# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
EventService handling for Redfish Mockup Server
"""

import os
import json
import threading
import logging
import grequests
from ..utils.file_utils import construct_path, get_cached_link

logger = logging.getLogger(__name__)


class EventServiceHandler:
    """Handler for EventService operations"""
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.event_subscriptions = []
        self.event_id = 1

    def handle_adding_subscriptions(self, path, data_received, cached_links):
        """Handle adding new event subscriptions"""
        sub_path = construct_path(
            self.server_config.mock_dir, 
            '/redfish/v1/EventService/Subscriptions', 
            'index.json', 
            self.server_config.short_form
        )
        success, sub_payload = get_cached_link(cached_links, sub_path)
        logger.info(sub_path)
        
        if not success:
            # Eventing not supported
            return 404
        
        members_count = sub_payload.get('Members@odata.count')
        
        subscription_entry = {
            '@odata.type': '#EventDestination.v1_7_0.EventDestination',
            '@odata.id': f"/redfish/v1/EventService/Subscriptions/EventSubscription{members_count+1}"
        }
        
        # Copy relevant fields from request
        fields_to_copy = [
            'Destination', 'Context', 'Protocol', 'SubscriptionType',
            'EventFormatType', 'HttpHeaders', 'DeliveryRetryPolicy',
            'MetricReportDefinitions', 'RegistryPrefixes', 'ResourceTypes',
            'MessageIds', 'Description'
        ]
        
        for field in fields_to_copy:
            if field in data_received:
                subscription_entry[field] = data_received[field]
        
        self.event_subscriptions.append(subscription_entry)
        
        # Create directory and save subscription
        os.makedirs(self.server_config.mock_dir + subscription_entry['@odata.id'], exist_ok=True)
        subscription_path = construct_path(
            self.server_config.mock_dir,
            subscription_entry['@odata.id'], 
            'index.json',
            self.server_config.short_form
        )
        
        with open(subscription_path, "w") as outfile:
            json.dump(subscription_entry, outfile, indent=4, separators=(',', ":"))
        
        # Update subscriptions collection
        members = sub_payload.get('Members', [])
        members.append({'@odata.id': subscription_entry['@odata.id']})
        sub_payload['Members@odata.count'] = members_count + 1
        
        with open(sub_path, "w") as outfile:
            json.dump(sub_payload, outfile, indent=4, separators=(',', ":"))

        # DSP0266: collection POST must return 201 Created + Location header
        return 201, subscription_entry['@odata.id'], subscription_entry

    def handle_eventing(self, path, data_received, cached_links):
        """Handle test event submission"""
        sub_path = construct_path(
            self.server_config.mock_dir,
            '/redfish/v1/EventService/Subscriptions', 
            'index.json',
            self.server_config.short_form
        )
        success, sub_payload = get_cached_link(cached_links, sub_path)
        logger.info(sub_path)
        
        if not success:
            return 404
        
        # Per DSP0266 / Redfish spec only MessageId is required
        if 'MessageId' not in data_received:
            return 400
        
        # Reformat OriginOfCondition if present
        if 'OriginOfCondition' in data_received:
            origin_of_cond = data_received['OriginOfCondition']
            if isinstance(origin_of_cond, str):
                data_received['OriginOfCondition'] = {'@odata.id': origin_of_cond}
        
        # Build event payload
        event_payload = {
            '@odata.type': '#Event.v1_9_0.Event',
            'Name': 'Event Log',
            'Id': str(self.event_id),
            'Events': []
        }
        
        event_record = {
            'MessageId': data_received.get('MessageId'),
            'Message': data_received.get('Message'),
            'EventType': 'Event'
        }
        
        # Forward optional fields from data_received into event_record
        for optional_field in ('EventId', 'EventTimestamp', 'Severity',
                               'MessageArgs', 'OriginOfCondition',
                               'AdditionalDataURI', 'DiagnosticData',
                               'DiagnosticDataType', 'Oem'):
            if optional_field in data_received:
                event_record[optional_field] = data_received[optional_field]
        
        # Handle CPER data if present
        if "CPERError" in data_received.get('MessageId', ''):
            cper_data_file = construct_path(
                self.server_config.mock_dir,
                f'/redfish/v1/Systems/system/LogServices/CPERLogs/Entries/{data_received["MessageArgs"][0]}',
                'Attachment',
                self.server_config.short_form
            )
            if os.path.exists(cper_data_file):
                event_record["AdditionalDataSizeBytes"] = os.path.getsize(cper_data_file)
                event_record["AdditionalDataURI"] = f'/redfish/v1/Systems/system/LogServices/CPERLogs/Entries/{data_received["MessageArgs"][0]}/Attachment'
        
        event_payload['Events'].append(event_record)
        
        # Send events to subscribers
        events = []
        for member in sub_payload.get('Members', []):
            entry_path = construct_path(
                self.server_config.mock_dir,
                member['@odata.id'], 
                'index.json',
                self.server_config.short_form
            )
            success, subscription = get_cached_link(cached_links, entry_path)
            
            if success and self._should_send_event(subscription, data_received):
                http_headers = {'Content-Type': 'application/json'}
                event_payload['Context'] = subscription.get('Context', 'Default Context')
                
                events.append(grequests.post(
                    subscription['Destination'], 
                    timeout=20, 
                    data=json.dumps(event_payload), 
                    headers=http_headers
                ))
        
        # Send events asynchronously
        try:
            threading.Thread(target=grequests.map, args=(events,)).start()
        except Exception as e:
            logger.info(f'post error {str(e)}')
        
        self.event_id += 1
        return 200

    def _should_send_event(self, subscription, data_received):
        """Check if event should be sent to subscriber"""
        if 'Destination' not in subscription or 'Protocol' not in subscription:
            return False
        
        if 'MessageId' in data_received:
            registry_prefix = data_received['MessageId'].split(".")[0]
            if registry_prefix in subscription.get('RegistryPrefixes', []):
                return True
        
        return False

    def handle_post_event_service(self, path, data_received, cached_links):
        """Handle POST requests to EventService endpoints"""
        if 'EventService/Subscriptions' in path:
            return self.handle_adding_subscriptions(path, data_received, cached_links)
        
        if 'EventService/Actions/EventService.SubmitTestEvent' in path:
            return self.handle_eventing(path, data_received, cached_links)
        
        return 404