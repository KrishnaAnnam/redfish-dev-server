# Analysis Orchestrator

The **Analysis Orchestrator** (AO) — [`analysis_orchestrator.py`](analysis_orchestrator.py),
class `AnalysisOrchestrator` — is the coordinator of the RAS API demo's
client/analysis side. It discovers analyzer plugins, discovers and monitors
hosts, receives CPERs from the event listener, and routes each CPER to the
vendor analyzer that owns it, then runs the resulting CPAD through policy and
submission.

The AO is deliberately **analyzer-agnostic**: it never imports vendor analysis
logic. It decodes only enough of each CPER (via the generic
[`CperDecoder`](cper_decoder.py), backed by cperlib) to read the header —
CreatorID and timestamp — and hands the rest to the owning
`analyzer-<vendor>.py`. This is the core RAS API abstraction: **one pipeline,
many vendors' hardware.** New silicon is supported by dropping in a new analyzer
script — no orchestrator changes required.

## Where it sits

```
  add_host()          ──►  Discover the host (ServiceRoot → RASService →
                           RASEndpoints); match each endpoint's CreatorID to a
                           discovered analyzer; tell the listener to subscribe.
        │
  event listener      ──►  Downloads each new .cper and pushes its path to the
                           AO over a control socket (no polling).
        │
  notify_new_cpers()  ──►  For each CPER: read header → route by CreatorID →
                           build lookback window → run the owning analyzer.
        │
  _handle_outputs()   ──►  Move the analyzer's .json/.cpad next to the CPER,
                           then run policy → submit on the .cpad.
```

## Analyzer discovery (at construction)

- Analyzers live under [`analyzers/`](analyzers) and are discovered
  **recursively**; each may have its own subdirectory (e.g.
  [`analyzers/contoso/analyzer-contoso.py`](analyzers/contoso/analyzer-contoso.py)).
- An analyzer is any script matching `analyzer-*.py`. The AO runs each with
  `--discover` (15 s timeout), expecting a single JSON identity object on stdout:

  ```json
  {
    "analyzer_name":    "Contoso CPER Analyzer",
    "analyzer_version": "1.0.0",
    "creator_ids":      ["11111111-2222-3333-4444-555555555555"],
    "prior_days":       30
  }
  ```

- The AO builds a **CreatorID → analyzer** routing table. `print_discovery_report()`
  prints one row per analyzer (name, version, CreatorIDs, prior days).
- **Fatal discovery errors** (recorded and reported, demo stops):
  - analyzers directory missing → error names the directory and the
    `analyzer-*.py` pattern;
  - no analyzers found (or none returned valid `--discover` JSON);
  - **CreatorID ownership conflict** — a CreatorID claimed by two analyzers
    fails startup, naming both analyzers and their paths (each CreatorID must be
    owned by exactly one analyzer).
- CreatorIDs are GUIDs, **normalized** (lowercase, braces/whitespace stripped)
  on both the discovery and CPER sides before matching.

## Host discovery & monitoring

- `add_host(...)` calls `discover_host(...)`, which walks ServiceRoot →
  RASService → RASEndpoints and records a `MonitoredHost` anchored by its
  **PlatformID** (the GUID that ties a host to the CPERs/CPADs it produces).
- Each RAS endpoint's CreatorID is matched to a discovered analyzer, so the AO
  knows every endpoint on the host is analyzable before it subscribes.
- The AO connects to the SDK event listener's control socket and asks it to
  **subscribe** to the host's CPER events. On shutdown, `close()` asks the
  listener to remove every subscription so no orphaned EventService
  subscriptions are left behind.

## CPER intake (explicit push, no polling)

- The event listener downloads each new `.cper` and notifies the AO over the
  control socket; `_handle_notification` buffers the path.
- `wait_for_cpers(count, timeout)` blocks until at least `count` are pending;
  `process_new_cpers()` drains the buffer and routes everything received since
  the last call via `notify_new_cpers(paths)`.
