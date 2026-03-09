# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Base handler class for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
"""

import os
import json
import time
import logging
import re
import base64
import secrets
from http.server import BaseHTTPRequestHandler
from ..utils.file_utils import construct_path, get_cached_link, send_header_file
from ..services.event_service import EventServiceHandler
from ..services.update_service import UpdateServiceHandler

# Plugin system - RAS and Telemetry are now plugins, not core services
from ..plugins import get_plugin_loader

# Backwards compatibility: try to import old service locations
# This allows existing code to work while transitioning to plugin model
try:
    from ..services.ras_service import RASServiceHandler as LegacyRASServiceHandler
    _LEGACY_RAS_AVAILABLE = True
except ImportError:
    _LEGACY_RAS_AVAILABLE = False
    LegacyRASServiceHandler = None

try:
    from ..services.telemetry_service import TelemetryServiceHandler as LegacyTelemetryServiceHandler
    _LEGACY_TELEMETRY_AVAILABLE = True
except ImportError:
    _LEGACY_TELEMETRY_AVAILABLE = False
    LegacyTelemetryServiceHandler = None

logger = logging.getLogger(__name__)


class BaseRedfishHandler(BaseHTTPRequestHandler):
    """Base handler for BMC Redfish Simulator"""
    
    server_version = "RedfishMockupHTTPD_v"
    cached_links = {}
    # Map of X-Auth-Token string -> {UserName, SessionPath}
    active_sessions = {}

    # Paths that never require a session token
    _AUTH_EXEMPT_EXACT = frozenset([
        '/redfish', '/redfish/', '/redfish/v1', '/redfish/v1/',
        '/redfish/v1/odata', '/redfish/v1/$metadata',
    ])

    def _is_auth_exempt(self):
        """Return True if this request does not require an authentication token."""
        path = self.path.split('?')[0].rstrip('/')
        if path in self._AUTH_EXEMPT_EXACT:
            return True
        if path.startswith('/redfish/v1/odata') or path.startswith('/redfish/v1/$metadata'):
            return True
        # POST to the Sessions *collection* is the login endpoint — exempt
        if (self.command == 'POST' and
                re.search(r'/SessionService/Sessions/?$', path)):
            return True
        return False

    def _validate_credentials(self, username, password):
        """Validate username/password against AccountService Accounts mockup data."""
        accounts_path = self.construct_path('/redfish/v1/AccountService/Accounts', 'index.json')
        success, accounts_data = self.get_cached_link(accounts_path)
        if not success or not isinstance(accounts_data, dict):
            # Accounts collection not found — fall back to permissive (simulator mode)
            return True
        for member in accounts_data.get('Members', []):
            account_odata_id = member.get('@odata.id', '')
            if not account_odata_id:
                continue
            account_path = self.construct_path(account_odata_id, 'index.json')
            ok, account = self.get_cached_link(account_path)
            if not ok or not isinstance(account, dict):
                continue
            if account.get('UserName') == username:
                stored = account.get('Password')
                # null/None in mockup means accept any password
                if stored is None or stored == password:
                    return True
        return False

    def _check_auth(self):
        """Return True if the request carries a valid credential or is auth-exempt."""
        if self._is_auth_exempt():
            return True
        # X-Auth-Token
        token = self.headers.get('X-Auth-Token', '')
        if token and token in self.active_sessions:
            return True
        # HTTP Basic
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Basic '):
            try:
                creds = base64.b64decode(auth_header[6:]).decode('utf-8')
                username, password = creds.split(':', 1)
                if self._validate_credentials(username, password):
                    return True
            except Exception:
                pass
        return False

    def _send_unauthorized(self):
        """Send 401 Unauthorized with a Redfish-compliant error body."""
        body = json.dumps({
            "error": {
                "code": "Base.1.5.0.GeneralError",
                "message": "The request requires authentication.",
                "@Message.ExtendedInfo": [{
                    "@odata.type": "#Message.v1_1_1.Message",
                    "MessageId": "Base.1.5.0.InsufficientPrivilege",
                    "Message": "There are insufficient privileges for the account or "
                               "credentials associated with the current session to perform "
                               "the requested operation.",
                    "Severity": "Critical",
                    "Resolution": "Either abandon the operation or change the associated "
                                  "access rights and resubmit the request."
                }]
            }
        }, indent=4).encode()
        self.send_response(401)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('WWW-Authenticate', 'Basic realm="RedfishSimulator"')
        self.end_headers()
        self.wfile.write(body)

    def __init__(self, request, client_address, server):
        self.event_service = EventServiceHandler(server.config)
        self.update_service = UpdateServiceHandler(server.config)
        
        # Initialize plugin loader and load configured plugins
        self.plugin_loader = get_plugin_loader(server.config)
        
        # Load plugins based on config (default to loading common plugins for compatibility)
        extensions = getattr(server.config, 'extensions', None) or ['ras', 'telemetry']
        for plugin_name in extensions:
            self.plugin_loader.load_plugin(plugin_name)
        
        # Backwards compatibility: expose service properties
        # This allows existing code to work while we transition to plugins
        self._ras_service = None
        self._telemetry_service = None
        
        # Add a fallback log_entry_service attribute to prevent property conflicts
        self._fallback_log_entry_service = None
        
        super().__init__(request, client_address, server)
    
    @property
    def ras_service(self):
        """
        RAS Service property for backwards compatibility.
        
        Returns the RAS plugin handler if loaded, otherwise falls back
        to legacy RAS service if available.
        """
        # Try plugin first
        ras_plugin = self.plugin_loader.get_plugin('ras')
        if ras_plugin and ras_plugin.enabled:
            return ras_plugin.handler
        
        # Fallback to legacy service
        if self._ras_service is None and _LEGACY_RAS_AVAILABLE:
            self._ras_service = LegacyRASServiceHandler(self.server.config)
        
        return self._ras_service
    
    @property
    def telemetry_service(self):
        """
        Telemetry Service property for backwards compatibility.
        
        Returns the Telemetry plugin handler if loaded, otherwise falls back
        to legacy Telemetry service if available.
        """
        # Try plugin first
        telemetry_plugin = self.plugin_loader.get_plugin('telemetry')
        if telemetry_plugin and telemetry_plugin.enabled:
            return telemetry_plugin.handler
        
        # Fallback to legacy service
        if self._telemetry_service is None and _LEGACY_TELEMETRY_AVAILABLE:
            self._telemetry_service = LegacyTelemetryServiceHandler(self.server.config)
        
        return self._telemetry_service
    
    @property
    def log_entry_service(self):
        """Fallback log_entry_service property to prevent inheritance conflicts"""
        return self._fallback_log_entry_service
    
    @log_entry_service.setter
    def log_entry_service(self, value):
        """Allow setting log_entry_service to prevent inheritance conflicts"""
        self._fallback_log_entry_service = value

    def construct_path(self, path, filename):
        """Construct path for resource files"""
        return construct_path(
            self.server.config.mock_dir, 
            path, 
            filename, 
            self.server.config.short_form
        )

    def get_cached_link(self, path):
        """Get cached link or load from file"""
        return get_cached_link(self.cached_links, path)

    def try_to_sleep(self, method, path):
        """Add response delay if configured"""
        if self.server.config.time_from_json:
            response_time = self.get_response_time(method, path)
            try:
                time.sleep(float(response_time))
            except ValueError:
                logger.info("Time is not a float value. Using default response time")
                time.sleep(self.server.config.response_time)
        else:
            time.sleep(self.server.config.response_time)

    def send_header_file(self, fpath):
        """Send headers from headers.json file"""
        send_header_file(self, fpath)

    def get_response_time(self, method, path):
        """Get response time from time.json file or use default"""
        fpath = self.construct_path(path, 'time.json')
        
        if not any(x in method for x in ("GET", "HEAD", "POST", "PATCH", "DELETE")):
            logger.info("Not a valid method")
            return 0
            
        if os.path.isfile(fpath):
            try:
                with open(fpath) as time_data:
                    d = json.load(time_data)
                    time_str = f"{method}_Time"
                    if time_str in d:
                        return float(d[time_str])
            except (json.JSONDecodeError, ValueError):
                logger.info("Invalid time data in JSON file. Using default time.")
        
        return self.server.config.response_time

    def check_if_dict_is_odata_id_only(self, odata_id_dict):
        """Helper method to check if a dict contains only @odata.id"""
        if "@odata.id" in odata_id_dict and len(odata_id_dict) == 1:
            return odata_id_dict["@odata.id"]
        return None

    def add_new_member(self, payload, data_received):
        """Add new member to a collection"""
        members = payload.get('Members', [])
        n = 1
        
        # Use existing member ID pattern if available
        if members:
            member_id = members[0].get('@odata.id', '').replace(self.path, '').strip('/')
            pattern = member_id.replace(member_id.split('/')[-1], '{id}') if '/' in member_id else '{id}'
        else:
            pattern = 'Member{id}'
        
        # Ensure pattern has {id} placeholder
        if '{id}' not in pattern:
            pattern += "{id}"
        
        # Generate unique ID
        newpath_id = data_received.get('Id', pattern.format(id=n))
        if data_received.get('Id') in [m.get('@odata.id', '').replace(self.path, '').strip('/') for m in members]:
            newpath_id = pattern.format(id=n)
        
        newpath = '/'.join([self.path, newpath_id])
        while newpath in [m.get('@odata.id') for m in members]:
            n += 1
            newpath_id = pattern.format(id=n)
            newpath = '/'.join([self.path, newpath_id])
        
        # Add new member
        members.append({'@odata.id': newpath})
        data_received['@odata.id'] = newpath
        data_received['Id'] = newpath_id
        
        payload['Members'] = members
        payload['Members@odata.count'] = len(members)
        
        return newpath