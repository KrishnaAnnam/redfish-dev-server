# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Telemetry Service handling for Redfish Mockup Server

.. deprecated:: 1.0.0
   This module is deprecated. Telemetry Service has been moved to the plugin system.
   Use `src.plugins.telemetry` instead.
   
   Migration:
       # Old way (deprecated):
       from src.services.telemetry_service import TelemetryServiceHandler
       
       # New way (plugin):
       from src.plugins.telemetry import TelemetryServiceHandler
       # Or use the plugin loader:
       from src.plugins import get_plugin_loader
       loader = get_plugin_loader(config)
       loader.load_plugin('telemetry')
"""

import warnings
import json
import datetime
import threading
import logging
import grequests
from ..utils.file_utils import construct_path, get_cached_link

# Emit deprecation warning when this module is imported
warnings.warn(
    "src.services.telemetry_service is deprecated. "
    "Use src.plugins.telemetry instead. "
    "Telemetry is now a plugin that can be optionally enabled.",
    DeprecationWarning,
    stacklevel=2
)

logger = logging.getLogger(__name__)


class TelemetryServiceHandler:
    """Handler for TelemetryService operations
    
    .. deprecated:: 1.0.0
       Use src.plugins.telemetry.TelemetryServiceHandler instead.
    """
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.event_id = 1

    def handle_telemetry(self, path, data_received, cached_links):
        """Handle telemetry data submission"""
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
        
        # Validate required telemetry parameters
        if not self._validate_telemetry_data(data_received):
            return 400
        
        # Build metric report payload
        event_payload = self._build_metric_report(data_received, cached_links)
        
        # Cache the metric report
        event_fpath = construct_path(
            self.server_config.mock_dir,
            event_payload['@odata.id'], 
            'index.json',
            self.server_config.short_form
        )
        cached_links[event_fpath] = event_payload
        
        # Update metric reports collection
        self._update_metric_reports_collection(event_payload, cached_links)
        
        # Send to subscribers
        self._send_telemetry_to_subscribers(event_payload, sub_payload, cached_links)
        
        self.event_id += 1
        return 204

    def _validate_telemetry_data(self, data_received):
        """Validate telemetry data parameters"""
        required_combinations = [
            ['MetricReportName', 'MetricReportValues'],
            ['MetricReportName', 'GeneratedMetricReportValues'],
            ['MetricName', 'MetricValues']
        ]
        
        for combo in required_combinations:
            if all(key in data_received for key in combo):
                return True
        
        return False

    def _build_metric_report(self, data_received, cached_links):
        """Build metric report payload from received data"""
        my_name = data_received.get('MetricName') or data_received.get('MetricReportName')
        my_data = (data_received.get('MetricValues') or 
                  data_received.get('MetricReportValues') or 
                  data_received.get('GeneratedMetricReportValues'))
        
        event_payload = {
            '@odata.context': '/redfish/v1/$metadata#MetricReport.MetricReport',
            '@odata.type': '#MetricReport.v1_0_0.MetricReport',
            '@odata.id': f'/redfish/v1/TelemetryService/MetricReports/{my_name}',
            'Id': my_name,
            'Name': my_name,
            'MetricReportDefinition': {
                "@odata.id": f"/redfish/v1/TelemetryService/MetricReportDefinitions/{my_name}"
            }
        }
        
        # Add timestamp
        now = datetime.datetime.now()
        event_payload['Timestamp'] = (
            now.strftime('%Y-%m-%dT%H:%M:%S') + 
            f'-{now.microsecond // 10000:02d}'
        )
        
        # Validate and add metric values
        expected_keys = ['MetricId', 'MetricValue', 'Timestamp', 'MetricProperty', 'MetricDefinition']
        value_list = []
        
        for tup in my_data:
            if all(x in tup for x in expected_keys):
                value_list.append(tup)
        
        event_payload['MetricValues'] = value_list
        logger.info(event_payload)
        
        return event_payload

    def _update_metric_reports_collection(self, event_payload, cached_links):
        """Update the MetricReports collection"""
        report_path = construct_path(
            self.server_config.mock_dir,
            '/redfish/v1/TelemetryService/MetricReports',
            'index.json',
            self.server_config.short_form
        )
        success, collection_payload = get_cached_link(cached_links, report_path)
        
        if not success:
            collection_payload = {
                '@odata.context': '/redfish/v1/$metadata#MetricReportCollection.MetricReportCollection',
                '@odata.type': '#MetricReportCollection.v1_0_0.MetricReportCollection',
                '@odata.id': '/redfish/v1/TelemetryService/MetricReports',
                'Name': 'MetricReports',
                'Members': []
            }
        
        # Add to collection if not already present
        existing_ids = [member.get('@odata.id') for member in collection_payload['Members']]
        if event_payload['@odata.id'] not in existing_ids:
            collection_payload['Members'].append({'@odata.id': event_payload['@odata.id']})
        
        collection_payload['Members@odata.count'] = len(collection_payload['Members'])
        cached_links[report_path] = collection_payload

    def _send_telemetry_to_subscribers(self, event_payload, sub_payload, cached_links):
        """Send telemetry data to subscribers"""
        events = []
        
        for member in sub_payload.get('Members', []):
            entry_path = construct_path(
                self.server_config.mock_dir,
                member['@odata.id'], 
                'index.json',
                self.server_config.short_form
            )
            success, subscription = get_cached_link(cached_links, entry_path)
            
            if not success:
                logger.info('No such subscription resource')
                continue
            
            # Check if subscription is valid for telemetry
            if not self._is_valid_telemetry_subscription(subscription):
                logger.info('Invalid subscription for telemetry')
                continue
            
            logger.info(f'Sending telemetry to: {subscription["Destination"]}')
            
            http_headers = {'Content-Type': 'application/json'}
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
            logger.info(f'Telemetry post error: {str(e)}')

    def _is_valid_telemetry_subscription(self, subscription):
        """Check if subscription is valid for telemetry data"""
        return ('Destination' in subscription and 
                'EventTypes' in subscription)

    def handle_submit_test_metric_report(self, path, data_received, cached_links):
        """Handle SubmitTestMetricReport action"""
        return self.handle_telemetry(path, data_received, cached_links)