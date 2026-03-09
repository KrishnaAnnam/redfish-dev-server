# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
File and path utility functions for Redfish Mockup Server
"""

import os
import json
from .helpers import clean_path


def construct_path(mock_dir, path, filename, short_form=False):
    """Construct file path for mockup resource
    
    :param mock_dir: base mockup directory
    :param path: resource path
    :param filename: filename to append
    :param short_form: whether to use short form
    :return: constructed file path
    """
    apath = mock_dir
    rpath = clean_path(path, short_form)
    return '/'.join([apath, rpath, filename]) if filename not in ['', None] else '/'.join([apath, rpath])


def get_cached_link(cached_links, path):
    """Get cached link data or load from file
    
    :param cached_links: dictionary of cached links
    :param path: file path to check
    :return: tuple (success, data)
    """
    if path not in cached_links:
        if os.path.isfile(path):
            with open(path) as f:
                json_data = json.load(f)
                f.close()
        else:
            json_data = None
    else:
        json_data = cached_links[path]
    return json_data is not None and json_data != '404', json_data


def send_header_file(handler, fpath):
    """Send headers from headers.json file
    
    :param handler: HTTP handler instance
    :param fpath: path to headers.json file
    """
    dont_send = ["connection", "keep-alive", "content-length", "transfer-encoding"]
    with open(fpath) as headers_data:
        d = json.load(headers_data)
    if isinstance(d.get("GET"), dict):
        for k, v in d["GET"].items():
            if k.lower() not in dont_send:
                handler.send_header(k, v)