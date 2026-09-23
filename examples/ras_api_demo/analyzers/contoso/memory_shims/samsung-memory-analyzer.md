# Samsung Memory Analyzer Adapter

The Samsung shim adapts canonical Contoso memory events to a Samsung-oriented
record model and translates Samsung decisions into complete version 3 Contoso
action requests.

Implementation: [`analyzer_samsung.py`](analyzer_samsung.py)

## Analyzer call contract

The shim calls the Samsung analysis seam as:

```python
result = analyze(records)
```

`records` is a newest-first list containing `memory_error` and
`platform_action` records. A Platform Action record may therefore appear before
the older memory error that caused the action. No configuration object is
passed across the adapter interface.

The number of spare rows per bank is Samsung proprietary data owned by
`analyze()`. It is not read from the Contoso CPER, stored in the adapter, or
included in the records passed to the analyzer.

## Complete memory-error input record

The following example shows every field passed to `analyze()` for a memory
error:

```python
{
    "record_type": "memory_error",
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
        "is_newest": True,
        "window_index": 0,
    },
    "timestamp": "2026-09-23T16:30:00Z",
    "record_id": 1042,
    "cper_severity": "Corrected",
    "platform_id": "990f8820-bd4d-5064-58cc-961a053dea79",
    "partition_id": "22222222-3333-4444-5555-666666666666",
    "creator_id": "11111111-2222-3333-4444-555555555555",
    "fru_id": "75824856-bd36-2cc8-61f4-39bb3276da2a",
    "fru_text": "DIMM A1",
    "error": {
        "bank": "DRAM Errors",
        "id": 1,
        "name": "Corrected Memory ECC Error",
        "severity": "Corrected",
        "address_valid": True,
        "overflow": False,
        "injected": False,
        "ce_count": 12,
        "physical_address": 0x0000001234500000,
    },
    "location": {
        "chiplet": 0,
        "controller": 0,
        "channel": 0,
        "dimm": 1,
        "subchannel": 0,
        "rank": 0,
        "dram_device": 3,
        "bank_group": 2,
        "bank": 3,
        "row": 1234,
        "column": 567,
    },
    "dimm": {
        "serial_number": "SERIAL",
        "part_number": "PART",
        "module_manufacturer_id": [0x04, 0xD5],
        "dram_manufacturer_id": [0x80, 0xCE],
        "spd_temperature_c": 40,
    },
    "ppr": {
        "capability_bits": 0x07,
        "soft_runtime": True,
        "soft_boot_time": True,
        "hard_boot_time": True,
        "target_bank_repair_count": 2,
        "repair_history": [
            {
                "subchannel": 0,
                "rank": 0,
                "device": 3,
                "bank_group": 2,
                "bank": 3,
                "count": 2,
            },
        ],
    },
    "system": {
        "total_memory_bytes": 549755813888,
    },
    "beats": {
        "mask_by_dq": [0x0000, 0x0000, 0x0021, 0x0000],
        "mask_64": 0x0000002100000000,
        "failing_dqs": [2],
        "failing_dq_count": 1,
        "failing_beats_by_dq": {
            2: [0, 5],
        },
        "failing_beat_count": 2,
    },
}
```

Fields copied from absent or invalid CPER fields may be `None`, an empty
string, an empty list, or zero according to the source decoder. The adapter
rejects a memory-error record unless `dimm.dram_manufacturer_id` is
`[0x80, 0xCE]`.

### Memory-error field notes

- `source.cper_file` and `source.section_index` uniquely identify the original
  memory-error section. An action recommendation must reference these exact
  values.
- `source.window_index` is zero for the newest record, one for the next-oldest
  record, and so on.
- `error.severity` is the decoded Contoso proprietary error severity.
  `cper_severity` is the record-level CPER severity.
- `location.dram_device` becomes `parameters.device` in a PPR request.
- `ppr.capability_bits` uses bit `0x01` for runtime soft PPR, `0x02` for
  boot-time soft PPR, and `0x04` for boot-time hard PPR.
- `ppr.target_bank_repair_count` is the count for the exact target tuple
  `(subchannel, rank, device, bank_group, bank)`.
- `ppr.repair_history` contains every repair entry supplied by the endpoint,
  not only the target bank.
- The adapter intentionally does not provide a total or remaining spare-row
  count. The Samsung analyzer combines its proprietary device knowledge with
  `target_bank_repair_count` internally.
- Each `beats.mask_by_dq[dq]` value is a 16-bit beat mask for one DQ. Bit
  `beat` is set when that DQ failed on that beat.
- `beats.mask_64` concatenates the DQ masks with DQ 0 in the least-significant
  16 bits. The remaining fields are derived summaries of the same masks.

## Complete Platform Action Event input record

