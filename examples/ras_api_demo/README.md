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
python3 servers/redfishMockupServer_platform.py -D mockups/ras_gen10 -p 8000

# Terminal 2 — SDK Event Listener
python3 examples/ras_api_demo/event_listener_sdk.py --port 8888 --bmc localhost:8000

# Terminal 3 — Demo
python3 examples/ras_api_demo/reset_server.py --clean-temp && python3 examples/ras_api_demo/init_error_pipeline.py && python3 examples/ras_api_demo/ras_api_plugin_demo.py
```

## Architecture

- **Pane 1 — BMC Server** (`redfishMockupServer_platform.py`): Simulates a BMC with RAS LogService
- **Pane 2 — SDK Listener** (`event_listener_sdk.py`): Subscribes to BMC events, auto-downloads CPERs, notifies demo client via TCP
- **Pane 3 — Demo Client** (`ras_api_plugin_demo.py`): Guided demo flow — inject errors, collect CPERs, analyze, policy check, submit SPPR

## Module Architecture

| Module | Class | Responsibility |
|---|---|---|
| `ras_api_plugin_demo.py` | `RASAPIPluginDemo` | Thin orchestrator — drives the demo flow |
| `event_listener_sdk.py` | — | SDK-based listener with auto-download and TCP notification |
| `analyzer.py` | `CPERAnalyzer` | Converts binary `.cper` → JSON via `cper-convert`, detects repeat errors, auto-creates SPPR CPADs |
| | `AnalysisOrchestrator` | Thin wrapper that creates a fresh (stateless) `CPERAnalyzer` per run |
| `policy.py` | `PolicyEngine` | Evaluates CPAD files against trust/action/platform registries |
| `submit_cpad.py` | `CPADSubmitter` | Reads binary CPAD, base64-encodes, POSTs as JSON to BMC |

### Data Flow

```
  inject_memory_error()     ──►  BMC creates Corrected CPER in LogService
         │                       BMC pushes OemCper.1.0.CperCreated event
         │
  SDK listener              ──►  Auto-downloads .cper files to cper_storage/
         │                       Sends TCP notification to demo client
         │
  collect_cpers()           ──►  Reads downloaded CPERs from local storage
         │
  analyze_cpers()           ──►  cper-convert to-json → decoded summary → repeat detection
         │                       Auto-creates SPPR CPAD if repeat error found
         │
  run_policy_check()        ──►  Validates SPPR CPAD against policy registries
         │
  submit_sppr_cpad()        ──►  Binary CPAD → base64 → JSON POST to BMC
         │
  (BMC creates Action Event CPER)
         │
  collect + analyze again   ──►  Picks up Action Event CPER, confirms repair
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

Each module can be run independently:

```bash
# Collect CPERs from a running server
python examples/ras_api_demo/collect_cpers.py --base-url http://localhost:8000

# Analyze collected CPER files
python examples/ras_api_demo/analyzer.py --cper-dir ras_demo_output/cper_storage

# Run policy check on analyzer-generated SPPR CPADs
python examples/ras_api_demo/policy.py --cpad-dir ras_demo_output/Analyzer_output_files

# Submit a binary CPAD to the server
python examples/ras_api_demo/submit_cpad.py --base-url http://localhost:8000 path/to/file.cpad
```
