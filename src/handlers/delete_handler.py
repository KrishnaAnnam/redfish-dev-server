# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
DELETE request handler for Redfish Mockup Server
"""

import json
import logging
import os
from .base_handler import BaseRedfishHandler

logger = logging.getLogger(__name__)


class DeleteHandler(BaseRedfishHandler):
    """Handler for DELETE requests"""

    def do_DELETE(self):
        """Handle DELETE request"""
        if not self._check_auth():
            self._send_unauthorized()
            return

        logger.info("DELETE: Headers: {}".format(self.headers))
        self.try_to_sleep('DELETE', self.path)

        # Get paths for resource and its parent collection
        fpath = self.construct_path(self.path, 'index.json')
        ppath = '/'.join(self.path.split('/')[:-1])
        parent_path = self.construct_path(ppath, 'index.json')

        success, payload = self.get_cached_link(fpath)

        # Check if resource exists
        if success:
            # Check if parent is a collection (has Members)
            success, parent_data = self.get_cached_link(parent_path)

            if success and isinstance(parent_data, dict) and parent_data.get('Members') is not None:
                # Mark resource as deleted (404)
                self.cached_links[fpath] = '404'

                # Remove from parent collection
                parent_data['Members'] = [
                    x for x in parent_data['Members']
                    if x.get('@odata.id') != self.path
                ]
                parent_data['Members@odata.count'] = len(parent_data['Members'])

                # Update cached parent collection
                self.cached_links[parent_path] = parent_data

                # Persist the updated parent collection to disk so that stale
                # entries do not reappear after a simulator restart.
                try:
                    with open(parent_path, 'w') as f:
                        json.dump(parent_data, f, indent=4, separators=(',', ':'))
                except OSError as exc:
                    logger.warning("DELETE: could not write parent collection to disk: %s", exc)

                # Remove the resource file itself so it cannot be reloaded
                # from disk on the next simulator start.
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        resource_dir = os.path.dirname(fpath)
                        if os.path.isdir(resource_dir) and not os.listdir(resource_dir):
                            os.rmdir(resource_dir)
                except OSError as exc:
                    logger.warning("DELETE: could not remove resource file from disk: %s", exc)

                # Invalidate session token when a Session resource is deleted
                if 'SessionService/Sessions/' in self.path:
                    session_path = self.path.rstrip('/')
                    for token, info in list(self.active_sessions.items()):
                        if info.get('SessionPath', '').rstrip('/') == session_path:
                            del self.active_sessions[token]
                            logger.info("Invalidated session token for %s", session_path)
                            break

                # 204 No Content — no body
                self.send_response(204)
                self.end_headers()
            else:
                # Parent is not a collection — method not allowed
                self._send_error(405, "OperationNotAllowed",
                                 "DELETE is not allowed on this resource.")
        else:
            # Resource not found
            self._send_error(404, "ResourceNotFound",
                             f"The resource at '{self.path}' was not found.")

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _send_error(self, status_code, message_id, message):
        """Send a minimal Redfish-compliant error response."""
        body = json.dumps({
            "error": {
                "code": f"Base.1.5.0.{message_id}",
                "message": message,
                "@Message.ExtendedInfo": [{
                    "@odata.type": "#Message.v1_1_1.Message",
                    "MessageId": f"Base.1.5.0.{message_id}",
                    "Message": message,
                    "Severity": "Critical",
                    "Resolution": "See the Redfish specification for allowed operations."
                }]
            }
        }, indent=4).encode()
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)