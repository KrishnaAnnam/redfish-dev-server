# Memory Vendor Analyzer Shim Interface

This document defines the common interface between the Contoso analyzer and
memory-vendor analyzers. It applies to every supported DRAM vendor, including
Micron, Samsung, and SK Hynix.

A memory-vendor shim is an adapter. It receives canonical decoded events from
the Contoso analyzer, translates them into the vendor analyzer's preferred
input, invokes the vendor analyzer, and translates the vendor decision into
source-referenced Contoso action requests.

The vendor analyzer does not need to understand the Contoso CPAD envelope,
binary action-section layouts, section offsets, GUIDs, or Base64 encoding.
Those remain Contoso responsibilities.

> **API version 3:** Memory-vendor analyzers must return every semantic
> parameter required by the action section body. Version 2 shims are rejected
> because they allowed PPR coordinates to be inferred from the referenced
> CPER.

## Overall Flow

```mermaid
flowchart TD
    VendorInput["Decoded memory-vendor<br/>records"]
    VendorAnalysis["Memory-vendor<br/>analyze"]
    VendorDecision["Memory-vendor<br/>fault/action decision"]
    Adapter["Memory-vendor shim adapter<br/>analyzer_vendor.py"]
    Request["Contoso<br/>action request"]
    Source["Find source event for<br/>header and FRU context"]
    Envelope["Build CPAD header<br/>and descriptor"]
    Codec["Encode action-specific<br/>body"]
    Json["Complete<br/>CPAD JSON"]
    Binary["Binary CPAD"]

    VendorInput --> VendorAnalysis
    VendorAnalysis --> VendorDecision
    VendorDecision --> Adapter
    Adapter --> Request
    Request --> Source
    Source --> Envelope
    Request --> Envelope
    Request --> Codec
    Envelope --> Json
    Codec --> Json
    Json --> Binary
```

The diagram begins after the shim has translated canonical Contoso events into
the memory vendor's preferred decoded-record format. The vendor analyzer
returns its fault and action decision to the same shim, which converts each
executable recommendation into a Contoso action request.

Each action request refers back to an input record using `cper_file` and
`section_index`. The Contoso analyzer uses that reference only for CPAD
envelope and descriptor context, such as PlatformID, PartitionID, CreatorID,
FRU ID, and FRU text. Every value encoded in the action-specific section body
must come from the action request's `parameters` object.

The memory-vendor analyzer is responsible for interpreting the decoded CPER
and copying or deriving all parameters required by its recommended action.
The Contoso analyzer validates and encodes those parameters but does not fill
missing action-body fields from the original CPER.

## Responsibility Boundaries

| Component | Responsibilities |
| --- | --- |
| Contoso analyzer | Decode CPERs, select same-vendor history, construct canonical events, validate source references, and build complete CPADs. |
| Memory-vendor shim | Translate between canonical events/action requests and one vendor analyzer's API without dropping required action parameters. |
| Memory-vendor analyzer | Diagnose DRAM faults and return every parameter required by each recommended action. |
| Contoso CPAD builder | Populate the CPAD envelope from CPER context and encode the supplied PPR, Page Offline, or retraining parameters without inferring section-body values. |
| Server-fleet policy | Decide whether a generated CPAD may be submitted. |
| Contoso endpoint | Validate and execute the approved action and emit a Platform Action Event. |

This separation allows each vendor analyzer to use its own terminology and
internal data model without duplicating Contoso protocol code.

## Implementation Map

| File | Role in the flow |
| --- | --- |
| [`memory_events.py`](../memory_events.py) | Decodes Contoso memory sections and Platform Action Events into canonical memory events. |
| [`contract.py`](contract.py) | Discovers shims, enforces the supported API version, deep-copies inputs, and validates the returned list shape. |
| `analyzer_<vendor>.py` | Adapts canonical events to one vendor analyzer and converts vendor decisions into Contoso action requests. |
| [`analyzer-contoso.py`](../analyzer-contoso.py) | Filters same-vendor history, validates source references, builds complete CPAD JSON, and emits paired JSON/binary files. |
| [`contoso_action_parameters.py`](../contoso_action_parameters.py) | Validates and encodes action request parameters without reading decoded CPER events. |
| [`cper_decoder.py`](../../../cper_decoder.py) | Invokes libcper to convert complete CPAD JSON into the binary `.cpad` submitted to the BMC. |

## Discovery

A shim is a Python file named `analyzer_*.py` in this directory. One shim may
register one or more exact DRAM manufacturer IDs:

```python
SHIM_INFO = {
    "api_version": 3,
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

API version 3 returns action requests containing every action-body parameter,
rather than complete CPAD documents. Shims declaring an older API version are
rejected explicitly.

## Adapter Pattern

A vendor shim should normally contain two translations around a vendor-owned
analyzer:

```python
def analyze_memory_events(events):
    vendor_records = [
        _to_vendor_record(event)
        for event in events
    ]
    vendor_decision = vendor_analyzer.analyze(vendor_records)
    return _to_contoso_action_requests(vendor_decision, events)
```

`_to_vendor_record()` may flatten, rename, or derive fields for the vendor
tool. `_to_contoso_action_requests()` must preserve the original source
reference, translate only executable Contoso actions, and include every field
needed in each action section body. Recommendations such as DIMM replacement
that have no Contoso ActionID should remain vendor advisories or report
findings rather than being disguised as CPAD actions.

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

Platform Action Event inputs use the same first three fields and carry the
action result under `platform_action`. A correlated action event also carries
the original memory target. This lets a vendor analyzer determine whether an
earlier recommendation succeeded before suggesting a follow-up action.

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
}
```

