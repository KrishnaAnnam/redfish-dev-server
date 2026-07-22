# Contoso Error Injector

## Objective

The Contoso Error Injector is used to simulate error conditions on the Contoso SoC.  It takes input from an editable JSON injection spec (or, for simple cases, command-line arguments) and generates a CPAD for a particular Contoso SoC.  The Contoso SoC on receipt of the CPAD will simulate logging an error in a CPER that is reported by the RAS API endpoint on the SoC.  Because this tool is specific to the Contoso SoC, every CPAD it produces is always stamped with the Contoso SoC CreatorID; the CreatorID is never a user input.

## RAS API Context

The RAS API can be used to inject errors via CPADs with an Action Id of 0x06.  This injection tool demonstrates how error injection CPADs can be constructed via standard interface to a vendor provided tool that generates vendor-specific CPADs.  This follows one of the key design patterns for the RAS API: having a standard pipeline and interfaces for proprietary data.  The vendor-specific error injection tool is the abstraction layer for proprietary implementations, allowing the chip designers to implement error injection in a manner that is convenient for their silicon's design and allowing them to innovate.

## Requirements

- This is a command-line tool that is intended to be called manually and also be scriptable
- The tool can:
    - Generate error injection CPADs
    - Read an error injection CPAD it created and recreate the inputs that generated the CPAD
    - Present a list of errors it can inject

### Design Rationale: Why a JSON Injection Spec

A Contoso CPER section can log a large amount of state (see `contoso-cper-sections.md`):

- **Error Status Register** bitfields — Address Valid, Overflow, Severity, errorID
- **Error Address** (64-bit)
- **Misc 0** — Injected bit, ce_count, implementation-specific bits
- **Misc 1** — implementation-specific context
- **Section-type-specific additional registers** — for example the memory controller's
  DRAM bank logs up to 94 bytes (channel, subchannel, dimm, rank, bank_group, bank,
  row, column, syndrome, and a `beat_mask[10][4]`)

Expressing all of this with flat command-line arguments (e.g. `--beat-mask-dram3-dq2=...`)
does not scale and is not usable. Instead, the primary interface is an **editable JSON
injection spec**: the tool generates a fully-populated spec for a chosen error (with
schema-valid defaults for every field), the user edits only the values they care about,
and the tool consumes the edited spec to produce a CPAD. This is inspired by the ACPI
EINJ two-step *SET_ERROR_TYPE → INJECT* sequence, but file-based, so specs are
diffable, scriptable, and version-controllable. The CLI never performs register reads
and writes; low-level, chip-specific details live inside the CPAD section body.

### Operations (CLI verbs)

The tool exposes the following operations:

- `list` — Print a table of every error the tool can inject (see the table columns below).
- `template` — Generate a JSON injection spec for a chosen error, pre-filled with valid
  defaults for every field the CPER can log. This is the "describe" step.
- `inject` — Consume an edited JSON injection spec (or a CLI fast-path) and emit a CPAD.
- `decode` — Read a CPAD; if it is an error-injection CPAD created by this tool,
  reconstruct the equivalent JSON injection spec (and equivalent CLI). This is the
  round-trip of `inject`.
- `help` — Show usage/help.

Example workflow:

```
# 1. See what can be injected
injector-contoso.py list

# 2. Generate an editable injection spec for a chosen error
injector-contoso.py template \
    --section "CPU Core - First Generation" \
    --error "Poison Consumption" \
    --out poison.inject.json

# 3. Edit poison.inject.json (target platform/partition, addresses, coordinates...), then:
injector-contoso.py inject --spec poison.inject.json --out poison.cpad

# Round-trip: reconstruct the spec from a CPAD
injector-contoso.py decode --cpad poison.cpad
```

A **CLI fast-path** is also supported for the simple case so no file is required. The
JSON spec remains the full-fidelity path:

```
injector-contoso.py inject \
    --section "Memory Controller - First Generation" \
    --error "Corrected Memory ECC Error" \
    --platform-id 990f8820-bd4d-5064-58cc-961a053dea79 \
    --partition-id 22222222-3333-4444-5555-666666666666 \
    --set section.errorAddress=0x6942759454E18F7B \
    --set section.additional.dimm=1 \
    --out mem.cpad
```

### The Injection Spec

