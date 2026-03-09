# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
POST request handler for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
"""

import json
import logging
import os
import secrets
from requests_toolbelt.multipart import decoder
from .base_handler import BaseRedfishHandler
from ..services.log_entry_service import LogEntryService
from ..services.custom_actions_service import CustomActionsService

logger = logging.getLogger(__name__)


class PostHandler(BaseRedfishHandler):
    """Handler for POST requests"""
    
    def __init__(self, *args, **kwargs):
        # These must be set BEFORE super().__init__() because
        # BaseHTTPRequestHandler.__init__ → handle() → do_POST() runs
        # during the super() call, before the lines below would execute.
        self._log_entry_service_post = None
        self._custom_actions_service = None
        super().__init__(*args, **kwargs)
    
    @property
    def post_log_entry_service(self):
        """Lazy initialization of log entry service for POST operations"""
        if self._log_entry_service_post is None:
            self._log_entry_service_post = LogEntryService(self.server.config)
        return self._log_entry_service_post
    
    @post_log_entry_service.setter
    def post_log_entry_service(self, value):
        """Allow setting the log entry service for testing or dependency injection"""
        self._log_entry_service_post = value
    
    @property
    def custom_actions_service(self):
        """Lazy initialization of custom actions service"""
        if self._custom_actions_service is None:
            self._custom_actions_service = CustomActionsService(self.server.config)
        return self._custom_actions_service
    
    @custom_actions_service.setter
    def custom_actions_service(self, value):
        """Allow setting the custom actions service for testing or dependency injection"""
        self._custom_actions_service = value

    def do_POST(self):
        """Handle POST request"""
        # Auth check — the Session creation POST is explicitly exempt so the
        # login call itself always passes.
        if not self._check_auth():
            self._send_unauthorized()
            return

        multipart_data = False
        logger.info("POST: Headers: {}".format(self.headers))
        
        # Handle content-length
        if "content-length" not in self.headers:
            self.send_response(411)
            self.end_headers()
            return

        lenn = int(self.headers["content-length"])
        data_received = None
        
        if lenn == 0:
            data_received = {}
        else:
            if 'multipart' in self.headers.get("content-type", ""):
                data_received, multipart_data = self._handle_multipart_data(lenn)
            else:
                data_received = self._handle_json_data(lenn)

        if data_received is None:
            self.send_response(400)
            self.end_headers()
            return

        self.try_to_sleep('POST', self.path)
        logger.info("POST: Data: {}".format(data_received))

        # Handle RAS service requests
        if "RASService" in self.path:
            result = self.ras_service.handle_post(self.path, data_received)
            if isinstance(result, tuple):
                status_code, headers, response_data = result
                self.send_response(status_code)
                for header_name, header_value in headers.items():
                    self.send_header(header_name, header_value)
                self.send_header("Content-Type", "application/json")
                encoded_data = json.dumps(response_data, sort_keys=True, indent=4).encode()
                self.send_header("Content-Length", len(encoded_data))
                self.end_headers()
                self.wfile.write(encoded_data)
            else:
                self.send_response(result)
                self.end_headers()
            return

        # Handle LogService/LogEntries requests
        if "LogServices" in self.path and self.path.endswith("/Entries"):
            self._handle_log_entry_post(data_received)
            return

        # Handle EventService requests
        if "EventService" in self.path:
            self._handle_event_service_post(data_received)
            return

        # Handle UpdateService requests
        if "UpdateService" in self.path:
            multipart_data_flag = 'multipart' in self.headers.get("content-type", "")
            uploaded_files = getattr(self, '_uploaded_files', {}) if multipart_data_flag else {}
            
            result = self.update_service.handle_update_service_post(
                self.path, data_received, multipart_data_flag, uploaded_files
            )
            if isinstance(result, tuple):
                status_code, headers, response_data = result
                self.send_response(status_code)
                for header_name, header_value in headers.items():
                    self.send_header(header_name, header_value)
                self.send_header("Content-Type", "application/json")
                encoded_data = json.dumps(response_data, sort_keys=True, indent=4).encode()
                self.send_header("Content-Length", len(encoded_data))
                self.end_headers()
                self.wfile.write(encoded_data)
            else:
                self.send_response(result)
                self.end_headers()
            return

        # Handle regular POST requests
        if not multipart_data and "Oem" not in self.path:
            self._handle_standard_post(data_received)
        else:
            self._handle_action_post(data_received)

    def _handle_multipart_data(self, lenn):
        """Handle multipart form data"""
        multipart_decoder = decoder.MultipartDecoder(
            self.rfile.read(lenn), 
            self.headers["content-type"]
        )
        data_received = None
        uploaded_files = {}
        
        for part in multipart_decoder.parts:
            hdrs = {
                key.decode('utf-8'): value.decode('utf-8') 
                for key, value in part.headers.items()
            }
            
            if 'json' in hdrs.get('Content-Type', ''):
                data_received = json.loads(part.content)
            elif 'octet-stream' in hdrs.get('Content-Type', '') or 'application/octet-stream' in hdrs.get('Content-Type', ''):
                content_disp = hdrs.get('Content-Disposition', '')
                if ';' in content_disp:
                    # Extract filename from Content-Disposition header
                    filename = content_disp.split(";")[2].split("=")[1].replace('"', '') if len(content_disp.split(";")) > 2 else f"upload_{len(uploaded_files)}.bin"
                    
                    # Save file and track it
                    filepath = os.path.join(os.getcwd(), filename)
                    with open(filepath, "wb") as outfile:
                        outfile.write(part.content)
                    
                    uploaded_files[filename] = filepath
                    logger.info(f"Saved uploaded file: {filename} -> {filepath}")
        
        # Store uploaded files in instance for later access
        self._uploaded_files = uploaded_files
        
        return data_received, True

    def _handle_json_data(self, lenn):
        """Handle JSON data"""
        try:
            raw_data = self.rfile.read(lenn)
            logger.info(f"POST: Raw data length: {len(raw_data)}, content: {raw_data[:200]}")
            return json.loads(raw_data.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f'Decoding JSON has failed: {e}')
            print('Decoding JSON has failed, sending 400')
            return None

    def _handle_event_service_post(self, data_received):
        """Handle EventService POST requests"""
        if 'EventService/Subscriptions' in self.path:
            result = self.event_service.handle_adding_subscriptions(
                self.path, data_received, self.cached_links
            )
            # handle_adding_subscriptions returns (201, location_uri, body_dict)
            if isinstance(result, tuple):
                status_code, location, body_dict = result
                encoded = json.dumps(body_dict, sort_keys=True, indent=4).encode()
                self.send_response(status_code)
                self.send_header('Location', location)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', len(encoded))
                self.end_headers()
                self.wfile.write(encoded)
            else:
                self._send_success_response(result)
        elif 'EventService/Actions/EventService.SubmitTestEvent' in self.path:
            r_code = self.event_service.handle_eventing(
                self.path, data_received, self.cached_links
            )
            self._send_success_response(r_code)
        else:
            self._send_success_response(404)

    def _handle_standard_post(self, data_received):
        """Handle standard collection POST requests"""
        fpath = self.construct_path(self.path, 'index.json')
        success, payload = self.get_cached_link(fpath)

        if success:
            if payload.get('Members') is None:
                self.send_response(405)
                self.end_headers()
                return

            # Special handling for session creation
            if 'SessionService/Sessions' in self.path:
                self._handle_session_creation(payload, data_received, fpath)
                return

            # Add new member to collection
            newpath = self.add_new_member(payload, data_received)
            newfpath = self.construct_path(newpath, 'index.json')

            logger.info(newfpath)

            self.cached_links[newfpath] = data_received
            self.cached_links[fpath] = payload

            self.send_response(201)
            self.send_header("Location", newpath)
            self.send_header("Content-Length", "0")
        else:
            self.send_response(404)

        self.end_headers()

    def _handle_session_creation(self, payload, data_received, fpath):
        """Handle POST to SessionService/Sessions: validate creds, issue unique token, return 201."""
        username = data_received.get('UserName', '')
        password = data_received.get('Password', '')

        if not self._validate_credentials(username, password):
            body = json.dumps({
                "error": {
                    "code": "Base.1.5.0.GeneralError",
                    "message": "Invalid credentials.",
                    "@Message.ExtendedInfo": [{
                        "@odata.type": "#Message.v1_1_1.Message",
                        "MessageId": "Base.1.5.0.InsufficientPrivilege",
                        "Message": "The supplied credentials are invalid.",
                        "Severity": "Critical",
                        "Resolution": "Provide valid UserName and Password."
                    }]
                }
            }, indent=4).encode()
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.send_header('WWW-Authenticate', 'Basic realm="RedfishSimulator"')
            self.end_headers()
            self.wfile.write(body)
            return

        # Generate a cryptographically unique token
        token = secrets.token_hex(16)

        # Allocate a new member path (updates payload['Members'] in-place)
        newpath = self.add_new_member(payload, data_received)
        session_id = newpath.split('/')[-1]

        # Build a clean session resource — no password in the response
        session_resource = {
            "@odata.type": "#Session.v1_3_0.Session",
            "@odata.id": newpath,
            "Id": session_id,
            "Name": "User Session",
            "Description": "Manager User Session",
            "UserName": username,
        }

        # Persist in cache
        newfpath = self.construct_path(newpath, 'index.json')
        self.cached_links[newfpath] = session_resource
        self.cached_links[fpath] = payload

        # Register token so subsequent requests are authorised
        self.active_sessions[token] = {
            'UserName': username,
            'SessionPath': newpath,
        }

        encoded = json.dumps(session_resource, sort_keys=True, indent=4).encode()
        self.send_response(201)
        self.send_header('Location', newpath)
        self.send_header('X-Auth-Token', token)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(encoded))
        self.end_headers()
        self.wfile.write(encoded)
        logger.info("Session created: path=%s token=%s", newpath, token)

    def _handle_action_post(self, data_received):
        """Handle action POST requests"""
        # Handle specific actions
        if 'EventService/Actions/EventService.SubmitTestEvent' in self.path:
            r_code = self.event_service.handle_eventing(
                self.path, data_received, self.cached_links
            )
            self.send_response(r_code)
        
        elif 'TelemetryService/Actions/TelemetryService.SubmitTestMetricReport' in self.path:
            r_code = self.telemetry_service.handle_telemetry(
                self.path, data_received, self.cached_links
            )
            self.send_response(r_code)
        
        elif 'RASService/Actions/' in self.path:
            r_code = self.ras_service.handle_post(self.path, data_received)
            self.send_response(r_code)
        
        elif '/Actions/' in self.path:
            self._handle_custom_actions_post(data_received)
        else:
            self.send_response(404)

        self.end_headers()

    def _handle_custom_actions_post(self, data_received):
        """Handle custom actions using CustomActionsService"""
        try:
            status_code, headers, response_data = self.custom_actions_service.handle_action(
                self.path, data_received, self.cached_links
            )
            
            self.send_response(status_code)
            
            # Set custom headers if any
            for header_name, header_value in headers.items():
                self.send_header(header_name, header_value)
            
            if response_data:  # Only send body if there's response data
                self.send_header("Content-Type", "application/json")
                encoded_data = json.dumps(response_data, sort_keys=True, indent=4).encode()
                self.send_header("Content-Length", len(encoded_data))
                self.end_headers()
                self.wfile.write(encoded_data)
            else:
                # No content response (204)
                self.send_header("Content-Length", "0") 
                self.end_headers()
                
        except Exception as e:
            logger.error(f"Error handling custom action: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            error_response = {"error": str(e)}
            encoded_data = json.dumps(error_response, sort_keys=True, indent=4).encode()
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)
            return

    def _handle_generic_action(self):
        """Handle generic actions"""
        fpath = self.construct_path(self.path.split('/Actions/', 1)[0], 'index.json')
        success, payload = self.get_cached_link(fpath)
        
        if success:
            action_found = self._check_action_exists(payload)
            self.send_response(204 if action_found else 404)
        else:
            self.send_response(404)

    def _check_action_exists(self, payload):
        """Check if action exists in resource"""
        try:
            for action in payload.get('Actions', {}):
                if action == 'Oem':
                    for oem_action in payload['Actions'][action]:
                        if payload['Actions'][action][oem_action].get('target') == self.path:
                            return True
                else:
                    if payload['Actions'][action].get('target') == self.path:
                        return True
        except (KeyError, TypeError):
            pass
        return False

    def _send_success_response(self, r_code):
        """Send success response based on return code"""
        self.send_response(r_code)
        self.end_headers()

    def _handle_log_entry_post(self, data_received):
        """Handle POST request to LogEntries collection"""
        try:
            status_code, response_data = self.post_log_entry_service.handle_post_log_entry(
                self.path, data_received, self.cached_links
            )
            
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            
            if status_code == 201:
                # Created response - include Location header
                location = response_data.get('Created')
                if location:
                    self.send_header("Location", location)
            
            encoded_data = json.dumps(response_data, sort_keys=True, indent=4).encode()
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)
            
        except Exception as e:
            logger.error(f"Error handling LogEntry POST: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            error_response = {"error": str(e)}
            encoded_data = json.dumps(error_response, sort_keys=True, indent=4).encode()
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)

    def _update_parameter_error_message(self, payload, parameter, action):
        """Update error message for parameter value error"""
        extended_info = payload.get('@Message.ExtendedInfo', [])
        for info in extended_info:
            message = info.get('Message', '').replace("%2", action).replace("%1", parameter)
            info['Message'] = message
            msg_args = info.get('MessageArgs', [])
            if len(msg_args) >= 2:
                msg_args[0] = parameter
                msg_args[1] = action

    def _send_json_response(self, payload):
        """Send JSON response"""
        encoded_data = json.dumps(payload, sort_keys=True, indent=4, separators=(",", ": ")).encode()
        self.send_header("Content-Length", len(encoded_data))
        self.end_headers()
        self.wfile.write(encoded_data)

    def _update_error_message(self, payload, action, parameter):
        """Update error message for missing parameter"""
        extended_info = payload.get('@Message.ExtendedInfo', [])
        for info in extended_info:
            message = info.get('Message', '').replace("%1", action).replace("%2", parameter)
            info['Message'] = message
            msg_args = info.get('MessageArgs', [])
            if len(msg_args) >= 2:
                msg_args[0] = action
                msg_args[1] = parameter

    def _update_parameter_error_message(self, payload, parameter, action):
        """Update error message for parameter value error"""
        extended_info = payload.get('@Message.ExtendedInfo', [])
        for info in extended_info:
            message = info.get('Message', '').replace("%2", action).replace("%1", parameter)
            info['Message'] = message
            msg_args = info.get('MessageArgs', [])
            if len(msg_args) >= 2:
                msg_args[0] = parameter
                msg_args[1] = action

    def _update_not_in_list_error_message(self, payload, value, parameter, action):
        """Update error message for value not in list"""
        extended_info = payload.get('@Message.ExtendedInfo', [])
        for info in extended_info:
            message = (info.get('Message', '')
                      .replace("%3", action)
                      .replace("%2", parameter)
                      .replace("%1", value))
            info['Message'] = message
            msg_args = info.get('MessageArgs', [])
            if len(msg_args) >= 3:
                msg_args[0] = value
                msg_args[1] = parameter
                msg_args[2] = action

    def _update_not_supported_error_message(self, payload, parameter, action):
        """Update error message for not supported parameter"""
        extended_info = payload.get('@Message.ExtendedInfo', [])
        for info in extended_info:
            message = info.get('Message', '').replace("%2", action).replace("%1", parameter)
            info['Message'] = message
            msg_args = info.get('MessageArgs', [])
            if len(msg_args) >= 2:
                msg_args[0] = parameter
                msg_args[1] = action