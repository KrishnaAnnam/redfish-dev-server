# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
PUT request handler for Redfish Mockup Server
"""

import json
import logging
from .base_handler import BaseRedfishHandler

logger = logging.getLogger(__name__)


class PutHandler(BaseRedfishHandler):
    """Handler for PUT requests"""

    def do_PUT(self):
        """Handle PUT request"""
        if not self._check_auth():
            self._send_unauthorized()
            return

        logger.info("PUT: Headers: {}".format(self.headers))
        self.try_to_sleep('PUT', self.path)

        data_received = None
        if "content-length" in self.headers:
            lenn = int(self.headers["content-length"])
            try:
                data_received = json.loads(self.rfile.read(lenn).decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                print('Decoding JSON has failed, sending 400')
                data_received = None
            
            if data_received:
                logger.info("PUT: Data: {}".format(data_received))

        # PUT is not supported in this mockup server implementation
        # Return 405 Method Not Allowed
        self.send_response(405)
        self.end_headers()