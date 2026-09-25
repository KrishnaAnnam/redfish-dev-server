"""Public Contoso analyzer API for demo memory-address translation."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.plugins.ras.memory_address_translation import (  # noqa: E402,F401
    DIMM_ORGANIZATIONS,
    MEMORY_ORGANIZATION_VERSION,
    SUPPORTED_DIMM_SIZES_GIB,
    TRANSLATION_SCHEME,
    ContosoMemoryAddressTranslator,
    DimmOrganization,
    MemoryAddressConfiguration,
    MemoryChannelAddress,
    MemoryOrganization,
    memory_address_to_cacheline_base,
    memory_address_to_physical_address,
    organization_for_size,
    physical_address_to_memory_address,
    physical_cacheline_base,
    physical_page_base,
)


__all__ = [
    "DIMM_ORGANIZATIONS",
    "MEMORY_ORGANIZATION_VERSION",
    "SUPPORTED_DIMM_SIZES_GIB",
    "TRANSLATION_SCHEME",
    "ContosoMemoryAddressTranslator",
    "DimmOrganization",
    "MemoryAddressConfiguration",
    "MemoryChannelAddress",
    "MemoryOrganization",
    "memory_address_to_cacheline_base",
    "memory_address_to_physical_address",
    "organization_for_size",
    "physical_address_to_memory_address",
    "physical_cacheline_base",
    "physical_page_base",
]
