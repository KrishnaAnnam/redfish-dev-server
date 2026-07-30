#!/usr/bin/env python3
"""
Contoso CPER Analyzer
=====================

A discoverable analyzer plugin for the Analysis Orchestrator (AO), and the home
of Contoso's chip-specific CPER analysis engine (:class:`ContosoAnalyzer`).

The analysis engine:
- Decodes binary CPERs (via the shared :class:`CperDecoder`).
- Generates detailed, human-readable CPER reports (decoded summary, DIMM info).
- Analyzes errors from the Contoso SoC
- For memory errors detected by the Contoso SoC, tracks error locations within an analysis run and detects repeat corrected memory errors on the same location.
    - Tracks error locations within an analysis run and detects repeat corrected
        memory errors on the same device row, different column.
   - Auto-creates an SPPR (Soft Post-Package Repair) CPAD when a row failure is detected.

The AO interacts with this script through two command-line modes:

1. Discovery mode (``--discover``)
   Emits a single JSON object on stdout describing this analyzer:
       {
         "analyzer_name":    "Contoso CPER Analyzer",
         "analyzer_version": "1.0.0",
         "creator_ids":      ["11111111-2222-3333-4444-555555555555"],
         "prior_days":       30
       }

2. Run mode (``--input-file <path>``)
   Reads a JSON input file produced by the AO that lists the CPERs to
   consider (newest first) and processes them.  Outputs are written next to
   this script (the AO clears stale ``.json``/``.cpad`` files beforehand and
   collects whatever this run produces):
       - exactly one ``.json``   — the analysis result, and
       - zero or one ``.cpad``   — an SPPR remediation, created only when a
                                    repeat corrected memory error is detected.

A standalone developer mode is also available:

3. Directory mode (``--cper-dir <path>``)
   Analyze every binary ``.cper`` under a directory and print reports, without
   the orchestrator.

Exit code: 0 on success, non-zero on failure.
"""

import sys
import json
import copy
import base64
import builtins
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List


# ── Analyzer identity (reported via --discover) ─────────────────────────────
ANALYZER_NAME = "Contoso CPER Analyzer"
ANALYZER_VERSION = "1.0.0"
CREATOR_IDS = ["11111111-2222-3333-4444-555555555555"]
PRIOR_DAYS = 30

# This analyzer writes its outputs next to itself.
SCRIPT_DIR = Path(__file__).resolve().parent

# The shared RAS API demo directory holds cper_decoder.py and cpad_storage/.
#   parents[0] = contoso/   parents[1] = analyzers/   parents[2] = RasApi/
RASAPI_DIR = Path(__file__).resolve().parents[2]

# Make the shared decoder importable regardless of the cwd the AO uses.
if str(RASAPI_DIR) not in sys.path:
    sys.path.insert(0, str(RASAPI_DIR))
# This analyzer's own directory holds the Contoso proprietary codec modules.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cper_decoder import CperDecoder  # noqa: E402  (path set up above)
import contoso_catalog            # noqa: E402  Contoso section registry
import contoso_encoder            # noqa: E402  Contoso body pack/unpack

# The Contoso Memory Controller proprietary CPER section-type GUID.
CONTOSO_MEMORY_SECTION = "Memory Controller - First Generation"
CONTOSO_MEMORY_GUID = contoso_catalog.SECTION_TYPES[CONTOSO_MEMORY_SECTION]["guid"].lower()

# Reverse of the Contoso severity encoding (register value → name) for reports.
_CONTOSO_SEV_NAME = {v: k for k, v in contoso_catalog.SEVERITY_VALUES.items()}


def _indented_print(indent: str):
    """Return a print() replacement that left-pads every line with ``indent``.

    Blank lines (including those produced by a leading ``\\n``) are emitted
    without padding so vertical spacing stays clean.  Accepts the same keyword
    arguments as the builtin (e.g. ``file=sys.stderr``).
    """
    def _p(text: str = "", **kwargs):
        for line in str(text).split("\n"):
            builtins.print(f"{indent}{line}" if line != "" else "", **kwargs)
    return _p


# ═══════════════════════════════════════════════════════════════════════════
# ContosoAnalyzer — Contoso's CPER analysis engine
# ═══════════════════════════════════════════════════════════════════════════

