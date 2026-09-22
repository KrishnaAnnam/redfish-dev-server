"""Stub shim for Micron memory-vendor analysis."""

SHIM_INFO = {
    "api_version": 3,
    "name": "Micron Memory Analyzer Shim",
    "version": "0.1.0",
    "dram_manufacturer_ids": [[0x80, 0x2C]],
}


def analyze_memory_events(events):
    """Return source-referenced Contoso action requests for decoded events."""
    return []
