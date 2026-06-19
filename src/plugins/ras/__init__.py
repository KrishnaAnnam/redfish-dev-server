# RAS Plugin Package

"""
Reliability, Availability, and Serviceability (RAS) Plugin for BMC Redfish Simulator
"""

from .plugin import RASPlugin, get_plugin, register_plugin
from .provider import RASHandler, ManagerOEMInjector

__all__ = [
    'RASPlugin',
    'get_plugin',
    'register_plugin',
    'RASHandler',
    'ManagerOEMInjector',
]

__version__ = "1.0.0"
__plugin_name__ = "ras"
