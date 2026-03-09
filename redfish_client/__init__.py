# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Redfish Client Library
=====================

A comprehensive Python library for interacting with Redfish-enabled BMCs.

Main Components:
- RedfishClient: Core client for BMC interaction
- RedfishMonitoringClient: Advanced monitoring and alerting
- Examples: Usage examples and demonstrations
- Tests: Test suite for validation
- Tools: Utilities including web dashboard

Usage:
    from redfish_client import RedfishClient
    
    client = RedfishClient("https://bmc.example.com")
    client.connect()
    client.login("admin", "password")
    systems = client.get_systems()
    client.logout()
"""

# Import main classes for easy access
from .client import (
    RedfishClient,
    RedfishResource, 
    EventSubscription,
    RedfishClientError,
    AuthenticationError,
    ResourceNotFoundError,
    OperationError,
    SessionState
)

from .monitoring import (
    RedfishMonitoringClient,
    SystemMetrics,
    HealthAlert
)

__version__ = "1.0.0"
__author__ = "DMTF Redfish Team"

__all__ = [
    'RedfishClient',
    'RedfishResource',
    'EventSubscription', 
    'RedfishClientError',
    'AuthenticationError',
    'ResourceNotFoundError',
    'OperationError',
    'SessionState',
    'RedfishMonitoringClient',
    'SystemMetrics',
    'HealthAlert'
]