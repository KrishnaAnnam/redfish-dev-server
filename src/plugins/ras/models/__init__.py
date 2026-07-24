"""
RAS Plugin Data Models

Defines data structures for CPAD (Common Platform Action Descriptor),
CPER (Common Platform Error Record), and related RAS entities.
"""

from .cpad_types import (
    CPADHeader,
    CPADSectionDescriptor,
    CPADSection,
    CPADDocument,
    CPERRecord,
)

__all__ = [
    'CPADHeader',
    'CPADSectionDescriptor',
    'CPADSection',
    'CPADDocument',
    'CPERRecord',
]
