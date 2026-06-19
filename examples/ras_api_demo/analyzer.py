#!/usr/bin/env python3
"""
CPER Analyzer & Analysis Orchestrator
======================================

Contains the full CPER analysis engine (CPERAnalyzer) and the thin
orchestrator wrapper (AnalysisOrchestrator) used by the demo.

CPERAnalyzer capabilities:
- Convert binary .cper files to JSON using cperlib's cper-convert tool
- Generate detailed analysis reports (decoded summary, DIMM info)
- Track error locations within each analysis run (stateless)
- Detect repeat errors at the same memory location
- Auto-create SPPR CPAD files when repeat corrected memory errors detected

Policy evaluation lives in policy.py, CPER collection in collect_cpers.py,
and CPAD submission in submit_cpad.py.

Usage (standalone — CPERAnalyzer):
    python examples/ras_api_demo/analyzer.py --cper-dir ras_demo_output/cper_storage
    python examples/ras_api_demo/analyzer.py ras_demo_output/cper_storage/**/*.cper

Usage (from orchestrator):
    from analyzer import AnalysisOrchestrator, CPERAnalyzer
    orch = AnalysisOrchestrator(platform_id=pid, partition_id=ptid, ...)
    orch.analyze_cpers()
"""

import sys
import os
import json
import argparse
import subprocess
import base64
import copy
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List


# Resolve paths relative to project root (examples/ras_api_demo/ → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CPERAnalyzer — full CPER analysis engine with cperlib integration
# ═══════════════════════════════════════════════════════════════════════════

