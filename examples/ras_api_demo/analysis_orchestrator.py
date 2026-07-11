#!/usr/bin/env python3
"""
Analysis Orchestrator
=====================

Discovers analyzer plugins and routes incoming CPERs to the correct analyzer.

The orchestrator is intentionally analyzer-agnostic: it never imports any
vendor-specific analysis logic.  It decodes just enough of each CPER (via the
generic :class:`CperDecoder`) to read the CreatorID/timestamp needed for
routing, then hands the work off to the owning ``analyzer-<company>.py`` plugin.

Pipeline:
- Discover ``analyzer-*.py`` scripts under ``analyzers/`` (recursive), run each
  with ``--discover``, and build a CreatorID → analyzer routing table.
- For each newly collected CPER (pushed via :meth:`notify_new_cpers`), select
  the owning analyzer, gather a directory-scoped lookback window, and invoke the
  analyzer with an input file.
- Collect the analyzer's outputs: move a produced ``.json`` next to the CPER,
  and route a produced ``.cpad`` through the policy engine and (on approval)
  the submitter.

Usage (standalone):
    python Demos/RasApi/analysis_orchestrator.py --analyze \
        --cper-dir ras_demo_output/cper_storage
"""

import sys
import json
import argparse
import subprocess
import shutil
import logging
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from cper_decoder import CperDecoder


# Resolve paths relative to project root (Demos/RasApi/ → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)


def normalize_guid(value: Any) -> str:
    """Normalize a GUID-like value for reliable comparison.

    Accepts a raw string or a cperlib-style dict ({"guid": ...} or
    {"data": ...}) and returns a lowercase, brace/whitespace-stripped string.

    Args:
        value: GUID string or dict containing a GUID.

    Returns:
        Normalized GUID string ('' if value is empty/None).
    """
    if isinstance(value, dict):
        value = value.get('guid') or value.get('data') or ''
    return str(value).strip().strip('{}').strip().lower()


@dataclass
class AnalyzerInfo:
    """Discovery metadata for a single analyzer plugin."""
    name: str
    version: str
    creator_ids: List[str]          # normalized GUIDs this analyzer supports
    prior_days: int                 # days of prior CPER context the analyzer wants
    script_path: Path               # path to the analyzer-<company>.py script


# ═══════════════════════════════════════════════════════════════════════════
# AnalysisOrchestrator — discovers analyzers and routes CPERs to them
# ═══════════════════════════════════════════════════════════════════════════

