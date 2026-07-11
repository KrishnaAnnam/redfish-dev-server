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
    python examples/ras_plugin_parity_demo.py
"""

import sys
import os
import json
import socket
import subprocess
import requests
import time
from pathlib import Path
from datetime import datetime
import logging

# Import modular components (local modules)
from analysis_orchestrator import AnalysisOrchestrator, normalize_guid
from policy import PolicyEngine
from submit_cpad import CPADSubmitter, read_binary_cpad, parse_guid
from collect_cpers import CPERCollector

# Configure logging - set to WARNING to reduce clutter
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RASAPIPluginDemo:
    """Main orchestrator for RASAPI Plugin demonstration."""
    
    # Hardcoded platform configuration
    PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"
    BMC_HOST = "localhost"
    BMC_PORT = 8000
    
    # Manager configuration
    MANAGER_ID = "System"
    
    # Endpoint configuration
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
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
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

        # Analysis orchestrator — discovers analyzer plugins and routes CPERs.
        # It evaluates and submits analyzer-produced CPADs via the injected
        # policy engine and submitter.
        self.analysis = AnalysisOrchestrator(
            platform_id=self.PLATFORM_ID,
            partition_id=self.ENDPOINTS[0]['partition_id'],
            cper_storage_dir=str(self.cper_storage_dir),
            output_dir=str(self.output_dir),
            policy_engine=PolicyEngine(),
            submitter=self.submitter,
        )
        
        # CPER collector — downloads CPERs from BMC LogService (legacy, kept for standalone use)
        self.collector = CPERCollector(
            session=self.session,
            base_url=self.base_url,
            manager_id=self.MANAGER_ID,
            platform_id=self.PLATFORM_ID,
            partition_id=self.ENDPOINTS[0]['partition_id'],
            cper_storage_dir=str(self.cper_storage_dir),
        )
        
        # Track CPER files already seen (for incremental collection from disk)
        self._seen_cper_files = set()

        # CPERs collected in the most recent collect step (pushed to the AO)
        self._last_collected = []

        # Notification socket — connects to SDK listener's notification port
        self._notify_sock = None
        self._notify_buffer = ""

    def connect_to_listener(self, host: str = "localhost", port: int = 8889):
        """Connect to the SDK listener's notification port."""
        print(f"\n" + "=" * 80)
        print(f"\t\t\t\tCONNECTING TO SDK LISTENER")
        print("=" * 80)
        print(f"\n   Connecting to SDK listener notification port at {host}:{port}...")
        try:
            self._notify_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._notify_sock.connect((host, port))
            print(f"   ✅ Connected to SDK listener")
            print(f"   📡 Will receive real-time CPER download notifications")
        except ConnectionRefusedError:
            print(f"   ⚠️  Could not connect — is the SDK listener running?")
            print(f"      Start it first: python3 Demos/RasApi/event_listener_sdk.py")
            self._notify_sock = None
        except Exception as e:
            print(f"   ❌ Connection error: {e}")
            self._notify_sock = None

    def _wait_for_notification(self, timeout: float = 30.0) -> dict | None:
        """Block until a JSON notification arrives from the listener, or timeout."""
        if not self._notify_sock:
            return None
        self._notify_sock.settimeout(timeout)
        try:
            while "\n" not in self._notify_buffer:
                chunk = self._notify_sock.recv(4096).decode()
                if not chunk:
                    return None
                self._notify_buffer += chunk
            line, self._notify_buffer = self._notify_buffer.split("\n", 1)
            return json.loads(line)
        except socket.timeout:
            return None
        except Exception as e:
            print(f"   ⚠️  Notification error: {e}")
            return None

    def _wait_and_show_notification(self, step: int = 7):
        """Step 7: Wait for SDK listener notification and display it."""
        print(f"\n   Step {step}: Waiting for SDK listener to download CPER and notify demo...")

        notification = self._wait_for_notification(timeout=30.0)

        if notification and notification.get("event") == "cper_downloaded":
            time.sleep(2)
            print(f"           ✅ Notification received from SDK listener")
        else:
            print(f"\n           ⚠️  No notification received within timeout")
            print(f"           Falling back to disk scan...")
            self._collect_cpers_from_disk()
        
    @staticmethod
    def _parse_guid(data: bytes) -> str:
        """Parse a GUID from 16 bytes of binary data (mixed-endian format)."""
        return parse_guid(data)

    @staticmethod
    def _read_binary_cpad(file_path, verbose=False):
        """Read a binary CPAD file — delegates to submit_cpad module."""
        return read_binary_cpad(file_path, verbose=verbose)
            
    def run(self):
        """Run the guided demonstration flow.
       
        1. Discovery
        2. Connect to SDK listener
        3. Inject 1st corrected memory error (DRAM row 1234, column 567)
        4. Collect CPERs (1st error — auto-downloaded by SDK listener)
        5. Analyze (records the row/column - first occurrence, no SPPR created)
        6. Inject 2nd corrected memory error (same row 1234, column 891)
        7. Collect CPERs (2nd error — auto-downloaded by SDK listener)
        8. Analyze (detects 2nd column on same row → failing row → auto-creates SPPR CPAD)
        9. Policy check on analyzer-generated SPPR CPAD
        10. Submit analyzer-generated SPPR CPAD
        11. Collect informational CPERs from SPPR operation
        12. Analyze informational CPERs
        """
        self.print_banner()

        # Analyzer discovery runs during construction; report it now and stop
        # immediately if no usable analyzers were found.
        if not self.analysis.print_discovery_report():
            print("\n" + "=" * 80)
            print("❌ Cannot proceed - no usable analyzers were discovered")
            print("=" * 80)
            return

        # Step 1: Discover the Server
        self.print_platform_info()
        
        if not self.server_online:
            print("\n" + "=" * 80)
            print("❌ Cannot proceed - Server is offline")
            print("=" * 80)
            return
        
        # Step 2: Connect to SDK listener
        input("\n🔑 Press Enter for the next operation...")
        self.connect_to_listener()
        
        # Step 3: Inject first memory corrected error (row 1234, column 567,
        # DRAM 3 / DQ 0).
        input("\n🔑 Press Enter for the next operation...")
        self.inject_memory_error(column=567, beat="dram=3;dq=0;beats=2",
                                 occurrence_label="1st column of the row")
        self._wait_and_show_notification(step=7)
        
        # Collect CPERs 
        input("\n🔑 Press Enter for the next operation...")
        self.collect_cpers()
        
        # Analyze first error 
        input("\n🔑 Press Enter for next action...")
        self.analyze_cpers()
        
        # Step 6: Inject second memory corrected error (same row, different
        # column, and a different DQ of the *same* DRAM 3).
        input("\n🔑 Press Enter for the next operation...")
        self.inject_memory_error(column=891, beat="dram=3;dq=1;beats=7",
                                 occurrence_label="2nd column of the same row")
        self._wait_and_show_notification(step=7)
        
        # Collect CPERs 
        input("\n🔑 Press Enter for the next operation...")
        self.collect_cpers()
        
        # Analyze second error — detects a 2nd column failing on the same row.
        # The orchestrator evaluates the generated SPPR CPAD against policy and,
        # on approval, submits it to trigger the repair operation.
        input("\n🔑 Press Enter for next action...")
        self.analyze_cpers()

        # The SPPR submission triggers informational CPERs from the repair.
        self._wait_and_show_notification(step=7)

        # Collect informational CPERs from SPPR operation
        input("\n🔑 Press Enter for next action...")
        self.collect_cpers()
        
        # Analyze informational CPERs from repair operation
        input("\n🔑 Press Enter for next action...")
        self.analyze_cpers()
        
        input("\n🔑 Press Enter to complete the demonstration...")
        print("\n" + "=" * 80)
        print("✅ RAS Plugin Demonstration Complete!")
        print("=" * 80)
        print("\n📊 What this demonstration showed:")
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
    
    def print_banner(self):
        """Print the application banner."""
        print("\n" + "=" * 80)
        print(" " * 20 + "RAS API Plugin Demo - Guided Demonstration")
        print("=" * 80 + "\n")
    
    def print_platform_info(self):
        """Print platform discovery information"""
        
        print(f"\n" + "=" * 80)
        print("\t\t\t\t\t DISCOVERY")
        print("=" * 80)
        
        # Check server status
        print(f"\n🔍 Step 1: Checking if server is online at {self.base_url}...")
        self._check_server_status()
        
        if self.server_online:
            # Print server information
            print(f"\n🔍 Step 2: Getting server information...")
            self._print_server_info()
            
            # Get RAS Plugin information
            print(f"\n🔍 Step 3: Getting RAS Plugin information...")
            self._print_ras_plugin_info()
            
            # Print platform details
            print(f"\n🔍 Step 4: Platform details...")
            self._print_platform_details()
            
            # Analyzer lookup
            print(f"\n🔍 Step 5: Analyzer lookup...")
            self._print_analyzer_lookup()
    
    def _check_server_status(self):
        """Check if server is online"""
        try:
            response = self.session.get(f"{self.base_url}/redfish/v1/", timeout=5)
            if response.status_code == 200:
                self.server_online = True
                print(f"   ✅ Server is ONLINE")
            else:
                self.server_online = False
                print(f"   ❌ Server returned status: {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.server_online = False
            print(f"   ❌ Server is OFFLINE - Cannot connect")
            print(f"\n   💡 Please start the server with:")
            print(f"      python servers/redfishMockupServer_platform.py -D mockups/public-rackmount1")
        except Exception as e:
            self.server_online = False
            print(f"   ❌ Error: {e}")
    
    def _print_server_info(self):
        """Print detailed server information from Redfish root"""
        try:
            response = self.session.get(f"{self.base_url}/redfish/v1/")
            if response.status_code != 200:
                print(f"   ❌ Failed to get server info")
                return
            
            server_data = response.json()
            print(f"   ✅ Redfish Service Root accessible")
            
            # Redfish version
            redfish_version = server_data.get('RedfishVersion', 'Unknown')
            print(f"\n   📌 Redfish Version: {redfish_version}")
            
            # UUID
            uuid = server_data.get('UUID', 'Unknown')
            print(f"   📌 Service UUID: {uuid}")
            
            # Product name
            product = server_data.get('Product', 'BMC Redfish Simulator')
            print(f"   📌 Product: {product}")
            
            # Available services
            print(f"\n   🔧 Available Services:")
            services = [
                ('Systems', 'Systems'),
                ('Chassis', 'Chassis'),
                ('Managers', 'Managers'),
                ('SessionService', 'Session Service'),
                ('AccountService', 'Account Service'),
                ('EventService', 'Event Service'),
                ('TaskService', 'Task Service'),
                ('UpdateService', 'Update Service')
            ]
            
            for service_key, service_name in services:
                if service_key in server_data:
                    service_data = server_data[service_key]
                    service_uri = service_data.get('@odata.id', 'N/A') if isinstance(service_data, dict) else 'N/A'
                    status = "✓" if service_uri != 'N/A' else "✗"
                    print(f"      {status} {service_name}: {service_uri}")
                    
        except Exception as e:
            print(f"   ❌ Error getting server info: {e}")
    
    def _print_ras_plugin_info(self):
        """Print detailed RAS Plugin information"""
        try:
            # Access Manager OEM RAS Service
            ras_url = f"{self.base_url}/redfish/v1/Managers/{self.MANAGER_ID}/Oem/RasProto/RASService"
            response = self.session.get(ras_url)
            
            if response.status_code == 200:
                ras_data = response.json()
                print(f"   ✅ RAS Service is available")
                
                # RAS API Version
                ras_version = ras_data.get('RasApiVersion', '1.0.0')
                print(f"\n   📌 RAS API Version: {ras_version}")
                
                # Description
                description = ras_data.get('Description', '')
                if description:
                    print(f"   📌 Description: {description}")
                
                # Actions supported
                actions = ras_data.get('Actions', {})
                if actions:
                    print(f"\n   ⚡ Actions Supported:")
                    for action_name, action_details in actions.items():
                        display_name = action_name.split('.')[-1] if '.' in action_name else action_name
                        target = action_details.get('target', 'N/A')
                        if not target.startswith('http'):
                            target = f"{self.base_url}{target}"
                        print(f"      • {display_name}")
                        print(f"        Target: {target}")
                
                # LogService
                log_service = ras_data.get('LogService', {})
                if log_service:
                    log_uri = log_service.get('@odata.id', 'N/A')
                    if not log_uri.startswith('http') and log_uri != 'N/A':
                        log_uri = f"{self.base_url}{log_uri}"
                    print(f"\n   📝 LogService:")
                    print(f"      URI: {log_uri}")
                    
                    # Get LogService details
                    if log_uri != 'N/A':
                        try:
                            log_response = self.session.get(log_uri.replace(self.base_url, '').split('?')[0] 
                                                           if log_uri.startswith('http') else log_uri)
                            if log_response.status_code == 200:
                                log_data = log_response.json()
                                max_records = log_data.get('MaxNumberOfRecords', 'N/A')
                                overflow = log_data.get('OverWritePolicy', 'N/A')
                                print(f"      Max Records: {max_records}")
                                print(f"      Overflow Policy: {overflow}")
                        except:
                            pass
                
            else:
                print(f"   ❌ RAS Service not available (Status: {response.status_code})")
                print(f"   💡 Ensure the RAS plugin is loaded in the platform configuration")
                
        except Exception as e:
            print(f"   ❌ Error getting RAS Plugin info: {e}")
    
    def _print_platform_details(self):
        """Print platform configuration details"""
        try:
            print(f"\n   📋 Platform Details:")
            print(f"      Platform ID / Node ID: {self.PLATFORM_ID}")
            print(f"      BMC URL: {self.base_url}")
            
            print(f"\n   🔌 Configured Endpoints:")
            for idx, endpoint in enumerate(self.ENDPOINTS, 1):
                print(f"      {idx}. Name: {endpoint['Name']}")
                print(f"         Partition ID: {endpoint['partition_id']}")
                print(f"         Creator ID: {endpoint['creator_id']}")
                
                if idx < len(self.ENDPOINTS):
                    print()
            
        except Exception as e:
            print(f"   ❌ Error getting platform details: {e}")
    
    def subscribe_to_events(self):
        """Subscribe for RAS CPER events from the BMC."""
        
        print("\n" + "=" * 80)
        print("\t\t\t\tSUBSCRIBING FOR RAS CPER EVENTS")
        print("=" * 80)
        
        listener_url = "http://localhost:8888/"
        subscription_url = f"{self.base_url}/redfish/v1/EventService/Subscriptions"
        
        # Step 1: Check if event listener is running
        print(f"\n   Step 1: Checking for event listener")
        try:
            response = requests.get(f"{listener_url}status", timeout=2)
            if response.status_code == 200:
                print(f"   ✅ Event listener is ready at {listener_url}")
            else:
                print(f"   ⚠️  Event listener may not be running at {listener_url}")
                print(f"      Start the listener first: python examples/event_listener.py")
        except Exception:
            print(f"   ⚠️  Event listener may not be running at {listener_url}")
            print(f"      Start the listener first: python examples/event_listener.py")
        
        # Step 2: Create event subscription
        print(f"\n   Step 2: Creating event subscription")
        print(f"      Redfish BMC Server URL: {self.base_url}")
        print(f"      Listener URL: {listener_url}")
        print(f"      Subscription Endpoint: {subscription_url}")
        
        payload = {
            "Destination": listener_url,
            "Protocol": "Redfish",
            "Context": "RAS Demo Subscription",
            "SubscriptionType": "RedfishEvent",
            "EventTypes": ["Alert", "StatusChange", "ResourceAdded", "ResourceUpdated"],
            "RegistryPrefixes": ["Base", "RasProto"],
            "ResourceTypes": ["LogEntry"]
        }
        
        print(f"\n   📡 POST {subscription_url}")
        
        try:
            response = self.session.post(subscription_url, json=payload, timeout=10)
            
            # Step 3: Check response
            print(f"\n   Step 3: Checking response")
            print(f"      Response Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                print(f"      ✓ Server accepted the subscription request")
                print(f"      Destination: {listener_url}")
                
                # Try to extract subscription details if available
                if response.text and response.text.strip():
                    try:
                        sub_data = response.json()
                        sub_id = sub_data.get('Id', None)
                        sub_uri = sub_data.get('@odata.id', None)
                        if sub_id:
                            print(f"      Subscription ID: {sub_id}")
                        if sub_uri:
                            print(f"      Subscription URI: {sub_uri}")
                    except json.JSONDecodeError:
                        pass
                
                print(f"\n   ✅ Subscription complete! CPER events will be sent by the server to the listener at {listener_url}")
            else:
                print(f"      ✗ Server rejected the subscription request (Status: {response.status_code})")
                if response.text:
                    print(f"      Response: {response.text}")
        except Exception as e:
            print(f"      ✗ Error creating subscription: {e}")
    
    def _print_analyzer_lookup(self):
        """Report which discovered analyzer owns each configured creator ID."""
        try:
            for endpoint in self.ENDPOINTS:
                creator_id = endpoint['creator_id']
                print(f"   Performing lookup for analyzers for Creator ID: {creator_id}")
                info = self.analysis.analyzer_by_creator.get(normalize_guid(creator_id))
                if info:
                    print(f"   ✅ Analyzer found: {info.name} (v{info.version})")
                else:
                    print(f"   ⓘ No analyzer registered for this Creator ID")
        except Exception as e:
            print(f"   ❌ Error during analyzer lookup: {e}")
    
    def check_listener_events(self):
        """Check the event listener for received event notifications.
        
        Displays the event notification details that would be received
        by the Redfish Event Listener after a CPAD submission.
        """
        
        print("\n" + "=" * 80)
        print("\t\t\t\tLISTENER EVENT NOTIFICATIONS")
        print("=" * 80)
        
        listener_url = "http://0.0.0.0:8888"
        
        print(f"\n   Received event notification on Redfish Event Listener {listener_url}")
        print(f"\n   Parsing event message:")
        
        # Query the latest LogEntry to get AdditionalDataURI and size
        additional_data_uri = "N/A"
        additional_data_size = "N/A"
        
        try:
            log_entries_url = f"{self.base_url}/redfish/v1/Managers/{self.MANAGER_ID}/LogServices/CPER/Entries"
            response = self.session.get(log_entries_url, timeout=5)
            
            if response.status_code == 200:
                entries = response.json()
                members = entries.get('Members', [])
                
                if members:
                    # Get the latest entry
                    latest_uri = members[-1].get('@odata.id', '')
                    if latest_uri:
                        entry_response = self.session.get(f"{self.base_url}{latest_uri}", timeout=5)
                        if entry_response.status_code == 200:
                            entry_data = entry_response.json()
                            additional_data_uri = entry_data.get('AdditionalDataURI', f"{latest_uri}/Attachment")
                            # Calculate size with indent=2 to match downloaded file size
                            additional_data_size = len(json.dumps(entry_data, indent=2).encode('utf-8'))
        except Exception:
            pass
        
        print(f'           "DiagnosticDataType": "CPER"')
        print(f'           "MessageId": "RAS.1.0.CorrectedError"')
        print(f'           "Message": "A Corrected Error CPER event has occurred"')
        print(f'           "AdditionalDataURI": "{additional_data_uri}"')
        print(f'           "AdditionalDataSizeBytes": {additional_data_size} bytes')
    
    def _generate_error_cpad(self, column, beat):
        """Run the Contoso Error Injector to build a memory-error CPAD.

        Every injection targets the *same* DRAM row (defined in the committed
        injection spec); only the column and the failing beats are overridden
        here.  Corrected errors on multiple columns of one row simulate a
        failing row, and the beats place both errors on the *same* DRAM chip.

        Args:
            column: DRAM column address for this injection.
            beat:   A --beat spec (e.g. "dram=3;dq=0;beats=2") selecting the
                    failing DRAM/DQ/beats for this injection.

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

    def inject_memory_error(self, column, beat, occurrence_label):
        """Generate and submit a corrected memory error at a given DRAM column.

        All injections hit the same DRAM row (only the column differs) and the
        same physical DRAM (only the DQ/beats differ), so the analyzer can show
        both a failing row and that the errors are on DQs of one DRAM.

        Args:
            column: DRAM column address for this injection.
            beat:   A --beat spec selecting the failing DRAM/DQ/beats.
            occurrence_label: Short description shown in the banner.
        """
        if not self.server_online:
            print("\n❌ Cannot inject error - server is offline!")
            print("   Please start the server and try again.")
            return

        print("\n" + "=" * 80)
        print(f"\t\t\tSPOOFING MEMORY CORRECTED ERROR ({occurrence_label})")
        print("=" * 80)

        try:
            cpad_path = self._generate_error_cpad(column, beat)
            print(f"\n🚀 Submitting injected CPAD (DRAM row 1234, column {column}; {beat})...")
            self._submit_binary_cpad(
                cpad_path, verbose_steps=True,
                source_label=(f"Contoso Error Injector CPAD — corrected memory "
                              f"error at row 1234, column {column} ({beat})"))
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    def _submit_binary_cpad(self, cpad_file_path, verbose_steps=True, source_label=None):
        """Submit a binary CPAD file — delegates to CPADSubmitter."""
        return self.submitter.submit(
            cpad_file_path, verbose_steps=verbose_steps, source_label=source_label)
    
    def collect_cpers(self):
        """Collect CPERs — wait for real-time notification from SDK listener."""
        print("\n" + "=" * 80)
        print("\t\t\t\tCOLLECTING CPERs")
        print("=" * 80)

        # SDK listener already downloaded CPERs — scan disk for new files
        self._collect_cpers_from_disk()

    def _collect_cpers_from_disk(self):
        """Collect CPERs by scanning the storage directory."""
        self._last_collected = []
        partition_id = self.ENDPOINTS[0]['partition_id']
        storage_path = self.cper_storage_dir / self.PLATFORM_ID / partition_id

        print(f"\n   Looking for CPERs in SDK listener storage:")
        print(f"      Platform ID:  {self.PLATFORM_ID}")
        print(f"      Partition ID: {partition_id}")

        if not storage_path.exists():
            print(f"\n   ⚠️  Storage directory not found: {storage_path}")
            print(f"   Waiting for SDK listener to auto-download CPERs...")
            import time
            for i in range(10):
                time.sleep(1)
                if storage_path.exists() and any(storage_path.glob("*.cper")):
                    break
                print(f"   ... waiting ({i+1}s)")

        if not storage_path.exists():
            print(f"\n   ❌ No CPER storage directory found after waiting")
            return

        all_cper_files = sorted(storage_path.glob("*.cper"))
        new_files = [f for f in all_cper_files if f.name not in self._seen_cper_files]

        if not new_files:
            import time
            print(f"\n   ⏳ Waiting for new CPERs from SDK listener...")
            for i in range(10):
                time.sleep(1)
                all_cper_files = sorted(storage_path.glob("*.cper"))
                new_files = [f for f in all_cper_files if f.name not in self._seen_cper_files]
                if new_files:
                    break
                print(f"   ... waiting ({i+1}s)")

        if not new_files:
            print(f"\n   ⚠️  No new CPER files found")
            return

        print(f"\n   Found {len(new_files)} new CPER file(s):\n")
        for cper_file in new_files:
            size = cper_file.stat().st_size
            print(f"      📥 {cper_file.name}  ({size} bytes)")
            self._seen_cper_files.add(cper_file.name)

        # Record newly collected CPERs so analyze_cpers() can push them to the AO.
        self._last_collected = [str(f) for f in new_files]

        print(f"\n   ✅ {len(new_files)} CPER(s) collected from local storage")
        print(f"      📂 {storage_path}")
    
    def analyze_cpers(self):
        """Analyze newly collected CPERs — push them to the orchestrator."""
        self.analysis.notify_new_cpers(self._last_collected)
    
    def run_policy_check(self):
        """Run policy check on analyzer-generated SPPR CPAD JSON files.

        Delegates to PolicyEngine (policy.py) for each SPPR CPAD file found
        in the Analyzer output directory.

        Returns:
            bool: True if all CPADs pass policy, False otherwise.
        """
        print("\n" + "=" * 80)
        print("\t\t\t\tPOLICY CHECK")
        print("=" * 80)

        try:
            analyzer_output_dir = self.output_dir / "Analyzer_output_files"

            if not analyzer_output_dir.exists():
                print(f"\n⚠️  Analyzer output directory not found: {analyzer_output_dir}")
                print(f"   No SPPR CPADs to evaluate")
                return True

            sppr_json_files = list(analyzer_output_dir.glob("*_sppr_cpad.json"))

            if not sppr_json_files:
                print(f"\n⚠️  No SPPR CPAD JSON files found in {analyzer_output_dir}")
                print(f"   (SPPR CPADs are only created for CMC notifications on Platform Memory 2 errors)")
                return True

            print(f"   Found {len(sppr_json_files)} SPPR CPAD JSON file(s) to evaluate")

            engine = PolicyEngine()
            results = engine.evaluate_multiple_cpads(sppr_json_files)
            return all(allowed for _, allowed in results)

        except Exception as e:
            logger.error(f"Error in policy check: {e}")
            print(f"\n❌ Error: {e}")
            return False
    
    def submit_sppr_cpad(self):
        """Submit SPPR CPAD — delegates to CPADSubmitter."""
        if not self.server_online:
            print("\n❌ Cannot submit SPPR CPAD - server is offline!")
            return
        analyzer_output_dir = self.output_dir / "Analyzer_output_files"
        self.submitter.submit_sppr_cpads(analyzer_output_dir)
    
    def show_advanced_features(self):
        """Demonstrate Phase 7 advanced features"""
        print("\n" + "=" * 80)
        print("\t\t\t\tADVANCED FEATURES (PHASE 7)")
        print("=" * 80)
        
        try:
            print(f"\n🚀 Demonstrating Advanced RAS Plugin Features")
            print(f"{'─' * 80}")
            
            # 1. Analytics
            print(f"\n📊 Feature 1: Analytics Engine")
            analytics_url = f"{self.base_url}/redfish/v1/Managers/{self.MANAGER_ID}/Oem/RasProto/Analytics"
            
            response = self.session.get(analytics_url)
            if response.status_code == 200:
                analytics_data = response.json()
                print(f"   ✅ Analytics endpoint accessible")
                print(f"   📈 Available Analytics:")
                
                if 'ErrorTrends' in analytics_data:
                    print(f"      • Error Trends Analysis")
                if 'ComponentHealth' in analytics_data:
                    print(f"      • Component Health Scores")
                if 'SeverityDistribution' in analytics_data:
                    print(f"      • Severity Distribution")
                if 'Summary' in analytics_data:
                    summary = analytics_data['Summary']
                    print(f"\n   📋 Summary:")
                    print(f"      Total Events: {summary.get('TotalEvents', 0)}")
                    print(f"      Critical: {summary.get('Critical', 0)}")
                    print(f"      Warning: {summary.get('Warning', 0)}")
            else:
                print(f"   ⚠️  Analytics endpoint not yet configured")
            
            # 2. Health Monitoring
            print(f"\n🏥 Feature 2: Health Monitor")
            health_url = f"{self.base_url}/redfish/v1/Managers/{self.MANAGER_ID}/Oem/RasProto/Health"
            
            response = self.session.get(health_url)
            if response.status_code == 200:
                health_data = response.json()
                print(f"   ✅ Health monitoring active")
                
                overall_health = health_data.get('OverallHealth', {})
                status = overall_health.get('Status', 'Unknown')
                print(f"   🏥 Overall Health: {status}")
                
                if 'QueueHealth' in health_data:
                    queue_health = health_data['QueueHealth']
                    print(f"\n   📊 Queue Health:")
                    print(f"      Items Queued: {queue_health.get('TotalQueued', 0)}")
                    print(f"      Items Processed: {queue_health.get('TotalProcessed', 0)}")
                
                if 'RemediationStats' in health_data:
                    remediation = health_data['RemediationStats']
                    print(f"\n   🔧 Remediation Stats:")
                    print(f"      Total Remediations: {remediation.get('TotalRemediations', 0)}")
                    print(f"      Successful: {remediation.get('Successful', 0)}")
            else:
                print(f"   ⚠️  Health endpoint not yet configured")
            
            # 3. Queue Management
            print(f"\n📥 Feature 3: CPER Queue Management")
            print(f"   ✅ Priority-based CPER processing")
            print(f"   ✅ Background worker threads (2 main + 1 deferred)")
            print(f"   ✅ Automatic overflow handling")
            
            # 4. Automated Remediation
            print(f"\n🤖 Feature 4: Automated Remediation")
            print(f"   ✅ Policy-based remediation rules")
            print(f"   ✅ Rate limiting and cooldown")
            print(f"   ✅ Remediation action types:")
            print(f"      • Log Critical Events")
            print(f"      • Notify on Repeated Failures")
            print(f"      • Disable Components (Safety)")
            print(f"      • Reset/Restart Actions")
            print(f"      • Failover Operations")
            
            print(f"\n{'=' * 80}")
            print(f"✅ Advanced Features Demonstration Complete")
            print(f"{'=' * 80}")
            
        except Exception as e:
            logger.error(f"Error showing advanced features: {e}")
            print(f"\n❌ Error: {e}")


def main():
    """Main entry point"""
    try:
        demo = RASAPIPluginDemo()
        demo.run()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("⚠️  Operation cancelled by user (Ctrl+C)")
        print("=" * 80)
        sys.exit(0)


if __name__ == "__main__":
    main()
