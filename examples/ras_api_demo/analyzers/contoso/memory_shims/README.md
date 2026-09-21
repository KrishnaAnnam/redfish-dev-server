# Contoso Memory-Vendor Shim Interface

Memory-vendor shims receive decoded, newest-first memory events and return
source-referenced requests for Contoso SoC actions. They do not receive binary
CPER data and do not construct CPAD envelopes or proprietary binary action
sections.

## Discovery

A shim is a Python file named `analyzer_*.py` in this directory. It declares:

```python
SHIM_INFO = {
    "api_version": 2,
    "name": "Example Memory Analyzer",
    "version": "1.0.0",
    "dram_manufacturer_ids": [[0x80, 0x2C]],
}
```

The Contoso analyzer invokes:

```python
def analyze_memory_events(events: list[dict]) -> list[dict]:
    ...
```

Inputs are deep-copied before invocation.

## Event Source Reference

Every event begins with:

```python
{
    "cper_file": "/path/to/original.cper",
    "section_index": 0,
    "event_type": "memory_error",
    ...
}
```

`cper_file` identifies the original binary CPER. `section_index` identifies the
zero-based section within that record. Both fields are present for
`memory_error` and `platform_action` events.

The full decoded memory data remains available under `memory_error`, including
the address, chiplet/controller, DIMM coordinates, DRAM manufacturer,
temperature, and repair history.

## Action Requests

A shim returns zero or more dictionaries with exactly this shape:

```python
{
    "cper_file": "/path/to/original.cper",
    "section_index": 0,
    "action_id": "0x8001",
    "confidence": 90,
    "parameters": {
        "ppr_type": 0x01,
    },
}
```

Rules:

- `cper_file` and `section_index` must identify one input `memory_error`.
- `action_id` must be a supported Contoso remediation action.
- `confidence` is an integer from 0 through 100.
- `parameters` is an action-specific object.
- Returning `[]` means analysis succeeded and no action is recommended.
- Raising an exception means the shim failed; default Contoso analysis may run.

The Contoso analyzer builds the complete CPAD, including the target platform,
most recent error PartitionID, CreatorID, FRU, shared action-parameter section,
and binary encoding.

## Supported Requests

### Post Package Repair: `0x8001`

```python
{
    "ppr_type": 0x01,
}
```

The referenced memory-error section supplies chiplet, controller, channel,
DIMM, subchannel, rank, DRAM device, bank group, bank, and row.

| Value | Type |
| --- | --- |
| `0x01` | Runtime soft PPR |
| `0x02` | Boot-time soft PPR |
| `0x04` | Boot-time hard PPR |

The values match the `memory_repair_capabilities` bits in Contoso memory CPERs.

### Page Offline: `0x8002`

```python
{
    "page_ranges": [
        {
            "start_address": 0x0000000012345000,
            "page_count": 1,
        }
    ]
}
```

Each address must be below `2^52` and aligned to 4 KiB. Page counts must be
positive. Ranges may overlap or be adjacent in the shim request; the Contoso
analyzer sorts and combines them before choosing the smallest PFN-list, range,
or bitmap wire encoding. Very large requests may produce several CPADs sharing
one batch ID.

### Reboot with Memory Retraining: `0x8003`

```python
{}
```

The action applies to the CPAD PartitionID and therefore needs no additional
payload.

## Example

```python
def analyze_memory_events(events):
    newest_error = next(
        event for event in events
        if event["event_type"] == "memory_error"
        and event["source"]["is_newest"]
    )
    if newest_error["spd_temperature"] < 85:
        return []
    return [{
        "cper_file": newest_error["cper_file"],
        "section_index": newest_error["section_index"],
        "action_id": "0x8001",
        "confidence": 90,
        "parameters": {"ppr_type": 0x02},
    }]
```

See [Contoso CPAD Actions](../contoso-cpad-actions.md) for the binary
action-parameter layouts and completion timing.
