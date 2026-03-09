# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/main/LICENSE.md

"""
Utility functions for Redfish Mockup Server
"""

import collections.abc


def dict_merge(dct, merge_dct):
    """
    https://gist.github.com/angstwad/bf22d1822c38a92ec0a9 modified
    Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k in merge_dct:
        if (k in dct and isinstance(dct[k], dict) and isinstance(merge_dct[k], collections.abc.Mapping)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


def clean_path(path, is_short):
    """Clean and normalize path
    
    :param path: URL path to clean
    :param is_short: whether to use short form (remove /redfish/v1)
    :return: cleaned path
    """
    path = path.strip("/")
    path = path.split("?", 1)[0]
    path = path.split("#", 1)[0]
    if is_short:
        path = path.replace("redfish/v1", "").strip("/")
    return path