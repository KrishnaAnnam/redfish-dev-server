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

Standalone module — no server dependencies.  Decodes local binary CPADs and
evaluates them against local JSON policy tables.

Usage (standalone):
    python examples/ras_api_demo/policy.py path/to/action.cpad
    python examples/ras_api_demo/policy.py --creators c.json --actions a.json action.cpad

Usage (from orchestrator):
    from policy import PolicyEngine
    engine = PolicyEngine()
    decision = engine.evaluate_cpad("path/to/action.cpad")
    if decision.allowed:
        ...
"""

import sys
import json
import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cper_decoder import CperDecoder

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
class PolicySectionDecision:
    """The policy outcome for one CPAD section."""

    section_index: int
    allowed: bool
    action_id: str
    action_name: Optional[str]
    fru_id: str
    fru_text: str
    confidence: int
    urgency: bool
    prioritized: bool = False
    threshold: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class PolicyDecision:
    """The outcome of evaluating one CPAD against policy."""

    allowed: bool
    reason: Optional[str] = None          # denial reason (None when allowed)
    creator_id: str = ""
    platform_id: str = ""
    action_id: str = ""
    action_name: Optional[str] = None
    fru_id: str = ""
    fru_text: str = ""
    confidence: int = 0
    urgency: bool = False
    prioritized: bool = False
    threshold: Optional[int] = None       # applied confidence threshold (None if not gated)
    section_decisions: List[PolicySectionDecision] = field(
        default_factory=list)
    # Platform Action codes to stamp on the rejection CPER (only used on deny).
    return_code: int = EFI_PLATFORM_ACTION_RETURN_CODE_POLICY_REJECTED
    reason_code: int = EFI_PLATFORM_ACTION_REASON_CODE_NONE

    def __bool__(self) -> bool:
        return self.allowed


class PolicyEngine:
    """Table-driven policy engine for evaluating CPAD actions.

    Loads a trusted-creator table and an action table (indexed by CreatorID and
    ActionID) from JSON files, then evaluates each CPAD's header and section
    descriptors against them. It never interprets the opaque CPAD section body.
    """

    def __init__(self, creators_path=None, actions_path=None, verbose=True,
                 decoder=None):
        """Initialize the policy engine and load the policy tables.

        Args:
            creators_path: Path to the trusted-creator table JSON
                           (defaults to policy_tables/creators.json).
            actions_path:  Path to the action table JSON
                           (defaults to policy_tables/actions.json).
            verbose:       Whether to display detailed output.
            decoder:       Optional binary CPAD decoder for dependency
                           injection; defaults to CperDecoder.
        """
        self.verbose = verbose
        self.creators_path = Path(creators_path) if creators_path else DEFAULT_CREATORS_PATH
        self.actions_path = Path(actions_path) if actions_path else DEFAULT_ACTIONS_PATH
        self.creators = self._load_table(self.creators_path)
        self.actions = self._load_table(self.actions_path)
        self.decoder = decoder or CperDecoder(verbose=False)

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
        """Evaluate a binary CPAD file against the policy tables.

        Args:
            cpad_file_path: Path to the binary CPAD file.

        Returns:
            PolicyDecision: allowed/denied plus the reason and the codes to
            stamp on a rejection CPER.  (Truthy when allowed.)
        """
        cpad_path = Path(cpad_file_path)
        if not cpad_path.exists():
            return PolicyDecision(False, reason=f"CPAD file not found: {cpad_path}")

        cpad_data = self.decoder.extract_cpad_data(str(cpad_path))
        if not isinstance(cpad_data, dict):
            return PolicyDecision(
                False, reason=f"Could not decode binary CPAD: {cpad_path}")

        header = cpad_data.get("header", {})
        creator_id = self._normalize_guid(header.get("creatorID", ""))
        platform_id = self._normalize_guid(header.get("platformID", ""))
        partition_id = self._normalize_guid(header.get("partitionID", ""))
        section_descs = cpad_data.get("sectionDescriptors", [])
        if not section_descs:
            return PolicyDecision(
                False, reason="CPAD contains no section descriptors",
                creator_id=creator_id, platform_id=platform_id)
        try:
            header_urgency = self._parse_urgency(
                header.get("urgency"), "CPAD header urgency")
        except ValueError as exc:
            return PolicyDecision(
                False,
                reason=str(exc),
                creator_id=creator_id,
                platform_id=platform_id,
            )

        if self.verbose:
            print(f"\n   📋 CPAD File: {cpad_path.name}")
            print(f"\n   Platform ID:  {platform_id}")
            print(f"   Partition ID: {partition_id}")
            print(f"   Creator ID:   {creator_id}")
            print(f"   Sections:     {len(section_descs)}")
            print(f"   Urgency:      "
                  f"{'Urgent' if header_urgency else 'Not urgent'}")
            print(f"\n🔍 Evaluating against policy tables...")

        creator = self.creators.get(creator_id)
        if not creator or not creator.get("trusted", False):
            return PolicyDecision(
                False,
                reason=f"Creator {creator_id} is not a trusted creator",
                creator_id=creator_id,
                platform_id=platform_id,
                urgency=header_urgency,
            )
        if self.verbose:
            print(f"\n   Rule 1: Creator trusted — {creator.get('name', creator_id)}")

        section_decisions = [
            self._evaluate_section(
                index, descriptor, creator_id, platform_id, header_urgency)
            for index, descriptor in enumerate(section_descs)
        ]
        if any(item.urgency for item in section_decisions) != header_urgency:
            return self._decision_from_sections(
                False,
                "CPAD header urgency must equal the aggregate section urgency",
                creator_id,
                platform_id,
                header_urgency,
                section_decisions,
            )
        denied = next(
            (item for item in section_decisions if not item.allowed), None)
        if denied is not None:
            return self._decision_from_sections(
                False,
                f"section {denied.section_index}: {denied.reason}",
                creator_id,
                platform_id,
                header_urgency,
                section_decisions,
            )

        if self.verbose:
            for item in section_decisions:
                if not item.urgency:
                    continue
                print(
                    "\n⚡ Prioritizing approved urgent action\n"
                    f"   Action: {item.action_name} ({item.action_id})\n"
                    f"   FRU Text: {item.fru_text}\n"
                    f"   FRU ID: {item.fru_id}"
                )
            print(f"\n{'─' * 80}")
            print(f"✅ Policy Evaluation: APPROVED — {cpad_path.name}")
            print(f"{'─' * 80}")
        return self._decision_from_sections(
            True, None, creator_id, platform_id, header_urgency,
            section_decisions)

    def _evaluate_section(
            self,
            section_index: int,
            descriptor: Dict[str, Any],
            creator_id: str,
            platform_id: str,
            header_urgency: bool) -> PolicySectionDecision:
        action_id = self._normalize_action_id(
            self._extract_action_id([descriptor]))
        confidence = descriptor.get("confidence", 0) or 0
        fru_id = self._normalize_guid(descriptor.get("fruID", ""))
        fru_text = str(descriptor.get("fruText", "")).strip()
        try:
            urgency = self._parse_urgency(
                descriptor.get("urgency", int(header_urgency)),
                f"CPAD section {section_index} urgency",
            )
        except ValueError as exc:
            return PolicySectionDecision(
                section_index, False, action_id, None, fru_id, fru_text,
                confidence, False, reason=str(exc))
        if not fru_id or not fru_text:
            return PolicySectionDecision(
                section_index, False, action_id, None, fru_id, fru_text,
                confidence, urgency,
                reason="section descriptor must contain FRU ID and FRU text")

        action = self.actions.get(creator_id, {}).get(action_id)
        action_name = action.get("name", action_id) if action else None
        threshold = action.get("confidence_threshold") if action else None
        reason = None
        if action is None:
            reason = (
                f"Action {action_id} is not defined for creator {creator_id}")
        elif not action.get("permitted", False):
            reason = f"Action '{action_name}' is not permitted"
        elif platform_id not in [
                self._normalize_guid(value)
                for value in action.get("supported_platforms", [])]:
            reason = (
                f"Platform {platform_id} is not supported for '{action_name}'")
        elif threshold is not None and confidence < threshold:
            reason = (
                f"Confidence {confidence} is below threshold {threshold}")
        else:
            urgency_policy = action.get("urgency_policy", "any")
            if urgency_policy not in {
                    "any", "urgent_only", "non_urgent_only"}:
                reason = (
                    f"Action '{action_name}' has invalid urgency_policy "
                    f"{urgency_policy!r}")
            elif urgency_policy == "urgent_only" and not urgency:
                reason = (
                    f"Action '{action_name}' requires an urgent recommendation")
            elif urgency_policy == "non_urgent_only" and urgency:
                reason = (
                    f"Action '{action_name}' does not permit urgent "
                    "recommendations")
        if self.verbose:
            print(
                f"   Section {section_index}: {action_name or action_id}; "
                f"FRU {fru_text} ({fru_id}); confidence {confidence}; "
                f"{'urgent' if urgency else 'not urgent'}"
            )
        allowed = reason is None
        return PolicySectionDecision(
            section_index=section_index,
            allowed=allowed,
            action_id=action_id,
            action_name=action_name,
            fru_id=fru_id,
            fru_text=fru_text,
            confidence=confidence,
            urgency=urgency,
            prioritized=allowed and urgency,
            threshold=threshold,
            reason=reason,
        )

    @staticmethod
    def _decision_from_sections(
            allowed: bool,
            reason: Optional[str],
            creator_id: str,
            platform_id: str,
            urgency: bool,
            sections: List[PolicySectionDecision]) -> PolicyDecision:
        first = sections[0]
        return PolicyDecision(
            allowed=allowed,
            reason=reason,
            creator_id=creator_id,
            platform_id=platform_id,
            action_id=first.action_id,
            action_name=first.action_name,
            fru_id=first.fru_id,
            fru_text=first.fru_text,
            confidence=first.confidence,
            urgency=urgency,
            prioritized=allowed and any(
                section.prioritized for section in sections),
            threshold=first.threshold,
            section_decisions=sections,
        )

    def evaluate_multiple_cpads(self, cpad_files) -> List[Tuple[Any, "PolicyDecision"]]:
        """Evaluate multiple CPAD files; returns [(path, PolicyDecision), ...]."""
        return [(f, self.evaluate_cpad(f)) for f in cpad_files]

    # ─── Internal Helpers ───────────────────────────────────────────────

    def _deny(self, creator_id, platform_id, action_id, action_name,
              confidence, threshold, reason, fru_text="",
              urgency=False) -> "PolicyDecision":
        """Build (and, if verbose, print) a DENIED decision."""
        if self.verbose:
            print(f"\n{'─' * 80}")
            print(f"❌ Policy Evaluation: DENIED — {reason}")
            print(f"{'─' * 80}")
        return PolicyDecision(False, reason=reason, creator_id=creator_id,
                              platform_id=platform_id, action_id=action_id,
                              action_name=action_name, fru_text=fru_text,
                              confidence=confidence, urgency=urgency,
                              threshold=threshold)

    @staticmethod
    def _parse_urgency(value, field_name) -> bool:
        """Parse a decoded CPAD urgency field as a strict binary value."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        raise ValueError(f"{field_name} must be 0 or 1")

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
    parser.add_argument(
        "cpad_files", nargs="+", help="Binary CPAD file(s) to evaluate")
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