The injection spec is a single JSON object with three blocks: `cpad` (targeting and
CPAD/CPER header), `error` (the human-friendly selector), and `section` (every register
logged in the CPER section body). `template` emits all three fully expanded with
schema-valid defaults; `inject` validates the edited spec against the same section-type
schema before emitting the CPAD.

#### Block 1 — `cpad`: targeting and CPAD/CPER header

This block carries the CPAD header fields, including the endpoint-targeting identifiers.

```jsonc
"cpad": {
    "platformID":  "990f8820-bd4d-5064-58cc-961a053dea79",  // target SoC
    "partitionID": "22222222-3333-4444-5555-666666666666",  // target partition/socket
    "revision":    { "major": 1, "minor": 0 },              // CPAD/CPER format revision
    "urgency":     false,                                    // action urgency hint
    "fruID":       "75824856-bd36-2cc8-61f4-39bb3276da2a",  // FRU identifier (GUID)
    "fruText":     "DIMM A1"                                 // human-readable FRU
}
```

The action is always `0x0006` ("Inject Error") and is stamped by the tool, not the spec.

**Confidence is always 100.** Error-injection CPADs are stamped with a confidence
of `100` in the section descriptor (`sectionDescriptors[0].confidence`, the
standard CPAD location — not the header). The operator explicitly ran the inject
command, so certainty is maximal; there is no analysis to be uncertain about. The
policy engine leaves error injection ungated (no `confidence_threshold`), so the
value is informational, but it is set for consistency with analyzer-produced CPADs.

**CreatorID is fixed and is NOT a user input.** The CreatorID identifies the analyzer
and endpoint that a CPAD is routed to. Because this tool is specific to the Contoso SoC,
it MUST always stamp the CPAD with the Contoso SoC CreatorID
(`11111111-2222-3333-4444-555555555555`). The tool does not expose a way to change it,
does not accept it as a CLI argument, and does not include it as an editable field in the
JSON injection spec. If a decoded CPAD does not carry the Contoso CreatorID, `decode`
reports that the CPAD was not produced by this tool.

**Endpoint-assigned fields.** The `recordID`, `timestamp`, CPER `severity`, and
`notificationType` are NOT carried in the CPAD. The endpoint (here, the BMC) assigns the
`recordID` (sequential, starting at 1) and the `timestamp` when it logs the CPER, and it
derives the `severity` and `notificationType` from the section body (see *Severity and
Notification Type* below). Only `revision` is injector-set and copied into the CPER.

#### Block 2 — `error`: the error selector

The selector uses the **exact names** from `contoso-cper-sections.md`, so users never
hand-encode section-type GUIDs or numeric errorIDs. The tool resolves `sectionType` to
its GUID, `errorName` to its errorID, and the default severity from the ErrorID table.

```jsonc
"error": {
    "sectionType": "CPU Core - First Generation",  // -> GUID f63f509b-8995-4efd-9144-4b7fed6c4fd3
    "errorBank":   "Core Errors",                   // -> bank 0
    "errorName":   "Poison Consumption",            // -> errorID 0x01
    "severityOverride": null,   // null = use the table default; may escalate at runtime
    "injected":    true,        // sets Misc0.Injected (spoofed/injected vs. natural)
    "occurrence":  "immediate"  // demo: always immediate and injected once
}
```

For this demo, all injected errors are Spoofed, occur immediately with no trigger
conditions, and are injected once (`injected: true`, `occurrence: "immediate"`, single
emit). These defaults are applied automatically.

#### Block 3 — `section`: every register logged in the CPER section body

`template` renders this block fully expanded and schema-driven per section type, so the
user only overrides the fields they care about.

**CPU Core example** (section type `f63f509b-8995-4efd-9144-4b7fed6c4fd3`):

```jsonc
"section": {
    "subcomponent": { "chiplet": 0, "core": 3 },   // Subcomponent Instance ID coordinates
    "errorStatus": {
        "addressValid": true,      // bit 63
        "overflow":     false      // bit 62
        // severity and errorID are auto-filled from the `error` block
    },
    "errorAddress": "0x6942759454E18F7B",
    "misc0": { "injected": true, "ce_count": 0 },   // injected auto-set from `error`
    "misc1": "0x0",
    "additional": {                                  // Bank 0 additional registers
        "timeout_transaction_details": "0x0",
        "register_parity_details":     "0x0",
        "cache_location":              "0x0",
        "assert_details":              "0x0",
        "core_debug_details":          "0x0"
    }
}
```

