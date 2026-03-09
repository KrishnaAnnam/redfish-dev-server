# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Configuration settings for Redfish Mockup Server
"""

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class ServerConfig:
    """Server configuration settings"""
    hostname: str = '127.0.0.1'
    port: int = 8000
    mock_dir_path: Optional[str] = None
    test_etag: bool = False
    headers: bool = False
    response_time: float = 0.0
    time_from_json: bool = False
    ssl_mode: bool = False
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    short_form: bool = False
    ssdp_start: bool = False
    mock_dir: Optional[str] = None
    tool_version: str = "2.0.0"

    def __post_init__(self):
        """Post-initialization processing"""
        # Set default mockup path if none specified
        if self.mock_dir_path is None:
            self.mock_dir_path = 'public-rackmount1'
            self.short_form = True
        
        # Create full path to mockup directory
        self.mock_dir = os.path.realpath(self.mock_dir_path)

    def validate(self):
        """Validate configuration settings"""
        # Validate mockup directory
        if not self.short_form:
            slash_redfish_dir = os.path.join(self.mock_dir, "redfish")
            if not os.path.isdir(slash_redfish_dir):
                raise ValueError("Invalid Mockup Directory--no /redfish directory at top")
        
        if self.short_form:
            if not os.path.isdir(self.mock_dir) or not os.path.isfile(os.path.join(self.mock_dir, "index.json")):
                raise ValueError("Invalid Mockup Directory--dir or index.json does not exist")
        
        # Validate response time
        try:
            float(self.response_time)
        except ValueError:
            raise ValueError("Response time must be a valid number")
        
        # Validate SSL settings
        if self.ssl_mode and (not self.ssl_cert or not self.ssl_key):
            raise ValueError("SSL mode requires both certificate and key files")


def parse_arguments():
    """Parse command line arguments and return ServerConfig"""
    parser = argparse.ArgumentParser(description='Serve a static Redfish mockup.')
    parser.add_argument('-H', '--host', '--Host', default='127.0.0.1',
                        help='hostname or IP address (default 127.0.0.1)')
    parser.add_argument('-p', '--port', '--Port', default=8000, type=int,
                        help='host port (default 8000)')
    parser.add_argument('-D', '--dir', '--Dir',
                        help='path to mockup dir (may be relative to CWD)')
    parser.add_argument('-E', '--test-etag', '--TestEtag',
                        action='store_true',
                        help='(unimplemented) etag testing')
    parser.add_argument('-X', '--headers', action='store_true',
                        help='load headers from headers.json files in mockup')
    parser.add_argument('-t', '--time', default=0,
                        help='delay in seconds added to responses (float or int)')
    parser.add_argument('-T', action='store_true',
                        help='delay response based on times in time.json files in mockup')
    parser.add_argument('-s', '--ssl', action='store_true',
                        help='place server in SSL (HTTPS) mode; requires a cert and key')
    parser.add_argument('--cert', help='the certificate for SSL')
    parser.add_argument('--key', help='the key for SSL')
    parser.add_argument('-S', '--short-form', '--shortForm', action='store_true',
                        help='apply short form to mockup (omit filepath /redfish/v1)')
    parser.add_argument('-P', '--ssdp', action='store_true',
                        help='make mockup SSDP discoverable')

    args = parser.parse_args()
    
    return ServerConfig(
        hostname=args.host,
        port=args.port,
        mock_dir_path=args.dir,
        test_etag=args.test_etag,
        headers=args.headers,
        response_time=float(args.time),
        time_from_json=args.T,
        ssl_mode=args.ssl,
        ssl_cert=args.cert,
        ssl_key=args.key,
        short_form=args.short_form,
        ssdp_start=args.ssdp
    )