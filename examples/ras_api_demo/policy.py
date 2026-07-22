#!/usr/bin/env python3
"""
RAS Policy Engine
=================

Table-driven policy engine.  Evaluates a CPAD (a *proposed* RAS action) against
two operator-owned tables loaded from JSON files and returns an allow/deny
decision with the reason.

Tables (see ``policy_tables/`` and POLICY_ENGINE.md):
  * creators.json  — CreatorID -> {name, trusted}
  * actions.json   — CreatorID -> ActionID -> {name, permitted,
                     [confidence_threshold], supported_platforms}

Standalone module — no server dependencies.  Operates on local JSON files.

Usage (standalone):
    python examples/ras_api_demo/policy.py path/to/cpad.json
    python examples/ras_api_demo/policy.py --creators c.json --actions a.json cpad.json

Usage (from orchestrator):
    from policy import PolicyEngine
    engine = PolicyEngine()
    decision = engine.evaluate_cpad("path/to/cpad.json")
    if decision.allowed:
        ...
"""

import sys
import json
import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Platform Action return/reason codes for a policy rejection, from
# src/plugins/ras/libcper/include/libcper/Cper.h.  When a CPAD is denied, the
# orchestrator mints a Platform Action CPER carrying these codes.
EFI_PLATFORM_ACTION_RETURN_CODE_POLICY_REJECTED = 0x03
EFI_PLATFORM_ACTION_REASON_CODE_NONE = 0x00

# Default table locations (alongside this module).
_TABLES_DIR = Path(__file__).resolve().parent / "policy_tables"
DEFAULT_CREATORS_PATH = _TABLES_DIR / "creators.json"
DEFAULT_ACTIONS_PATH = _TABLES_DIR / "actions.json"


@dataclass
class PolicyDecision:
    """The outcome of evaluating one CPAD against policy."""

    allowed: bool
    reason: Optional[str] = None          # denial reason (None when allowed)
    creator_id: str = ""
    platform_id: str = ""
    action_id: str = ""
    action_name: Optional[str] = None
    confidence: int = 0
    threshold: Optional[int] = None       # applied confidence threshold (None if not gated)
    # Platform Action codes to stamp on the rejection CPER (only used on deny).
    return_code: int = EFI_PLATFORM_ACTION_RETURN_CODE_POLICY_REJECTED
    reason_code: int = EFI_PLATFORM_ACTION_REASON_CODE_NONE

    def __bool__(self) -> bool:
        return self.allowed


