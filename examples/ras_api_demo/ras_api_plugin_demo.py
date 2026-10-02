#!/usr/bin/env python3
"""
RAS Plugin Demo - Guided Demonstration
======================================

Demonstrates the RASAPI plugin capabilities of the BMC Redfish Simulator.
Shows platform info, injects errors via CPAD, collects CPERs, analyzes them,
validates policies, and triggers automated remediation.

Usage:
    # Start the simulator first
    python servers/redfishMockupServer_platform.py -D mockups/public-rackmount1

    # Run the demo
    python examples/ras_api_demo/ras_api_plugin_demo.py
"""

import sys
import subprocess
import logging
from pathlib import Path

# Import modular components (local modules)
from analysis_orchestrator import AnalysisOrchestrator
from policy import PolicyEngine
from submit_cpad import CPADSubmitter

# Configure logging - set to WARNING to reduce clutter
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class RASAPIPluginDemo:
    """Main orchestrator for RASAPI Plugin demonstration."""
    
    # Hardcoded platform configuration
    PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"
    BMC_HOST = "localhost"
    BMC_PORT = 8000
    
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

        # Contoso Error Injector (vendor tool) + its editable injection spec.
        # The demo shells out to this tool to build error-injection CPADs,
        # demonstrating the standard "vendor tool produces vendor CPADs" pattern.
        self.injector = self.script_dir / "analyzers" / "contoso" / "injector-contoso.py"
        self.injection_spec = self.cpad_storage_dir / "contosoMemErrorSpoof.inject.json"
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

    def _wait_and_analyze(self):
        """Wait for the listener to deliver CPER(s), then route them.

        The event listener downloads CPERs and notifies the orchestrator, which
        buffers them.  Here we wait for at least one, then ask the orchestrator
        to route everything it has received (analyze → policy → submit).
        """
        input("\n🔑 Press Enter to wait for the listener and analyze...")
        if not self.analysis.wait_for_cpers(count=1, timeout=30.0):
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
        3. Inject a corrected memory error (row 1234, column 567). The listener
           downloads the CPER; the orchestrator routes it to the analyzer.
        4. Inject a second corrected error (same row, column 891). The analyzer
           detects the failing row, produces an SPPR CPAD; the orchestrator runs
           policy and submits it back to the host.
        5. The SPPR repair emits informational CPERs; analyze them.
        """
        self.print_banner()

        # Step 1 — Analyzer discovery (runs during construction; report it now).
        if not self.analysis.print_discovery_report():
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

        # Step 3 — Inject a first corrected DRAM row error (row 1234, column
        # 567, DRAM 3 / DQ 0), then wait for the listener and analyze.
        input("\n🔑 Press Enter for the next operation...")
        self.inject_dram_row_error(column=567, beat="dram=3;dq=0;beats=2",
                                   occurrence_label="1st column address in the row")
        self._wait_and_analyze()

        # Step 4 — Inject a second corrected DRAM row error (same row, different
        # column, and a different DQ of the *same* DRAM 3).  This analysis
        # detects the failing row, generates an SPPR CPAD, clears policy, and
        # submits it back to the host.
        input("\n🔑 Press Enter for the next operation...")
        self.inject_dram_row_error(column=891, beat="dram=3;dq=1;beats=7",
                                   occurrence_label="2nd column address in the row")
        self._wait_and_analyze()

        # Step 5 — The SPPR submission triggers informational CPERs from the
        # repair; wait for and analyze them.
        self._wait_and_analyze()
        
        input("\n🔑 Press Enter to complete the demonstration...")
        print("\n" + "=" * 80)
        print("✅ OCP RAS API Demonstration Complete!")
        print("=" * 80)
        print("\n📊 What this demonstration showed:")
        print("   ✓ Discovered RAS API endpoints via Redfish")
        print("   ✓ Injected an error via CPADs")
        print("   ✓ Collected the resulting CPERs via Redfish RAS API interfaces")
        print("   ✓ Analyzed the CPERs")
        print("   ✓ The analyzer suggested a RAS action, which we evaluated against")
        print("     a data center operator policy")
        print("   ✓ Routed an approved RAS action back to the BMC that reported the")
        print("     errors")
        print("   ✓ Demonstrated the full round-trip flow: RAS API endpoint → analyzer")
        print("     → back to the endpoint")
        print("\n🎯 RAS Plugin Demonstration Complete!")
        print("=" * 80 + "\n")
        print("🧹 To close the demo windows and return to a clean terminal, run:")
        print("      ./examples/ras_api_demo/cleanup_ras_demo.sh")
        print("   (If you launched via run_ras_demo.sh, this command is already")
        print("    pre-typed in this pane — just press ENTER to run it.)\n")
    
    def print_banner(self):
        """Print the application banner."""
        print("\n" + "=" * 80)
        print(" " * 20 + "RAS API Plugin Demo - Guided Demonstration")
        print("=" * 80 + "\n")
    
    def _build_dram_row_error_cpad(self, column, beat):
        """Build one corrected DRAM row-error CPAD via the Contoso Error Injector.

        A DRAM row error is just one of the many error types the RAS API can
        carry; this demo focuses on it because repeated errors on the same row
        are what trigger a row-repair (SPPR) action.  Every call targets the
        *same* DRAM row (fixed in the committed injection spec); only the column
        and failing beats vary, so the beats stay on one physical DRAM chip
        while the column moves — which looks like a failing row.

        Args:
            column: DRAM column address for this error.
            beat:   A --beat spec (e.g. "dram=3;dq=0;beats=2") selecting the
                    failing DRAM/DQ/beats.

        Returns:
            Path to the generated binary .cpad file.
        """
        out_path = self.generated_cpad_dir / f"mem_err_col{column}.cpad"
        cmd = [
            sys.executable, str(self.injector), "inject",
            "--spec", str(self.injection_spec),
            "--set", f"section.additional.column={column}",
            "--beat", beat,
            "--out", str(out_path),
        ]
        print(f"\n   Running the Contoso Error Injector (vendor tool):")
        print(f"      injector-contoso.py inject --spec {self.injection_spec.name} "
              f"--set section.additional.column={column} --beat \"{beat}\" "
              f"--out {out_path.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip():
            for line in result.stdout.rstrip().splitlines():
                print(f"      {line}")
        if result.returncode != 0:
            print(result.stderr.rstrip())
            raise RuntimeError("Contoso Error Injector failed to generate the CPAD")
        return out_path

    def inject_dram_row_error(self, column, beat, occurrence_label):
        """Inject one corrected DRAM row error: build its CPAD and submit it.

        A DRAM row error is one specific error type among the many the RAS API
        can carry.  Each call hits the same DRAM row (only the column differs)
        on the same physical DRAM (only the DQ/beats differ), so repeated calls
        look like a failing row to the analyzer.

        Args:
            column: DRAM column address for this error.
            beat:   A --beat spec selecting the failing DRAM/DQ/beats.
            occurrence_label: Short description shown in the banner.
        """
        if not self.server_online:
            print("\n❌ Cannot inject error - server is offline!")
            print("   Please start the server and try again.")
            return

        print("\n" + "=" * 80)
        print(f"\t\tSPOOFING CORRECTED DRAM ROW ERROR ({occurrence_label})")
        print("=" * 80)

        try:
            cpad_path = self._build_dram_row_error_cpad(column, beat)
            print(f"\n🚀 Submitting Error Injection CPAD (row 1234, column {column}; {beat})...")
            self._submit_binary_cpad(
                cpad_path, verbose_steps=True,
                source_label=(f"Contoso DRAM row-error CPAD — corrected error at "
                              f"row 1234, column {column} ({beat})"))
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    def _submit_binary_cpad(self, cpad_file_path, verbose_steps=True, source_label=None):
        """Submit a binary CPAD file — delegates to CPADSubmitter."""
        return self.submitter.submit(
            cpad_file_path, verbose_steps=verbose_steps, source_label=source_label)


def main():
    """Main entry point"""
    demo = None
    try:
        demo = RASAPIPluginDemo()
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
