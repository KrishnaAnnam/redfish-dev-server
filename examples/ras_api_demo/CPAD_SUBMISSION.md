# CPAD Submission

A **CPAD** (Common Platform Action Descriptor) is a binary record describing a
*proposed action* — an error injection, a repair such as SPPR, or a rejection —
that is sent **to** a RAS API endpoint. This document describes how a CPAD is
submitted to the BMC and the checks the BMC runs before it accepts one.

Two pieces of code implement this flow:

- **Client side** — [`submit_cpad.py`](submit_cpad.py) (`CPADSubmitter`): reads a
  binary `.cpad`, base64-encodes it, and POSTs it as JSON.
- **BMC / plugin side** — [`submit_cpad_action.py`](../../src/plugins/ras/handlers/submit_cpad_action.py)
  (`SubmitCPADActionHandler`): decodes, validates, runs the acceptance checks,
  and (on acceptance) performs the action.

## Transport

```
POST /redfish/v1/Oem/OCPRASAPIWS/RASService/Actions/RASService.SubmitCPAD
Content-Type: application/json

{ "CPADData": "<base64 of the binary CPAD>", "EncodingType": "Base64" }
```

The binary CPAD is base64-encoded and wrapped in JSON so it travels over a
standard Redfish action without a separate binary upload channel. The BMC
base64-decodes it and reconstructs the original bytes.

## Client-side steps

With `--verbose`, [`submit_cpad.py`](submit_cpad.py) narrates each step:

| Step | Action |
|---|---|
| 1 | Load the binary `.cpad` file and validate its `CPAD` signature. |
| 2 | Parse the header to read `PlatformID` and `PartitionID`. |
| 3 | Look up the target BMC URL by `PlatformID` (supports a multi-BMC map). |
| 4 | Base64-encode the bytes and POST the JSON payload to the BMC. |
| 5 | Receive the response. `202 Accepted` (or `2xx`) means the BMC accepted it. |
| 6 | **Store the accepted CPAD** in the infrastructure database, keyed by `PlatformID`/`PartitionID`. |
| 7 | **Listen for the Platform Action CPER(s)** that report the *outcome* of the action. |

### Why store (step 6) comes before listening (step 7)

Acceptance (`202`) is the BMC's commitment to *process* the CPAD — it is **not**
confirmation that the action has run. The endpoint may act much later, once
preconditions are met (maintenance windows, quiescing, etc.). The client
therefore **records the CPAD as soon as it is accepted** (step 6) so the pending
action is never lost, and *only then* waits for the Platform Action CPER(s) that
report success or failure (step 7). These two concerns are deliberately
decoupled: "the BMC accepted it" and "the endpoint eventually acted on it" are
different events, potentially far apart in time.

## BMC-side processing

[`SubmitCPADActionHandler.handle_submit_cpad`](../../src/plugins/ras/handlers/submit_cpad_action.py)
runs these stages. The first failure returns an error and stops.

1. **Field check** — require `EncodingType: "Base64"` and a `CPADData` field
   (else `400`).
2. **Decode & signature** — base64-decode, require the minimum header size and
   the `CPAD` signature (else `400`).
3. **Decode to JSON** — convert the binary CPAD to JSON with cperlib
   (`cpad-convert to-json`) so the header/section descriptors can be inspected
   (a tool failure is `500`).
4. **Structure validation** — require a header, at least one section descriptor,
   the required header fields, and a `sectionCount` that matches the number of
   descriptors (else `400`).
5. **Acceptance checks (spec §6.5)** — see below. These gate the `202`.
6. **Acceptance gate** — once §6.5 passes, the CPAD is **Accepted (`202`)**.
7. **Post-acceptance action** — mint the resulting CPER(s) (an error CPER for an
   injection, and always a Platform Action Event CPER). A failure here does
   **not** revoke acceptance — the CPAD was already accepted at step 6.

### Acceptance checks (spec §6.5)

| Check | Rule | On failure |
|---|---|---|
| **PlatformID** | The CPAD's `platformID` must equal the BMC's own `PlatformID`. | `400` `OCPRAS.1.0.PlatformIDMismatch` |
| **PartitionID** | The CPAD's `partitionID` must map to a known RAS endpoint (`RASService/RASEndpoints`). | `404` `OCPRAS.1.0.PartitionIDUnknown` |
| **Well-formed length** | `recordLength` must be consistent with the payload: `header-min ≤ recordLength ≤ received-bytes`. | `400` `OCPRAS.1.0.CPADValidationFailed` |

> **Note on the length rule.** Per `Cpad.h`, the received buffer *may be larger*
> than the declared record (room to append section descriptors). So the check is
> a bound (`recordLength ≤ received-bytes`), not strict equality — it rejects a
> truncated payload or an absurd `recordLength` while allowing legitimate
> trailing buffer space.

The BMC sources its own `PlatformID` and the set of valid `PartitionID`s from the
RAS discovery tree ([`discovery.py`](../../src/plugins/ras/discovery.py)), so the
checks stay in sync with what the service advertises.

### Why `202` means "Accepted", not "Done"

`202 Accepted` is returned **once the acceptance checks pass** — before the
action necessarily completes. This matches §6.5: acceptance and execution are
separate. The Platform Action Event CPER (delivered later via the event
listener) is what reports the actual *result* of the action. This is the same
principle the client honors with its store-then-listen ordering (steps 6 → 7).

## Error responses

Rejections return a standard Redfish error body so the client can react
programmatically:

```json
{
  "error": {
    "@Message.ExtendedInfo": [
      {
        "MessageId": "OCPRAS.1.0.PlatformIDMismatch",
        "Message": "CPAD PlatformID <x> does not match this platform (<y>).",
        "MessageArgs": ["<x>", "<y>"],
        "Severity": "Warning",
        "Resolution": "Correct the request body and resubmit."
      }
    ]
  }
}
```

| HTTP | MessageId | Cause |
|---|---|---|
| `202` | *(success — Task body)* | CPAD accepted for processing |
| `400` | `Base.1.16.ActionParameterMissing` | Missing `EncodingType`/`CPADData` |
| `400` | `OCPRAS.1.0.CPADValidationFailed` | Bad signature/size, structure, or length |
| `400` | `OCPRAS.1.0.PlatformIDMismatch` | CPAD targets a different platform |
| `404` | `OCPRAS.1.0.PartitionIDUnknown` | PartitionID does not map to a known endpoint |
| `500` | `OCPRAS.1.0.CPADConversionFailed` | `cpad-convert` could not decode the CPAD |

## Where submission sits in the demo

In the guided demo the orchestrator submits two kinds of CPAD through this path:

- **Error-injection CPADs** (`0x0006`) from the Contoso injector, to create the
  corrected DRAM errors the analyzer then studies.
- **SPPR repair CPADs** (`0x8001`) that the analyzer emits and the
  [PolicyEngine](POLICY_ENGINE.md) approves.

See the [end-to-end walkthrough](README.md#end-to-end-walkthrough) for how
submission fits into the full inject → analyze → policy → submit → repair loop,
and [analyzer-orchestrator.md](analyzer-orchestrator.md) for the component that
drives submission after policy approval.
