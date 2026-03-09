#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
OEM Actions Service - stub module.
OEM-specific actions have been migrated to the plugin system.
This module is retained for backwards compatibility.
"""


class OEMActionsService:
    """Stub OEM actions service. Functionality moved to plugin system."""

    def __init__(self, config=None):
        pass

    def handle_oem_action(self, path, body):
        return None