**Memory Controller example** (section type `e01ce992-d080-43f4-8a2c-df8a9d81eb4e`,
Bank 0 "DRAM Errors") — the tool renders the full additional-register set including the
beat mask:

```jsonc
"section": {
    "subcomponent": { "chiplet": 1, "controller": 0 },
    "errorStatus": { "addressValid": true, "overflow": false },
    "errorAddress": "0x0000000123456780",
    "misc0": { "injected": true, "ce_count": 1 },
    "misc1": "0x0",
    "additional": {
        "channel": 0, "subchannel": 0, "dimm": 1, "rank": 0,
        "bank_group": 2, "bank": 3, "row": 1234, "column": 567,
        "syndrome": "0x00A5",
        "beat_mask": [ /* [10][4] uint16; defaults all-zero */ ]
    },
    "beatErrors": [
        { "dram": 3, "dq": 2, "beats": "0,5,15" }   // failing beats (see below)
    ]
}
```

#### DRAM beat errors (`beatErrors` and `--beat`)

The DRAM error bank logs `beat_mask[10][4]` — indexed `[DRAM][DQ]`, where each element is
a 16-bit mask (one bit per beat). Rather than hand-editing that grid, describe the failing
beats declaratively with a `beatErrors` list in the `section` block:

```jsonc
"beatErrors": [
    { "dram": 3,     "dq": 2,     "beats": "0,5,15" },  // DRAM 3, DQ 2, beats 0/5/15
    { "dram": "3,7", "dq": "all", "beats": "4-6" }      // DRAMs 3&7, all DQs, beats 4-6
]
```

- `dram` (0–9), `dq` (0–3), and `beats` (0–15) each accept an integer, a comma list, a
  `lo-hi` range, or `"all"`.
- Entries OR together onto the zero-initialised grid; `beat_mask` still defaults to all
  zeros, so you only add the beats you want.

The same thing on the command line, with a repeatable `--beat` flag (fields separated by
`;`):

```
injector-contoso.py inject \
    --section "Memory Controller - First Generation" \
    --error "Corrected Memory ECC Error" \
    --beat "dram=3;dq=2;beats=0,5,15" \
    --beat "dram=3,7;dq=all;beats=4-6" \
    --out beats.cpad
```

`decode` reverse-compiles a populated `beat_mask` back into a readable `beatErrors` list.

#### Severity and Notification Type (endpoint-derived)

The injector does not set the CPER severity or notification type. The **Contoso** severity
is encoded in the section body's Error Status Register (from the error's typical severity,
or a `severityOverride`). When the endpoint logs the CPER it maps that Contoso severity to
a standard CPER severity and picks the notification type:

| Contoso severity      | CPER severity  | Notification type |
| ---                   | ---            | ---               |
| Fatal / Uncorrected   | Fatal          | MCE               |
| Recoverable           | Recoverable    | MCE               |
| Deferred              | Informational  | CMC               |
| Corrected             | Corrected      | CMC               |

The CPER **header** severity is the highest severity across all of the CPER's sections.

#### One error per CPAD (current scope)

The current tool injects a single error section per CPAD. The CPAD/CPER format does allow
multiple sections (`sectionCount > 1`), matching the Contoso "one or more sets of error
banks" layout; multi-section injection is a planned extension.

### The Inject Error Operation

- Use the `contoso-cper-sections.md` file for the list of errors that are supported.
- The names listed there MUST be exactly the names used as inputs to specify which
  error is injected (section-type name, error bank name, and error name).
- The error is specified using:
    - The name of the CPER Section and the Error Bank name.
    - The name of the error in the bank.
- The location of the error is specified in the `section` block: the subcomponent
  instance coordinates (e.g. chiplet/core or chiplet/controller), the Error Address,
  and any section-type-specific additional registers.
- For this demo, all errors are Spoofed, occur immediately with no trigger conditions,
  and are injected once.

### Examples

All examples run from `Demos/RasApi/analyzers/contoso/` (prefix with `python` as needed).

**1. Inject a corrected memory error (CLI fast-path):**

```
injector-contoso.py inject \
    --section "Memory Controller - First Generation" \
    --error "Corrected Memory ECC Error" \
    --set section.additional.dimm=1 \
    --set section.additional.row=1234 \
    --set section.additional.column=567 \
    --out mem.cpad
```