class AnalysisOrchestrator:
    """Discovers analyzer plugins and routes incoming CPERs to them.

    Responsibilities:
    - At construction, recursively scan the ``analyzers/`` directory for
      ``analyzer-*.py`` scripts, run each with ``--discover``, and build a
      CreatorID → analyzer routing table.
    - For each newly collected CPER (pushed via ``notify_new_cpers``), extract
      its CreatorID/timestamp, select the owning analyzer, gather a directory
      scoped lookback window, and invoke the analyzer with an input file.
    - Collect the analyzer's outputs: move a produced ``.json`` next to the
      CPER, and route a produced ``.cpad`` through the policy engine and
      (on approval) the submitter.

    CPER decoding reuses CperDecoder (cperlib).  Policy evaluation and CPAD
    submission are delegated to injected ``policy_engine`` and ``submitter``.
    """

    ANALYZER_GLOB = "analyzer-*.py"
    DISCOVER_TIMEOUT = 15   # seconds for a --discover call
    RUN_TIMEOUT = 120       # seconds for an analysis run

    def __init__(self, *, platform_id=None, partition_id=None,
                 cper_storage_dir=None, output_dir=None,
                 analyzers_dir=None, policy_engine=None, submitter=None):
        """Initialize the orchestrator and run analyzer discovery.

        Args:
            platform_id:      Platform GUID string.
            partition_id:     Partition GUID string.
            cper_storage_dir: Path where collected CPERs are stored.
            output_dir:       Root output directory (Analyzer_output_files created underneath).
            analyzers_dir:    Directory to scan for analyzer plugins
                              (defaults to Demos/RasApi/analyzers).
            policy_engine:    Optional object exposing evaluate_cpad(json_path) -> bool.
            submitter:        Optional object exposing submit(cpad_path, ...).
        """
        self.platform_id = platform_id
        self.partition_id = partition_id
        self.cper_storage_dir = Path(cper_storage_dir) if cper_storage_dir else None
        self.output_dir = Path(output_dir) if output_dir else None
        self.analyzer_output_dir = self.output_dir / "Analyzer_output_files" if self.output_dir else None

        if analyzers_dir:
            self.analyzers_dir = Path(analyzers_dir)
        else:
            self.analyzers_dir = Path(__file__).resolve().parent / "analyzers"

        self.policy_engine = policy_engine
        self.submitter = submitter

        # Discovery results
        self.analyzers: List[AnalyzerInfo] = []
        self.analyzer_by_creator: Dict[str, AnalyzerInfo] = {}
        self.discovery_error: Optional[str] = None

        self._discover_analyzers()

    # ─── Analyzer Discovery ─────────────────────────────────────────────

    def _discover_analyzers(self):
        """Scan analyzers_dir recursively, run --discover, and build maps.

        On any fatal condition (directory missing, no analyzers, CreatorID
        conflict), sets self.discovery_error and leaves the maps as built so
        far.  Does not raise — print_discovery_report() reports the outcome.
        """
        self.analyzers = []
        self.analyzer_by_creator = {}
        self.discovery_error = None

        if not self.analyzers_dir.exists():
            self.discovery_error = (
                f"Analyzer directory does not exist:\n"
                f"   {self.analyzers_dir}\n"
                f"   Expected analyzer scripts matching '{self.ANALYZER_GLOB}' "
                f"under this directory (including subdirectories)."
            )
            return

        scripts = sorted(self.analyzers_dir.rglob(self.ANALYZER_GLOB))
        if not scripts:
            self.discovery_error = self._no_analyzers_message()
            return

        for script in scripts:
            info = self._discover_one(script)
            if info is None:
                continue

            # Enforce single-owner-per-CreatorID before registering.
            for creator_id in info.creator_ids:
                existing = self.analyzer_by_creator.get(creator_id)
                if existing is not None:
                    self.discovery_error = (
                        f"CreatorID ownership conflict for '{creator_id}':\n"
                        f"   - {existing.name}  ({existing.script_path})\n"
                        f"   - {info.name}  ({info.script_path})\n"
                        f"   Each CreatorID must be owned by exactly one analyzer."
                    )
                    return

            self.analyzers.append(info)
            for creator_id in info.creator_ids:
                self.analyzer_by_creator[creator_id] = info

        if not self.analyzers:
            self.discovery_error = (
                f"{self._no_analyzers_message()}\n"
                f"   (Candidate scripts were found, but none returned valid "
                f"--discover JSON.)"
            )

    def _no_analyzers_message(self) -> str:
        """Build the standard 'no analyzers found' message."""
        return (
            f"No analyzers could be found.\n"
            f"   Searched (recursively): {self.analyzers_dir}\n"
            f"   Filename pattern:       {self.ANALYZER_GLOB}"
        )

    def _discover_one(self, script: Path) -> Optional[AnalyzerInfo]:
        """Run ``<script> --discover`` and validate its JSON descriptor.

        Returns an AnalyzerInfo, or None if the script could not be run or
        produced an invalid descriptor (a warning is printed in that case).
        """
        try:
            proc = subprocess.run(
                [sys.executable, str(script), "--discover"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.DISCOVER_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"   ⚠️  {script.name}: --discover timed out — skipping")
            return None
        except Exception as e:
            print(f"   ⚠️  {script.name}: could not run --discover ({e}) — skipping")
            return None

        if proc.returncode != 0:
            err = proc.stderr.decode('utf-8', errors='replace').strip()
            print(f"   ⚠️  {script.name}: --discover exited {proc.returncode} "
                  f"({err}) — skipping")
            return None

        raw = proc.stdout.decode('utf-8', errors='replace').strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"   ⚠️  {script.name}: --discover did not emit valid JSON "
                  f"({e}) — skipping")
            return None

        return self._validate_descriptor(script, data)

    def _validate_descriptor(self, script: Path, data: Any) -> Optional[AnalyzerInfo]:
        """Validate a discovery descriptor and convert it to an AnalyzerInfo."""
        def reject(reason: str):
            print(f"   ⚠️  {script.name}: invalid discovery descriptor "
                  f"({reason}) — skipping")
            return None

        if not isinstance(data, dict):
            return reject("not a JSON object")

        name = data.get('analyzer_name')
        if not isinstance(name, str) or not name.strip():
            return reject("missing 'analyzer_name'")

        version = data.get('analyzer_version', 'unknown')

        creator_ids = data.get('creator_ids')
        if not isinstance(creator_ids, list) or not creator_ids:
            return reject("'creator_ids' must be a non-empty list")
        normalized = [normalize_guid(c) for c in creator_ids]
        normalized = [c for c in normalized if c]
        if not normalized:
            return reject("'creator_ids' contained no valid GUIDs")

        prior_days = data.get('prior_days')
        if isinstance(prior_days, bool) or not isinstance(prior_days, int) or prior_days < 0:
            return reject("'prior_days' must be a non-negative integer")

        return AnalyzerInfo(
            name=name.strip(),
            version=str(version),
            creator_ids=normalized,
            prior_days=prior_days,
            script_path=script,
        )

    # ─── Discovery Report ───────────────────────────────────────────────

    def print_discovery_report(self) -> bool:
        """Print the discovery outcome (table or error) at demo startup.

        Returns:
            True if at least one analyzer was discovered with no fatal error;
            False otherwise (caller should stop).
        """
        print("\n" + "=" * 80)
        print("\t\t\t\tANALYZER DISCOVERY")
        print("=" * 80)
        print(f"\n   Searched: {self.analyzers_dir}")
        print(f"   Pattern:  {self.ANALYZER_GLOB} (recursive)")

        if self.discovery_error:
            print("\n   ❌ Analyzer discovery failed:\n")
            for line in self.discovery_error.splitlines():
                print(f"   {line}")
            print()
            return False

        print(f"\n   ✅ Discovered {len(self.analyzers)} analyzer(s):\n")
        self._print_analyzer_table()
        return True

    def _print_analyzer_table(self):
        """Render a table of discovered analyzers."""
        rows = [("Analyzer", "Version", "CreatorIDs", "Prior Days")]
        for info in self.analyzers:
            rows.append((
                info.name,
                info.version,
                ", ".join(info.creator_ids),
                str(info.prior_days),
            ))

        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]

        def fmt(row):
            return "   " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

        header = fmt(rows[0])
        print(header)
        print("   " + "-" * (len(header) - 3))
        for row in rows[1:]:
            print(fmt(row))
        print()

    # ─── CPER Orchestration (explicit push) ─────────────────────────────

    def notify_new_cpers(self, cper_paths: List[str]):
        """Process newly collected CPERs, in the order received.

        This is the explicit-push entry point: the collection step calls it
        with the paths of the CPERs it just wrote.

        Args:
            cper_paths: CPER file paths in arrival order.
        """
        print("\n" + "=" * 80)
        print("\t\t\t\tANALYZE CPERs")
        print("=" * 80)

        print("\n   ℹ️  The Analysis Orchestrator (AO) is vendor-agnostic. It never interprets a")
        print("      CPER's contents — it reads only the header to find the CreatorID, then")
        print("      routes the CPER to the vendor analyzer that owns that CreatorID. This is")
        print("      the core RAS API abstraction: one pipeline, many vendors' hardware.")

        if self.discovery_error:
            print("\n   ❌ No analyzers available — cannot analyze CPERs.")
            return

        if not cper_paths:
            print("\n   ⚠️  No new CPERs to analyze.")
            return

        for cper_path in cper_paths:
            try:
                self._process_cper(Path(cper_path))
            except Exception as e:
                logger.error(f"Error processing CPER {cper_path}: {e}")
                print(f"\n   ❌ Error processing {cper_path}: {e}")

    def _process_cper(self, cper_path: Path):
        """Route a single CPER to its analyzer and handle the outputs."""
        cper_path = cper_path.resolve()
        if not cper_path.exists():
            print(f"\n   ⚠️  CPER not found: {cper_path}")
            return

        decoder = self._make_decoder()
        cper_data = decoder.extract_cper_data(str(cper_path))
        if not cper_data:
            print(f"\n   ⚠️  Could not decode CPER: {cper_path.name}")
            return

        header = cper_data.get('header', {})
        creator_id = normalize_guid(header.get('creatorID'))
        platform_id = normalize_guid(header.get('platformID'))
        partition_id = normalize_guid(header.get('partitionID'))
        timestamp = self._cper_timestamp(cper_path, header)

        analyzer = self.analyzer_by_creator.get(creator_id)
        if analyzer is None:
            self._print_no_analyzer_error(
                cper_path, timestamp, creator_id, platform_id, partition_id)
            return

        print(f"\n{'─' * 80}")
        print(f"📋 CPER: {cper_path.name}")

        print(f"\n   Step 1 — Read the CPER header (the only part the AO decodes)")
        print(f"   ✓ Creator ID:  {creator_id}")
        print(f"   ✓ Platform ID: {platform_id or '(none)'}")
        print(f"   ✓ Timestamp:   {timestamp.isoformat()}")

        print(f"\n   Step 2 — Route by CreatorID")
        print(f"   ✓ Owning analyzer: {analyzer.name} (the AO matched the CreatorID to a")
        print(f"     discovered analyzer plugin; an unknown CreatorID would be rejected here)")

        print(f"\n   Step 3 — Build the lookback window")
        print(f"   The analyzer asked for prior_days={analyzer.prior_days} of history so it can")
        print(f"   recognize a fault that repeats at the same location. The AO gathers")
        print(f"   same-CreatorID CPERs in that window and hands them to the analyzer")
        print(f"   (it does not analyze them itself).")
        window = self._build_lookback(cper_path, analyzer.prior_days, timestamp)
        print(f"   ✓ Window: {len(window)} CPER(s) within {analyzer.prior_days} day(s)  (newest first)")

        input_file = self._write_input_file(
            cper_path, creator_id, timestamp, analyzer.prior_days, window)

        # Clear stale outputs so anything present after the run is this run's.
        self._clear_outputs(analyzer.script_path.parent)

        print(f"\n   Step 4 — Hand off to the vendor analyzer")
        if not self._run_analyzer(analyzer, input_file):
            return

        self._handle_outputs(analyzer.script_path.parent, cper_path)

    def _print_no_analyzer_error(self, cper_path, timestamp, creator_id,
                                 platform_id, partition_id):
        """Print a hard-to-ignore error when no analyzer owns a CreatorID."""
        print("\n" + "!" * 80)
        print("   ❌  NO ANALYZER FOR CPER — SKIPPING")
        print("!" * 80)
        print(f"   CPER:         {cper_path.name}")
        print(f"   Timestamp:    {timestamp.isoformat()}")
        print(f"   Creator ID:   {creator_id or '(none)'}")
        print(f"   Platform ID:  {platform_id or '(none)'}")
        print(f"   Partition ID: {partition_id or '(none)'}")
        print("!" * 80)

    # ─── Lookback Window ────────────────────────────────────────────────

    def _build_lookback(self, cper_path: Path, prior_days: int,
                        current_ts: datetime) -> List[str]:
        """Build the directory-scoped lookback CPER list (newest first).

        Only CPERs in the same directory as the triggering CPER are considered
        (all share the same CreatorID by construction).  Includes CPERs whose
        timestamp falls in the inclusive range [current_ts - prior_days,
        current_ts].  The triggering CPER is always first.

        Args:
            cper_path:  The newly arrived CPER (already resolved).
            prior_days: Days of history the owning analyzer requested.
            current_ts: Timestamp of the triggering CPER.

        Returns:
            CPER paths ordered by descending timestamp, newest (triggering) first.
        """
        directory = cper_path.parent
        window_start = current_ts - timedelta(days=prior_days)
        decoder = self._make_decoder()

        entries: List[tuple] = []
        for candidate in directory.glob("*.cper"):
            candidate = candidate.resolve()
            if candidate == cper_path:
                ts = current_ts
            else:
                data = decoder.extract_cper_data(str(candidate))
                header = data.get('header', {}) if data else {}
                ts = self._cper_timestamp(candidate, header)
            if window_start <= ts <= current_ts:
                entries.append((ts, candidate))

        # Newest first.
        entries.sort(key=lambda e: e[0], reverse=True)
        paths = [str(p) for _, p in entries]

        # Guarantee the triggering CPER is element 0 even if timestamps tie.
        trigger = str(cper_path)
        if trigger in paths:
            paths.remove(trigger)
        paths.insert(0, trigger)
        return paths

    def _cper_timestamp(self, cper_path: Path, header: Dict[str, Any]) -> datetime:
        """Return a CPER's timestamp, falling back to filesystem mtime.

        Header timestamps are normalized to naive datetimes so all comparisons
        are consistent.  On an unparseable header timestamp, a warning is
        emitted and the file's modification time is used instead.
        """
        parsed = self._parse_timestamp(header.get('timestamp'))
        if parsed is not None:
            return parsed
        print(f"   ⚠️  Unparseable timestamp in {cper_path.name} — "
              f"ordering by filesystem mtime")
        return datetime.fromtimestamp(cper_path.stat().st_mtime)

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        """Parse an ISO-8601 timestamp into a naive datetime, or None."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
        # Drop tzinfo so naive (mtime) and aware (header) values compare cleanly.
        return dt.replace(tzinfo=None)

    # ─── Analyzer Invocation ────────────────────────────────────────────

    def _write_input_file(self, cper_path: Path, creator_id: str,
                          timestamp: datetime, prior_days: int,
                          window: List[str]) -> Path:
        """Write the AO → analyzer input file and return its path."""
        self.analyzer_output_dir.mkdir(parents=True, exist_ok=True)
        input_path = self.analyzer_output_dir / f"{cper_path.stem}_input.json"
        payload = {
            "creator_id": creator_id,
            "newest_cper": str(cper_path),
            "newest_timestamp": timestamp.isoformat(),
            "prior_days": prior_days,
            "cper_files": window,  # newest first
        }
        with open(input_path, "w") as f:
            json.dump(payload, f, indent=2)
        return input_path

    def _clear_outputs(self, directory: Path):
        """Delete pre-existing .json/.cpad files from an analyzer's directory."""
        for pattern in ("*.json", "*.cpad"):
            for stale in directory.glob(pattern):
                try:
                    stale.unlink()
                except OSError as e:
                    print(f"   ⚠️  Could not remove stale output {stale.name}: {e}")

    def _run_analyzer(self, analyzer: AnalyzerInfo, input_file: Path) -> bool:
        """Invoke an analyzer with --input-file and wait for completion.

        Returns:
            True if the analyzer exited 0, False otherwise.
        """
        print(f"   🛠️  Running {analyzer.name}...")
        try:
            proc = subprocess.run(
                [sys.executable, str(analyzer.script_path),
                 "--input-file", str(input_file)],
                timeout=self.RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"   ❌ {analyzer.name} timed out after {self.RUN_TIMEOUT}s")
            return False
        except Exception as e:
            print(f"   ❌ Could not run {analyzer.name}: {e}")
            return False

        if proc.returncode != 0:
            print(f"   ❌ {analyzer.name} exited with code {proc.returncode}")
            return False
        return True

    # ─── Output Handling ────────────────────────────────────────────────

    def _handle_outputs(self, analyzer_dir: Path, cper_path: Path):
        """Collect analyzer outputs and route them.

        - A produced .json is moved next to the triggering CPER.
        - A produced .cpad is moved next to the triggering CPER (same place as
          the JSON), then routed through the policy engine and (on approval)
          the submitter.  Moving (rather than copying) avoids leaving build
          artifacts in the analyzer's source directory.
        """
        dest_dir = cper_path.parent
        json_outputs = sorted(analyzer_dir.glob("*.json"))
        cpad_outputs = sorted(analyzer_dir.glob("*.cpad"))

        print(f"\n   Step 5 — Collect and store the analyzer's outputs")
        moved_json: Optional[Path] = None
        for produced in json_outputs:
            dest = dest_dir / produced.name
            shutil.move(str(produced), str(dest))
            moved_json = dest
            print(f"   📄 Analysis JSON → {dest}")

        if not cpad_outputs:
            return

        for produced in cpad_outputs:
            dest = dest_dir / produced.name
            shutil.move(str(produced), str(dest))
            print(f"   📦 CPAD         → {dest}")
            print(f"   A CPAD is a *proposed RAS action*. The analyzer recommends it, but it does")
            print(f"   not act on its own — it must clear policy before anything happens.")
            self._policy_and_submit(cpad_binary=dest, cpad_json=moved_json)

    def _policy_and_submit(self, *, cpad_binary: Path, cpad_json: Optional[Path]):
        """Evaluate a CPAD against policy and, on approval, submit it."""
        print("\n" + "=" * 80)
        print("\t\t\t\tPOLICY CHECK")
        print("=" * 80)

        print("\n   The Server Fleet Operator's policy engine decides whether a proposed action")
        print("   is allowed. It inspects only the CPAD's decoded header and section")
        print("   descriptors (IDs, action type, FRU/target, severity) — never the CPAD")
        print("   section body. That keeps proprietary vendor data opaque to the operator")
        print("   while still allowing fleet-wide policy (rate limits, maintenance windows,")
        print("   blast-radius rules) to gate the action.")

        allowed = True
        if self.policy_engine is not None and cpad_json is not None:
            allowed = self.policy_engine.evaluate_cpad(str(cpad_json))
        elif self.policy_engine is not None:
            print("\n   ⚠️  No CPAD JSON available to evaluate — denying by default.")
            allowed = False
        else:
            print("\n   ⓘ No policy engine configured — skipping policy check.")

        if not allowed:
            print("\n   ❌ Policy denied — the SPPR CPAD will not be submitted.")
            return

        print("\n   ✅ Policy allowed — the SPPR CPAD may be submitted.")

        print("\n" + "=" * 80)
        print("\t\t\t\tSUBMIT CPAD")
        print("=" * 80)

        print("\n   Submitting sends the CPAD back to the endpoint, which triggers the actual")
        print("   RAS action (SPPR) on the hardware — closing the detect → analyze → act loop.")

        if self.submitter is None:
            print("\n   ⓘ No submitter configured — skipping submission.")
            return

        self.submitter.submit(
            str(cpad_binary), verbose_steps=True,
            source_label="Analyzer-generated SPPR CPAD")

    # ─── Helpers ────────────────────────────────────────────────────────

    def _make_decoder(self) -> CperDecoder:
        """Create a CperDecoder used only for cperlib decoding during routing."""
        return CperDecoder(verbose=False)

    # ─── Backward-compatible entry point ────────────────────────────────

    def analyze_cpers(self):
        """Analyze all CPERs in this platform/partition directory.

        Convenience entry point (used by the CLI and standalone callers):
        gathers the stored CPERs and routes them through notify_new_cpers in
        timestamp order.
        """
        if not (self.cper_storage_dir and self.platform_id and self.partition_id):
            print("\n⚠️  cper_storage_dir/platform_id/partition_id not configured")
            return

        base_dir = self.cper_storage_dir / self.platform_id / self.partition_id
        if not base_dir.exists():
            print(f"\n⚠️  No CPER directory found at {base_dir}")
            return

        cper_files = sorted(base_dir.glob("*.cper"))
        if not cper_files:
            print(f"\n⚠️  No CPER files found in {base_dir}")
            return

        self.notify_new_cpers([str(f) for f in cper_files])