class PolicyEngine:
    """Table-driven policy engine for evaluating CPAD actions.

    Loads a trusted-creator table and an action table (indexed by CreatorID and
    ActionID) from JSON files, then evaluates each CPAD's header and section
    descriptors against them.  It never inspects the opaque CPAD section body.
    """

    def __init__(self, creators_path=None, actions_path=None, verbose=True):
        """Initialize the policy engine and load the policy tables.

        Args:
            creators_path: Path to the trusted-creator table JSON
                           (defaults to policy_tables/creators.json).
            actions_path:  Path to the action table JSON
                           (defaults to policy_tables/actions.json).
            verbose:       Whether to display detailed output.
        """
        self.verbose = verbose
        self.creators_path = Path(creators_path) if creators_path else DEFAULT_CREATORS_PATH
        self.actions_path = Path(actions_path) if actions_path else DEFAULT_ACTIONS_PATH
        self.creators = self._load_table(self.creators_path)
        self.actions = self._load_table(self.actions_path)

    @staticmethod
    def _load_table(path):
        """Load and parse a policy table JSON file (raises on error)."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Policy table not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in policy table {path}: {e}")
        if not isinstance(data, dict):
            raise ValueError(f"Policy table {path} must be a JSON object")
        return data

    # ─── Public API ─────────────────────────────────────────────────────

    def evaluate_cpad(self, cpad_file_path) -> "PolicyDecision":
        """Evaluate a CPAD JSON file against the policy tables.

        Args:
            cpad_file_path: Path to the CPAD JSON file.

        Returns:
            PolicyDecision: allowed/denied plus the reason and the codes to
            stamp on a rejection CPER.  (Truthy when allowed.)
        """
        cpad_path = Path(cpad_file_path)
        if not cpad_path.exists():
            return PolicyDecision(False, reason=f"CPAD file not found: {cpad_path}")

        try:
            with open(cpad_path, "r") as f:
                cpad_data = json.load(f)
        except json.JSONDecodeError as e:
            return PolicyDecision(False, reason=f"Invalid JSON in CPAD file: {e}")

        header = cpad_data.get("header", {})
        creator_id = self._normalize_guid(header.get("creatorID", ""))
        platform_id = self._normalize_guid(header.get("platformID", ""))
        partition_id = self._normalize_guid(header.get("partitionID", ""))

        section_descs = cpad_data.get("sectionDescriptors", [])
        # Confidence lives on the section descriptor — the standard CPAD location.
        confidence = (section_descs[0].get("confidence", 0) if section_descs else 0) or 0
        action_id = self._normalize_action_id(self._extract_action_id(section_descs))
        fru_text = section_descs[0].get("fruText", "Unknown") if section_descs else "Unknown"

        if self.verbose:
            print(f"\n   📋 CPAD File: {cpad_path.name}")
            print(f"\n   Platform ID:  {platform_id}")
            print(f"   Partition ID: {partition_id}")
            print(f"   Creator ID:   {creator_id}")
            print(f"   Action ID:    {action_id}")
            print(f"   FRU:          {fru_text}")
            print(f"   Confidence:   {confidence}")
            print(f"\n🔍 Evaluating against policy tables...")

        # Rule 1 — Creator trust (creators.json).
        creator = self.creators.get(creator_id)
        if not creator or not creator.get("trusted", False):
            return self._deny(creator_id, platform_id, action_id, None, confidence, None,
                              f"Creator {creator_id} is not a trusted creator")
        if self.verbose:
            print(f"\n   Rule 1: Creator trusted — {creator.get('name', creator_id)}")

        # Rule 2 — Action is known for this creator (actions.json[creator][action]).
        action = self.actions.get(creator_id, {}).get(action_id)
        if action is None:
            return self._deny(creator_id, platform_id, action_id, None, confidence, None,
                              f"Action {action_id} is not defined for creator {creator_id}")
        action_name = action.get("name", action_id)
        if self.verbose:
            print(f"   Rule 2: Action known — {action_name}")

        # Rule 3 — Action permitted.
        if not action.get("permitted", False):
            return self._deny(creator_id, platform_id, action_id, action_name, confidence, None,
                              f"Action '{action_name}' is not permitted")
        if self.verbose:
            print(f"   Rule 3: Action permitted")

        # Rule 4 — Platform supported for this action.
        supported = [self._normalize_guid(p) for p in action.get("supported_platforms", [])]
        if platform_id not in supported:
            return self._deny(creator_id, platform_id, action_id, action_name, confidence, None,
                              f"Platform {platform_id} is not supported for '{action_name}'")
        if self.verbose:
            print(f"   Rule 4: Platform supported")

        # Rule 5 — Confidence threshold (only when the action defines one).
        threshold = action.get("confidence_threshold")
        if threshold is not None:
            if confidence < threshold:
                return self._deny(creator_id, platform_id, action_id, action_name,
                                  confidence, threshold,
                                  f"Confidence {confidence} is below threshold {threshold}")
            if self.verbose:
                print(f"   Rule 5: Confidence {confidence} >= threshold {threshold}")
        elif self.verbose:
            print(f"   Rule 5: No confidence threshold defined for this action")

        if self.verbose:
            print(f"\n{'─' * 80}")
            print(f"✅ Policy Evaluation: APPROVED — {cpad_path.name}")
            print(f"{'─' * 80}")
        return PolicyDecision(True, creator_id=creator_id, platform_id=platform_id,
                              action_id=action_id, action_name=action_name,
                              confidence=confidence, threshold=threshold)

    def evaluate_multiple_cpads(self, cpad_files) -> List[Tuple[Any, "PolicyDecision"]]:
        """Evaluate multiple CPAD files; returns [(path, PolicyDecision), ...]."""
        return [(f, self.evaluate_cpad(f)) for f in cpad_files]

    # ─── Internal Helpers ───────────────────────────────────────────────

    def _deny(self, creator_id, platform_id, action_id, action_name,
              confidence, threshold, reason) -> "PolicyDecision":
        """Build (and, if verbose, print) a DENIED decision."""
        if self.verbose:
            print(f"\n{'─' * 80}")
            print(f"❌ Policy Evaluation: DENIED — {reason}")
            print(f"{'─' * 80}")
        return PolicyDecision(False, reason=reason, creator_id=creator_id,
                              platform_id=platform_id, action_id=action_id,
                              action_name=action_name, confidence=confidence,
                              threshold=threshold)

    @staticmethod
    def _normalize_guid(value) -> str:
        """Normalize a GUID to a lowercase, brace/whitespace-stripped string."""
        return str(value).strip().strip("{}").strip().lower()

    @staticmethod
    def _normalize_action_id(value) -> str:
        """Normalize an action id to a canonical lowercase '0x....' hex string.

        Accepts an int (0x8001), a hex string ('0x8001'), or a decimal string,
        so JSON- and binary-sourced CPADs match the same table keys.
        """
        if value in (None, ""):
            return ""
        if isinstance(value, int):
            return f"0x{value:04x}"
        s = str(value).strip().lower()
        try:
            n = int(s, 16) if s.startswith("0x") else int(s)
            return f"0x{n:04x}"
        except ValueError:
            return s

    @staticmethod
    def _extract_action_id(section_descs):
        """Extract the action ID from sectionDescriptors, handling multiple formats."""
        if not section_descs:
            return ""
        # JSON CPAD: {"actionId": "0x8001"}
        action_id = section_descs[0].get("actionId")
        if action_id:
            return action_id
        # Binary-derived CPAD: {"actionID": {"code": "0x8001"}} or an int
        action_id_obj = section_descs[0].get("actionID", {})
        if isinstance(action_id_obj, dict):
            return action_id_obj.get("code", "")
        return action_id_obj or ""


# ─── CLI Entry Point ────────────────────────────────────────────────────

def main():
    """Command-line interface for standalone policy evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate CPAD file(s) against the policy tables.")
    parser.add_argument("cpad_files", nargs="+", help="CPAD JSON file(s) to evaluate")
    parser.add_argument("--creators", help="Path to the creators table JSON")
    parser.add_argument("--actions", help="Path to the actions table JSON")
    args = parser.parse_args()

    engine = PolicyEngine(creators_path=args.creators, actions_path=args.actions)

    print("\n" + "=" * 80)
    print("\t\t\t\tPOLICY EVALUATION")
    print("=" * 80)

    all_allowed = True
    for cpad_file in args.cpad_files:
        print(f"\n{'─' * 80}")
        decision = engine.evaluate_cpad(cpad_file)
        if not decision.allowed:
            all_allowed = False

    print("\n" + "=" * 80)
    sys.exit(0 if all_allowed else 1)


if __name__ == "__main__":
    main()
