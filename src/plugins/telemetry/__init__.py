# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
# Telemetry Plugin Package
"""
Telemetry Plugin for BMC Simulator

This plugin provides:
- Metric report collection and management
- Metric report definitions
- Telemetry data submission and streaming
- Subscriber notification for metric reports

Usage:
    Enable in platform config:
    
    platform:
      extensions:
        - telemetry
"""

from .telemetry_service import TelemetryServiceHandler
from .plugin import TelemetryPlugin, get_plugin

__all__ = ['TelemetryServiceHandler', 'TelemetryPlugin', 'get_plugin']