- CPERs are always processed **in the order received**.

## Routing a single CPER

For each CPER, `_process_cper` does:

1. **Read the header** (the only part the AO decodes) — CreatorID, PlatformID,
   PartitionID, timestamp.
2. **Route by CreatorID** — select the owning analyzer from the routing table.
   - **No matching analyzer / no CreatorID** → print a hard-to-ignore error
     showing the CPER's timestamp, CreatorID, PlatformID, PartitionID, then
     **continue** to the next CPER (one bad CPER never aborts the batch).
3. **Build the lookback window** (below).
4. **Hand off** to the analyzer with `--input-file <path>` and **wait** for it
   (120 s timeout).
5. **Handle outputs** (below).

### Lookback window (directory-scoped)

CPERs are stored under `cper_storage/{PlatformID}/{PartitionID}/`. PlatformID is
the machine GUID, PartitionID identifies a piece of silicon, and every CPER in
that directory shares the same CreatorID. So the AO looks **only in the
triggering CPER's directory** and selects CPERs whose timestamp falls in the
inclusive range `[timestamp − prior_days, timestamp]`.

- The list is ordered **newest first**, and the triggering CPER is guaranteed to
  be element 0 even if timestamps tie.
- On an unparseable header timestamp, the AO warns and falls back to the file's
  filesystem mtime for ordering.
- The window is written to an **input file** passed as `--input-file` (avoids
  overflowing the command line).

## Output handling

- Before invoking an analyzer, the AO **deletes any pre-existing `.json`/`.cpad`
  files** from the analyzer's own directory, so anything present afterward is
  definitively this run's output.
- Each run produces **zero-or-one `.json`** and **zero-or-one `.cpad`**.
- On success (`_handle_outputs`):
  - a produced `.json` is **moved** into the triggering CPER's directory;
  - a produced `.cpad` is **moved** into the same directory, then passed to
    `_policy_and_submit`.
- `_policy_and_submit` evaluates the CPAD with the injected `policy_engine`
  ([PolicyEngine](POLICY_ENGINE.md)) and, on approval, submits it with the
  injected `submitter` ([CPADSubmitter](CPAD_SUBMISSION.md)). On **denial**, the
  AO mints a `POLICY_REJECTED` Platform Action CPER and delivers it back through
  the listener's `store_cper` path, where it is analyzed like any other CPER
  (see [POLICY_ENGINE.md](POLICY_ENGINE.md#rejections-policy_rejected-cper)).

> Policy evaluation and submission are **injected dependencies**, so the AO owns
> orchestration while the policy and transport logic live in their own modules.

## Analyzer authoring contract

A new analyzer `analyzer-<vendor>.py` must support:

1. `--discover` → print the JSON identity object above and exit 0.
2. `--input-file <path>` → read the AO's JSON input file (`cper_files`
   newest-first, `newest_cper`, `creator_id`, `newest_timestamp`, `prior_days`),
   analyze, and write outputs **next to the script**:
   - exactly one `.json` (analysis result), and
   - zero or one `.cpad` (remediation, e.g. SPPR), created only when warranted.
3. Exit code 0 on success, non-zero on failure.

See [analyzers/contoso/Analyzer-Design.md](analyzers/contoso/Analyzer-Design.md)
for a worked implementation of this contract.

## Standalone CLI

The AO can run without the guided demo, analyzing a directory of stored CPERs:

```bash
python examples/ras_api_demo/analysis_orchestrator.py --analyze \
    --cper-dir ras_demo_output/cper_storage
```

## Related documents

- [README.md](README.md#end-to-end-walkthrough) — where the AO sits in the full demo flow.
- [Analyzer-Design.md](analyzers/contoso/Analyzer-Design.md) — the analyzer side of the contract.
- [POLICY_ENGINE.md](POLICY_ENGINE.md) — the policy gate the AO calls.
- [CPAD_SUBMISSION.md](CPAD_SUBMISSION.md) — how approved CPADs are submitted.