Rules:

- `cper_file` and `section_index` must identify one input `memory_error`.
- `action_id` must be a supported Contoso remediation action.
- `confidence` is an integer from 0 through 100.
- `parameters` contains the complete action-specific section-body input.
- Returning `[]` means analysis succeeded and no action is recommended.
- Raising an exception means the shim failed; default Contoso analysis may run.

The Contoso analyzer builds the complete CPAD, including the target platform,
most recent error PartitionID, CreatorID, FRU, shared action-parameter section,
and binary encoding.

## How Requests Become CPADs

For every returned action request, the Contoso analyzer:

1. Matches `cper_file` and `section_index` to exactly one input memory-error
   event.
2. Gets FRU identity from that referenced section.
3. Gets PlatformID, CreatorID, and the target PartitionID from the newest
   relevant memory-error event.
4. Validates the ActionID, confidence, and action-specific parameters.
5. Encodes only the supplied parameters into the shared Contoso
   action-parameter section.
6. Populates section offsets, lengths, ActionID, confidence, and CPAD header.
7. Writes paired JSON and binary `.cpad` files.

The shared action-parameter section GUID is:

```text
a813b17b-db08-416b-810c-172668affb28
```

Large Page Offline requests may produce several independently retryable CPADs.
The Contoso analyzer chooses PFN-list, range, or bitmap encoding and adds batch
metadata when chunking is required. The vendor shim describes the desired page
ranges but does not select the wire encoding.

## CPAD Builder Contract

The implementation enforces the section-body boundary in its function
signatures. The action encoder accepts only the ActionID and complete action
parameters:

```python
encode_action_parameter_bodies(
    action_id,
    parameters,
)
```

It does not accept a decoded CPER event. The envelope builder receives
CPER-derived context separately:

```python
build_action_cpads(
    header_context,
    fru_context,
    action_id,
    confidence,
    parameters,
)
```

Action-specific validation and encoding are isolated by ActionID:

```python
ACTION_PARAMETER_CODECS = {
    "0x8001": encode_ppr_parameters,
    "0x8002": encode_page_offline_parameters,
    "0x8003": encode_retraining_parameters,
}
```

Each codec accepts only its complete `parameters` object. Adding another
Contoso action means registering a new schema and codec; it does not give the
codec permission to inspect the source CPER for missing fields.

This separation prevents a codec from silently filling missing section-body
fields from a source error. The default Contoso analyzer may use decoded CPER
data when making its own decision, but it must materialize a complete
`parameters` object before calling the same builder used for vendor requests.
Builder-generated transport metadata, such as Page Offline chunk indexes, may
be added during encoding; semantic action parameters must come from the
analyzer request.

The implemented boundary guarantees:

1. `encode_action_parameter_bodies()` accepts `(action_id, parameters)` only.
2. PPR requests must contain every field shown below.
3. `_build_action_cpads()` passes no decoded event to the section-body codec.
4. Source-event lookup is retained only for CPAD header, FRU, and correlation
   fields.
5. The default Contoso row analyzer materializes the same complete PPR
   parameter object before calling the builder.
6. Page Offline batch metadata is derived from the ActionID and canonical
   supplied page set rather than from CPER section-body data.
7. Contract tests verify that identical parameters produce identical action
   bodies even when the CPAD envelopes come from different source CPERs.

## Supported Requests

### Post Package Repair: `0x8001`

```python
{
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
}
```

The vendor analyzer obtains these values from its decoded input records and
returns them explicitly. The CPAD builder does not retrieve missing PPR
coordinates from the referenced CPER.

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

## Complete Shim Example

```python
def analyze_memory_events(events):
    newest_error = next(
        event for event in events
        if event["event_type"] == "memory_error"
        and event["source"]["is_newest"]
    )
    if newest_error["spd_temperature"] < 85:
        return []
    error = newest_error["memory_error"]
    subcomponent = error["subcomponent"]
    location = error["additional"]
    return [{
        "cper_file": newest_error["cper_file"],
        "section_index": newest_error["section_index"],
        "action_id": "0x8001",
        "confidence": 90,
        "parameters": {
            "ppr_type": 0x02,
            "chiplet": subcomponent["chiplet"],
            "controller": subcomponent["controller"],
            "channel": location["channel"],
            "dimm": location["dimm"],
            "subchannel": location["subchannel"],
            "rank": location["rank"],
            "device": location["device"],
            "bank_group": location["bank_group"],
            "bank": location["bank"],
            "row": location["row"],
        },
    }]
```

## Success, Failure, and Fallback

- Returning `[]` means the vendor analyzer handled the events and recommends
  no action. Default Contoso row analysis is suppressed for that vendor.
- Returning one or more valid requests transfers those recommendations to the
  Contoso CPAD builder.
- Raising an exception, returning an invalid request, or failing binary CPAD
  conversion marks the shim invocation as failed. Applicable newest errors
  then fall back to default Contoso analysis.
- Inputs are deep-copied, so vendor code cannot mutate the Contoso analyzer's
  canonical event list.

## Related Documentation

See [Contoso CPAD Actions](../contoso-cpad-actions.md) for the binary
action-parameter layouts and completion timing.

See [Contoso Analyzer Design](../Analyzer-Design.md) for event-window
selection, same-vendor history filtering, and fallback behavior.

See [CPAD Submission](../../../CPAD_SUBMISSION.md) for policy and Redfish
submission after the Contoso analyzer emits a CPAD.
