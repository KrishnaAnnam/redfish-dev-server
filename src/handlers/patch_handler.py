# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Enhanced PATCH Handler with Redfish-Compliant Message Responses
================================================================
PATCH request handler for Redfish Mockup Server with integrated schema validation
and proper Redfish message registry compliance.
"""

import json
import logging
from .base_handler import BaseRedfishHandler
from ..utils.helpers import dict_merge
from ..services.log_entry_service import LogEntryService
from ..services.schema_property_validator import SchemaPropertyValidator
from ..services.redfish_message_service import get_redfish_message_service

logger = logging.getLogger(__name__)


class PatchHandler(BaseRedfishHandler):
    """Enhanced PATCH Handler with Redfish-compliant message responses"""
    
    def __init__(self, *args, **kwargs):
        # These must be set BEFORE super().__init__() because
        # BaseHTTPRequestHandler.__init__ → handle() → do_PATCH() runs
        # during the super() call, before the lines below would execute.
        self._schema_validator = None
        self._message_service = None
        self._log_entry_service = None
        super().__init__(*args, **kwargs)
    
    @property
    def schema_validator(self):
        """Lazy initialization of schema validator"""
        if self._schema_validator is None:
            self._schema_validator = SchemaPropertyValidator(self.server.config)
        return self._schema_validator
    
    @schema_validator.setter  
    def schema_validator(self, value):
        """Allow setting the schema validator for testing or dependency injection"""
        self._schema_validator = value
    
    @property
    def message_service(self):
        """Lazy initialization of message service"""
        if self._message_service is None:
            self._message_service = get_redfish_message_service(self.server.config)
        return self._message_service
    
    @message_service.setter
    def message_service(self, value):
        """Allow setting the message service for testing or dependency injection"""
        self._message_service = value
    
    @property
    def patch_log_entry_service(self):
        """Lazy initialization of log entry service for PATCH operations"""
        if self._log_entry_service is None:
            self._log_entry_service = LogEntryService(self.server.config)
        return self._log_entry_service
    
    @patch_log_entry_service.setter
    def patch_log_entry_service(self, value):
        """Allow setting the log entry service for testing or dependency injection"""
        self._log_entry_service = value

    def do_PATCH(self):
        """Handle PATCH request"""
        if not self._check_auth():
            self._send_unauthorized()
            return

        logger.info("PATCH: Headers: {}".format(self.headers))
        self.try_to_sleep('PATCH', self.path)

        data_received = None
        if "content-length" in self.headers:
            lenn = int(self.headers["content-length"])
            try:
                data_received = json.loads(self.rfile.read(lenn).decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                print('Decoding JSON has failed, sending 400')
                data_received = None

        if data_received:
            logger.info("PATCH: Data: {}".format(data_received))
            
            # Handle LogEntry PATCH requests
            if "LogServices" in self.path and "/Entries/" in self.path and not self.path.endswith("/Entries"):
                self._handle_log_entry_patch(data_received)
                return
            
            # Construct path for resource
            fpath = self.construct_path(self.path, 'index.json')
            success, payload = self.get_cached_link(fpath)

            # Check if resource exists
            if success:
                # If this is a collection, return 405 Method Not Allowed
                if payload.get('Members') is not None:
                    self._send_patch_error(405, "OperationNotAllowed",
                                          "PATCH is not allowed on collections.")
                    return
                else:
                    # Perform schema-based property validation inside a try/except
                    # so that lazy-init failures never crash the request thread.
                    try:
                        resource_type = self._extract_resource_type(payload)
                        is_valid, validation_errors, filtered_data = self.schema_validator.validate_patch_properties(
                            resource_type, payload, data_received
                        )
                    except Exception as exc:
                        logger.error("PATCH: schema validation raised: %s", exc)
                        self._send_patch_error(500, "InternalError",
                                              f"Internal error during validation: {exc}")
                        return

                    if not is_valid:
                        # Create Redfish-compliant error response
                        try:
                            error_response, status_code = self.message_service.create_validation_error_response(
                                validation_errors, 400
                            )
                        except Exception as exc:
                            logger.error("PATCH: message service raised: %s", exc)
                            self._send_patch_error(500, "InternalError",
                                                  f"Internal error building error response: {exc}")
                            return
                        
                        self.send_response(status_code)
                        self.send_header("Content-Type", "application/json")
                        encoded_data = json.dumps(error_response, sort_keys=True, indent=4).encode()
                        self.send_header("Content-Length", len(encoded_data))
                        self.end_headers()
                        self.wfile.write(encoded_data)
                        
                        logger.warning(f"PATCH validation failed for {fpath}: {validation_errors}")
                        return
                    
                    # Use filtered data (only valid writable properties)
                    logger.info(self.headers.get('content-type'))
                    logger.info("Original payload: {}".format(payload))
                    logger.info("Validated data to merge: {}".format(filtered_data))
                    
                    # Merge the validated data into existing payload
                    dict_merge(payload, filtered_data)
                    
                    logger.info("Merged payload: {}".format(payload))
                    
                    # Store in cached links for future requests
                    self.cached_links[fpath] = payload
                    
                    # Create success response with optional ExtendedInfo
                    success_messages = []
                    if len(filtered_data) < len(data_received):
                        # Some properties were filtered out, inform the client
                        filtered_count = len(data_received) - len(filtered_data)
                        info_msg = f"{filtered_count} properties were not applied due to validation constraints."
                        success_messages.append(info_msg)
                    
                    # Return 204 No Content for successful PATCH (per Redfish spec)
                    self.send_response(204)
                    
                    # Add ExtendedInfo header if there are informational messages
                    if success_messages:
                        success_response = self.message_service.create_success_response(
                            additional_messages=[
                                {
                                    "@odata.type": "#Message.v1_1_1.Message", 
                                    "MessageId": "Base.1.5.0.Success",
                                    "Message": msg,
                                    "Severity": "OK",
                                    "Resolution": "None"
                                } for msg in success_messages
                            ]
                        )
                        
                        # Include ExtendedInfo as header for 204 responses (per Redfish spec)
                        extended_info_header = json.dumps(success_response.get("@Message.ExtendedInfo", []))
                        self.send_header("X-ExtendedInfo", extended_info_header)
                    
                    self.end_headers()
                    
                    logger.info(f"PATCH applied successfully to {fpath}. Properties updated: {list(filtered_data.keys())}")
                    return
            else:
                # Resource not found - return Redfish-compliant error
                error_response, status_code = self.message_service.create_validation_error_response(
                    [f"Resource at path '{fpath}' was not found"], 404
                )
                
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                encoded_data = json.dumps(error_response, sort_keys=True, indent=4).encode()
                self.send_header("Content-Length", len(encoded_data))
                self.end_headers()
                self.wfile.write(encoded_data)
                
                logger.warning(f"PATCH failed - resource not found: {fpath}")
                return
        else:
            # Bad request - no valid JSON received
            try:
                error_response, status_code = self.message_service.create_validation_error_response(
                    ["Request body contains malformed JSON or is empty"], 400
                )
            except Exception as exc:
                logger.error("PATCH: message service raised: %s", exc)
                self._send_patch_error(400, "MalformedJSON",
                                      "Request body is empty or contains malformed JSON.")
                return

            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            encoded_data = json.dumps(error_response, sort_keys=True, indent=4).encode()
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)

    def _send_patch_error(self, status_code, message_id, message):
        """Send a minimal Redfish-compliant error response for PATCH failures."""
        body = json.dumps({
            "error": {
                "code": f"Base.1.5.0.{message_id}",
                "message": message,
                "@Message.ExtendedInfo": [{
                    "@odata.type": "#Message.v1_1_1.Message",
                    "MessageId": f"Base.1.5.0.{message_id}",
                    "Message": message,
                    "Severity": "Critical",
                    "Resolution": "Correct the request and resubmit."
                }]
            }
        }, indent=4).encode()
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _extract_resource_type(self, resource_data: dict) -> str:
        """Extract Redfish resource type from @odata.type field"""
        odata_type = resource_data.get("@odata.type", "")
        
        # Extract type from @odata.type (e.g., "#ComputerSystem.v1_17_0.ComputerSystem" -> "ComputerSystem")
        if odata_type.startswith("#"):
            # Remove # and version info
            type_part = odata_type[1:].split(".")[0]
            return type_part
        
        # Fallback: try to determine from path or resource structure
        if "Members" in resource_data:
            return "Collection"  # Generic collection
        
        # Try to infer from common properties
        if "PowerState" in resource_data and "ProcessorSummary" in resource_data:
            return "ComputerSystem"
        elif "ManagerType" in resource_data:
            return "Manager"
        elif "ChassisType" in resource_data:
            return "Chassis"
        elif "InterfaceEnabled" in resource_data and "LinkStatus" in resource_data:
            return "EthernetInterface"
        elif "EntryType" in resource_data and ("Created" in resource_data or "Severity" in resource_data):
            return "LogEntry"
        elif "AttributeRegistry" in resource_data:
            return "Bios"
        elif "UserName" in resource_data and "RoleId" in resource_data:
            return "ManagerAccount"
        
        # Default fallback
        logger.warning(f"Could not determine resource type from data: {odata_type}")
        return "Unknown"

    def _handle_log_entry_patch(self, data_received):
        """Handle PATCH request to LogEntry resource"""
        try:
            status_code, response_data = self.patch_log_entry_service.handle_patch_log_entry(
                self.path, data_received, self.cached_links
            )
            
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            
            encoded_data = json.dumps(response_data, sort_keys=True, indent=4).encode()
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)
            
        except Exception as e:
            logger.error(f"Error handling LogEntry PATCH: {e}")
            
            # Create Redfish-compliant error response
            error_response, status_code = self.message_service.create_validation_error_response(
                [f"Internal error occurred while processing PATCH request: {str(e)}"], 500
            )
            
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            encoded_data = json.dumps(error_response, sort_keys=True, indent=4).encode()
            self.send_header("Content-Length", len(encoded_data))
            self.end_headers()
            self.wfile.write(encoded_data)