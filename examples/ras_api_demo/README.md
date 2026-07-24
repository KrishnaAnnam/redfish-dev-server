# OCP RAS API Demo

End-to-end demonstration of the OCP RAS (Reliability, Availability, Serviceability) API plugin.

The [RAS API](https://www.opencompute.org/contributions?contributions%5Bquery%5D=RAS%20API) is a standard interface
collecting rich error event data and provides interfaces for driving automated actions.  When errors occur, they
are logged in Common Plaform Error Records (CPERs). An error analyzer can generate a Common Platform Action 
Descriptor (CPAD) to suggest actions that might be taken to mitigate the hardware fault inferred from analyzing
errors. This demo provides a non-normative example of how the RAS API could be used for Out Of Band fault 
management using standard Redfish interfaces on the BMC.

> **This demo is an example plugin for the Redfish dev server.** The server
> ([`servers/redfishMockupServer_platform.py`](../../servers/redfishMockupServer_platform.py))
> loads plugins declared in a platform's `platform_config.json`. The RAS plugin
> lives at [`src/plugins/ras/`](../../src/plugins/ras) and is enabled for this
> demo by [`mockups/ras_gen1/platform_config.json`](../../mockups/ras_gen1/platform_config.json)
> (`"plugins": [{"name": "ras", ...}]`). Everything in this folder is the
> **client/analysis side** that drives that plugin. To learn how plugins are
> built and registered, see [`docs/PLUGIN_SDK.md`](../../docs/PLUGIN_SDK.md).

## Documentation index

| Document | What it covers |
|---|---|
| **README.md** (this file) | Setup, how to run, architecture, [glossary](#glossary), and the [end-to-end walkthrough](#end-to-end-walkthrough) |
| [analyzer-orchestrator.md](analyzer-orchestrator.md) | The Analysis Orchestrator: analyzer/host discovery, CPER routing, and policy → submit |
| [CPAD_SUBMISSION.md](CPAD_SUBMISSION.md) | How a CPAD is submitted to the BMC and the acceptance checks it must pass (spec §6.5) |
| [POLICY_ENGINE.md](POLICY_ENGINE.md) | The operator policy gate that approves/denies proposed actions |
| [analyzers/contoso/Analyzer-Design.md](analyzers/contoso/Analyzer-Design.md) | How the example Contoso CPER analyzer works |
| [analyzers/contoso/contoso-cper-sections.md](analyzers/contoso/contoso-cper-sections.md) | Binary layout of the Contoso CPER sections (reference) |
| [analyzers/contoso/error-injector-contoso.md](analyzers/contoso/error-injector-contoso.md) | The vendor error-injection tool and its JSON injection spec |

## Prerequisites

- Python 3.10+
- WSL (Ubuntu 24.04 recommended) for running the demo
- `tmux` for the 3-pane demo launcher
- `meson` and `ninja-build` for building libcper

```bash
sudo apt-get install tmux meson ninja-build
```

## Setup

All commands below assume you are at the **project root** in WSL:
```bash
cd /mnt/c/Projects/<your-clone>
```

### 1. Create and activate a virtual environment

```bash
python3 -m venv RasApiEnv
source RasApiEnv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Fetch external dependencies

```bash
# Build libcper (server-side CPER parsing)
bash build_libcper.sh

# Install the Redfish Client SDK (demo event listener)
bash examples/ras_api_demo/setup_dependencies.sh
```

- **libcper** — cloned from [github.com/dwalton64/libcper](https://github.com/dwalton64/libcper), built with meson/ninja into `src/plugins/ras/libcper/`. Produces `cper-convert` and `cpad-convert` binaries.
- **redfish-client-sdk** — cloned from [github.com/harira-microsoft/redfish-client-sdk](https://github.com/harira-microsoft/redfish-client-sdk) and installed as a pip package into `redfish_client_sdk/python/`

To update the SDK:
```bash
bash examples/ras_api_demo/setup_dependencies.sh --update
```

## Quick Start

```bash
# From the project root, launch all three panes (server, listener, demo) in tmux:
bash examples/ras_api_demo/run_ras_demo.sh
```

Or run each component manually:

```bash
# Terminal 1 — BMC Server
python3 servers/redfishMockupServer_platform.py -D mockups/ras_gen1 -p 8000

# Terminal 2 — SDK Event Listener
python3 examples/ras_api_demo/event_listener_sdk.py --port 8888 --bmc localhost:8000

# Terminal 3 — Demo
python3 examples/ras_api_demo/reset_server.py --clean-temp && python3 examples/ras_api_demo/init_error_pipeline.py && python3 examples/ras_api_demo/ras_api_plugin_demo.py
```

## Architecture

- **Pane 1 — BMC Server** (`redfishMockupServer_platform.py`): Simulates a BMC with a RAS LogService
- **Pane 2 — SDK Listener** (`event_listener_sdk.py`): Subscribes to a host's events on command, auto-downloads CPERs, and notifies the orchestrator over a control socket
- **Pane 3 — Demo Client** (`ras_api_plugin_demo.py`): Guided demo flow — tells the orchestrator which host to monitor, then injects DRAM row errors; the orchestrator handles discovery, analysis, policy, and submit

## Module Architecture

| Module | Class | Responsibility |
|---|---|---|
| `ras_api_plugin_demo.py` | `RASAPIPluginDemo` | Drives the guided demo: tells the orchestrator which host to monitor, then injects DRAM row errors |
| `analysis_orchestrator.py` | `AnalysisOrchestrator` | Coordinator — discovers analyzer plugins, discovers/monitors hosts (RAS API discovery), tells the listener to subscribe, and routes CPERs → analyzers → policy → back to the host |
| `analyzers/<vendor>/analyzer-<vendor>.py` | — | Vendor analyzer plugin (e.g. Contoso): decodes its own CPERs, detects repeat errors, and emits SPPR CPADs; discovered via `--discover` |
| `event_listener_sdk.py` | — | Standalone SDK listener: subscribes on command, auto-downloads `.cper` files, notifies the orchestrator over a control socket |
| `cper_decoder.py` | `CperDecoder` | cperlib-based CPER decode; the orchestrator reads only the header (CreatorID) to route |
| `policy.py` | `PolicyEngine` | Evaluates CPAD files against trust/action/platform registries (see [POLICY_ENGINE.md](POLICY_ENGINE.md)) |
| `submit_cpad.py` | `CPADSubmitter` | Reads a binary CPAD, base64-encodes, and POSTs it as JSON to the BMC (routed by PlatformID) |

### Data Flow

```
  orchestrator.add_host()   ──►  Discovers the host (ServiceRoot → RASService →
         │                       RASEndpoints), matches every endpoint's CreatorID
         │                       to an analyzer, then tells the SDK listener to
         │                       subscribe to the host's CPER events
         │
  inject_dram_row_error()   ──►  BMC creates a Corrected CPER in its LogService
         │                       and pushes an OCPRAS CperCreated event
         │
  SDK listener              ──►  Auto-downloads the .cper to cper_storage/ and
         │                       sends a 'cper_downloaded' notification to the
         │                       orchestrator over the control socket
         │
  orchestrator              ──►  Reads the CPER header (CreatorID) and routes the
   .process_new_cpers()          CPER to the owning analyzer-<vendor>.py plugin,
         │                       which decodes it, detects a repeat, and (on the
         │                       2nd column of the same row) emits an SPPR CPAD
         │
  PolicyEngine              ──►  Evaluates the SPPR CPAD against the operator's
         │                       table-driven policy (creators + actions tables;
         │                       see POLICY_ENGINE.md)
         │
    approved ──────────────┴────────────── denied
       │                                     │
  CPADSubmitter                        orchestrator mints a POLICY_REJECTED
  POST back to the host                Platform Action CPER (create-platform-
  (routed by PlatformID)               action-cper) and delivers it via the
       │                               listener 'store_cper' → cper_storage/,
       │                               where the analyzer reports the rejection
       │
  (BMC performs the SPPR repair and emits informational Action-Event CPERs)
         │
  listener → orchestrator   ──►  Same path again: downloads, routes, and analyzes
                                 the informational CPERs to confirm the repair
```

## End-to-end walkthrough

The guided demo ([`ras_api_plugin_demo.py`](ras_api_plugin_demo.py)) advances
one step at a time — press **Enter** at each prompt. Watch all three panes: the
**demo** pane narrates the client/analysis side, the **server** pane shows the
BMC (plugin) side, and the **listener** pane shows CPERs being downloaded.

1. **Analyzer discovery.** The orchestrator runs every `analyzer-<vendor>.py`
   with `--discover` and builds a CreatorID → analyzer routing table. It prints
   one row per analyzer (name, CreatorIDs, lookback days). The Contoso analyzer
   claims CreatorID `11111111-…-555555555555`.
2. **Monitor the host.** The orchestrator discovers the host's RAS service
   (ServiceRoot → RASService → RASEndpoints), matches each endpoint's CreatorID
   to an analyzer, then tells the SDK listener to subscribe to the host's CPER
   events.
3. **Inject the 1st corrected DRAM error** (row 1234, column 567). The injector
   builds an error-injection CPAD (action `0x0006`) and submits it; the BMC logs
   a Corrected CPER and pushes an event. The listener downloads the `.cper`; the
   analyzer decodes it and records the location. One error on one cell is normal
   wear — **no action yet**.
4. **Inject the 2nd corrected DRAM error** (same row 1234, *different* column
   891). The analyzer now sees two distinct columns failing on the same row —
   evidence of a **failing row** — and emits an **SPPR CPAD** (action `0x8001`)
   with a confidence that scales with the evidence.
5. **Policy gate.** The orchestrator runs the SPPR CPAD through the
   [PolicyEngine](POLICY_ENGINE.md). On approval it submits the CPAD back to the
   BMC (see [CPAD_SUBMISSION.md](CPAD_SUBMISSION.md)); on denial it mints a
   `POLICY_REJECTED` Platform Action CPER instead.
6. **Repair confirmation.** The approved SPPR runs on the BMC, which emits
   informational Action-Event CPERs. These flow back through the same
   download → route → analyze path so the analyzer can confirm the repair.

To reset between runs, the launcher calls
[`reset_server.py`](reset_server.py) (BMC log/state) and
[`init_error_pipeline.py`](init_error_pipeline.py) (client-side storage).

## Support Files

| File | Purpose |
|---|---|
| `run_ras_demo.sh` | Tmux launcher (3 panes: server, SDK listener, demo) |
| `setup_dependencies.sh` | Fetches and installs the Redfish Client SDK |
| `reset_server.py` | Resets BMC/Redfish LogService entries and temporary CPER files |
| `init_error_pipeline.py` | Clears client-side CPER/CPAD/analyzer storage under `ras_demo_output/` |
| `cpad_storage/` | Binary CPAD files used for error injection and SPPR templates |
| `ras_demo_output/` | Runtime output (collected CPERs, analyzer JSON, SPPR CPADs) |

## Standalone Usage

Some modules can be run independently:

```bash
# Run a policy check on one or more CPAD JSON files (rule-by-rule trace).
# Exit code is 0 if every CPAD is approved, 1 otherwise.
python examples/ras_api_demo/policy.py path/to/cpad.json [more.json ...]
# Optionally override the policy tables:
python examples/ras_api_demo/policy.py --creators c.json --actions a.json cpad.json

# Submit a binary CPAD to the BMC (base64 + JSON). Default server is
# http://localhost:8000; add --verbose for the step-by-step transcript.
python examples/ras_api_demo/submit_cpad.py cpad_storage/memErrorSpoof.cpad
python examples/ras_api_demo/submit_cpad.py cpad_storage/spprSpoof.cpad --server http://localhost:8000 --verbose
```

## Glossary

| Term | Meaning |
|---|---|
| **RAS** | Reliability, Availability, and Serviceability — hardware error detection, reporting, and repair. |
| **CPER** | Common Platform Error Record — the UEFI-standard binary record a RAS endpoint emits when it detects a hardware error. Carries a header plus one or more sections. |
| **CPAD** | Common Platform Action Descriptor — a binary record describing a *proposed action* (e.g. an error injection or a repair) sent **to** an endpoint. The mirror image of a CPER. |
| **RAS API** | The OCP RAS API (Redfish) that standardizes routing CPERs from endpoints to analyzers and CPADs from analyzers back to endpoints. |
| **RAS API endpoint** | A RAS-capable hardware source (e.g. a CPU socket) that emits CPERs and accepts CPADs. Advertised under `RASService/RASEndpoints`. |
| **SPPR** | Soft Post-Package Repair — a DRAM row-repair action (CPAD action `0x8001`) that remaps a failing row to a spare. |
| **Analyzer** | A vendor-supplied `analyzer-<vendor>.py` plugin that decodes its own CPERs and, when warranted, emits a remediation CPAD. |
| **Orchestrator** | The coordinator ([`analysis_orchestrator.py`](analysis_orchestrator.py)) that discovers analyzers/hosts, routes CPERs to analyzers, and runs policy → submit. |
| **Policy Engine** | The Server Fleet Operator's gate ([POLICY_ENGINE.md](POLICY_ENGINE.md)) that approves or denies a proposed CPAD before it is submitted. |
| **FRU** | Field-Replaceable Unit — the serviceable hardware part (e.g. a DIMM) a record refers to, via `fruID`/`fruText`. |
| **CMC / MCE** | Corrected Machine Check / Machine Check Exception — CPER notification classes for corrected vs. uncorrectable errors. |
| **CreatorID** | GUID identifying the vendor/endpoint that produced a record; used to route a CPER to the right analyzer. |
| **PlatformID** | GUID identifying the physical platform (machine/node). |
| **PartitionID** | GUID identifying a piece of silicon (e.g. a socket) within the platform; maps to a RAS endpoint. |