Platform Action Events tell the analyzer the status of a previously sent CPAD.
The following example shows every field passed for an action result correlated
with an older memory error.  This correlation with an older error is necessary
because Platform Action Events do not have information about the DRAM.  This
means that the only way to steer a Platform Action Event to an memory-vendor-
analyzer is to look at the last CPER from the host that points to the same
FRUID and Fru Text.

```python
{
    "record_type": "platform_action",
    "source": {
        "cper_file": "record-18.cper",
        "section_index": 0,
        "is_newest": True,
        "window_index": 0,
    },
    "timestamp": "2026-09-23T16:35:00Z",
    "record_id": 1043,
    "cper_severity": "Platform Action Event",
    "platform_id": "990f8820-bd4d-5064-58cc-961a053dea79",
    "partition_id": "22222222-3333-4444-5555-666666666666",
    "creator_id": "11111111-2222-3333-4444-555555555555",
    "fru_id": "75824856-bd36-2cc8-61f4-39bb3276da2a",
    "fru_text": "DIMM A1",
    "action": {
        "action_id": "0x8001",
        "return_code": "0x01",
        "return_name": "Failed",
        "reason_code": "0x55",
        "successful": False,
        "additional_context": None,
        "cpad_record_id": "0x0000000000001234",
        "cpad_section_index": 0,
    },
    "correlation": {
        "method": "fru_id_and_text",
        "matched": True,
        "ambiguous": False,
        "source_error_cper": "record-17.cper",
        "source_error_section_index": 2,
    },
    "memory_target": {
        "channel": 0,
        "dimm": 1,
        "subchannel": 0,
        "rank": 0,
        "device": 3,
        "bank_group": 2,
        "bank": 3,
        "row": 1234,
        "column": 567,
        "beat_mask": [0x0000, 0x0000, 0x0021, 0x0000],
        "serial_number": "SERIAL",
        "part_number": "PART",
        "module_manufacturer_id": [0x04, 0xD5],
        "dram_manufacturer_id": [0x80, 0xCE],
        "spd_temperature": 40,
        "total_memory_bytes": 549755813888,
        "memory_repair_capabilities": 0x07,
        "reserved": 0,
        "repairs": [
            {
                "subchannel": 0,
                "rank": 0,
                "device": 3,
                "bank_group": 2,
                "bank": 3,
                "count": 2,
            },
        ],
        "subcomponent": {
            "chiplet": 0,
            "controller": 0,
        },
    },
}
```

Correlation uses exact FRU ID and FRU text. When no older memory error matches:

```python
"correlation": {
    "method": "fru_id_and_text",
    "matched": False,
    "ambiguous": False,
},
"memory_target": None,
```

`ambiguous` is `True` when matching history contains more than one DRAM
manufacturer ID. A matched record adds `source_error_cper` and
`source_error_section_index` and supplies `memory_target`.

## Required Samsung result

`analyze()` must return an object containing exactly these three top-level
fields:

```python
{
    "fault": {
        "mode": "Row",
        "detail": "Single Row",
        "confidence": 92,
        "reason": "Repeated corrected errors on one DRAM row",
    },
    "actions": [],
    "advisories": [],
}
```

`fault` may be `None`. `actions` and `advisories` must be lists. The shim
currently treats `fault` and `advisories` as Samsung-owned diagnostic output;
only `actions` are translated into Contoso action requests.

Every action object must contain exactly:

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "replace_dimm",
    "confidence": 95,
    "parameters": {},
    "reason": "Repair budget exhausted",
}
```

The action rules are:

- `source` must contain exactly `cper_file` and `section_index`.
- `source` must identify a `memory_error` record from the current input list;
  a Platform Action record cannot be the source of a new request.
- `confidence` must be an integer from 0 through 100; booleans are rejected.
- `parameters` must be an object.
- `reason` must be a non-empty string. It is diagnostic context and is not
  encoded into the Contoso action request.

## Supported actions

| Samsung action | CPAD ActionID | CPAD action | Parameters |
| --- | ---: | --- | --- |
| `cold_reboot` | `0x0002` | Power Cycle | Must be `{}` |
| `reseat_dimm` | `0x0003` | Reseat Part | Must be `{}` |
| `dance_dimm` | `0x0004` | Shuffle Part | Must be `{}` |
| `replace_dimm` | `0x0005` | Replace Part | Must be `{}` |
| `ppr` | `0x8001` | Post Package Repair | Complete PPR type and target |
| `page_offline` | `0x8002` | Page Offline | `pages`, `page_ranges`, or both |
| `reboot_with_training` | `0x8003` | Reboot with Memory Retraining | Must be `{}` |

### Power Cycle (`cold_reboot`, `0x0002`)

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "cold_reboot",
    "confidence": 90,
    "parameters": {},
    "reason": "A cold restart is required to recover the platform",
}
```

