#!/usr/bin/env python3
"""
RAS Plugin Demo - Samsung DIMM Guided Demonstration
====================================================

Demonstrates the RASAPI plugin capabilities of the BMC Redfish Simulator
against a Samsung-manufacturer DIMM. Injects five corrected DRAM errors
one at a time, and lets the Samsung memory-vendor shim
(analyzers/contoso/memory_shims/analyzer_samsung.py) analyze them and
recommend actions such as Page Offline and a Replace DIMM advisory.

Usage:
    # Start the simulator first
    python servers/redfishMockupServer_platform.py -D mockups/ras_gen1 -p 8000 \
        --endpoint-config ras_endpoint_config_samsung.json

    # Run the demo
    python examples/ras_api_demo/ras_api_samsung_demo.py

Prerequisite: the Samsung DIMM slot (chiplet 0, controller 0, channel 0,
dimm 1) must be configured in mockups/ras_gen1/ras_endpoint_config_samsung.json with
dram_manufacturer_id [0x80, 0xCE].
"""

import sys
import subprocess
import logging
import importlib.util
from pathlib import Path

# Import modular components (local modules)
from analysis_orchestrator import AnalysisOrchestrator
from demo_state import (
    DEMO_EVENT_DESTINATION,
    DemoStateError,
    reset_demo_state as reset_shared_demo_state,
)
from policy import PolicyEngine
from submit_cpad import CPADSubmitter

