# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Main Redfish Mockup Server Handler
This module combines all HTTP method handlers into a single class.
"""

from .get_handler import GetHandler
from .post_handler import PostHandler
from .patch_handler import PatchHandler
from .put_handler import PutHandler
from .delete_handler import DeleteHandler


class RedfishMockupHandler(GetHandler, PostHandler, PatchHandler, PutHandler, DeleteHandler):
    """
    Combined Redfish Mockup Server Handler
    
    This class inherits from all individual HTTP method handlers to provide
    a complete implementation of the Redfish Mockup Server functionality.
    """
    
    def __init__(self, request, client_address, server):
        """Initialize the handler with all method capabilities"""
        # Initialize the base class which sets up all the services
        super().__init__(request, client_address, server)
    
    def log_message(self, format, *args):
        """Override log message to control server output"""
        # You can customize logging behavior here
        # For now, we'll use the default behavior
        super().log_message(format, *args)