# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
GET request handler for BMC Redfish Simulator
Based on DMTF Redfish-Mockup-Server
"""

import os
import json
import re
import logging
from urllib.parse import urlparse, urlunparse, parse_qs
from .base_handler import BaseRedfishHandler

logger = logging.getLogger(__name__)


class GetHandler(BaseRedfishHandler):
    """Handler for GET requests"""

    def do_GET(self):
        """Handle GET request"""
        if not self._check_auth():
            self._send_unauthorized()
            return

        # Construct file paths
        fpath = self.construct_path(self.path, 'index.json')
        fpath_xml = self.construct_path(self.path, 'index.xml')
        fpath_headers = self.construct_path(self.path, 'headers.json')
        fpath_direct = self.construct_path(self.path, '')

        success, payload = self.get_cached_link(fpath)
        scheme, netloc, path, params, query, fragment = urlparse(self.path)
        query_pieces = parse_qs(query, keep_blank_values=True)

        self.try_to_sleep('GET', self.path)

        # Handle RAS service requests
        if self.path.startswith('/redfish/v1/RASService'):
            result = self.ras_service.handle_get(self.path)
            if result:
                if isinstance(result, tuple):
                    status_code, headers, response_data = result
                    self.send_response(status_code)
                    for header_name, header_value in headers.items():
                        self.send_header(header_name, header_value)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("OData-Version", "4.0")
                    encoded_data = json.dumps(response_data, sort_keys=True, indent=4, separators=(",", ": ")).encode()
                    self.send_header("Content-Length", len(encoded_data))
                    self.end_headers()
                    self.wfile.write(encoded_data)
                else:
                    # Fallback for simple response format
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("OData-Version", "4.0")
                    encoded_data = json.dumps(result, sort_keys=True, indent=4, separators=(",", ": ")).encode()
                    self.send_header("Content-Length", len(encoded_data))
                    self.end_headers()
                    self.wfile.write(encoded_data)
                return

        # Handle special cases for shortForm
        if self.path == '/' and self.server.config.short_form:
            self.send_response(404)
            self.end_headers()
            return

        if self.path in ['/redfish', '/redfish/'] and self.server.config.short_form:
            self._handle_redfish_root()
            return

        # Handle existing resources
        if success:
            self._handle_json_resource(payload, fpath_headers, query_pieces, path)
        elif os.path.isfile(fpath_xml):
            self._handle_xml_resource(fpath_xml)
        elif os.path.isfile(fpath_direct):
            self._handle_direct_file(fpath_direct)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_redfish_root(self):
        """Handle /redfish root endpoint for shortForm"""
        self.send_response(200)
        fpath_headers = self.construct_path('/redfish', 'headers.json')
        
        if self.server.config.headers and os.path.isfile(fpath_headers):
            self.send_header_file(fpath_headers)
        else:
            self.send_header("Content-Type", "application/json")
            self.send_header("OData-Version", "4.0")

        encoded_data = json.dumps({'v1': '/redfish/v1'}, indent=4).encode()

        if not (self.server.config.headers and os.path.isfile(fpath_headers)):
            self.send_header("Content-Length", len(encoded_data))
        
        self.end_headers()
        self.wfile.write(encoded_data)

    def _handle_json_resource(self, payload, fpath_headers, query_pieces, path):
        """Handle JSON resource responses"""
        self.send_response(200)
        
        if self.server.config.headers and os.path.isfile(fpath_headers):
            self.send_header_file(fpath_headers)
        else:
            self.send_header("Content-Type", "application/json")
            self.send_header("OData-Version", "4.0")

        # Process payload
        output_data = payload.copy()
        output_data.pop("@Redfish.Copyright", None)

        # Handle EventService subscriptions
        if 'EventService/Subscriptions' in self.path:
            if output_data.get('HttpHeaders') is not None:
                output_data['HttpHeaders'] = []

        # Handle query parameters
        self._process_query_parameters(output_data, query_pieces, path)
        
        # Handle expand query
        self._handle_expand_query(output_data, query_pieces)

        encoded_data = json.dumps(output_data, sort_keys=True, indent=4, separators=(",", ": ")).encode()

        if not (self.server.config.headers and os.path.isfile(fpath_headers)):
            self.send_header("Content-Length", len(encoded_data))
        
        self.end_headers()
        self.wfile.write(encoded_data)

    def _process_query_parameters(self, output_data, query_pieces, path):
        """Process OData query parameters"""
        if output_data.get('Members') is not None:
            my_members = output_data['Members']
            top_count = int(query_pieces.get('$top', [str(len(my_members))])[0])
            top_skip = int(query_pieces.get('$skip', ['0'])[0])

            my_members = my_members[top_skip:]
            
            if top_count < len(my_members):
                my_members = my_members[:top_count]
                query_out = {'$skip': top_skip + top_count, '$top': top_count}
                query_string = '&'.join([f'{k}={v}' for k, v in query_out.items()])
                output_data['Members@odata.nextLink'] = urlunparse(('', '', path, '', query_string, ''))

            output_data['Members'] = my_members

    def _handle_expand_query(self, output_data, query_pieces):
        """Handle $expand query parameter"""
        expand_str = query_pieces.get('$expand', [''])[0]
        expand = re.match(r'([\.\~\*])(\(\$levels=(\d+)\))?', expand_str)
        
        if expand:
            regex_groups = expand.groups()
            expand_type = regex_groups[0]
            levels = int(regex_groups[2]) if regex_groups[1] else 1
            self.handle_expand_query(output_data, expand_type, levels)

    def handle_expand_query(self, data, expand_type, levels):
        """Expand the data based on Redfish $expand spec"""
        stack = [(data, levels)]
        
        while stack:
            current_data, expand_level = stack.pop()
            
            if expand_level < 1:
                continue

            for key, value in current_data.items():
                if not isinstance(value, (list, dict)):
                    continue

                # Skip "Links" for '.' expand type
                if expand_type == '.' and key == 'Links':
                    continue

                if isinstance(value, dict):
                    expanded = False
                    odata_id = self.check_if_dict_is_odata_id_only(value)
                    
                    if odata_id:
                        path = self.construct_path(odata_id, 'index.json')
                        res, response_data = self.get_cached_link(path)
                        if res:
                            response_data.pop('@Redfish.Copyright', None)
                            current_data[key] = response_data
                            expanded = True
                    
                    remove_level = 1 if expanded else 0
                    stack.append((current_data[key], expand_level - remove_level))
                
                else:  # list
                    for index, array_item in enumerate(value):
                        if isinstance(array_item, dict):
                            expanded = False
                            odata_id = self.check_if_dict_is_odata_id_only(array_item)
                            
                            if odata_id:
                                path = self.construct_path(odata_id, 'index.json')
                                res, response_data = self.get_cached_link(path)
                                if res:
                                    response_data.pop('@Redfish.Copyright', None)
                                    value[index] = response_data
                                    expanded = True
                            
                            remove_level = 1 if expanded else 0
                            stack.append((value[index], expand_level - remove_level))
                    
                    current_data[key] = value

    def _handle_xml_resource(self, fpath_xml):
        """Handle XML resource responses"""
        with open(fpath_xml, "r") as f:
            content = f.read()
        
        self.send_response(200)
        self.send_header("Content-Type", "application/xml;charset=utf-8")
        self.send_header("OData-Version", "4.0")
        self.end_headers()
        self.wfile.write(content.encode())

    def _handle_direct_file(self, fpath_direct):
        """Handle direct file responses"""
        self.send_response(200)
        
        with open(fpath_direct, 'rb') as f:
            content = f.read()
        
        try:
            decoded_content = content.decode()
            # Text file
            file_extension = os.path.splitext(fpath_direct)[1]
            mime_type = "text/plain" if file_extension == "" else f"application/{file_extension[1:]}"
            
            self.send_header("Content-Type", f"{mime_type};charset=utf-8")
            self.send_header("OData-Version", "4.0")
            self.end_headers()
            self.wfile.write(decoded_content.encode("utf-8"))
        
        except ValueError:
            # Binary file
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("OData-Version", "4.0")
            self.end_headers()
            self.wfile.write(content)

    def do_HEAD(self):
        """Handle HEAD request"""
        logger.info("Headers: ")
        logger.info(self.server.config.headers)

        fpath = self.construct_path(self.path, 'index.json')
        fpath_xml = self.construct_path(self.path, 'index.xml')
        fpath_headers = self.construct_path(self.path, 'headers.json')
        fpath_direct = self.construct_path(self.path, '')

        if self.server.config.headers and os.path.isfile(fpath_headers):
            self.send_response(200)
            self.send_header_file(fpath_headers)
        elif not self.server.config.headers or not os.path.isfile(fpath_headers):
            if self.get_cached_link(fpath)[0]:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("OData-Version", "4.0")
            elif os.path.isfile(fpath_xml) or os.path.isfile(fpath_direct):
                file_extension = 'xml' if os.path.isfile(fpath_xml) else os.path.splitext(fpath_direct)[1].strip('.')
                self.send_response(200)
                self.send_header("Content-Type", f"application/{file_extension};charset=utf-8")
                self.send_header("OData-Version", "4.0")
            else:
                self.send_response(404)
        else:
            self.send_response(404)
        
        self.end_headers()