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
         "analyzer_version": "1.1.0",
         "creator_ids":      ["11111111-2222-3333-4444-555555555555"],
         "prior_days":       30
       }

2. Run mode (``--input-file <path>``)
   Reads a JSON input file produced by the AO that lists the CPERs to
   consider (newest first) and processes them.  Outputs are written next to
   this script (the AO clears stale ``.json``/``.cpad`` files beforehand and
   collects whatever this run produces):
    - exactly one analysis ``.json`` manifest, and
    - zero or more paired ``*_cpad.json``/``*.cpad`` action outputs.

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
ANALYZER_VERSION = "1.1.0"
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
from memory_events import (       # noqa: E402
    decode_memory_events,
    events_for_manufacturer,
    newest_manufacturer_ids,
)
from memory_shims import ShimContractError  # noqa: E402
from cpu_core_analyzer import CpuCoreAnalyzer  # noqa: E402
from cross_subcomponent_correlator import (  # noqa: E402
    correlate_subcomponent_results,
)
from memory_controller_analyzer import MemoryControllerAnalyzer  # noqa: E402

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


def decode_newest_sections(analyzer: "ContosoAnalyzer",
                           cper_data: Dict[str, Any],
                           cper_file: str) -> Dict[str, List[Dict[str, Any]]]:
    """Decode and group every supported section while retaining its index."""
    grouped = {"cpu_core": [], "memory_controller": []}
    descriptors = cper_data.get("sectionDescriptors", [])
    for section_index in range(len(descriptors)):
        section_name, decoded = analyzer._decode_contoso_section(
            cper_data, section_index)
        if section_name is None:
            continue
        category = contoso_catalog.SECTION_TYPES[section_name]["category"]
        subcomponent = {
            "core": "cpu_core",
            "memory": "memory_controller",
        }.get(category)
        if subcomponent is None:
            continue
        descriptor = descriptors[section_index]
        grouped[subcomponent].append({
            "source": {
                "cper_file": cper_file,
                "window_index": 0,
                "section_index": section_index,
                "is_newest": True,
            },
            "section_name": section_name,
            "decoded": decoded,
            "section_descriptor": copy.deepcopy(descriptor),
            "fru": {
                "id": analyzer._normalized_id(descriptor.get("fruID")),
                "text": str(descriptor.get("fruText", "")).strip(),
            },
        })
    return grouped


def _has_platform_action_event(cper_data: Dict[str, Any]) -> bool:
    return any(
        isinstance(section, dict) and "PlatformActionEvent" in section
        for section in cper_data.get("sections", [])
    )


