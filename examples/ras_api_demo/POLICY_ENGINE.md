# Policy Engine

The **Policy Engine** ([`policy.py`](policy.py), class `PolicyEngine`) is the
Server Fleet Operator's gate that decides whether a **proposed RAS action**
(a CPAD produced by a vendor analyzer) is allowed to run on the hardware.

It is **table-driven**: all policy lives in two JSON files under
[`policy_tables/`](policy_tables), which the engine loads at construction. The
engine itself is small, self-contained, and has **no server dependencies** — it
reads local JSON and returns a decision.

## Where it sits in the pipeline

```
vendor analyzer  ──►  emits a CPAD (a proposed action)
                          │
                   PolicyEngine.evaluate_cpad()   ◄── operator policy gate (tables)
                          │
              approved ───┴─── denied
                 │                 │
          CPADSubmitter      create-platform-action-cper (POLICY_REJECTED)
          POST to host             │
                          store_cper → event listener → cper_storage/
                                    │
                          orchestrator analyzes it like any host CPER
```

A CPAD is only a *recommendation*. The analyzer never acts on its own; the
operator's policy engine must approve it before `CPADSubmitter` sends it back to
the reporting host. Driven from `AnalysisOrchestrator._policy_and_submit()`,
which calls `policy_engine.evaluate_cpad(cpad_json)` and, on denial, emits a
rejection CPER (see [Rejections](#rejections-policy_rejected-cper)).

## What it inspects (and what it does not)

The engine reads only the CPAD's **header** and **section descriptors**:

- `header.creatorID`, `header.platformID`, `header.partitionID`
- `sectionDescriptors[].actionId` / `actionID.code`, `sectionDescriptors[].confidence`, and `fruText`

It never parses the opaque vendor **section body**. So it can tell *that* an
action is, say, an error injection or an SPPR (from the action id in the section
descriptor), but not the private details inside the section. That keeps
proprietary vendor data private while still letting the operator gate on
identity, action type, target platform, and confidence.

## The policy tables

Two JSON files, loaded at construction (defaults shown; override via constructor
args or the CLI `--creators` / `--actions` flags).

### `policy_tables/creators.json` — who is trusted

Maps a **CreatorID** to a trust record.

```json
{
  "11111111-2222-3333-4444-555555555555": {
    "name": "Contoso",
    "trusted": true
  }
}
```

| Field | Meaning |
|-------|---------|
| *(key)* | CreatorID GUID (lowercase) |
| `name` | Human-friendly owner name (display only) |
| `trusted` | `true` ⇒ creator is trusted; anything else ⇒ denied at Rule 1 |

### `policy_tables/actions.json` — what each creator may do

Indexed by **CreatorID → ActionID**, so each row is the policy for one action
type from one creator.

```json
{
  "11111111-2222-3333-4444-555555555555": {
    "0x0006": {
      "name": "Error Injection",
      "permitted": true,
      "supported_platforms": ["990f8820-bd4d-5064-58cc-961a053dea79"]
    },
    "0x8001": {
      "name": "SPPR (Soft Post Package Repair)",
      "permitted": true,
      "confidence_threshold": 80,
      "supported_platforms": ["990f8820-bd4d-5064-58cc-961a053dea79"]
    }
  }
}
```

| Field | Meaning |
|-------|---------|
| *(outer key)* | CreatorID GUID |
| *(inner key)* | ActionID as a hex string (e.g. `0x0006`, `0x8001`) |
| `name` | Human-friendly action name (display only) |
| `permitted` | `true` ⇒ action is allowed; `false` ⇒ denied at Rule 3 |
| `confidence_threshold` | *Optional.* If present, the CPAD's section-descriptor `confidence` must be `>=` this value. **Omit it to apply no confidence gate** (e.g. error injection). |
| `supported_platforms` | List of PlatformID GUIDs on which this action is allowed |

**Why `confidence_threshold` is optional:** the policy engine only sees the
action *type* from the section descriptor. For an error injection (`0x0006`) it
cannot tell what error is being injected, and confidence is not meaningful — so
that row simply omits `confidence_threshold` and the confidence rule is skipped.
An analyzer-driven remediation like SPPR (`0x8001`) carries the analyzer's
confidence and is gated (here at `80`). Omitting the field is preferred over a
`0` threshold because it's unambiguous ("no confidence policy" vs "threshold of
zero").

Note that proprietary CPAD ActionIDs (0x8000 to 0xFFFF) are specific to a particular CreatorID.  This means that proprietary ActionIDs may have different meanings for different vendors (CreatorIDs). 

## The rules

`evaluate_cpad()` approves a CPAD only if **all** applicable rules pass; it
denies on the first failure and records the reason.

| # | Rule | Check |
|---|------|-------|
| 1 | **Creator trust** | `creators[creatorID].trusted == true` |
| 2 | **Known action** | `actions[creatorID][actionID]` exists |
| 3 | **Permitted** | that row's `permitted == true` |
| 4 | **Platform supported** | `platformID ∈ row.supported_platforms` |
| 5 | **Confidence** | if the row has `confidence_threshold`, require `confidence >= threshold`; if absent, not evaluated |

## Rejections (POLICY_REJECTED CPER)

When a CPAD is denied, the action is **not** sent to the host. Instead the
orchestrator records the rejection as a first-class event the analyzer can see:

1. `create-platform-action-cper <cpad> --return-code 0x03 --reason-code 0x00`
   turns the rejected CPAD into a **Platform Action CPER** whose
   `actionReturnCode` is `EFI_PLATFORM_ACTION_RETURN_CODE_POLICY_REJECTED (0x03)`
   with reason `EFI_PLATFORM_ACTION_REASON_CODE_NONE (0x00)`. (Both constants are
   defined in `src/plugins/ras/libcper/include/libcper/Cper.h`.)
2. The orchestrator sends the bytes to the event listener via a `store_cper`
   command; the listener writes them under
   `cper_storage/{platformID}/{partitionID}/` — the same tree as host CPERs —
   and sends the usual `cper_downloaded` notification.
3. The orchestrator picks it up like any other CPER and routes it to the
   analyzer, which reports the `POLICY_REJECTED` action result.

The `PolicyEngine` itself only makes the decision; the orchestrator owns the
cperlib call and delivery. `PolicyDecision` carries the `return_code` /
`reason_code` constants so the "what" is expressed in policy and the "how" is
plumbing.

## `PolicyDecision`

`evaluate_cpad()` returns a `PolicyDecision` (truthy when allowed):

| Field | Meaning |
|-------|---------|
| `allowed` | Approved (`True`) or denied (`False`) |
| `reason` | Human-readable denial reason (`None` when allowed) |
| `creator_id`, `platform_id`, `action_id`, `action_name` | Normalized values read from the CPAD |
| `confidence`, `threshold` | The CPAD confidence and the applied threshold (`None` if not gated) |
| `return_code`, `reason_code` | Platform Action codes to stamp on a rejection CPER |

## API

```python
from policy import PolicyEngine

engine = PolicyEngine()                      # loads policy_tables/*.json
decision = engine.evaluate_cpad("cpad.json") # -> PolicyDecision (truthy if allowed)
if decision.allowed:
    ...
else:
    print(decision.reason)

# Custom tables:
engine = PolicyEngine(creators_path="c.json", actions_path="a.json")

# Batch:
results = engine.evaluate_multiple_cpads([p1, p2])   # [(path, PolicyDecision), ...]
```

## Standalone CLI

```bash
python examples/ras_api_demo/policy.py path/to/cpad.json [more.json ...]
python examples/ras_api_demo/policy.py --creators c.json --actions a.json cpad.json
```

Prints a rule-by-rule trace and a final `APPROVED` / `DENIED` per file; exit code
is `0` if every CPAD is approved, `1` otherwise.

## Extending policy

Edit the JSON files — no code changes:

- **New trusted vendor** → add a CreatorID entry to `creators.json`.
- **New action** → add `actions[creatorID][actionID]` with `permitted`,
  `supported_platforms`, and (optionally) `confidence_threshold`.
- **Allow an action on more platforms** → add PlatformIDs to that row's
  `supported_platforms`.

For a real deployment these files would be backed by an operator-managed policy
source, and additional rules (rate limits, maintenance windows, blast-radius
limits) would slot in alongside the existing ones.

## Related documents

- [analyzer-orchestrator.md](analyzer-orchestrator.md) — calls this engine and
  delivers the `POLICY_REJECTED` CPER on denial.
- [Analyzer-Design.md](analyzers/contoso/Analyzer-Design.md) — produces the SPPR
  CPADs this engine evaluates.
- [CPAD_SUBMISSION.md](CPAD_SUBMISSION.md) — how an **approved** CPAD is
  submitted back to the endpoint.
- [README.md](README.md#end-to-end-walkthrough) — where the policy gate sits in
  the full demo flow.
