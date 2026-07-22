# RAS API Demo

End-to-end demonstration of the BMC Redfish Simulator's RAS (Reliability, Availability, Serviceability) plugin.

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
bash examples/ras_api_demo/setup.sh
```

- **libcper** — cloned from [github.com/dwalton64/libcper](https://github.com/dwalton64/libcper), built with meson/ninja into `src/plugins/ras/libcper/`. Produces `cper-convert` and `cpad-convert` binaries.
- **redfish-client-sdk** — cloned from [github.com/harira-microsoft/redfish-client-sdk](https://github.com/harira-microsoft/redfish-client-sdk) and installed as a pip package into `redfish_client_sdk/python/`

To update the SDK:
```bash
bash examples/ras_api_demo/setup.sh --update
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

## Support Files

| File | Purpose |
|---|---|
| `run_ras_demo.sh` | Tmux launcher (3 panes: server, SDK listener, demo) |
| `setup.sh` | Fetches and installs the Redfish Client SDK |
| `reset_server.py` | Resets BMC/Redfish LogService entries and temporary CPER files |
| `init_error_pipeline.py` | Clears client-side CPER/CPAD/analyzer storage under `ras_demo_output/` |
| `cpad_storage/` | Binary CPAD files used for error injection and SPPR templates |
| `ras_demo_output/` | Runtime output (collected CPERs, analyzer JSON, SPPR CPADs) |

## Standalone Usage

Some modules can be run independently:

```bash
# Run policy check on analyzer-generated SPPR CPADs
python examples/ras_api_demo/policy.py --cpad-dir ras_demo_output/Analyzer_output_files

# Submit a binary CPAD to the server
python examples/ras_api_demo/submit_cpad.py --base-url http://localhost:8000 path/to/file.cpad
```
