# Analyzer Orchestrator — Design & Instructions

> Working notes captured at the user's request. **Do not commit this file** —
> it is intended to be copied out of the repository.

## Goal

Refactor the analysis pipeline so new analyzers (for new chips) can be added by
dropping a script into an `analyzers/` directory — no orchestrator changes
required. The Analysis Orchestrator (AO) discovers analyzers at startup, routes
incoming CPERs to the correct analyzer by CreatorID, and handles the analyzer's
outputs.

## 1. Analyzer discovery

- Analyzers live under `Demos/RasApi/analyzers/`, discovered **recursively**
  (each analyzer may optionally have its own subdirectory).
- An analyzer is any script named `analyzer-<companyname>.py`.
- The existing Contoso analyzer lives at
  `Demos/RasApi/analyzers/contoso/analyzer-contoso.py`.
- The AO runs each discovered script with `--discover`. The script responds with
  a single JSON object on stdout:

  ```json
  {
    "analyzer_name":    "Contoso CPER Analyzer",
    "analyzer_version": "1.0.0",
    "creator_ids":      ["11111111-2222-3333-4444-555555555555"],
    "prior_days":       30
  }
  ```

- The AO stores each analyzer's name and discovery metadata and builds a
  CreatorID → analyzer routing table.
- Discovery runs at the **beginning of the demo**. When it finishes, the AO
  prints a table with one row per analyzer: **name**, **CreatorIDs**,
  **prior days** (version is also shown).
- **No analyzers found** → print a clear error stating *where it looked* (the
  search directory) and the *filename pattern*, then stop the demo.
- **CreatorID owned by two analyzers** → fail startup with a conflict error
  naming both analyzers and their paths.
- CreatorIDs are GUIDs and are **normalized** (lowercase, braces/whitespace
  stripped) on both the discovery side and the CPER side before matching.

## 2. Error analysis orchestration

- When new CPERs are collected and written to files, the collection step
  **explicitly pushes** the new CPER paths to the AO
  (`AnalysisOrchestrator.notify_new_cpers(paths)`). The AO does not poll.
- CPERs are always processed **in the order received**.
- For each new CPER, the AO uses cperlib to extract the **CreatorID** and
  **timestamp** (also PlatformID/PartitionID for diagnostics).
- The AO selects the analyzer from the CreatorID routing table.
  - **No matching analyzer / no CreatorID** → print a hard-to-ignore on-screen
    error showing the CPER's timestamp, CreatorID, PlatformID, PartitionID, then
    **continue** to the next CPER.
- **Lookback window (directory-scoped):** CPERs are stored under
  `cper_storage/{PlatformID}/{PartitionID}/`. PlatformID is the machine GUID,
  PartitionID identifies a piece of silicon, and every CPER in that directory
  shares the same CreatorID. The AO looks **only in the triggering CPER's
  directory** and selects CPERs whose timestamp falls in the inclusive range
  `[timestamp − prior_days, timestamp]`.
  - On an unparseable header timestamp, warn and fall back to the file's
    filesystem mtime for ordering.
- The window list is ordered by **descending time**: the new CPER is first, the
  oldest in-range CPER is last.
- The AO writes the list to an **input file** and calls the analyzer with
  `--input-file <path>` (avoids overflowing the command line).
- The AO **waits** for the analyzer to complete.

## 3. Output handling

- Before invoking an analyzer, the AO **deletes any pre-existing `.json` and
  `.cpad` files** from the analyzer's own directory, so any such file present
  after the run is definitively this run's output.
- Each run produces **zero-or-one `.json`** and **zero-or-one `.cpad`**.
- On success:
  - A produced `.json` is **moved** into the newest CPER's directory.
  - A produced `.cpad` is **copied** into the newest CPER's directory (same place
    as the JSON), then **evaluated by the policy engine** and, on approval,
    **submitted** (policy → submit order preserved, reusing `policy.py` and
    `submit_cpad.py`).

## Analyzer authoring contract

A new analyzer `analyzer-<company>.py` must support:

1. `--discover` → print the JSON descriptor above and exit 0.
2. `--input-file <path>` → read the AO's JSON input file
   (`cper_files` newest-first, `newest_cper`, `creator_id`, `newest_timestamp`,
   `prior_days`), analyze, and write outputs **next to the script**:
   - exactly one `.json` (analysis result), and
   - zero or one `.cpad` (remediation, e.g. SPPR), created only when warranted.
3. Exit code 0 on success, non-zero on failure.

## Simplicity decisions (this iteration)

- No timestamp caching (convert via cperlib as needed; revisit if slow).
- No temp/working directories — outputs are written next to the analyzer script
  and the AO clears stale outputs beforehand.
- Contoso analyzer lives in its own subdirectory.