class ContosoAnalyzer:
    """Analyzes Contoso binary CPER files decoded from the BMC LogService.

    Key capabilities:
    - Generate detailed analysis reports (decoded summary, DIMM info)
    - Track error locations within each analysis run (stateless)
        - Detect row failures from repeat corrected memory errors on the same DRAM
            device row at different columns
    - Auto-create SPPR CPAD files when repeat corrected memory errors detected
    """

    def __init__(self, output_dir=None, verbose=False):
        """Initialize the Contoso analyzer.

        Args:
            output_dir: Directory for analysis output files.  Defaults to
                        Demos/RasApi/ras_demo_output/Analyzer_output_files.
            verbose: Enable verbose output.
        """
        self.verbose = verbose
        self.decoder = CperDecoder(verbose=verbose)

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = RASAPI_DIR / "ras_demo_output" / "Analyzer_output_files"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # SPPR template lives at Demos/RasApi/cpad_storage/spprTemplate.json
        self.cpad_storage_dir = RASAPI_DIR / "cpad_storage"
        self.sppr_template_path = self.cpad_storage_dir / "spprTemplate.json"

        # In-memory tracking of seen memory locations (stateless — rebuilt each run)
        self.seen_locations = []

    # ─── CPER Data Extraction ───────────────────────────────────────────

    def extract_cper_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Decode a binary .cper file to full CPER JSON (header + sections)."""
        return self.decoder.extract_cper_data(file_path)

    # ─── Error Tracking ─────────────────────────────────────────────────

    def _extract_memory_location(self, cper_data: Dict[str, Any]) -> Optional[Dict]:
        """Extract the DRAM location from a Contoso Memory Controller CPER.

        Finds the section whose descriptor GUID is the Contoso Memory Controller
        section type, decodes its proprietary opaque body via the Contoso codec,
        and returns the DRAM coordinates logged in the DRAM error bank.

        Args:
            cper_data: Parsed CPER JSON (header/sectionDescriptors/sections).

        Returns:
            dict with chiplet, controller, channel, subchannel, dimm, rank,
            bank_group, bank, row, column, physical_address — or None.
        """
        sections = cper_data.get('sections', [])
        descriptors = cper_data.get('sectionDescriptors', [])
        if not sections:
            return None

        for idx, section in enumerate(sections):
            # Match this section to the Contoso Memory Controller section type.
            guid = None
            if idx < len(descriptors):
                st = descriptors[idx].get('sectionType', {})
                if isinstance(st, dict):
                    guid = st.get('data')
            if not guid or guid.lower() != CONTOSO_MEMORY_GUID:
                continue

            b64 = section.get('Unknown', {}).get('data')
            if not b64:
                continue
            try:
                body = base64.b64decode(b64)
                decoded = contoso_encoder.unpack_section_body(CONTOSO_MEMORY_SECTION, body)
            except Exception:
                return None
            if not decoded:
                return None

            sub = decoded['subcomponent']
            add = decoded['additional']
            # Decode the beat_mask into the failing (DRAM, DQ, beats) it records.
            # beat_mask[DRAM][DQ] is a 16-bit mask; a DRAM index identifies one
            # physical DRAM chip on the DIMM.
            beat_errors = []
            grid = add.get('beat_mask')
            if isinstance(grid, list):
                for d, row in enumerate(grid):
                    if not isinstance(row, list):
                        continue
                    for q, mask in enumerate(row):
                        mask = int(mask)
                        if mask:
                            beats = [b for b in range(16) if mask & (1 << b)]
                            beat_errors.append({'dram': d, 'dq': q, 'beats': beats})
            drams = sorted({be['dram'] for be in beat_errors})
            return {
                'chiplet': sub.get('chiplet', 0),
                'controller': sub.get('controller', 0),
                'channel': add.get('channel', 0),
                'subchannel': add.get('subchannel', 0),
                'dimm': add.get('dimm', 0),
                'rank': add.get('rank', 0),
                'bank_group': add.get('bank_group', 0),
                'bank': add.get('bank', 0),
                'row': add.get('row', 0),
                'column': add.get('column', 0),
                'physical_address': decoded.get('error_address', 0),
                'beat_errors': beat_errors,
                'drams': drams,
                'device': drams[0] if len(drams) == 1 else None,
            }
        return None

    # Fields that together identify a single DRAM device row (column excluded).
    _ROW_FIELDS = ('chiplet', 'controller', 'channel', 'subchannel',
                   'dimm', 'rank', 'bank_group', 'bank', 'row', 'device')

    @classmethod
    def _row_key(cls, loc: Dict) -> tuple:
        """Return fields identifying one DRAM device row (no column)."""
        return tuple(loc.get(f, 0) for f in cls._ROW_FIELDS)

    @classmethod
    def _format_row(cls, loc: Dict) -> str:
        """Human-readable DRAM row coordinates (no column)."""
        return (f"Chiplet {loc['chiplet']}, Controller {loc['controller']}, "
                f"Channel {loc['channel']}, Subchannel {loc['subchannel']}, "
                f"DIMM {loc['dimm']}, Rank {loc['rank']}, Bank Group {loc['bank_group']}, "
                f"Bank {loc['bank']}, Row {loc['row']}, Device {loc['device']}")

    # ── SPPR confidence ──────────────────────────────────────────────────
    # Confidence scales with evidence: 80% at two distinct column addresses on
    # the failing row, +1% for each additional distinct column, capped at 95%.
    # The more columns we see failing on one row, the surer we are it is a row
    # failure that SPPR can repair.
    SPPR_CONFIDENCE_BASE = 80
    SPPR_CONFIDENCE_MAX = 95

    @classmethod
    def _sppr_confidence(cls, distinct_columns: int) -> int:
        """Confidence (0-100) for an SPPR given the number of distinct failing
        column addresses on the row."""
        return min(cls.SPPR_CONFIDENCE_BASE + max(distinct_columns - 2, 0),
                   cls.SPPR_CONFIDENCE_MAX)

    def _distinct_columns_on_row(self, current: Optional[Dict]) -> int:
        """Count distinct columns failing on the current DRAM device row."""
        if not current or current.get('device') is None:
            return 0
        same_row = [p for p in self.seen_locations
                    if self._row_key(p) == self._row_key(current)]
        errors = same_row + [current]
        return len({loc.get('column') for loc in errors
                    if loc.get('column') is not None})

    @staticmethod
    def _fmt_beat(be: Dict) -> str:
        """Format one beat-error entry (DRAM/DQ/beat) for display."""
        beats = be.get('beats', [])
        if len(beats) == 1:
            return f"DRAM {be['dram']}, DQ {be['dq']}, beat {beats[0]}"
        return f"DRAM {be['dram']}, DQ {be['dq']}, beats {beats}"

    @staticmethod
    def _wrap_labeled(label: str, value: str, print_fn, width: int = 70) -> None:
        """Print ``label``/``value`` with the value wrapped to fit the frame.

        Long comma-separated coordinate strings (e.g. a full DRAM location) are
        broken at ``", "`` boundaries and continued on lines aligned under the
        value column, so nothing wraps raw in the terminal.  All detail is
        preserved — only the line breaks change.
        """
        col = 23                       # value column: 3-space indent + 20-char label
        avail = width + 3 - col        # printable width for the value
        prefix = f"   {label:<20}"
        indent = " " * col
        lines, cur = [], ""
        for part in value.split(", "):
            piece = f"{cur}, {part}" if cur else part
            if cur and len(piece) > avail:
                lines.append(cur)
                cur = part
            else:
                cur = piece
        if cur:
            lines.append(cur)
        print_fn(f"{prefix}{lines[0] if lines else ''}")
        for line in lines[1:]:
            print_fn(f"{indent}{line}")

    def _failing_row_lines(self, current: Optional[Dict]) -> List[str]:
        """Evidence lines for a failing-row diagnosis.

        Lists the per-error column addresses and the DRAM/DQ/beat each maps to,
        then explains why that pattern (same Bank Group / Bank / Row, different
        columns) indicates a failing row that PPR can repair.
        """
        if not current:
            return []
        same_row = [p for p in self.seen_locations
                    if self._row_key(p) == self._row_key(current)]
        errors = list(same_row)
        if current not in errors:
            errors.append(current)

        lines = ["   Corrected errors observed on this row:"]
        columns, drams, dqs = [], set(), set()
        for i, loc in enumerate(errors, 1):
            columns.append(loc.get('column'))
            beat_list = loc.get('beat_errors', [])
            for be in beat_list:
                drams.add(be['dram'])
                dqs.add(be['dq'])
            detail = "; ".join(self._fmt_beat(be) for be in beat_list) or "(no beat detail)"
            lines.append(f"      Error {i}:  Column {loc.get('column')}   \u2192  {detail}")

        uniq_cols = sorted({c for c in columns if c is not None})
        lines.append("   Why this is a failing row:")
        lines.append(
            f"      \u2022 {len(errors)} corrected errors hit the SAME Bank Group "
            f"({current.get('bank_group')}), Bank ({current.get('bank')}), and "
            f"Row ({current.get('row')})")
        lines.append(
            f"        at DIFFERENT columns ({', '.join(str(c) for c in uniq_cols)}).")
        lines.append("      \u2022 Multiple failing columns along a single row indicate the row")
        lines.append("        itself is faulty \u2014 not isolated single-cell wear.")
        if len(drams) == 1:
            lines.append(
                f"      \u2022 The failing beats are all on DRAM {next(iter(drams))} "
                f"(DQs {sorted(dqs)}), consistent")
            lines.append("        with one DRAM's row being bad.")
        return lines

    def _has_prior_error_on_same_dram_device_row_at_different_column(
            self, memory_location: Optional[Dict]) -> bool:
        """Detect a failing DRAM row: a prior error on the *same device row*
        at a *different column*.

        A single corrected error at one cell is normal wear. Corrected errors
        striking multiple columns of the same row on the same DRAM device
        indicate the row itself is failing and is worth repairing with SPPR.

        Args:
            memory_location: the DRAM location of the current error.

        Returns:
            True if a prior error shares this device row but has a different
            column.
        """
        if not memory_location or memory_location.get('device') is None:
            return False

        key = self._row_key(memory_location)
        for prev in self.seen_locations:
            if self._row_key(prev) == key and prev.get('column') != memory_location['column']:
                return True
        return False

    def _add_to_seen_locations(self, memory_location: Optional[Dict]):
        """Record a DRAM location (row coordinates + column) as seen this run.

        Args:
            memory_location: the DRAM location to remember.
        """
        if not memory_location:
            return
        self.seen_locations.append(dict(memory_location))

    # ─── Report Generation ──────────────────────────────────────────────

    def _decode_contoso_section(self, cper_data: Dict[str, Any], idx: int):
        """Decode the Contoso proprietary body of section ``idx`` (0-based).

        Returns (section_name, decoded) for any Contoso section type, or
        (None, None) if the section is not a known Contoso section.
        """
        descriptors = cper_data.get('sectionDescriptors', [])
        sections = cper_data.get('sections', [])
        if idx >= len(descriptors) or idx >= len(sections):
            return None, None
        st = descriptors[idx].get('sectionType', {})
        guid = st.get('data') if isinstance(st, dict) else None
        if not guid:
            return None, None
        section_name = contoso_catalog.section_name_from_guid(guid)
        if not section_name:
            return None, None
        b64 = sections[idx].get('Unknown', {}).get('data')
        if not b64:
            return None, None
        try:
            body = base64.b64decode(b64)
            decoded = contoso_encoder.unpack_section_body(section_name, body)
        except Exception:
            return None, None
        return section_name, decoded

    def _collect_section_error_names(self, cper_data: Dict[str, Any]) -> List[str]:
        """Return the unique error names logged across all Contoso sections."""
        names: List[str] = []
        descriptors = cper_data.get('sectionDescriptors', [])
        for idx in range(len(descriptors)):
            section_name, decoded = self._decode_contoso_section(cper_data, idx)
            if not decoded:
                continue
            err_name = contoso_catalog.error_name_from_id(
                section_name, decoded['bank_name'], decoded['error_status']['error_id'])
            if err_name and err_name not in names:
                names.append(err_name)
        return names

    @staticmethod
    def _fmt_register(name, code, value) -> str:
        """Format a Contoso register/additional value for display.

        64-bit registers (code 'Q') and packed arrays read better in hex; the
        logical DRAM coordinates (channel, dimm, …) read better in decimal.
        """
        if name == 'beat_mask' and isinstance(value, list):
            entries = []
            for device, row in enumerate(value):
                for dq, mask in enumerate(row):
                    if not mask:
                        continue
                    beats = [beat for beat in range(16) if mask & (1 << beat)]
                    beat_label = (f"beat {beats[0]}" if len(beats) == 1
                                  else f"beats {', '.join(map(str, beats))}")
                    entries.append(
                        f"Device {device}, DQ {dq}, {beat_label} (mask {hex(mask)})")
            return "; ".join(entries) if entries else "(all zero)"
        if isinstance(value, list):          # 2-D arrays such as beat_mask[10][4]
            nonzero = [f"[{r}][{c}]={hex(v)}"
                       for r, row in enumerate(value)
                       for c, v in enumerate(row) if v]
            return ", ".join(nonzero) if nonzero else "(all zero)"
        if code == 'Q':
            return hex(value)
        return str(value)

    def _print_contoso_section_body(self, print, section_name: str, decoded: Dict):
        """Print a decoded Contoso section body using the CPER section layout
        (Error Status Register, Error Address, Misc 0/1, Additional Registers)
        defined in contoso-cper-sections.md."""
        bank = contoso_catalog.get_bank(
            contoso_catalog.resolve_section(section_name), decoded['bank_name'])
        st = decoded['error_status']
        m0 = decoded['misc0']
        err_name = contoso_catalog.error_name_from_id(
            section_name, decoded['bank_name'], st['error_id'])
        sev_name = _CONTOSO_SEV_NAME.get(st['severity_value'], 'Unknown')
        subcomponent = ", ".join(f"{k}={v}" for k, v in decoded['subcomponent'].items())

        print(f"         Error Bank:      {decoded['bank_name']}")
        print(f"         Error:           {err_name} ({hex(st['error_id'])})")
        print(f"         Subcomponent:    {subcomponent}")
        print(f"         Error Status Register:")
        print(f"            Address Valid:  {st['addressValid']}")
        print(f"            Overflow:       {st['overflow']}")
        print(f"            Severity:       {sev_name} ({st['severity_value']})")
        print(f"            Error ID:       {hex(st['error_id'])}")
        print(f"         Error Address:   {hex(decoded['error_address'])}")
        print(f"         Misc 0:")
        print(f"            Injected:       {m0['injected']}")
        print(f"            CE Count:       {m0['ce_count']}")
        print(f"         Misc 1:          {hex(decoded['misc1'])}")
        print(f"         Additional Registers:")
        for name, code in bank['additional']:
            print(f"            {name + ':':<30} {self._fmt_register(name, code, decoded['additional'].get(name))}")

    def generate_cper_report(self, cper_data: Dict[str, Any], indent: str = ""):
        """Generate a detailed analysis report from CPER JSON data.

        Displays decoded CPER summary including header info, section details,
        and memory DIMM information.

        Args:
            cper_data: Parsed CPER JSON data (full format with header/sections)
            indent: Optional left-margin prefix applied to every printed line
                (used when the report is nested inside the orchestrator flow).
        """
        print = _indented_print(indent)
        try:
            print(f"\n   📊 Decoded CPER Summary")
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

            # Errors logged across the CPER's sections (by name).
            error_names = self._collect_section_error_names(cper_data)
            if error_names:
                print(f"   Errors:             {', '.join(error_names)}")

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

                    # libcper reports proprietary GUIDs as "Unknown"; show the
                    # Contoso section name when we recognize the GUID.
                    contoso_section = (
                        contoso_catalog.section_name_from_guid(section_type)
                        if isinstance(section_type, str) else None)
                    display_type = contoso_section or section_name

                    print(f"      Section {idx}:")
                    print(f"         Type:            {display_type}")
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

                    # Section severity
                    sec_severity = section.get('severity', {})
                    if isinstance(sec_severity, dict):
                        sec_sev_name = sec_severity.get('name', 'N/A')
                        if sec_sev_name == 'Unknown' and sec_severity.get('code') == 4:
                            sec_sev_name = 'Action Event'
                        print(f"         Severity:        {sec_sev_name}")

                    # Contoso proprietary section: decode and print its body in
                    # the same structure as the Contoso CPER section format.
                    if contoso_section:
                        _sn, decoded = self._decode_contoso_section(cper_data, idx - 1)
                        if decoded:
                            self._print_contoso_section_body(print, contoso_section, decoded)

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
                                       dram_row_failure_detected: bool = False,
                                       memory_location: Optional[Dict] = None):
        """Print the Analysis Recommendation section (legacy single-CPER).
        Kept for standalone CLI usage.
        """
        self.print_batch_recommendation([{
            'cper_data': cper_data,
            'sppr_created': sppr_created,
            'sppr_filename': sppr_filename,
            'dram_row_failure_detected': dram_row_failure_detected,
            'memory_location': memory_location,
        }])

    def print_batch_recommendation(self, analysis_results: list,
                                     successful: int = 0, failed: int = 0,
                                     created_files: list = None,
                                     created_sppr_files: list = None,
                                     indent: str = ""):
        """Print a combined analysis summary and recommendation for the batch.

        Args:
            analysis_results: list of dicts with keys: cper_data, sppr_created,
                              sppr_filename, dram_row_failure_detected,
                              memory_location
            successful: number of successfully analyzed files
            failed: number of failed files
            created_files: list of created JSON output filenames
            created_sppr_files: list of created SPPR CPAD filenames
            indent: Optional left-margin prefix applied to every printed line
                (used when the block is nested inside the orchestrator flow).
        """
        print = _indented_print(indent)
        created_files = created_files or []
        created_sppr_files = created_sppr_files or []
        dram_row_failure_detected = any(
            r['dram_row_failure_detected'] for r in analysis_results)
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

            print(f"\n   Finding:            A DRAM row is failing — repeated corrected errors")
            print(f"                       map to one row at multiple column addresses.")
            if memory_location:
                print("")
                self._wrap_labeled("Failing Row:", self._format_row(memory_location), print)
                print("")
                for line in self._failing_row_lines(memory_location):
                    print(line)
            print(f"\n   Recommendation:     Soft Post Package Repair (SPPR) of the failing row")
            print(f"   Rationale:          PPR remaps the failing row to a spare row inside the")
            print(f"                       DRAM, mitigating further errors from this row.")

            if sppr_filename:
                print(f"\n   ✅ SPPR CPAD created: {sppr_filename}")
                print(f"   Next Step:          Submit the SPPR CPAD to the platform to execute the repair")
        elif dram_row_failure_detected:
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
                print(f"\n   Recommendation:     No action required yet")
                print(f"   Reason:             Insufficient data to infer a fault from the errors.")
                print(f"                       Continue monitoring for errors.")
                if first_memory_location:
                    col = first_memory_location.get('column')
                    self._wrap_labeled(
                        "Error Location:",
                        f"{self._format_row(first_memory_location)}, Column {col}",
                        print,
                    )
                    beat_list = first_memory_location.get('beat_errors', [])
                    if beat_list:
                        detail = "; ".join(self._fmt_beat(be) for be in beat_list)
                        print(f"                       ({detail})")
                print(f"   Next Step:          Continue monitoring; more error patterns are")
                print(f"                       needed before a fault can be identified.")

        print(f"   {'=' * 70}")

    # ─── SPPR CPAD Creation ─────────────────────────────────────────────

    def create_sppr_cpad_from_cper(self, cper_data: Dict[str, Any],
                                    original_file: str = None) -> Optional[str]:
        """Create a JSON CPAD file for SPPR action based on CPER data.

        Only creates an SPPR CPAD when the newest error is a REPEAT on a
        failing DRAM row — i.e. a corrected error on the same device row
        (chiplet/controller/channel/subchannel/dimm/rank/bank_group/bank/row/
        device) as a prior error but at a *different column*. The first
        occurrence is recorded in memory; a later hit on another column of
        that device row triggers SPPR creation.

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
            dram_row_failure_detected = (
                self._has_prior_error_on_same_dram_device_row_at_different_column(
                    memory_location))

            if not dram_row_failure_detected:
                # First occurrence - record it, don't create SPPR
                self._add_to_seen_locations(memory_location)
                return None

            # Repeat error - create SPPR CPAD.  Confidence scales with the
            # number of distinct column addresses failing on this row.
            distinct_columns = self._distinct_columns_on_row(memory_location)
            confidence = self._sppr_confidence(distinct_columns)
            if self.verbose:
                print(f"  📊 SPPR confidence: {confidence}% "
                      f"({distinct_columns} distinct column address(es) on the row)")

            # Build SPPR CPAD from CPER data
            sppr_cpad = self._build_sppr_cpad(cper_data, original_file, confidence)

            # Record this column too, so further columns on the row raise the
            # confidence on the next SPPR.
            self._add_to_seen_locations(memory_location)

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
            binary_result = self.decoder._convert_json_to_binary_cpad(
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

    def _build_sppr_cpad(self, cper_data: Dict[str, Any], original_file: str,
                         confidence: int) -> Dict[str, Any]:
        """Build SPPR CPAD JSON by loading the spprTemplate.json template and
        overlaying values from the source CPER.

        Steps:
        1. Load the SPPR CPAD template (spprTemplate.json)
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
        # cpad-convert can't serialize typed CPER sections, so we read the raw
        # bytes of the proprietary Contoso section from the original binary CPER
        # and base64-encode them as {"Unknown": {"data": "<base64>"}}.
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

        # Update sectionLength and recordLength to match actual data.  A
        # single-section CPAD's body starts at a fixed 202-byte offset
        # (CPAD header + one section descriptor), verified against libcper.
        CPAD_SINGLE_SECTION_OFFSET = 202
        if sppr_cpad.get('sectionDescriptors'):
            sppr_cpad['sectionDescriptors'][0]['sectionOffset'] = CPAD_SINGLE_SECTION_OFFSET
            sppr_cpad['sectionDescriptors'][0]['sectionLength'] = section_length
            # Confidence is a section-descriptor field (the standard CPAD
            # location); cpad-convert sets its validation bit automatically.
            sppr_cpad['sectionDescriptors'][0]['confidence'] = confidence
        sppr_cpad['header'].pop('confidence', None)  # never in the top-level header
        sppr_cpad['header']['recordLength'] = CPAD_SINGLE_SECTION_OFFSET + section_length

        return sppr_cpad

    # ─── Main Analysis Flow ─────────────────────────────────────────────

    def analyze_files(self, cper_files: List[str]) -> int:
        """Analyze multiple binary CPER files.

        For each file:
        1. Convert binary .cper to JSON via cper-convert
        2. Generate decoded CPER report
        3. Check for repeat errors and auto-create SPPR CPAD if needed
        4. Print analysis recommendation

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

            # Step 2: Extract Creator ID (informational)
            header = cper_data.get('header', {})
            creator_id_data = header.get('creatorID', 'N/A')
            if isinstance(creator_id_data, dict):
                creator_id = creator_id_data.get('guid', str(creator_id_data))
            else:
                creator_id = str(creator_id_data)

            print(f"   ✓ Creator ID: {creator_id}")
            print(f"   🏢 Analyzer:   {ANALYZER_NAME}")

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
            dram_row_failure_detected = (
                self._has_prior_error_on_same_dram_device_row_at_different_column(
                    memory_location))

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
                'dram_row_failure_detected': dram_row_failure_detected,
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
# Plugin protocol — discovery and orchestrator-driven run modes
# ═══════════════════════════════════════════════════════════════════════════

def emit_discovery() -> int:
    """Print this analyzer's discovery descriptor as JSON and exit."""
    descriptor = {
        "analyzer_name": ANALYZER_NAME,
        "analyzer_version": ANALYZER_VERSION,
        "creator_ids": CREATOR_IDS,
        "prior_days": PRIOR_DAYS,
    }
    print(json.dumps(descriptor))
    return 0


def run_analysis(input_file: str) -> int:
    """Analyze the CPER window described by the AO's input file.

    Args:
        input_file: Path to the JSON input file written by the AO.  Contains
            ``cper_files`` (newest first) and ``newest_cper``.

    Returns:
        Process exit code (0 success, non-zero failure).
    """
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"   ✗ Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        with open(input_path, "r") as f:
            context = json.load(f)
    except json.JSONDecodeError as e:
        print(f"   ✗ Input file is not valid JSON: {e}", file=sys.stderr)
        return 1

    cper_files = context.get("cper_files", [])
    newest_cper = context.get("newest_cper")

    if not cper_files or not newest_cper:
        print("   ✗ Input file must list cper_files and newest_cper", file=sys.stderr)
        return 1

    newest_path = Path(newest_cper)

    IND = "      "  # 6-space margin: nest this plugin's output inside its box

    print(f"\n{IND}┌─────────────────────────────────────────────────────────────────────┐")
    print(f"{IND}│  Contoso CPER Analyzer (vendor plugin — runs as its own process)     │")
    print(f"{IND}└─────────────────────────────────────────────────────────────────────┘")

    # The engine writes its outputs (analysis JSON, SPPR CPAD JSON/binary)
    # into our own directory so the AO can collect them afterward.
    analyzer = ContosoAnalyzer(output_dir=str(SCRIPT_DIR), verbose=False)

    # Pre-load the prior CPERs in the window (oldest → newest, excluding the
    # newest) so repeat-error detection has the correct history.  cper_files is
    # ordered newest → oldest, so we reverse and drop the final (newest) entry.
    history = list(reversed(cper_files))[:-1]
    print(f"\n{IND}   📚 Establishing error history from the lookback window")
    if history:
        print(f"{IND}      Loaded {len(history)} prior CPER(s) to learn where errors have already been seen:")
        for prior_file in history:
            prior_data = analyzer.extract_cper_data(prior_file)
            if not prior_data:
                continue
            location = analyzer._extract_memory_location(prior_data)
            analyzer._add_to_seen_locations(location)
            if location:
                print(f"{IND}         • {analyzer._format_row(location)} "
                      f"Col={location['column']}")
    else:
        print(f"{IND}      No prior CPERs in the window — this is the first error")
        print(f"{IND}      at any location.")

    # Decode the newest (triggering) CPER — it is the subject of analysis.
    print(f"\n{IND}   📋 Analyzing newest CPER: {newest_path.name}")
    newest_data = analyzer.extract_cper_data(str(newest_path))
    if not newest_data:
        print(f"   ✗ Could not decode newest CPER: {newest_path}", file=sys.stderr)
        return 1
    print(f"{IND}      ✓ Valid CPER data extracted")

    creator_id = context.get("creator_id")
    if not creator_id:
        ch = newest_data.get("header", {}).get("creatorID", "N/A")
        creator_id = ch.get("guid", str(ch)) if isinstance(ch, dict) else str(ch)
    print(f"{IND}      ✓ Creator ID: {creator_id}")
    print(f"{IND}      🏢 Analyzer:   {ANALYZER_NAME}")

    # Full decoded CPER report (header, sections, DIMM info, action-event details).
    analyzer.generate_cper_report(newest_data, indent=IND)

    # Determine repeat status before creating the SPPR (create_... re-checks
    # and records first occurrences itself).
    memory_location = analyzer._extract_memory_location(newest_data)
    dram_row_failure_detected = (
        analyzer._has_prior_error_on_same_dram_device_row_at_different_column(
            memory_location))

    print(f"\n{IND}   🔁 DRAM device-row failure check")
    if dram_row_failure_detected:
        print(f"{IND}      A prior CPER recorded a different column on this DRAM device row.")
        print(f"{IND}      A single corrected error is normal wear; multiple errors on the same device row")
        print(f"{IND}      indicate a failing row that might be repairable with PPR.")
    elif memory_location:
        print(f"{IND}      First time this location has been seen → recorded, no repair yet.")
    else:
        print(f"{IND}      No memory-location data in this CPER (informational record).")

    # Attempt SPPR creation for the newest CPER.  This returns a path only when
    # the newest CPER is a repeat corrected error at a known memory location,
    # in which case it writes <stem>_sppr_cpad.json and <stem>_sppr_cpad.cpad.
    sppr_path = analyzer.create_sppr_cpad_from_cper(newest_data, str(newest_path))
    sppr_filename = Path(sppr_path).name if sppr_path else None

    # Recommendation block — explains the decision, error location, and next step.
    analyzer.print_batch_recommendation(
        [{
            'cper_data': newest_data,
            'sppr_created': sppr_path is not None,
            'sppr_filename': sppr_filename,
            'dram_row_failure_detected': dram_row_failure_detected,
            'memory_location': memory_location,
        }],
        successful=1,
        created_sppr_files=[sppr_filename] if sppr_filename else [],
        indent=IND,
    )

    if not sppr_path:
        # No remediation needed: emit a single analysis-result JSON so the AO
        # always has exactly one .json output to collect.
        result = {
            "analyzer_name": ANALYZER_NAME,
            "analyzer_version": ANALYZER_VERSION,
            "newest_cper": newest_path.name,
            "creator_id": context.get("creator_id"),
            "timestamp": context.get("newest_timestamp"),
            "window_size": len(cper_files),
            "sppr_recommended": False,
            "header": newest_data.get("header", {}),
        }
        result_path = SCRIPT_DIR / f"{newest_path.stem}_analysis.json"
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contoso CPER analyzer plugin for the Analysis Orchestrator"
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Emit this analyzer's discovery descriptor as JSON and exit",
    )
    parser.add_argument(
        "--input-file",
        help="Path to the AO-generated JSON input file listing CPERs to analyze",
    )
    parser.add_argument(
        "--cper-dir",
        help="Standalone mode: analyze every .cper under a directory and print reports",
    )
    parser.add_argument(
        "--error-type",
        help="With --cper-dir, filter by error type subdirectory (e.g. corrected)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose output",
    )
    args = parser.parse_args()

    if args.discover:
        return emit_discovery()

    if args.input_file:
        return run_analysis(args.input_file)

    if args.cper_dir:
        analyzer = ContosoAnalyzer(verbose=args.verbose)
        successful = analyzer.analyze_directory(args.cper_dir, error_type=args.error_type)
        return 0 if successful > 0 else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