### Reseat DIMM (`reseat_dimm`, `0x0003`)

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "reseat_dimm",
    "confidence": 91,
    "parameters": {},
    "reason": "The fault pattern indicates a DIMM seating problem",
}
```

### DIMM dance (`dance_dimm`, `0x0004`)

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "dance_dimm",
    "confidence": 92,
    "parameters": {},
    "reason": "Move the DIMM to isolate the failing component",
}
```

### Replace DIMM (`replace_dimm`, `0x0005`)

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "replace_dimm",
    "confidence": 95,
    "parameters": {},
    "reason": "The available repair budget is exhausted",
}
```

Power Cycle, Reseat Part, Shuffle Part, and Replace Part use the source memory
error's FRU ID and FRU text in the CPAD section descriptor. They have no action
body parameters. After policy approval, these standard actions are routed to
the simulated server-fleet control plane rather than submitted to the Contoso
endpoint.

### Post Package Repair (`ppr`, `0x8001`)

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "ppr",
    "confidence": 94,
    "parameters": {
        "ppr_type": 0x01,
        "chiplet": 0,
        "controller": 0,
        "channel": 0,
        "dimm": 1,
        "subchannel": 0,
        "rank": 0,
        "device": 3,
        "bank_group": 2,
        "bank": 3,
        "row": 1234,
    },
    "reason": "Repair the repeatedly failing DRAM row",
}
```

PPR parameters must contain exactly the eleven fields shown above:

| Parameter | Valid values |
| --- | --- |
| `ppr_type` | `0x01` runtime soft PPR, `0x02` boot-time soft PPR, or `0x04` boot-time hard PPR |
| `chiplet` | Integer `0..65535` |
| `controller` | Integer `0..65535` |
| `channel` | Integer `0..255` |
| `dimm` | Integer `0..255` |
| `subchannel` | Integer `0..255` |
| `rank` | Integer `0..255` |
| `device` | Integer `0..255` |
| `bank_group` | Integer `0..255` |
| `bank` | Integer `0..255` |
| `row` | Integer `0..4294967295` |

The Samsung analyzer must select the PPR type and copy the complete target into
the request. The Contoso analyzer does not infer missing coordinates from the
referenced memory-error record.

### Page Offline (`page_offline`, `0x8002`)

An action may identify individual pages:

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "page_offline",
    "confidence": 88,
    "parameters": {
        "pages": [
            0x0000000012345000,
            0x0000000012347000,
        ],
    },
    "reason": "Offline the pages containing recurring corrected errors",
}
```

It may identify ranges:

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "page_offline",
    "confidence": 89,
    "parameters": {
        "page_ranges": [
            {
                "start_address": 0x0000000020000000,
                "page_count": 32,
            },
        ],
    },
    "reason": "Offline the physical range affected by the fault",
}
```

Or it may use both forms:

```python
"parameters": {
    "pages": [
        0x0000000012345000,
        0x0000000012347000,
    ],
    "page_ranges": [
        {
            "start_address": 0x0000000020000000,
            "page_count": 32,
        },
    ],
},
```

Only `pages` and `page_ranges` are permitted. At least one list must be
non-empty. Every physical address must be an integer in the 52-bit physical
address space and aligned to 4 KiB. `page_count` must be an integer from 1
through `4294967295`, and the resulting range must remain within the 52-bit
address space.

The Contoso analyzer canonicalizes overlapping or adjacent pages, selects the
smallest PFN-list, range, or bitmap encoding, and divides large requests into
independently retryable, batch-correlated CPADs. The endpoint remains
stateless: it performs the request, emits a Platform Action Event, and does not
include offlined-page state in later CPERs.

### Reboot with memory training (`reboot_with_training`, `0x8003`)

```python
{
    "source": {
        "cper_file": "record-17.cper",
        "section_index": 2,
    },
    "action": "reboot_with_training",
    "confidence": 93,
    "parameters": {},
    "reason": "Retrain memory on the next system reset",
}
```

The parameter object must be empty. The endpoint records a pending retraining
request and performs it on the next supported system reset.

## Translation to the Contoso request

For example, the Samsung `replace_dimm` action above becomes:

```python
{
    "cper_file": "record-17.cper",
    "section_index": 2,
    "action_id": "0x0005",
    "confidence": 95,
    "parameters": {},
}
```

The adapter maps the action name to its ActionID, moves the two source fields
to the top level, copies the confidence and parameters, and validates that the
source identifies an input memory error. The Contoso analyzer then builds and
emits the binary CPAD.

## Analysis seam

The current `analyze(records)` implementation is intentionally
conservative:

```python
{
    "fault": None,
    "actions": [],
    "advisories": [],
}
```

Samsung-specific diagnostic logic or an external Samsung tool can replace that
function without changing the adapter or Contoso action request contract.

See [Memory Vendor Analyzer Shim Interface](memory-vendor-analyzer-shim.md) for
the common shim flow and [Contoso CPAD Actions](../contoso-cpad-actions.md) for
the binary action formats.