**2. Inject a fatal CPU-core error at a specific core:**

```
injector-contoso.py inject \
    --section "CPU Core - First Generation" \
    --error "Transaction Timeout" \
    --set section.subcomponent.core=3 \
    --set section.errorAddress=0x6942759454E18F7B \
    --out core.cpad
```

**3. Inject DRAM beat errors** — DRAM 3 / DQ 2 / beats 0,5,15 and every DQ of DRAM 7 / beat 4:

```
injector-contoso.py inject \
    --section "Memory Controller - First Generation" \
    --error "Corrected Memory ECC Error" \
    --beat "dram=3;dq=2;beats=0,5,15" \
    --beat "dram=7;dq=all;beats=4" \
    --out beats.cpad
```

**4. Author a spec, edit it, then inject:**

```
injector-contoso.py template \
    --section "Memory Controller - First Generation" \
    --error "Corrected Memory ECC Error" \
    --out mem.inject.json
# edit mem.inject.json (DRAM coordinates, beatErrors, FRU text, revision, ...)
injector-contoso.py inject --spec mem.inject.json --out mem.cpad
```

**5. List injectable errors, and decode a CPAD back to a spec:**

```
injector-contoso.py list
injector-contoso.py decode --cpad mem.cpad
```

### The List Operation

When listing the errors it can inject, the tool prints a table that includes:

- The type of error, e.g. core, memory, SoC-internal, PCIe error (varies per SoC).
- The name of the error.
- Whether it is injected or spoofed.
- If the error has configurable trigger conditions (e.g. read the address where the
  error was injected).
- A description of the trigger condition options:
    - Error can occur immediately.
    - Error can occur when trigger conditions are met.
- Whether the error is injected once or persists.

This is a simple interface inspired by the ACPI EINJ interface at
https://uefi.org/htmlspecs/ACPI_Spec_6_4_html/18_ACPI_Platform_Error_Interfaces/error-injection.html.
EINJ allows users to specify errors to inject; this interface does something similar.
Unlike EINJ, the CLI does not perform register reads and writes — the CPAD sections can
contain the low-level, chip-specific details such as register reads and writes.

### Schema Registry

The section-type schemas (field lists, defaults, section-type name-to-GUID maps,
error name-to-errorID maps, and severity tables) SHOULD live in one machine-readable
registry (a Python dict or a JSON sidecar) that drives `list`, `template`, `inject`
validation, and `decode` alike. Adding a future Contoso generation then means adding one
schema entry rather than editing four code paths. This mirrors the existing pattern where
`analyzer-contoso.py` owns the Contoso-specific CPER decode logic.

### Targeting an Endpoint

- The target endpoint is identified by the `platformID` and `partitionID` in the `cpad`
  block of the injection spec (or the `--platform-id` / `--partition-id` CLI arguments).
  These are routed downstream by the existing submission pipeline (`submit_cpad.py`),
  which reads the platformID from the CPAD header to select the target BMC.
- The CreatorID is always the Contoso SoC CreatorID and is not a targeting input
  (see Block 1 above).
- Filename format: injection specs use the `*.inject.json` suffix; generated CPADs use
  the `.cpad` suffix. The `template` and `inject` verbs accept an explicit `--out` path.

### CPAD Output Requirements

- The tool emits a CPAD with an Action ID of `0x0006` ("Inject Error") in the section
  descriptor, and the Contoso SoC CreatorID in the CPAD header.
- The CPAD header carries `platformID`, `partitionID`, `revision`, and `urgency` from the
  `cpad` block. `recordID` is left unassigned (0) and no meaningful `timestamp` is set —
  the endpoint assigns both when it logs the CPER.
- The single section encodes the Contoso section body (header + error banks + additional
  registers) in the little-endian, packed binary format defined in
  `contoso-cper-sections.md`, populated from the `section` block of the spec.
- The output is a valid CPAD (correct `CPAD` signature, section count, and section
  offsets/lengths) that the SubmitCPAD pipeline and policy engine can consume unchanged.
- `decode` on a tool-produced CPAD reconstructs the originating injection spec.




## Acceptance Criteria

- Errors generate CPADs
- CPADs are correctly formed
- The demo generates correct CPERs from the CPADs
- CPADs can be decoded to JSON files

## AI Instructions