def dispatch_subcomponent_analysis(
        analyzer: "ContosoAnalyzer", records: List[Dict[str, Any]],
        source_stem: str,
        grouped: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        prior_cper_count: Optional[int] = None,
        cpu_analyzer_factory=CpuCoreAnalyzer,
        memory_analyzer_factory=MemoryControllerAnalyzer) -> Dict[str, Any]:
    """Invoke every analyzer applicable to the newest decoded CPER."""
    if not records:
        raise ValueError("decoded CPER window must not be empty")
    newest = records[0]
    if grouped is None:
        grouped = decode_newest_sections(
            analyzer, newest["cper_data"], newest["cper_file"])
    if prior_cper_count is None:
        prior_cper_count = max(len(records) - 1, 0)
    results = []
    if grouped["cpu_core"]:
        results.append(cpu_analyzer_factory().analyze(
            grouped["cpu_core"], prior_cper_count))
    if (grouped["memory_controller"]
            or _has_platform_action_event(newest["cper_data"])):
        memory_analyzer = memory_analyzer_factory(analyzer, SCRIPT_DIR / "memory_shims")
        results.append(memory_analyzer.analyze(
            grouped["memory_controller"], records, source_stem,
            prior_cper_count))
    return correlate_subcomponent_results(results)


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

        # The memory-action template starts with the original SPPR example.
        self.cpad_storage_dir = RASAPI_DIR / "cpad_storage"
        self.sppr_template_path = self.cpad_storage_dir / "spprTemplate.json"

        # In-memory tracking of seen memory locations (stateless — rebuilt each run)
        self.seen_locations = []

        # Memory support is initialized only when dispatch finds a memory
        # section (or a Platform Action Event requiring memory correlation).
        self.memory_shims = {}
        self.memory_shim_errors = []

    @staticmethod
    def _normalized_id(value) -> str:
        if isinstance(value, dict):
            value = value.get('guid', value.get('data', ''))
        return str(value or '').strip().strip('{}').lower()

    @classmethod
    def _validate_shim_cpad(cls, cpad: Dict[str, Any],
                            events: List[Dict[str, Any]]) -> None:
        """Validate a shim's complete CPAD against its input event context."""
        header = cpad.get('header')
        descriptors = cpad.get('sectionDescriptors')
        sections = cpad.get('sections')
        if not isinstance(header, dict):
            raise ShimContractError("shim CPAD must contain a header object")
        if not isinstance(descriptors, list) or not descriptors:
            raise ShimContractError(
                "shim CPAD must contain at least one section descriptor")
        if not isinstance(sections, list) or len(sections) != len(descriptors):
            raise ShimContractError(
                "shim CPAD sections must match its section descriptors")
        section_count = header.get('sectionCount')
        if (not isinstance(section_count, int) or isinstance(section_count, bool)
                or section_count != len(descriptors)):
            raise ShimContractError(
                "shim CPAD header.sectionCount must match its section descriptors")
        if any(not isinstance(section, dict) for section in sections):
            raise ShimContractError("shim CPAD sections must contain objects")

        allowed_headers = {
            (
                cls._normalized_id(event.get('header', {}).get('platformID')),
                cls._normalized_id(event.get('header', {}).get('partitionID')),
                cls._normalized_id(event.get('header', {}).get('creatorID')),
            )
            for event in events
        }
        cpad_header = (
            cls._normalized_id(header.get('platformID')),
            cls._normalized_id(header.get('partitionID')),
            cls._normalized_id(header.get('creatorID')),
        )
        if cpad_header not in allowed_headers:
            raise ShimContractError(
                "shim CPAD platform, partition, and creator IDs must match an input event")

        input_frus = {
            (event.get('fru', {}).get('id'), event.get('fru', {}).get('text'))
            for event in events
        }
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                raise ShimContractError("shim CPAD section descriptor must be an object")
            action = descriptor.get('actionID', descriptor.get('actionId'))
            if isinstance(action, dict):
                action = action.get('code')
            if action in (None, ''):
                raise ShimContractError("shim CPAD section must contain an action ID")
            confidence = descriptor.get('confidence')
            if (not isinstance(confidence, int) or isinstance(confidence, bool)
                    or not 0 <= confidence <= 100):
                raise ShimContractError(
                    "shim CPAD confidence must be an integer from 0 through 100")
            fru = (
                cls._normalized_id(descriptor.get('fruID')),
                str(descriptor.get('fruText', '')).strip(),
            )
            if fru not in input_frus:
                raise ShimContractError(
                    "shim CPAD FRU ID and text must match an input event")

    def analyze_memory_events(self, events: List[Dict[str, Any]],
                              shims=None,
                              newest_vendor=None):
        """Invoke the matching shim for a pre-filtered decoded event window."""
        active_shims = self.memory_shims if shims is None else shims
        invocations = []
        cpads = []
        cpads_by_manufacturer = {}
        handled_manufacturers = set()
        failed_manufacturers = set()
        vendor_ids = ([newest_vendor] if newest_vendor is not None
                      else newest_manufacturer_ids(events))
        for vendor_id in vendor_ids:
            shim = active_shims.get(vendor_id)
            if shim is None:
                continue
            vendor_events = events_for_manufacturer(events, vendor_id)
            try:
                returned = shim.analyze(vendor_events)
                validated = []
                pending_fingerprints = set()
                for cpad in returned:
                    self._validate_shim_cpad(cpad, vendor_events)
                    fingerprint = json.dumps(cpad, sort_keys=True, separators=(',', ':'))
                    if fingerprint not in pending_fingerprints:
                        pending_fingerprints.add(fingerprint)
                        validated.append((fingerprint, cpad))
                vendor_cpads = [(shim, cpad) for _fingerprint, cpad in validated]
                cpads.extend(vendor_cpads)
                cpads_by_manufacturer[vendor_id] = vendor_cpads
                handled_manufacturers.add(vendor_id)
                invocations.append({
                    'shim': shim.name,
                    'manufacturer_id': list(vendor_id),
                    'event_count': len(vendor_events),
                    'cpad_count': len(vendor_cpads),
                    'status': 'ok',
                })
            except Exception as exc:
                failed_manufacturers.add(vendor_id)
                invocations.append({
                    'shim': shim.name,
                    'manufacturer_id': list(vendor_id),
                    'event_count': len(vendor_events),
                    'cpad_count': 0,
                    'status': 'failed',
                    'error': str(exc),
                })
        return {
            'events': events,
            'invocations': invocations,
            'cpads': cpads,
            'cpads_by_manufacturer': cpads_by_manufacturer,
            'handled_manufacturers': handled_manufacturers,
            'failed_manufacturers': failed_manufacturers,
        }

    def analyze_memory_event_window(self, records: List[Dict[str, Any]]):
        """Compatibility delegate for callers supplying a decoded CPER window."""
        return self.analyze_memory_events(decode_memory_events(records))

    def emit_shim_cpads(self, shim_cpads, source_stem: str,
                        vendor_id=None):
        """Write paired shim CPAD JSON/binary outputs and return binary paths."""
        outputs = []
        generated = []
        try:
            for index, (shim, cpad) in enumerate(shim_cpads, 1):
                vendor = shim.path.stem.removeprefix('analyzer_')
                vendor_suffix = ""
                if vendor_id is not None:
                    vendor_suffix = f"_{vendor_id[0]:02x}{vendor_id[1]:02x}"
                stem = f"{source_stem}_{vendor}{vendor_suffix}_{index}_cpad"
                json_path = self.output_dir / f"{stem}.json"
                binary_path = self.output_dir / f"{stem}.cpad"
                generated.extend((json_path, binary_path))
                with open(json_path, 'w') as stream:
                    json.dump(cpad, stream, indent=2)
                converted = self.decoder._convert_json_to_binary_cpad(
                    str(json_path), str(binary_path))
                if not converted:
                    raise ShimContractError(
                        f"could not convert {shim.name} CPAD {index} to binary")
                outputs.append(str(binary_path))
            return outputs
        except Exception:
            for path in generated:
                path.unlink(missing_ok=True)
            raise

    def emit_shim_cpad_groups(self, shim_result, source_stem: str):
        """Emit each vendor's CPADs atomically without affecting other vendors."""
        outputs = []
        errors = []
        for vendor_id, shim_cpads in shim_result[
                'cpads_by_manufacturer'].items():
            try:
                outputs.extend(self.emit_shim_cpads(
                    shim_cpads, source_stem, vendor_id))
            except Exception as exc:
                shim_result['handled_manufacturers'].discard(vendor_id)
                shim_result['failed_manufacturers'].add(vendor_id)
                error = str(exc)
                errors.append((vendor_id, error))
                for invocation in shim_result['invocations']:
                    if tuple(invocation['manufacturer_id']) == vendor_id:
                        invocation['status'] = 'failed'
                        invocation['error'] = error
                        invocation['cpad_count'] = 0
                        break
        return outputs, errors

    def default_memory_events(self, shim_result):
        """Return newest DRAM errors not successfully owned by a shim."""
        return [
            event for event in shim_result['events']
            if event['event_type'] == 'memory_error'
            and event['source']['is_newest']
            and self._memory_location_from_event(event) is not None
            and tuple(event['dram_manufacturer_id']) not in
            shim_result['handled_manufacturers']
        ]

    # ─── CPER Data Extraction ───────────────────────────────────────────

    def extract_cper_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Decode a binary .cper file to full CPER JSON (header + sections)."""
        return self.decoder.extract_cper_data(file_path)

    # ─── Error Tracking ─────────────────────────────────────────────────

    @staticmethod
    def _memory_location_from_event(event: Dict[str, Any]) -> Optional[Dict]:
        """Adapt one fully decoded DRAM error event to legacy row analysis."""
        memory_error = event.get('memory_error', {})
        if memory_error.get('bank') != 'DRAM Errors':
            return None
        sub = memory_error.get('subcomponent', {})
        add = memory_error.get('additional', {})
        device = add.get('device')
        beat_errors = []
        masks = add.get('beat_mask')
        if isinstance(masks, list):
            for dq, mask in enumerate(masks):
                mask = int(mask)
                if mask:
                    beat_errors.append({
                        'dram': device,
                        'dq': dq,
                        'beats': [beat for beat in range(16)
                                  if mask & (1 << beat)],
                    })
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
            'serial_number': add.get('serial_number', ''),
            'part_number': add.get('part_number', ''),
            'dram_manufacturer_id': add.get('dram_manufacturer_id', [0, 0]),
            'dram_manufacturer': contoso_catalog.decode_spd_manufacturer_id(
                add.get('dram_manufacturer_id', [0, 0])),
            'module_manufacturer_id': add.get('module_manufacturer_id', [0, 0]),
            'module_manufacturer': contoso_catalog.decode_spd_manufacturer_id(
                add.get('module_manufacturer_id', [0, 0])),
            'spd_temperature': add.get('spd_temperature'),
            'physical_address': memory_error.get('error_address', 0),
            'beat_errors': beat_errors,
            'drams': [device],
            'device': device,
            'repairs': add.get('repairs', []),
        }

    def _extract_memory_locations(self, cper_data: Dict[str, Any]):
        events = decode_memory_events([{
            'cper_data': cper_data,
            'cper_file': '',
            'is_newest': True,
        }])
        return [
            location for event in events
            if event['event_type'] == 'memory_error'
            for location in [self._memory_location_from_event(event)]
            if location is not None
        ]

    def _extract_memory_location(self, cper_data: Dict[str, Any]) -> Optional[Dict]:
        """Return the first DRAM location for legacy single-section callers."""
        return next(iter(self._extract_memory_locations(cper_data)), None)

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
            body = base64.b64decode(b64, validate=True)
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
    def _memory_repair_capability_lines(value: int) -> List[str]:
        """Return one display line for each memory repair capability."""
        capabilities = (
            (0, "Soft PPR at runtime"),
            (1, "Soft PPR at boot time"),
            (2, "Hard PPR at boot time"),
        )
        return [
            f"{label}: {'Supported' if value & (1 << bit) else 'Not supported'}"
            for bit, label in capabilities
        ]

    @staticmethod
    def _fmt_register(name, code, value) -> str:
        """Format a Contoso register/additional value for display.

        64-bit registers (code 'Q') and packed arrays read better in hex; the
        logical DRAM coordinates (channel, dimm, …) read better in decimal.
        """
        if (isinstance(code, tuple) and code[0] == 'bytes' and
                isinstance(value, list)):
            raw = " ".join(f"{byte:02X}" for byte in value)
            if name in ('dram_manufacturer_id', 'module_manufacturer_id'):
                vendor = contoso_catalog.decode_spd_manufacturer_id(value)
                return f"{raw} ({vendor})"
            return raw
        if name == 'beat_mask' and isinstance(value, list):
            entries = []
            for dq, mask in enumerate(value):
                if not mask:
                    continue
                beats = [beat for beat in range(16) if mask & (1 << beat)]
                beat_label = (f"beat {beats[0]}" if len(beats) == 1
                              else f"beats {', '.join(map(str, beats))}")
                entries.append(f"DQ {dq}, {beat_label} (mask {hex(mask)})")
            return "; ".join(entries) if entries else "(all zero)"
        if name == 'repairs' and isinstance(value, list):
            if not value:
                return "(none)"
            return "; ".join(
                f"SC {entry['subchannel']}, Rank {entry['rank']}, "
                f"Device {entry['device']}, BG {entry['bank_group']}, "
                f"Bank {entry['bank']}: {entry['count']}"
                for entry in value)
        if name == 'total_memory_bytes':
            gib = value / (1024 ** 3)
            return f"{gib:g} GiB ({value} bytes)"
        if name == 'memory_repair_capabilities':
            return "; ".join(
                ContosoAnalyzer._memory_repair_capability_lines(value))
        if name == 'spd_temperature':
            return "not recorded" if value is None else f"{value} C"
        if isinstance(value, list):          # Other packed array fields
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
            value = decoded['additional'].get(name)
            if name == 'memory_repair_capabilities':
                print(f"            {name}:")
                for capability in self._memory_repair_capability_lines(value):
                    print(f"               {capability}")
                continue
            print(f"            {name + ':':<30} "
                  f"{self._fmt_register(name, code, value)}")

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
                                '0x8002': 'Page Offline',
                                '0x8003': 'Reboot with Memory Retraining',
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
                                       sppr_filename: Optional[str] = None,
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
                                     created_files: Optional[List[str]] = None,
                                     created_sppr_files: Optional[List[str]] = None,
                                     vendor_cpad_files: Optional[List[str]] = None,
                                     cpad_generation_failed: bool = False,
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
            vendor_cpad_files: list of memory-vendor CPAD filenames
            indent: Optional left-margin prefix applied to every printed line
                (used when the block is nested inside the orchestrator flow).
        """
        print = _indented_print(indent)
        created_files = created_files or []
        created_sppr_files = created_sppr_files or []
        vendor_cpad_files = vendor_cpad_files or []
        dram_row_failure_detected = any(
            r['dram_row_failure_detected'] for r in analysis_results)
        sppr_results = [r for r in analysis_results if r['sppr_created']]
        has_sppr = len(sppr_results) > 0
        has_platform_action_event = any(
            any(
                'action event' in str(
                    descriptor.get('sectionType', {}).get('type', '')
                    if isinstance(descriptor.get('sectionType'), dict)
                    else descriptor.get('sectionType', '')
                ).lower()
                for descriptor in result['cper_data'].get('sectionDescriptors', [])
            )
            for result in analysis_results
        )
        has_failed_platform_action_event = any(
            section.get('PlatformActionEvent', {}).get('actionReturnCode') != '0x00'
            for result in analysis_results
            for section in result['cper_data'].get('sections', [])
            if 'PlatformActionEvent' in section
        )

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
        for filename in vendor_cpad_files:
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
        elif vendor_cpad_files:
            print(f"\n   Recommendation:     Memory vendor-recommended RAS action")
            print(f"   Reason:             Memory vendor analysis returned "
                  f"{len(vendor_cpad_files)} CPAD(s).")
            print(f"   Next Step:          Evaluate each CPAD against operator policy.")
        elif cpad_generation_failed:
            print(f"\n   Finding:            A DRAM row-failure pattern was detected.")
            print(f"   Recommendation:     No action emitted")
            print(f"   Reason:             CPAD generation failed.")
        elif dram_row_failure_detected:
            print(f"\n   Recommendation:     Perform SPPR (Soft Post-Package Repair) operation")
            print(f"   ⚠️  SPPR CPAD not created")
        elif has_failed_platform_action_event:
            print(f"\n   Recommendation:     Review Failed Platform Action")
            print(f"   Reason:             Platform Action Failed.")
        elif has_platform_action_event:
            print(f"\n   Recommendation:     No Action Required")
            print(f"   Reason:             Platform Action Completed.")
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

        if cpad_generation_failed and (has_sppr or vendor_cpad_files):
            print(f"   Warning:            CPAD generation failed for another memory section.")

        print(f"   {'=' * 70}")

    # ─── SPPR CPAD Creation ─────────────────────────────────────────────

    def create_sppr_cpad_from_memory_event(
            self, event: Dict[str, Any], cper_data: Dict[str, Any],
            original_file: Optional[str] = None,
            output_stem: Optional[str] = None,
            record_location: bool = True) -> Optional[str]:
        """Run default row analysis for one decoded DRAM error event."""
        try:
            memory_error = event.get('memory_error', {})
            status = memory_error.get('error_status', {})
            if (event.get('event_type') != 'memory_error' or
                    memory_error.get('bank') != 'DRAM Errors' or
                    status.get('severity_value') !=
                    contoso_catalog.SEVERITY_VALUES['Corrected']):
                return None

            memory_location = self._memory_location_from_event(event)
            failure_detected = (
                self._has_prior_error_on_same_dram_device_row_at_different_column(
                    memory_location))
            if not failure_detected:
                if record_location:
                    self._add_to_seen_locations(memory_location)
                return None

            distinct_columns = self._distinct_columns_on_row(memory_location)
            confidence = self._sppr_confidence(distinct_columns)
            if self.verbose:
                print(f"  📊 SPPR confidence: {confidence}% "
                      f"({distinct_columns} distinct column address(es) on the row)")
            section_index = event.get('source', {}).get('section_index', 0)
            sppr_cpad = self._build_sppr_cpad(
                cper_data, original_file, confidence, section_index)
            if record_location:
                self._add_to_seen_locations(memory_location)

            header = cper_data.get('header', {})
            base_name = output_stem
            if not base_name:
                base_name = (Path(original_file).stem if original_file else
                             f"cper_{header.get('recordID', 'unknown')}")
            sppr_json_path = self.output_dir / f"{base_name}_sppr_cpad.json"
            sppr_binary_path = self.output_dir / f"{base_name}_sppr_cpad.cpad"
            with open(sppr_json_path, 'w') as stream:
                json.dump(sppr_cpad, stream, indent=2)
            try:
                binary_result = self.decoder._convert_json_to_binary_cpad(
                    str(sppr_json_path), str(sppr_binary_path))
            except Exception:
                sppr_json_path.unlink(missing_ok=True)
                sppr_binary_path.unlink(missing_ok=True)
                raise
            if binary_result:
                return str(sppr_binary_path)
            sppr_json_path.unlink(missing_ok=True)
            sppr_binary_path.unlink(missing_ok=True)
            if self.verbose:
                print("  ⚠️  Binary conversion failed; no SPPR CPAD emitted")
            return None
        except Exception as exc:
            print(f"  ✗ Error creating SPPR CPAD: {exc}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def create_sppr_cpad_from_cper(self, cper_data: Dict[str, Any],
                                    original_file: Optional[str] = None) -> Optional[str]:
        """Compatibility wrapper for the first decoded DRAM error section."""
        events = decode_memory_events([{
            'cper_data': cper_data,
            'cper_file': original_file or '',
            'is_newest': True,
        }])
        event = next((item for item in events
                      if self._memory_location_from_event(item) is not None), None)
        if event is None:
            return None
        return self.create_sppr_cpad_from_memory_event(
            event, cper_data, original_file)

    def create_page_offline_cpad_from_memory_event(
            self,
            event: Dict[str, Any],
            cper_data: Dict[str, Any],
            original_file: Optional[str] = None,
            output_stem: Optional[str] = None,
            confidence: int = 100) -> Optional[str]:
        """Create a Page Offline CPAD for a 4 KiB-aligned physical address."""
        address = event.get('memory_error', {}).get('physical_address')
        if not isinstance(address, int) or address < 0:
            raise ValueError("Page Offline requires a physical address")
        if address % contoso_catalog.PAGE_SIZE_BYTES:
            raise ValueError(
                "Page Offline physical address must be 4 KiB aligned")
        return self._create_memory_action_cpad_output(
            event,
            cper_data,
            contoso_catalog.PAGE_OFFLINE_ACTION,
            "page_offline",
            confidence,
            original_file,
            output_stem,
        )

    def create_reboot_with_retraining_cpad_from_memory_event(
            self,
            event: Dict[str, Any],
            cper_data: Dict[str, Any],
            original_file: Optional[str] = None,
            output_stem: Optional[str] = None,
            confidence: int = 100) -> Optional[str]:
        """Create a partition-scoped reboot-with-retraining CPAD."""
        return self._create_memory_action_cpad_output(
            event,
            cper_data,
            contoso_catalog.REBOOT_WITH_RETRAINING_ACTION,
            "reboot_with_retraining",
            confidence,
            original_file,
            output_stem,
        )

    def _create_memory_action_cpad_output(
            self,
            event: Dict[str, Any],
            cper_data: Dict[str, Any],
            action: Dict[str, str],
            suffix: str,
            confidence: int,
            original_file: Optional[str],
            output_stem: Optional[str]) -> Optional[str]:
        """Write paired JSON and binary output for one Contoso memory action."""
        section_index = event.get('source', {}).get('section_index')
        if not isinstance(section_index, int):
            raise ValueError("memory action requires a source section index")
        action_cpad = self._build_memory_action_cpad(
            cper_data,
            original_file,
            action,
            confidence,
            section_index,
        )
        header = cper_data.get('header', {})
        base_name = output_stem
        if not base_name:
            base_name = (
                Path(original_file).stem if original_file
                else f"cper_{header.get('recordID', 'unknown')}"
            )
        json_path = self.output_dir / f"{base_name}_{suffix}_cpad.json"
        binary_path = self.output_dir / f"{base_name}_{suffix}_cpad.cpad"
        with open(json_path, 'w') as stream:
            json.dump(action_cpad, stream, indent=2)
        try:
            result = self.decoder._convert_json_to_binary_cpad(
                str(json_path), str(binary_path))
        except Exception:
            json_path.unlink(missing_ok=True)
            binary_path.unlink(missing_ok=True)
            raise
        if result:
            return str(binary_path)
        json_path.unlink(missing_ok=True)
        binary_path.unlink(missing_ok=True)
        return None

    def _build_sppr_cpad(self, cper_data: Dict[str, Any], original_file: Optional[str],
                         confidence: int, section_index: int = 0) -> Dict[str, Any]:
        """Build an SPPR CPAD from one source memory section."""
        return self._build_memory_action_cpad(
            cper_data,
            original_file,
            contoso_catalog.SPPR_ACTION,
            confidence,
            section_index,
        )

    def _build_memory_action_cpad(
            self,
            cper_data: Dict[str, Any],
            original_file: Optional[str],
            action: Dict[str, str],
            confidence: int,
            section_index: int = 0) -> Dict[str, Any]:
        """Build a Contoso memory-action CPAD from one source CPER section.

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
            dict: CPAD data in cperlib format, ready for cpad-convert
        """
        # ── Step 1: Load template ───────────────────────────────────────
        if not self.sppr_template_path.exists():
            raise FileNotFoundError(
                f"SPPR template not found: {self.sppr_template_path}")

        with open(self.sppr_template_path, 'r') as f:
            sppr_cpad = json.load(f)

        # Deep-copy so we never mutate the cached template
        action_cpad = copy.deepcopy(sppr_cpad)
        action_cpad['sectionDescriptors'][0]['actionID'] = dict(action)

        # ── Step 2: Overlay header IDs from CPER ────────────────────────
        cper_header = cper_data.get('header', {})

        def _extract_id(data):
            if isinstance(data, dict):
                return data.get('guid', data.get('data', str(data)))
            return str(data) if data else ''

        for field in ('platformID', 'creatorID', 'partitionID'):
            value = cper_header.get(field)
            if value:
                action_cpad['header'][field] = _extract_id(value)

        # ── Step 3: Timestamp = CPER timestamp + 5 seconds ──────────────
        cper_timestamp_str = cper_header.get('timestamp', datetime.now().isoformat())
        try:
            dt = datetime.fromisoformat(cper_timestamp_str.replace('Z', '+00:00'))
            new_dt = dt + timedelta(seconds=5)
            new_timestamp = new_dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except Exception:
            new_timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')

        action_cpad['header']['timestamp'] = new_timestamp

        # ── Step 4: Fresh recordID ──────────────────────────────────────
        action_cpad['header']['recordID'] = int(datetime.now().timestamp())

        # ── Step 5: Copy FRU / sectionType from CPER descriptors ────────
        cper_descriptors = cper_data.get('sectionDescriptors', [])
        if (section_index < len(cper_descriptors) and
                action_cpad.get('sectionDescriptors')):
            cper_desc = cper_descriptors[section_index]
            action_desc = action_cpad['sectionDescriptors'][0]

            for field in ('fruID', 'fruText'):
                if field in cper_desc:
                    action_desc[field] = cper_desc[field]

            st = cper_desc.get('sectionType', {})
            if isinstance(st, dict) and 'data' in st:
                action_desc['sectionType'] = {
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
        if section_index < len(cper_descriptors) and original_file:
            sec_offset = cper_descriptors[section_index].get('sectionOffset', 0)
            sec_length = cper_descriptors[section_index].get('sectionLength', 0)
            try:
                with open(original_file, 'rb') as f:
                    f.seek(sec_offset)
                    raw_section = f.read(sec_length)
                section_data_b64 = base64.b64encode(raw_section).decode('ascii')
                section_length = sec_length
            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️  Could not read section bytes from {original_file}: {e}")
        elif section_index < len(cper_data.get('sections', [])):
            section_data_b64 = cper_data['sections'][section_index].get(
                'Unknown', {}).get('data', '')
            try:
                section_length = len(base64.b64decode(
                    section_data_b64, validate=True))
            except Exception:
                section_data_b64 = ""
                section_length = 0

        # Update section data in template
        action_cpad['sections'] = [{"Unknown": {"data": section_data_b64}}]

        # Update sectionLength and recordLength to match actual data.  A
        # single-section CPAD's body starts at a fixed 202-byte offset
        # (CPAD header + one section descriptor), verified against libcper.
        CPAD_SINGLE_SECTION_OFFSET = 202
        if action_cpad.get('sectionDescriptors'):
            action_cpad['sectionDescriptors'][0]['sectionOffset'] = CPAD_SINGLE_SECTION_OFFSET
            action_cpad['sectionDescriptors'][0]['sectionLength'] = section_length
            # Confidence is a section-descriptor field (the standard CPAD
            # location); cpad-convert sets its validation bit automatically.
            action_cpad['sectionDescriptors'][0]['confidence'] = confidence
        action_cpad['header'].pop('confidence', None)
        action_cpad['header']['recordLength'] = (
            CPAD_SINGLE_SECTION_OFFSET + section_length)

        return action_cpad

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

    def analyze_directory(self, cper_dir: str,
                          error_type: Optional[str] = None) -> int:
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

    history = cper_files[1:]
    decoded_window = {}
    print(f"\n{IND}   📚 Prior CPER candidates")
    if history:
        print(f"{IND}      {len(history)} prior CPER(s) are available for "
              "subcomponent analyzers to consider.")
        print(f"{IND}      Relevant history will be selected after the newest "
              "CPER is decoded.")
    else:
        print(f"{IND}      No prior CPER candidates are available.")

    # Decode the newest (triggering) CPER — it is the subject of analysis.
    print(f"\n{IND}   📋 Analyzing newest CPER: {newest_path.name}")
    newest_data = analyzer.extract_cper_data(str(newest_path))
    if not newest_data:
        print(f"   ✗ Could not decode newest CPER: {newest_path}", file=sys.stderr)
        return 1
    decoded_window[str(newest_path)] = newest_data
    print(f"{IND}      ✓ Valid CPER data extracted")

    creator_id = context.get("creator_id")
    if not creator_id:
        ch = newest_data.get("header", {}).get("creatorID", "N/A")
        creator_id = ch.get("guid", str(ch)) if isinstance(ch, dict) else str(ch)
    print(f"{IND}      ✓ Creator ID: {creator_id}")
    print(f"{IND}      🏢 Analyzer:   {ANALYZER_NAME}")

    # Full decoded CPER report (header, sections, DIMM info, action-event details).
    analyzer.generate_cper_report(newest_data, indent=IND)

    grouped = decode_newest_sections(analyzer, newest_data, str(newest_path))
    needs_history = (
        bool(grouped["memory_controller"])
        or _has_platform_action_event(newest_data)
    )
    selected_files = cper_files if needs_history else cper_files[:1]
    records = []
    for window_index, cper_file in enumerate(selected_files):
        cper_path = Path(cper_file)
        cper_data = decoded_window.get(str(cper_path))
        if cper_data is None:
            cper_data = analyzer.extract_cper_data(str(cper_path))
        if cper_data is not None:
            records.append({
                'cper_data': cper_data,
                'cper_file': str(cper_path),
                'is_newest': window_index == 0,
            })

    try:
        combined_result = dispatch_subcomponent_analysis(
            analyzer, records, newest_path.stem, grouped, len(history))
    except ValueError as exc:
        print(f"   ✗ Invalid newest CPER: {exc}", file=sys.stderr)
        return 1

    for subcomponent_result in combined_result["subcomponents"]:
        history_summary = subcomponent_result.get("history_summary")
        if history_summary is None:
            continue
        print(f"\n{IND}   🧠 {history_summary['heading']}")
        for message in history_summary["messages"]:
            print(f"{IND}      {message}")

    memory_result = next(
        (result for result in combined_result["subcomponents"]
         if result["subcomponent"] == "memory_controller"),
        None,
    )
    shim_result = memory_result["shim_result"] if memory_result else {
        "events": [], "invocations": [], "handled_manufacturers": set(),
    }
    shim_cpad_paths = memory_result["shim_cpads"] if memory_result else []
    shim_cpad_filenames = [Path(path).name for path in shim_cpad_paths]
    default_cpad_paths = memory_result["default_cpads"] if memory_result else []
    generation_failed = (
        memory_result["cpad_generation_failed"] if memory_result else False)
    memory_location = (
        memory_result["recommendation_location"] if memory_result else None)
    dram_row_failure_detected = (
        memory_result["dram_row_failure_detected"] if memory_result else False)

    if memory_result is not None:
        analysis_route = memory_result["analysis_route"]
        print(f"\n{IND}   🧭 {analysis_route['heading']}")
        for message in analysis_route["messages"]:
            print(f"{IND}      {message}")
        for error in analyzer.memory_shim_errors:
            print(f"{IND}   ⚠️  Memory shim discovery: {error}")
        for invocation in shim_result["invocations"]:
            if invocation["status"] == "ok":
                print(f"{IND}   🧩 {invocation['shim']}: "
                      f"{invocation['event_count']} event(s), "
                      f"{invocation['cpad_count']} CPAD(s)")
            else:
                print(f"{IND}   ⚠️  {invocation['shim']} failed: "
                      f"{invocation['error']} — using default analysis when applicable")
        for _vendor_id, error in memory_result["emission_errors"]:
            print(f"{IND}   ⚠️  Memory shim CPAD emission failed: {error}")

        print(f"\n{IND}   🔁 DRAM device-row failure check")
        if dram_row_failure_detected:
            print(f"{IND}      A prior CPER recorded a different column on this DRAM device row.")
            print(f"{IND}      A single corrected error is normal wear; multiple errors on the same device row")
            print(f"{IND}      indicate a failing row that might be repairable with PPR.")
        elif memory_result["all_newest_dram_errors_handled"]:
            print(f"{IND}      Matching memory-vendor shim owns analysis for this event.")
        elif memory_location:
            print(f"{IND}      First time this location has been seen → recorded, no repair yet.")
        else:
            print(f"{IND}      No DRAM-location data in this CPER.")
    default_cpad_filenames = [Path(path).name for path in default_cpad_paths]
    sppr_path = default_cpad_paths[0] if default_cpad_paths else None
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
        created_sppr_files=default_cpad_filenames,
        vendor_cpad_files=shim_cpad_filenames,
        cpad_generation_failed=generation_failed,
        indent=IND,
    )

    result = {
        "analyzer_name": ANALYZER_NAME,
        "analyzer_version": ANALYZER_VERSION,
        "newest_cper": newest_path.name,
        "creator_id": context.get("creator_id"),
        "timestamp": context.get("newest_timestamp"),
        "window_size": len(cper_files),
        "memory_event_count": len(shim_result['events']),
        "memory_shim_invocations": shim_result['invocations'],
        "shim_cpad_count": len(shim_cpad_paths),
        "sppr_recommended": bool(default_cpad_paths),
        "cpad_generation_failed": generation_failed,
        "subcomponent_results": [
            {
                "subcomponent": item["subcomponent"],
                "section_indexes": item.get("section_indexes", []),
                "findings": item.get("findings", []),
            }
            for item in combined_result["subcomponents"]
        ],
        "cross_subcomponent_correlations": combined_result["correlations"],
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
