"""Stub shim for SK Hynix memory-vendor analysis."""

SHIM_INFO = {
    "api_version": 1,
    "name": "SK Hynix Memory Analyzer Shim",
    "version": "0.1.0",
    "dram_manufacturer_ids": [[0x80, 0xAD]],
}


def analyze_memory_events(events):
    """Accept decoded memory events; vendor analysis will be added later."""
    return []