# ─── CLI Entry Point ────────────────────────────────────────────────────

def main():
    """Command-line interface for standalone CPER orchestration."""
    parser = argparse.ArgumentParser(
        description='Analysis Orchestrator — discover analyzers and route CPERs to them',
        epilog='Examples:\n'
               '  python Demos/RasApi/analysis_orchestrator.py --analyze --cper-dir ras_demo_output/cper_storage\n',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--analyze', action='store_true',
                        help='Analyze collected CPER files via the orchestrator')
    parser.add_argument('--cper-dir',
                        help='Directory containing CPER storage (platform/partition tree)')
    parser.add_argument('--output-dir',
                        help='Output directory for analysis files')
    parser.add_argument('--platform-id',
                        default='990f8820-bd4d-5064-58cc-961a053dea79',
                        help='Platform GUID')
    parser.add_argument('--partition-id',
                        default='22222222-3333-4444-5555-666666666666',
                        help='Partition GUID')

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    default_output = script_dir / "ras_demo_output"

    output_dir = Path(args.output_dir) if args.output_dir else default_output
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    cper_storage_dir = Path(args.cper_dir) if args.cper_dir else output_dir / "cper_storage"
    if not cper_storage_dir.is_absolute():
        cper_storage_dir = PROJECT_ROOT / cper_storage_dir

    orch = AnalysisOrchestrator(
        platform_id=args.platform_id,
        partition_id=args.partition_id,
        cper_storage_dir=str(cper_storage_dir),
        output_dir=str(output_dir),
    )

    if not orch.print_discovery_report():
        sys.exit(1)
    orch.analyze_cpers()


if __name__ == "__main__":
    main()