class CPERAnalyzer:
    """Analyzes binary CPER files from the BMC Redfish Simulator's LogService.

    Key capabilities:
    - Decode binary .cper files to JSON via cperlib's cper-convert tool
    - Generate detailed analysis reports (decoded summary, DIMM info)
    - Track error locations within each analysis run (stateless)
    - Detect repeat errors at the same memory location
    - Auto-create SPPR CPAD files when repeat corrected memory errors detected
    """

    # Registry of Creator IDs to analyzer tool names
    ANALYZER_REGISTRY = {
        '11111111-2222-3333-4444-555555555555': 'Contoso CPER analyzer',
        # Add more creator IDs and their analyzers here
    }

    def __init__(self, output_dir=None, verbose=False):
        """Initialize the CPER Analyzer.

        Args:
            output_dir: Directory for analysis output files.
                        Defaults to examples/ras_api_demo/ras_demo_output/Analyzer_output_files.
            verbose: Enable verbose output.
        """
        self.verbose = verbose

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = PROJECT_ROOT / "ras_demo_output" / "Analyzer_output_files"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # SPPR template location
        # Directory layout: examples/ras_api_demo/cpad_storage/spprSpoof.json
        #                   examples/ras_api_demo/ras_demo_output/Analyzer_output_files/  (output_dir)
        # So template is at output_dir / ../../cpad_storage/
        self.cpad_storage_dir = self.output_dir.parent.parent / "cpad_storage"
        self.sppr_template_path = self.cpad_storage_dir / "spprSpoof.json"

        # In-memory tracking of seen memory locations (stateless — rebuilt each run)
        self.seen_locations = []

    # ─── cperlib Integration ────────────────────────────────────────────

    def _locate_cper_convert(self):
        """Locate the cper-convert tool in the project's libcper build directory.

        Returns:
            tuple: (path_to_cper_convert, build_dir) or (None, None)
        """
        plugin_dir = PROJECT_ROOT / 'src' / 'plugins' / 'ras'
        build_dir = plugin_dir / 'libcper' / 'build'
        cper_convert = build_dir / 'cper-convert'

        if cper_convert.exists():
            return str(cper_convert), str(build_dir)

        return None, None

    def _locate_cpad_convert(self):
        """Locate the cpad-convert tool in the project's libcper build directory.

        Returns:
            tuple: (path_to_cpad_convert, build_dir) or (None, None)
        """
        plugin_dir = PROJECT_ROOT / 'src' / 'plugins' / 'ras'
        build_dir = plugin_dir / 'libcper' / 'build'
        cpad_convert = build_dir / 'cpad-convert'

        if cpad_convert.exists():
            return str(cpad_convert), str(build_dir)

        return None, None

    def _convert_json_to_binary_cpad(self, json_path: str, output_path: str) -> Optional[str]:
        """Convert CPAD JSON to binary CPAD format using cperlib's cpad-convert tool.

        Args:
            json_path: Path to the CPAD JSON file
            output_path: Path for the output binary .cpad file

        Returns:
            str: Path to the binary CPAD file, or None if conversion failed
        """
        cpad_convert, build_dir = self._locate_cpad_convert()
        if not cpad_convert:
            print(f"   ✗ cpad-convert tool not found at src/plugins/ras/libcper/build/")
            return None

        try:
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = build_dir + ':' + env.get('LD_LIBRARY_PATH', '')

            # Resolve to absolute paths since cwd is the build directory
            abs_json_path = str(Path(json_path).resolve())
            abs_output_path = str(Path(output_path).resolve())
            cmd = [cpad_convert, 'to-cpad', abs_json_path, '--out', abs_output_path, '--no-validate']

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=build_dir,
                env=env
            )
            stdout, stderr = proc.communicate(timeout=10)

            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                print(f"   ✗ cpad-convert failed: {err_msg}")
                return None

            if os.path.exists(output_path):
                return output_path

            print(f"   ✗ Binary CPAD file not created: {output_path}")
            return None

        except subprocess.TimeoutExpired:
            print(f"   ✗ cpad-convert timed out after 10 seconds")
            return None
        except Exception as e:
            print(f"   ✗ Error converting to binary CPAD: {e}")
            return None

    def _convert_binary_cper_to_json(self, binary_path: str) -> Optional[Dict[str, Any]]:
        """Convert a binary .cper file to JSON using cperlib's cper-convert tool.

        Args:
            binary_path: Path to the binary .cper file

        Returns:
            dict: Parsed CPER JSON data, or None if conversion failed
        """
        cper_convert, build_dir = self._locate_cper_convert()
        if not cper_convert:
            print(f"   ✗ cper-convert tool not found at src/plugins/ras/libcper/build/")
            return None

        try:
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = build_dir + ':' + env.get('LD_LIBRARY_PATH', '')

            # Resolve to absolute path since cwd is the build directory
            abs_binary_path = str(Path(binary_path).resolve())
            cmd = [cper_convert, 'to-json', abs_binary_path]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=build_dir,
                env=env
            )
            stdout, stderr = proc.communicate(timeout=10)

            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                print(f"   ✗ cper-convert failed: {err_msg}")
                return None

            json_text = stdout.decode('utf-8', errors='replace')
            cper_data = json.loads(json_text)
            return cper_data

        except subprocess.TimeoutExpired:
            print(f"   ✗ cper-convert timed out after 10 seconds")
            return None
        except json.JSONDecodeError as e:
            print(f"   ✗ cper-convert output is not valid JSON: {e}")
            return None
        except Exception as e:
            print(f"   ✗ Error converting binary CPER: {e}")
            return None

    # ─── Error Tracking ─────────────────────────────────────────────────

    def _extract_memory_location(self, cper_data: Dict[str, Any]) -> Optional[Dict]:
        """Extract memory location info from CPER data.

        Searches for Memory2 section data within the CPER JSON.

        Args:
            cper_data: Parsed CPER JSON data (full CPER format with header/sections)

        Returns:
            dict with node, card, module, bank, device, rank, row, column or None
        """
        sections = cper_data.get('sections', [])
        if not sections:
            return None

        for section in sections:
            # Check for Memory2 key (standard template format)
            mem2 = section.get('Memory2') or section.get('platformMemory2')
            if mem2:
                bank_data = mem2.get('bank', {})
                bank = bank_data.get('value', 0) if isinstance(bank_data, dict) else bank_data
                return {
                    'node': mem2.get('node', 0),
                    'card': mem2.get('card', 0),
                    'module': mem2.get('module', 0),
                    'bank': bank if bank is not None else 0,
                    'device': mem2.get('device', 0),
                    'rank': mem2.get('rank', 0),
                    'row': mem2.get('row', 0),
                    'column': mem2.get('column', 0)
                }
        return None

    def _check_for_matching_error(self, memory_location: Optional[Dict]) -> bool:
        """Check if there's a previously seen error with matching memory location.

        Uses in-memory tracking from the current analysis run.

        Args:
            memory_location: dict with node, card, module, bank, device, rank, row, column

        Returns:
            True if matching error found, False otherwise
        """
        if not memory_location:
            return False

        for prev in self.seen_locations:
            if (prev.get('node') == memory_location['node'] and
                prev.get('card') == memory_location['card'] and
                prev.get('module') == memory_location['module'] and
                prev.get('bank') == memory_location['bank'] and
                prev.get('device') == memory_location['device'] and
                prev.get('rank') == memory_location['rank'] and
                prev.get('row') == memory_location['row'] and
                prev.get('column') == memory_location['column']):
                return True
        return False

    def _add_to_seen_locations(self, memory_location: Optional[Dict]):
        """Record a memory location as seen during this analysis run.

        Args:
            memory_location: dict with node, card, module, bank, device, rank, row, column
        """
        if not memory_location:
            return

        self.seen_locations.append({
            'node': memory_location['node'],
            'card': memory_location['card'],
            'module': memory_location['module'],
            'bank': memory_location['bank'],
            'device': memory_location['device'],
            'rank': memory_location['rank'],
            'row': memory_location['row'],
            'column': memory_location['column'],
        })

    # ─── CPER Data Extraction ───────────────────────────────────────────

    def extract_cper_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Extract full CPER data from a binary .cper file.

        Uses cperlib's cper-convert tool to decode binary CPER to JSON.

        Args:
            file_path: Path to a binary .cper file

        Returns:
            dict: Full CPER data (with header, sectionDescriptors, sections) or None
        """
        cper_data = self._convert_binary_cper_to_json(file_path)
        if cper_data and 'header' in cper_data:
            return cper_data
        if self.verbose:
            print(f"   ⚠️  cper-convert did not produce valid CPER JSON for {file_path}")
        return None

    def get_analyzer_for_creator(self, creator_id: str) -> Optional[str]:
        """Get the analyzer tool name for a given Creator ID.

        Args:
            creator_id: The Creator ID UUID string

        Returns:
            str: Analyzer tool name, or None if not found
        """
        return self.ANALYZER_REGISTRY.get(creator_id)

    # ─── Report Generation ──────────────────────────────────────────────

    def generate_cper_report(self, cper_data: Dict[str, Any]):
        """Generate a detailed analysis report from CPER JSON data.

        Displays decoded CPER summary including header info, section details,
        and memory DIMM information.

        Args:
            cper_data: Parsed CPER JSON data (full format with header/sections)
        """
        try:
            print(f"\n   � Decoded CPER Summary")
            print(f"   {'-' * 70}")

            # Header information
            header = cper_data.get('header', {})

            # Platform ID (handle both string and dict formats)
            platform_id_data = header.get('platformID', 'N/A')
            if isinstance(platform_id_data, dict):
                platform_id = platform_id_data.get('guid', 'N/A')
            else:
                platform_id = platform_id_data
            print(f"   Platform ID:        {platform_id}")

            # Partition ID
            partition_id_data = header.get('partitionID', 'N/A')
            if isinstance(partition_id_data, dict):
                partition_id = partition_id_data.get('guid', 'N/A')
            else:
                partition_id = partition_id_data
            print(f"   Partition ID:       {partition_id}")

            # Creator ID
            creator_id_data = header.get('creatorID', 'N/A')
            if isinstance(creator_id_data, dict):
                creator_id = creator_id_data.get('guid', 'N/A')
            else:
                creator_id = creator_id_data
            print(f"   Creator ID:         {creator_id}")

            # Timestamp
            timestamp = header.get('timestamp', 'N/A')
            print(f"   Timestamp:          {timestamp}")

            # Record ID
            record_id = header.get('recordID', 'N/A')
            print(f"   Record ID:          {record_id}")

            # Severity
            severity_data = header.get('severity', {})
            if isinstance(severity_data, dict):
                severity_code = severity_data.get('code', 'N/A')
                severity_name = severity_data.get('name', 'N/A')
                # severity code 4 = Action Event (proposed extension), libcper reports as "Unknown"
                if severity_name == 'Unknown' and severity_code == 4:
                    severity_name = 'Action Event'
            else:
                severity_code = 'N/A'
                severity_name = severity_data
            print(f"   Severity:           {severity_name} ({severity_code})")

            # Notification Type
            notif_data = header.get('notificationType', {})
            if isinstance(notif_data, dict):
                notif_type = notif_data.get('type', 'N/A')
                notif_guid = notif_data.get('guid', 'N/A')
            else:
                notif_type = notif_data
                notif_guid = 'N/A'
            print(f"   Notification Type:  {notif_type}")

            # Section information
            sections = cper_data.get('sectionDescriptors', [])
            if sections:
                print(f"\n   📄 Section Information:")
                for idx, section in enumerate(sections, 1):
                    section_type_info = section.get('sectionType', {})
                    if isinstance(section_type_info, dict):
                        section_type = section_type_info.get('data', 'N/A')
                        section_name = section_type_info.get('type', 'Unknown')
                    else:
                        section_type = 'N/A'
                        section_name = section_type_info if section_type_info else 'Unknown'

                    fru_id = section.get('fruID', 'N/A')
                    fru_text = section.get('fruText', 'N/A')

                    print(f"      Section {idx}:")
                    print(f"         Type:            {section_name}")
                    print(f"         FRU ID:          {fru_id}")
                    if fru_text != 'N/A':
                        print(f"         FRU Text:        {fru_text}")

                    # For PlatformActionEvent sections, show full action event details
                    is_action_event = isinstance(section_name, str) and 'action event' in section_name.lower()
                    if is_action_event:
                        all_sections = cper_data.get('sections', [])
                        if idx <= len(all_sections):
                            ae_data = all_sections[idx - 1].get('PlatformActionEvent', {})

                            # Action Return Code
                            return_code = ae_data.get('actionReturnCode', 'N/A')
                            ACTION_RETURN_CODES = {
                                '0x00': 'Success',
                                '0x01': 'Failed',
                                '0x02': 'Deferred',
                                '0x03': 'Not Supported',
                            }
                            return_desc = ACTION_RETURN_CODES.get(return_code, return_code)
                            print(f"         Action Result:   {return_desc} ({return_code})")

                            # Source Action ID
                            action_id = ae_data.get('cpadActionId', 'N/A')
                            ACTION_ID_MAP = {
                                '0x0006': 'Memory Error Injection',
                                '0x8001': 'Soft Post Package Repair (SPPR)',
                            }
                            action_desc = ACTION_ID_MAP.get(action_id, action_id)
                            print(f"         Source Action:    {action_desc} ({action_id})")

                            # Additional Context (base64-decoded if present)
                            additional = ae_data.get('additionalContext')
                            if additional and ae_data.get('additionalContextValid', False):
                                try:
                                    import base64
                                    decoded = base64.b64decode(additional).decode('utf-8', errors='replace')
                                    print(f"         Context:         {decoded}")
                                except Exception:
                                    print(f"         Context:         {additional}")

                    # Section severity
                    sec_severity = section.get('severity', {})
                    if isinstance(sec_severity, dict):
                        sec_sev_name = sec_severity.get('name', 'N/A')
                        if sec_sev_name == 'Unknown' and sec_severity.get('code') == 4:
                            sec_sev_name = 'Action Event'
                        print(f"         Severity:        {sec_sev_name}")

                    # Check if this is a memory error section
                    is_memory_section = False
                    if isinstance(section_name, str) and 'memory' in section_name.lower():
                        is_memory_section = True
                    if section_type == '61ec04fc-48e6-d813-25c9-8daa44750b12':
                        is_memory_section = True

                    if is_memory_section:
                        memory_sections = cper_data.get('sections', [])
                        if idx <= len(memory_sections):
                            mem_section_data = memory_sections[idx - 1]
                            mem_section = mem_section_data.get('Memory2') or mem_section_data.get('Memory', {})

                            if mem_section:
                                # Memory error type
                                error_type_info = mem_section.get('memoryErrorType', {})
                                if isinstance(error_type_info, dict):
                                    error_type = error_type_info.get('name', 'N/A')
                                else:
                                    error_type = error_type_info if error_type_info else 'N/A'

                                if error_type != 'N/A':
                                    print(f"         Error Type:      {error_type}")

                                # DIMM information
                                print(f"\n      💾 DIMM Information:")

                                phys_addr = mem_section.get('physicalAddressHex') or mem_section.get('physicalAddress', 'N/A')
                                if phys_addr != 'N/A':
                                    print(f"         Physical Addr:   {phys_addr}")

                                for field_name, field_key in [
                                    ('Node', 'node'), ('Card', 'card'), ('Module', 'module'),
                                    ('Rank', 'rank'), ('Device', 'device')
                                ]:
                                    val = mem_section.get(field_key, 'N/A')
                                    if val != 'N/A':
                                        print(f"         {field_name + ':':<18}{val}")

                                # Bank (can be nested dict)
                                bank_info = mem_section.get('bank', {})
                                bank = bank_info.get('value', 'N/A') if isinstance(bank_info, dict) else bank_info
                                if bank != 'N/A':
                                    print(f"         {'Bank:':<18}{bank}")

                                for field_name, field_key in [
                                    ('Row', 'row'), ('Column', 'column'), ('Bit Position', 'bitPosition')
                                ]:
                                    val = mem_section.get(field_key, 'N/A')
                                    if val != 'N/A':
                                        print(f"         {field_name + ':':<18}{val}")

            print(f"\n   {'=' * 70}")

        except json.JSONDecodeError as e:
            print(f"   ❌ Error: Invalid JSON: {e}")
        except Exception as e:
            print(f"   ❌ Error generating report: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()

    def print_analysis_recommendation(self, cper_data: Dict[str, Any],
                                       sppr_created: bool = False,
                                       sppr_filename: str = None,
                                       is_repeat_error: bool = False,
                                       memory_location: Optional[Dict] = None):
        """Print the Analysis Recommendation section (legacy single-CPER).
        Kept for standalone CLI usage.
        """
        self.print_batch_recommendation([{
            'cper_data': cper_data,
            'sppr_created': sppr_created,
            'sppr_filename': sppr_filename,
            'is_repeat_error': is_repeat_error,
            'memory_location': memory_location,
        }])

    def print_batch_recommendation(self, analysis_results: list,
                                     successful: int = 0, failed: int = 0,
                                     created_files: list = None,
                                     created_sppr_files: list = None):
        """Print a combined analysis summary and recommendation for the batch.

        Args:
            analysis_results: list of dicts with keys: cper_data, sppr_created,
                              sppr_filename, is_repeat_error, memory_location
            successful: number of successfully analyzed files
            failed: number of failed files
            created_files: list of created JSON output filenames
            created_sppr_files: list of created SPPR CPAD filenames
        """
        created_files = created_files or []
        created_sppr_files = created_sppr_files or []
        has_repeat = any(r['is_repeat_error'] for r in analysis_results)
        sppr_results = [r for r in analysis_results if r['sppr_created']]
        has_sppr = len(sppr_results) > 0

        print(f"\n   💡 Analysis Summary & Recommendation")
        print(f"   {'─' * 70}")

        # Summary section
        print(f"   CPERs Analyzed:     {successful}")
        if failed > 0:
            print(f"   Failed:             {failed}")
        print(f"   Output Location:    {self.output_dir}/")
        for filename in created_files:
            print(f"      - {filename}")
        if created_sppr_files:
            for filename in created_sppr_files:
                print(f"      - {filename}")

        # Recommendation section
        if has_sppr:
            sppr_r = sppr_results[0]
            memory_location = sppr_r['memory_location']
            sppr_filename = sppr_r['sppr_filename']

            print(f"\n   Recommendation:     Perform SPPR (Soft Post-Package Repair) operation")
            print(f"   Reason:             Repeat corrected memory error at same location")
            if memory_location:
                print(f"   Error Location:     Node={memory_location['node']}, Card={memory_location['card']}, "
                      f"Module={memory_location['module']}")
                print(f"                       Bank={memory_location['bank']}, Device={memory_location['device']}, "
                      f"Rank={memory_location['rank']}")
                print(f"                       Row={memory_location['row']}, Column={memory_location['column']}")
            print(f"   Action Required:    Memory repair operation needed to prevent future errors")

            if sppr_filename:
                print(f"\n   ✅ SPPR CPAD created: {sppr_filename}")
                print(f"   Next Step:          Submit SPPR CPAD to platform to execute repair")
        elif has_repeat:
            print(f"\n   Recommendation:     Perform SPPR (Soft Post-Package Repair) operation")
            print(f"   ⚠️  SPPR CPAD not created")
        else:
            all_informational = all(
                (lambda s: s.get('name', 'N/A') if isinstance(s, dict) else s)(
                    r['cper_data'].get('header', {}).get('severity', {})
                ) == 'Informational'
                for r in analysis_results
            )

            first_memory_location = next(
                (r['memory_location'] for r in analysis_results if r['memory_location']), None
            )

            if all_informational:
                print(f"\n   Recommendation:     No action required (informational records)")
                print(f"   Reason:             All CPERs are informational (e.g., SPPR results)")
            else:
                print(f"\n   Recommendation:     No action required")
                print(f"   Reason:             First occurrence of corrected memory error at this location")
                if first_memory_location:
                    print(f"   Error Location:     Node={first_memory_location['node']}, Card={first_memory_location['card']}, "
                          f"Module={first_memory_location['module']}")
                    print(f"                       Bank={first_memory_location['bank']}, Device={first_memory_location['device']}, "
                          f"Rank={first_memory_location['rank']}")
                    print(f"                       Row={first_memory_location['row']}, Column={first_memory_location['column']}")
                print(f"   Next Step:          Monitor for repeat errors at this location")

        print(f"   {'=' * 70}")

    # ─── SPPR CPAD Creation ─────────────────────────────────────────────

    def create_sppr_cpad_from_cper(self, cper_data: Dict[str, Any],
                                    original_file: str = None) -> Optional[str]:
        """Create a JSON CPAD file for SPPR action based on CPER data.

        Only creates SPPR CPAD when this is a REPEAT error at the same
        memory location (node, card, module, bank, device, rank, row, column).
        First occurrence is recorded in memory; second triggers SPPR creation.

        Args:
            cper_data: Full CPER JSON data (with header, sectionDescriptors, sections)
            original_file: Path to the original CPER file (for history tracking)

        Returns:
            Path to the generated SPPR CPAD JSON file, or None
        """
        try:
            header = cper_data.get('header', {})

            # Skip for non-corrected errors (e.g., informational SPPR results)
            severity_data = header.get('severity', {})
            if isinstance(severity_data, dict):
                severity_name = severity_data.get('name', '')
            else:
                severity_name = str(severity_data)

            if severity_name not in ['CPER_SEV_CORRECTED', 'Corrected']:
                return None

            # Extract memory location for matching check
            memory_location = self._extract_memory_location(cper_data)

            # Check if this is a repeat error
            is_repeat_error = self._check_for_matching_error(memory_location)

            if not is_repeat_error:
                # First occurrence - record it, don't create SPPR
                self._add_to_seen_locations(memory_location)
                return None

            # Repeat error - create SPPR CPAD

            # Build SPPR CPAD from CPER data
            sppr_cpad = self._build_sppr_cpad(cper_data, original_file)

            # Generate output filenames using source CPER filename stem
            # e.g. corrected_20260130_102809 → corrected_20260130_102809_sppr_cpad.json/.cpad
            base_name = Path(original_file).stem if original_file else f"cper_{header.get('recordID', 'unknown')}"
            sppr_json_filename = f"{base_name}_sppr_cpad.json"
            sppr_json_path = self.output_dir / sppr_json_filename

            with open(sppr_json_path, 'w') as f:
                json.dump(sppr_cpad, f, indent=2)

            # Convert JSON to binary CPAD using cpad-convert
            sppr_binary_filename = f"{base_name}_sppr_cpad.cpad"
            sppr_binary_path = self.output_dir / sppr_binary_filename
            binary_result = self._convert_json_to_binary_cpad(
                str(sppr_json_path), str(sppr_binary_path)
            )

            if binary_result:
                return str(sppr_binary_path)
            else:
                if self.verbose:
                    print(f"  ⚠️  Binary conversion failed, JSON file available: {sppr_json_filename}")
                return str(sppr_json_path)

        except Exception as e:
            print(f"  ✗ Error creating SPPR CPAD: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def _build_sppr_cpad(self, cper_data: Dict[str, Any], original_file: str) -> Dict[str, Any]:
        """Build SPPR CPAD JSON by loading the spprSpoof.json template and
        overlaying values from the source CPER.

        Steps:
        1. Load the SPPR CPAD template (spprSpoof.json)
        2. Copy platformID, creatorID, partitionID from the CPER header
        3. Set timestamp to CPER timestamp + 5 seconds
        4. Set a fresh recordID
        5. Copy FRU info and sectionType from CPER sectionDescriptors
        6. Extract raw section bytes from the original binary CPER file
           and base64-encode them as {"Unknown": {"data": "<base64>"}}

        Args:
            cper_data: Full CPER data (in cperlib JSON format from cper-convert)
            original_file: Path to the original binary CPER file

        Returns:
            dict: SPPR CPAD data in cperlib format, ready for cpad-convert
        """
        # ── Step 1: Load template ───────────────────────────────────────
        if not self.sppr_template_path.exists():
            raise FileNotFoundError(
                f"SPPR template not found: {self.sppr_template_path}")

        with open(self.sppr_template_path, 'r') as f:
            sppr_cpad = json.load(f)

        # Deep-copy so we never mutate the cached template
        sppr_cpad = copy.deepcopy(sppr_cpad)

        # ── Step 2: Overlay header IDs from CPER ────────────────────────
        cper_header = cper_data.get('header', {})

        def _extract_id(data):
            if isinstance(data, dict):
                return data.get('guid', data.get('data', str(data)))
            return str(data) if data else ''

        for field in ('platformID', 'creatorID', 'partitionID'):
            value = cper_header.get(field)
            if value:
                sppr_cpad['header'][field] = _extract_id(value)

        # ── Step 3: Timestamp = CPER timestamp + 5 seconds ──────────────
        cper_timestamp_str = cper_header.get('timestamp', datetime.now().isoformat())
        try:
            dt = datetime.fromisoformat(cper_timestamp_str.replace('Z', '+00:00'))
            new_dt = dt + timedelta(seconds=5)
            new_timestamp = new_dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except Exception:
            new_timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')

        sppr_cpad['header']['timestamp'] = new_timestamp

        # ── Step 4: Fresh recordID ──────────────────────────────────────
        sppr_cpad['header']['recordID'] = int(datetime.now().timestamp())

        # ── Step 5: Copy FRU / sectionType from CPER descriptors ────────
        cper_descriptors = cper_data.get('sectionDescriptors', [])
        if cper_descriptors and sppr_cpad.get('sectionDescriptors'):
            cper_desc = cper_descriptors[0]
            sppr_desc = sppr_cpad['sectionDescriptors'][0]

            for field in ('fruID', 'fruText'):
                if field in cper_desc:
                    sppr_desc[field] = cper_desc[field]

            st = cper_desc.get('sectionType', {})
            if isinstance(st, dict) and 'data' in st:
                sppr_desc['sectionType'] = {
                    'data': st['data'],
                    'type': st.get('type', 'Unknown')
                }

        # ── Step 6: Extract raw section bytes from binary CPER ──────────
        #
        # cpad-convert can't serialize typed CPER sections (e.g. Memory2),
        # so we read the raw bytes from the original binary CPER and
        # base64-encode them as {"Unknown": {"data": "<base64>"}}.
        section_data_b64 = ""
        section_length = 0
        if cper_descriptors:
            sec_offset = cper_descriptors[0].get('sectionOffset', 0)
            sec_length = cper_descriptors[0].get('sectionLength', 0)
            try:
                with open(original_file, 'rb') as f:
                    f.seek(sec_offset)
                    raw_section = f.read(sec_length)
                section_data_b64 = base64.b64encode(raw_section).decode('ascii')
                section_length = sec_length
            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️  Could not read section bytes from {original_file}: {e}")

        # Update section data in template
        sppr_cpad['sections'] = [{"Unknown": {"data": section_data_b64}}]

        # Update sectionLength and recordLength to match actual data
        if sppr_cpad.get('sectionDescriptors'):
            sppr_cpad['sectionDescriptors'][0]['sectionLength'] = section_length
        cpad_section_offset = sppr_cpad['sectionDescriptors'][0].get('sectionOffset', 200)
        sppr_cpad['header']['recordLength'] = cpad_section_offset + section_length

        return sppr_cpad

    # ─── Main Analysis Flow ─────────────────────────────────────────────

    def analyze_files(self, cper_files: List[str]) -> int:
        """Analyze multiple binary CPER files.

        For each file:
        1. Convert binary .cper to JSON via cper-convert
        2. Look up analyzer for Creator ID
        3. Generate decoded CPER report
        4. Check for repeat errors and auto-create SPPR CPAD if needed
        5. Print analysis recommendation

        Args:
            cper_files: List of paths to binary .cper files

        Returns:
            Number of successfully analyzed files
        """
        total_files = len(cper_files)
        print(f"\n   📂 {total_files} CPER file(s) to analyze\n")

        successful = 0
        failed = 0
        sppr_created = 0
        created_files = []       # Track created JSON analysis files
        created_sppr_files = []  # Track created SPPR CPAD files
        # Collect data for deferred recommendation
        analysis_results = []

        # ── Phase 1: Decode all CPERs ──────────────────────────────────
        for idx, cper_file in enumerate(cper_files, 1):
            cper_path = Path(cper_file)

            if not cper_path.exists():
                print(f"   ⚠️  File not found: {cper_file}")
                failed += 1
                continue

            print(f"{'─' * 80}")
            print(f"📋 [{idx}/{total_files}] Reading binary CPER: {cper_path.name}")

            # Step 1: Extract CPER data from file
            cper_data = self.extract_cper_data(str(cper_path))
            if not cper_data:
                print(f"   ✗ Could not extract CPER data - skipping")
                failed += 1
                continue

            print(f"   ✓ Valid CPER data extracted")

            # Step 2: Extract Creator ID and look up analyzer
            header = cper_data.get('header', {})
            creator_id_data = header.get('creatorID', 'N/A')
            if isinstance(creator_id_data, dict):
                creator_id = creator_id_data.get('guid', str(creator_id_data))
            else:
                creator_id = str(creator_id_data)

            print(f"   ✓ Creator ID: {creator_id}")

            print(f"\n🔍 Looking up analyzer for Creator ID...")
            analyzer_name = self.get_analyzer_for_creator(creator_id)
            if analyzer_name:
                print(f"   ✓ Analyzer found: {analyzer_name}")
                print(f"\n🛠️  Calling analyzer: {analyzer_name}")
            else:
                print(f"   ⓘ No specific analyzer registered for this Creator ID")
                print(f"   ✓ Using default: RasApi CPER analyzer")
                print(f"🛠️  Calling analyzer: RasApi CPER analyzer")

            # Step 3: Save a copy of the extracted CPER to output dir
            base_name = cper_path.stem
            output_filename = f"{base_name}.json"
            output_path = self.output_dir / output_filename
            with open(output_path, 'w') as f:
                json.dump(cper_data, f, indent=2)

            print(f"   ✓ Analysis complete")
            print(f"   📄 Output file: {output_filename}")
            successful += 1
            created_files.append(output_filename)

            # Step 4: Generate decoded CPER report
            self.generate_cper_report(cper_data)

            # Step 5: Extract memory location for tracking
            memory_location = self._extract_memory_location(cper_data)
            is_repeat_error = self._check_for_matching_error(memory_location)

            # Step 6: Auto-check if SPPR CPAD should be created
            sppr_path = self.create_sppr_cpad_from_cper(cper_data, str(cper_path))
            sppr_was_created = sppr_path is not None
            sppr_filename = Path(sppr_path).name if sppr_path else None

            if sppr_was_created:
                sppr_created += 1
                created_sppr_files.append(sppr_filename)

            # Save for deferred recommendation
            analysis_results.append({
                'cper_data': cper_data,
                'sppr_created': sppr_was_created,
                'sppr_filename': sppr_filename,
                'is_repeat_error': is_repeat_error,
                'memory_location': memory_location,
            })

        # ── Analysis Summary & Recommendation ──────────────────────────
        if analysis_results:
            self.print_batch_recommendation(
                analysis_results, successful, failed,
                created_files, created_sppr_files
            )

        return successful

    def analyze_directory(self, cper_dir: str, error_type: str = None) -> int:
        """Analyze all binary .cper files in a directory (recursively).

        Args:
            cper_dir: Path to directory containing binary CPER files
            error_type: Optional filter by error type subdirectory (e.g., 'corrected')

        Returns:
            Number of successfully analyzed files
        """
        cper_dir_path = Path(cper_dir)

        if not cper_dir_path.exists():
            print(f"   ⚠️  Directory not found: {cper_dir}")
            return 0

        if error_type:
            # Look in the specific error type subdirectory
            search_dir = cper_dir_path / error_type.lower()
            if not search_dir.exists():
                matches = list(cper_dir_path.rglob(error_type.lower()))
                if matches:
                    search_dir = matches[0]
                else:
                    print(f"   ⚠️  No '{error_type}' directory found under {cper_dir}")
                    return 0
            cper_files = sorted(search_dir.glob("*.cper"))
        else:
            cper_files = sorted(cper_dir_path.rglob("*.cper"))

        if not cper_files:
            print(f"   ⚠️  No binary CPER files (.cper) found in {cper_dir}")
            return 0

        return self.analyze_files([str(f) for f in cper_files])


# ═══════════════════════════════════════════════════════════════════════════
# AnalysisOrchestrator — thin wrapper used by the demo
# ═══════════════════════════════════════════════════════════════════════════

class AnalysisOrchestrator:
    """Thin orchestrator that wraps CPERAnalyzer for demo usage.

    Stateless analysis — each analyze_cpers() call creates a fresh CPERAnalyzer
    instance with no persistent error history.  Error location tracking lives
    only within a single analyze_cpers() invocation.

    CPER collection, policy evaluation, and CPAD submission are handled by
    their respective modules (collect_cpers.py, policy.py, submit_cpad.py).
    """

    def __init__(self, *, platform_id=None, partition_id=None,
                 cper_storage_dir=None, output_dir=None):
        """Initialize the analysis orchestrator.

        Args:
            platform_id:      Platform GUID string.
            partition_id:     Partition GUID string.
            cper_storage_dir: Path where collected CPERs are stored.
            output_dir:       Root output directory (Analyzer_output_files created underneath).
        """
        self.platform_id = platform_id
        self.partition_id = partition_id
        self.cper_storage_dir = Path(cper_storage_dir) if cper_storage_dir else None
        self.output_dir = Path(output_dir) if output_dir else None
        self.analyzer_output_dir = self.output_dir / "Analyzer_output_files" if self.output_dir else None

    # ─── CPER Analysis ──────────────────────────────────────────────────

    def analyze_cpers(self):
        """Analyze collected CPERs using the stateless CPERAnalyzer.

        Creates a fresh CPERAnalyzer instance each time — no persistent
        error history.  The in-memory seen_locations list is built from
        scratch within this single invocation.

        Provides:
        - Binary CPER → JSON conversion via cperlib's cper-convert
        - Decoded CPER summary (header, section info, DIMM details)
        - Repeat error detection at the same memory location
        - Auto-creation of SPPR CPAD when repeat corrected errors detected
        - Analysis recommendation (no action / perform SPPR)
        """
        print("\n" + "=" * 80)
        print("\t\t\t\tANALYZE CPERs")
        print("=" * 80)

        try:
            # Fresh CPERAnalyzer instance — stateless analysis
            analyzer = CPERAnalyzer(
                output_dir=str(self.analyzer_output_dir),
                verbose=True
            )

            # CPER files live under cper_storage/{platform_id}/{partition_id}/
            cper_base_dir = self.cper_storage_dir / self.platform_id / self.partition_id

            if not cper_base_dir.exists():
                print(f"\n⚠️  No CPER directory found at {cper_base_dir}")
                return

            # Use the analyzer's directory analysis method
            successful = analyzer.analyze_directory(str(cper_base_dir))

            if successful == 0:
                print(f"\n⚠️  No CPER files were analyzed")

        except Exception as e:
            logger.error(f"Error analyzing CPERs: {e}")
            print(f"\n❌ Error: {e}")


# ─── CLI Entry Point ────────────────────────────────────────────────────

def main():
    """Command-line interface for standalone CPER analysis."""
    parser = argparse.ArgumentParser(
        description='CPER Analyzer — analyze binary .cper files using cperlib (cper-convert)',
        epilog='Examples:\n'
               '  python examples/ras_api_demo/analyzer.py --cper-dir ras_demo_output/cper_storage\n'
               '  python examples/ras_api_demo/analyzer.py ras_demo_output/cper_storage/**/*.cper\n'
               '  python examples/ras_api_demo/analyzer.py --analyze --cper-dir ras_demo_output/cper_storage\n'
               '  python examples/ras_api_demo/analyzer.py --cper-dir ras_demo_output/cper_storage --error-type corrected\n',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('cper_files', nargs='*', help='Binary .cper files to analyze')
    parser.add_argument('--analyze', action='store_true',
                        help='Analyze collected CPER files (via AnalysisOrchestrator)')
    parser.add_argument('--cper-dir',
                        help='Directory containing CPER files (recursive search)')
    parser.add_argument('--error-type',
                        help='Filter by error type (e.g., corrected, informational)')
    parser.add_argument('--output-dir',
                        help='Output directory for analysis files')
    parser.add_argument('--platform-id',
                        default='990f8820-bd4d-5064-58cc-961a053dea79',
                        help='Platform GUID (for --analyze mode)')
    parser.add_argument('--partition-id',
                        default='22222222-3333-4444-5555-666666666666',
                        help='Partition GUID (for --analyze mode)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    # Resolve paths relative to project root
    script_dir = Path(__file__).resolve().parent
    default_output = script_dir / "ras_demo_output"

    output_dir = Path(args.output_dir) if args.output_dir else default_output
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    if args.analyze:
        # Use AnalysisOrchestrator (demo-style: platform/partition aware)
        cper_storage_dir = Path(args.cper_dir) if args.cper_dir else output_dir / "cper_storage"
        if not cper_storage_dir.is_absolute():
            cper_storage_dir = PROJECT_ROOT / cper_storage_dir

        orch = AnalysisOrchestrator(
            platform_id=args.platform_id,
            partition_id=args.partition_id,
            cper_storage_dir=str(cper_storage_dir),
            output_dir=str(output_dir),
        )
        orch.analyze_cpers()
    elif args.cper_dir:
        # Direct CPERAnalyzer usage — analyze directory
        analyzer_output = str(output_dir / "Analyzer_output_files") if args.output_dir else None
        analyzer = CPERAnalyzer(output_dir=analyzer_output, verbose=args.verbose)

        cper_dir = Path(args.cper_dir)
        if not cper_dir.is_absolute():
            cper_dir = PROJECT_ROOT / cper_dir

        successful = analyzer.analyze_directory(str(cper_dir), error_type=args.error_type)
        sys.exit(0 if successful > 0 else 1)
    elif args.cper_files:
        # Direct CPERAnalyzer usage — analyze specific files
        analyzer_output = str(output_dir / "Analyzer_output_files") if args.output_dir else None
        analyzer = CPERAnalyzer(output_dir=analyzer_output, verbose=args.verbose)

        valid_files = []
        for f in args.cper_files:
            file_path = Path(f)
            if not file_path.is_absolute():
                file_path = PROJECT_ROOT / file_path
            if file_path.exists():
                valid_files.append(str(file_path))
            else:
                print(f"Warning: File not found: {f}")

        if not valid_files:
            print("Error: No valid CPER files found")
            sys.exit(1)

        successful = analyzer.analyze_files(valid_files)
        sys.exit(0 if successful > 0 else 1)
    else:
        # Default: analyze all files in cper_storage
        default_dir = output_dir / "cper_storage"
        if default_dir.exists():
            print(f"No files specified, scanning default: {default_dir}")
            analyzer = CPERAnalyzer(verbose=args.verbose)
            successful = analyzer.analyze_directory(str(default_dir))
            sys.exit(0 if successful > 0 else 1)
        else:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