# Configure logging - set to WARNING to reduce clutter
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class RASAPISamsungDemo:
    """Main orchestrator for the Samsung DIMM RASAPI Plugin demonstration."""

    # Hardcoded platform configuration
    PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"
    BMC_HOST = "localhost"
    BMC_PORT = 8000
    EVENT_DESTINATION = DEMO_EVENT_DESTINATION

    # Manager configuration
    MANAGER_ID = "System"

    # BMC credentials.  Passed to the orchestrator, which uses them to discover
    # the host and to tell the event listener how to subscribe (the EventService
    # subscription requires auth).  The mockup runs in permissive simulator mode
    # (no AccountService), so any Basic credentials are accepted.
    BMC_USER = "demo"
    BMC_PASSWORD = "demo"

    # Contoso partition seed for the orchestrator's standalone CPER lookup.
    # At runtime the orchestrator discovers the live endpoint inventory from
    # the host's RASEndpoints collection; this value only mirrors the mockup
    # so the standalone analyze path has a partition to look under.
    ENDPOINTS = [
        {"Name": "Contoso Endpoint", "partition_id": "22222222-3333-4444-5555-666666666666", "creator_id": "11111111-2222-3333-4444-555555555555"}
    ]

    # Platform to BMC URL mapping (for multi-BMC support)
    PLATFORM_BMC_MAP = {
        # Example: "990f8820-bd4d-5064-58cc-961a053dea79": "http://localhost:8000",
    }

    # The five corrected DRAM errors this demo injects, one at a time.
    # All land on subchannel A / rank 1 / bank group 4 / bank 3 / DRAM device 5
    # (set in contososamsungMemErrorSpoof.inject.json); device 5 carries
    # DQ 20-23, given here as device-local DQ 0-3. The scenario's channel 2
    # is mapped to the Samsung DIMM slot this platform configures (channel 0,
    # dimm 1).
    SAMSUNG_DRAM_ERRORS = [
        {"row": 0xE4C7, "column": 0x350, "ce_count": 1,
         "beat": "dram=5;dq=1,2,3;beats=0,2,3,4,5,6,7,8,9,12,13,14"},
        {"row": 0xE4C7, "column": 0x160, "ce_count": 2,
         "beat": "dram=5;dq=1,3;beats=1,2,3,4,5,6,7,8,9,10,13,14,15"},
        {"row": 0xE4C2, "column": 0x7D0, "ce_count": 3,
         "beat": "dram=5;dq=0,1;beats=1,2,5,6"},
        {"row": 0xE2C7, "column": 0x430, "ce_count": 4,
         "beat": "dram=5;dq=0,1,2;beats=0,2,4,6,8,10,12,14"},
        {"row": 0xE2C3, "column": 0x7B0, "ce_count": 5,
         "beat": "dram=5;dq=0,1,2,3;beats=0,1,2,3,8,9,10,11"},
        # 6th error disabled for now:
        # {"row": 0xE2C2, "column": 0x610, "ce_count": 6,
        #  "beat": "dram=5;dq=0,1,2,3;beats=0,4,6,8,10,11,12,13,15"},
    ]

    def __init__(self):
        """Initialize the demo orchestrator."""
        self.base_url = f"http://{self.BMC_HOST}:{self.BMC_PORT}"
        self.server_online = False

        # Storage directories (relative to this script's location)
        self.script_dir = Path(__file__).resolve().parent
        self.output_dir = self.script_dir / "ras_demo_output"
        self.cper_storage_dir = self.output_dir / "cper_storage"
        self.cpad_storage_dir = self.script_dir / "cpad_storage"
        self.cper_storage_dir.mkdir(parents=True, exist_ok=True)
        self._require_samsung_dfa()

        # Contoso Error Injector (vendor tool) + its editable injection spec.
        # The demo shells out to this tool to build error-injection CPADs,
        # demonstrating the standard "vendor tool produces vendor CPADs" pattern.
        # The committed spec already targets channel 0 / dimm 1 - the DIMM
        # slot configured as Samsung in ras_endpoint_config_samsung.json.
        self.injector = self.script_dir / "analyzers" / "contoso" / "injector-contoso.py"
        self.injection_spec = self.cpad_storage_dir / "contososamsungMemErrorSpoof.inject.json"
        self.endpoint_config = (
            self.script_dir.parents[1] / "mockups" / "ras_gen1"
            / "ras_endpoint_config_samsung.json")
        self.generated_cpad_dir = self.output_dir / "injected_cpads"
        self.generated_cpad_dir.mkdir(parents=True, exist_ok=True)

        # CPAD submitter — handles base64 + JSON transport to BMC
        self.submitter = CPADSubmitter(
            base_url=self.base_url,
            manager_id=self.MANAGER_ID,
            platform_bmc_map=self.PLATFORM_BMC_MAP,
        )

        # Analysis orchestrator — the coordinator.  It discovers analyzer
        # plugins, discovers/monitors hosts, receives CPERs from the event
        # listener, and routes them to analyzers → policy → back to the host.
        self.analysis = AnalysisOrchestrator(
            platform_id=self.PLATFORM_ID,
            partition_id=self.ENDPOINTS[0]['partition_id'],
            cper_storage_dir=str(self.cper_storage_dir),
            output_dir=str(self.output_dir),
            policy_engine=PolicyEngine(),
            submitter=self.submitter,
        )
        if not any(
                "80 CE" in shim.get("dram_manufacturer_ids", [])
                for analyzer in self.analysis.analyzers
                for shim in analyzer.memory_analyzers):
            raise RuntimeError(
                "Samsung Memory Analyzer Shim was not discovered for "
                "DRAM manufacturer 80 CE")

    def _require_samsung_dfa(self):
        """Fail before injection when the separately distributed DFA is absent."""
        path = (
            self.script_dir / "analyzers" / "contoso" / "memory_shims"
            / "samsung_dfa.py")
        if not path.is_file():
            raise RuntimeError(
                f"Samsung DFA is not installed: place samsung_dfa.py at {path}")
        spec = importlib.util.spec_from_file_location(
            "samsung_dfa_startup_check", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Samsung DFA cannot be loaded from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, "analyze", None)):
            raise RuntimeError(
                "Samsung DFA must define callable analyze(records)")

    def _wait_and_analyze(self, count=1):
        """Wait for the listener to deliver `count` CPER(s), then route them.

        The event listener downloads CPERs and notifies the orchestrator, which
        buffers them.  Here we wait for at least one, then ask the orchestrator
        to route everything it has received (analyze → policy → submit).
        Each error injection yields two CPERs — the memory-error CPER and the
        Platform Action Event CPER acknowledging the injection CPAD — so the
        injection steps wait for both before analyzing.  Every
        decoded memory-controller CPER passes through the Contoso analyzer's
        MemoryControllerAnalyzer, which invokes the Samsung shim for this DIMM's
        manufacturer ID.
        """
        input("\n🔑 Press Enter to wait for the listener and analyze...")
        if not self.analysis.wait_for_cpers(count=count, timeout=30.0):
            print("\n   ⚠️  No CPER notification within the timeout — "
                  "analyzing whatever has arrived.")
        self.analysis.process_new_cpers()

    def run(self):
        """Run the guided demonstration flow.

        Real-world order:
        1. Analyzer discovery — which CreatorIDs can we handle?
        2. Tell the orchestrator to monitor the host. It discovers the host's
           RAS service, matches every endpoint to an analyzer, and only then
           tells the event listener to subscribe to the host.
        3. Inject five corrected memory errors on the Samsung DIMM, one at a
           time. After each
           injection, wait for the listener and let the orchestrator route
           the CPER to the Contoso analyzer, which calls the Samsung
           memory-vendor shim. Each injection yields two CPERs: the memory
           error and the injection acknowledgment. The shim's recommendations
           (e.g. Page Offline) are submitted to the host after policy
           approval; boot-time advisories (e.g. Replace DIMM) are routed to
           the simulated server-fleet control plane instead.
        4. The BMC confirms the Page Offline with a Platform Action CPER;
           analyze it so it becomes history for later decisions.
        """
        self.print_banner()
        try:
            self.reset_demo_state()
        except DemoStateError as exc:
            print(f"\n❌ Cannot start with a clean demo state: {exc}")
            return

        # Step 1 — Analyzer discovery (runs during construction; report it now).
        if not self.analysis.print_discovery_report(show_memory_analyzers=True):
            print("\n" + "=" * 80)
            print("❌ Cannot proceed - no usable analyzers were discovered")
            print("=" * 80)
            return

        # Step 2 — Tell the orchestrator to discover and monitor the host.
        # The orchestrator performs the RAS API discovery and, on success,
        # commands the event listener to subscribe.
        input("\n🔑 Press Enter to discover and start monitoring the host...")
        monitored = self.analysis.add_host(
            name="Contoso Cloud Host Gen 1",
            host=self.BMC_HOST, port=self.BMC_PORT,
            username=self.BMC_USER, password=self.BMC_PASSWORD,
            manager_id=self.MANAGER_ID,
        )
        if not monitored:
            print("\n" + "=" * 80)
            print("❌ Cannot proceed - the host is not monitorable")
            print("=" * 80)
            return
        self.server_online = True

        # Step 3 — Inject the five corrected DRAM errors, one at a time.
        for index, error in enumerate(self.SAMSUNG_DRAM_ERRORS, 1):
            input("\n🔑 Press Enter for the next operation...")
            injected = self.inject_dram_row_error(
                row=error["row"], column=error["column"], beat=error["beat"],
                ce_count=error["ce_count"],
                occurrence_label=f"error {index} of {len(self.SAMSUNG_DRAM_ERRORS)}")
            if not injected:
                print("\n   ⚠️  Skipping analysis for this error - injection failed.")
                continue
            self._wait_and_analyze(count=2)

        # Step 4 — Any approved repair submission triggers informational CPERs
        # from the endpoint; wait for and analyze them.
        self._wait_and_analyze()

        input("\n🔑 Press Enter to complete the demonstration...")
        print("\n" + "=" * 80)
        print("✅ OCP RAS API Samsung DIMM Demonstration Complete!")
        print("=" * 80)
        print("\n📊 What this demonstration showed (Samsung DFA integration flow):")
        print("\n   Part 1 — Detect")
        print("   [1] Injected five corrected DRAM errors on a Samsung DIMM")
        print("       via Error Injection CPADs")
        print("   [2] The BMC minted a memory-error CPER (plus a Platform Action")
        print("       CPER acknowledging the injection) and fired a Redfish event")
        print("   [3] The SDK event listener downloaded each CPER over the RAS API")
        print("   [4] The orchestrator routed it by CreatorID to the Contoso analyzer,")
        print("       which built the lookback window and dispatched it to the")
        print("       Samsung shim by DRAM manufacturer ID (80 CE)")
        print("\n   Part 2 — Decide")
        print("   [5] Samsung DFA analyzed the DIMM's error history on every error")
        print("   [6] Identified the DIMM fault from that history")
        print("   [7] Issued a runtime Recommendation (Page Offline, 0x8002)")
        print("       for every implicated page plus a boot-time Advisory")
        print("       (Replace DIMM, 0x0005)")
        print("   [8] The PolicyEngine checked each CPAD: creator trusted, action")
        print("       known, action permitted, platform allowed, confidence ≥")
        print("       threshold — denied CPADs become POLICY_REJECTED CPERs")
        print("\n   Part 3 — Act")
        print("   [9] Submitted the approved runtime CPAD to the BMC; the boot-time")
        print("       advisory went to the simulated fleet control plane")
        print("   [10] The BMC executed it and emitted a confirmation CPER, which")
        print("        loops back to [3] as history: later decisions skip pages")
        print("        already offlined and offline only new ones")
        print("\n🎯 RAS Plugin Demonstration Complete!")
        print("=" * 80 + "\n")
        print("🧹 To close the demo windows and return to a clean terminal, run:")
        print("      ./examples/ras_api_demo/cleanup_ras_demo.sh")
        print("   (If you launched via run_samsung_ras_demo.sh, this command is")
        print("    already pre-typed in this pane — just press ENTER to run it.)\n")

    def print_banner(self):
        """Print the application banner."""
        print("\n" + "=" * 80)
        print(" " * 15 + "RAS API Plugin Demo - Samsung DIMM Guided Demonstration")
        print("=" * 80 + "\n")

    def reset_demo_state(self):
        """Start every run from a clean state, however the demo is launched.

        Clears the BMC's stored CPER log entries and the client-side CPER,
        CPAD, and analyzer storage (same as reset_server.py --clean-temp and
        init_error_pipeline.py). Without this, CPERs from earlier runs stay
        in the lookback window, so every analysis re-reads them and the
        Samsung analyzer reports the old fault from the first error.
        """
        entries_path = (self.script_dir.parent.parent / "mockups" / "ras_gen1" /
                        "redfish" / "v1" / "Managers" / self.MANAGER_ID /
                        "LogServices" / "CPER" / "Entries")
        removed = reset_shared_demo_state(
            entries_path,
            self.MANAGER_ID,
            self.output_dir,
            self.base_url,
            self.BMC_USER,
            self.BMC_PASSWORD,
            destination=self.EVENT_DESTINATION,
        )
        print(
            f"Removed {removed} leftover demo event subscription(s) "
            "from the BMC")

    def _build_dram_row_error_cpad(self, row, column, beat, ce_count=1):
        """Build one corrected DRAM row-error CPAD via the Contoso Error Injector.

        Unlike the original two-error demo (which fixes the row in the
        committed injection spec and only varies the column), this demo
        overrides both row and column per call so it can spread errors across
        multiple rows as well as multiple columns.

        Args:
            row:    DRAM row address for this error.
            column: DRAM column address for this error.
            beat:   A --beat spec (e.g. "dram=3;dq=0;beats=1") selecting the
                    failing DRAM/DQ/beats.
            ce_count: Corrected-error count reported for this error.

        Returns:
            Path to the generated binary .cpad file.
        """
        out_path = self.generated_cpad_dir / f"mem_err_row{row}_col{column}.cpad"
        cmd = [
            sys.executable, str(self.injector), "inject",
            "--spec", str(self.injection_spec),
            "--endpoint-config", str(self.endpoint_config),
            "--set", f"section.additional.row={row}",
            "--set", f"section.additional.column={column}",
            "--set", f"section.misc0.ce_count={ce_count}",
            "--beat", beat,
            "--out", str(out_path),
        ]
        print(f"\n   Running the Contoso Error Injector (vendor tool):")
        print(f"      injector-contoso.py inject --spec {self.injection_spec.name} "
              f"--endpoint-config {self.endpoint_config.name} "
              f"--set section.additional.row={row} "
              f"--set section.additional.column={column} "
              f"--set section.misc0.ce_count={ce_count} --beat \"{beat}\" "
              f"--out {out_path.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip():
            for line in result.stdout.rstrip().splitlines():
                print(f"      {line}")
        if result.returncode != 0:
            print(result.stderr.rstrip())
            raise RuntimeError("Contoso Error Injector failed to generate the CPAD")
        return out_path

    def inject_dram_row_error(self, row, column, beat, occurrence_label,
                              ce_count=1):
        """Inject one corrected DRAM row error: build its CPAD and submit it.

        Args:
            row:    DRAM row address for this error.
            column: DRAM column address for this error.
            beat:   A --beat spec selecting the failing DRAM/DQ/beats.
            occurrence_label: Short description shown in the banner.
            ce_count: Corrected-error count reported for this error.

        Returns:
            True if the injection CPAD was built and submitted.
        """
        if not self.server_online:
            print("\n❌ Cannot inject error - server is offline!")
            print("   Please start the server and try again.")
            return False

        print("\n" + "=" * 80)
        print(f"\t\tSPOOFING CORRECTED DRAM ERROR ({occurrence_label})")
        print("=" * 80)

        try:
            cpad_path = self._build_dram_row_error_cpad(row, column, beat, ce_count)
            print(f"\n🚀 Submitting Error Injection CPAD (row {row}, column {column}; {beat})...")
            self._submit_binary_cpad(
                cpad_path, verbose_steps=True,
                source_label=(f"Contoso DRAM error CPAD — corrected error at "
                              f"row {row}, column {column} ({beat})"))
            return True
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return False

    def _submit_binary_cpad(self, cpad_file_path, verbose_steps=True, source_label=None):
        """Submit a binary CPAD file — delegates to CPADSubmitter."""
        return self.submitter.submit(
            cpad_file_path, verbose_steps=verbose_steps, source_label=source_label)


def main():
    """Main entry point"""
    demo = None
    try:
        demo = RASAPISamsungDemo()
        demo.run()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("⚠️  Operation cancelled by user (Ctrl+C)")
        print("=" * 80)
    finally:
        # Remove the event subscriptions this demo created on the host(s).
        if demo is not None:
            demo.analysis.close()


if __name__ == "__main__":
    main()
