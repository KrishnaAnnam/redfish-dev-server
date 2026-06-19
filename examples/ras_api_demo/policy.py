#!/usr/bin/env python3
"""
RAS Policy Engine
==================

Evaluates CPAD files against policy rules to determine if the recommended
actions should be allowed or denied.

Standalone module — no server dependencies.  Operates on local JSON files.

Usage (standalone):
    python examples/ras_api_demo/policy.py path/to/sppr_cpad.json

Usage (from orchestrator):
    from policy import PolicyEngine
    engine = PolicyEngine()
    allowed = engine.evaluate_cpad("path/to/sppr_cpad.json")
"""

import sys
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Policy engine for evaluating CPAD actions.

    Self-contained — loads a CPAD JSON file, extracts header/section fields,
    and checks them against trusted-creator, known-action, and known-platform
    registries.
    """

    # Registry of trusted Creator IDs and their names
    TRUSTED_CREATORS = {
        '11111111-2222-3333-4444-555555555555': 'Contoso',
        # Add more trusted creator IDs here
    }

    # Registry of known Action IDs and their descriptions
    # Both hex-integer and hex-string representations are supported
    KNOWN_ACTIONS = {
        # Hex integer format
        0x0006: {
            'name': 'Memory Error Spoof',
            'description': 'Spoof a corrected memory error for testing',
            'risk_level': 'Low',
        },
        0x8001: {
            'name': 'SPPR (Soft Post Package Repair)',
            'description': 'Perform memory repair operation to isolate faulty memory cells',
            'risk_level': 'Medium',
        },
        # Hex string format (from JSON files)
        '0x0006': {
            'name': 'Memory Error Spoof',
            'description': 'Spoof a corrected memory error for testing',
            'risk_level': 'Low',
        },
        '0x8001': {
            'name': 'SPPR (Soft Post Package Repair)',
            'description': 'Perform memory repair operation to isolate faulty memory cells',
            'risk_level': 'Medium',
        },
        # Add more action IDs here
    }

    # Registry of known Platform IDs
    KNOWN_PLATFORMS = {
        '990f8820-bd4d-5064-58cc-961a053dea79': {
            'name': 'Demo Platform',
            'description': 'RAS API Demo/Test Platform',
            'allowed_actions': ['Memory Error Spoof', 'SPPR (Soft Post Package Repair)'],
        },
        # Add more platform IDs here
    }

    def __init__(self, verbose=True):
        """Initialize the policy engine.

        Args:
            verbose: Whether to display detailed output.
        """
        self.verbose = verbose

    # ─── Public API ─────────────────────────────────────────────────────

    def evaluate_cpad(self, cpad_file_path):
        """Evaluate a CPAD JSON file against policy rules.

        Args:
            cpad_file_path: Path to the CPAD JSON file.

        Returns:
            bool: True if action is allowed, False if denied.
        """
        cpad_path = Path(cpad_file_path)

        if not cpad_path.exists():
            print(f"\n   ❌ CPAD file not found: {cpad_path}")
            return False

        try:
            with open(cpad_path, 'r') as f:
                cpad_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"\n   ❌ Invalid JSON in CPAD file: {e}")
            return False

        # Extract header information
        header = cpad_data.get('header', {})
        creator_id = header.get('creatorID', 'Unknown')
        platform_id = header.get('platformID', 'Unknown')
        partition_id = header.get('partitionID', 'Unknown')
        confidence = header.get('confidence', 0)

        # Extract action from sectionDescriptors
        section_descs = cpad_data.get('sectionDescriptors', [])
        action_id = self._extract_action_id(section_descs)
        fru_text = section_descs[0].get('fruText', 'Unknown') if section_descs else 'Unknown'

        print(f"\n   📋 CPAD File: {cpad_path.name}")
        print(f"\n   Platform ID:  {platform_id}")
        print(f"   Partition ID: {partition_id}")
        print(f"   Creator ID:   {creator_id}")
        print(f"   Action ID:    {action_id}")
        print(f"   FRU:          {fru_text}")
        print(f"   Confidence:   {confidence}")

        # Evaluate against policy rules
        print(f"\n🔍 Evaluating against policy rules...")

        # Rule 1: Creator trust verification
        print(f"\n   Rule 1: Creator Trust Verification")
        creator_trusted = self._verify_creator(creator_id)

        # Rule 2: Action authorization
        print(f"\n   Rule 2: Action Authorization")
        action_info = self._verify_action(action_id)

        # Rule 3: Platform authorization
        print(f"\n   Rule 3: Platform Authorization")
        platform_ok = self._verify_platform(platform_id, action_info)

        # Rule 4: Confidence threshold
        print(f"\n   Rule 4: Confidence Threshold")
        confidence_ok = True
        if confidence >= 80:
            print(f"      ✓ Confidence {confidence} meets minimum threshold (80)")
        else:
            print(f"      ✗ Confidence {confidence} below minimum threshold (80)")
            confidence_ok = False

        # Final decision
        print(f"\n{'─' * 80}")

        if creator_trusted and action_info and platform_ok and confidence_ok:
            print(f"✅ Policy Evaluation: APPROVED")
            print(f"   All policy rules satisfied for {cpad_path.name}")
            print(f"{'─' * 80}")
            return True
        else:
            print(f"❌ Policy Evaluation: DENIED")
            if not creator_trusted:
                print(f"   • Creator ID is not in trusted list")
            if not action_info:
                print(f"   • Action ID is not recognized")
            if not platform_ok:
                print(f"   • Platform is not authorized for this action")
            if not confidence_ok:
                print(f"   • Confidence below minimum threshold")
            print(f"{'─' * 80}")
            return False

    def evaluate_multiple_cpads(self, cpad_files):
        """Evaluate multiple CPAD files.

        Args:
            cpad_files: List of CPAD file paths.

        Returns:
            list: List of (file_path, allowed) tuples.
        """
        results = []
        for cpad_file in cpad_files:
            allowed = self.evaluate_cpad(cpad_file)
            results.append((cpad_file, allowed))
        return results

    # ─── Internal Helpers ───────────────────────────────────────────────

    @staticmethod
    def _extract_action_id(section_descs):
        """Extract the action ID from sectionDescriptors, handling multiple formats."""
        if not section_descs:
            return 'Unknown'

        # Try actionId first (GUID/hex string from JSON CPAD)
        action_id = section_descs[0].get('actionId')
        if action_id:
            return action_id

        # Try actionID (object format from binary CPAD)
        action_id_obj = section_descs[0].get('actionID', {})
        if isinstance(action_id_obj, dict):
            return action_id_obj.get('code', 'Unknown')
        elif isinstance(action_id_obj, int):
            return action_id_obj
        elif action_id_obj:
            return action_id_obj

        return 'Unknown'

    def _verify_creator(self, creator_id):
        """Verify if the creator ID is trusted."""
        if creator_id in self.TRUSTED_CREATORS:
            creator_name = self.TRUSTED_CREATORS[creator_id]
            print(f"      ✓ Creator {creator_id} — trusted ({creator_name})")
            return True
        else:
            print(f"      ✗ Creator {creator_id} — not in trusted registry")
            return False

    def _verify_action(self, action_id):
        """Verify the action ID and return action information."""
        if action_id in self.KNOWN_ACTIONS:
            action_info = self.KNOWN_ACTIONS[action_id]
            print(f"      ✓ Action {action_id} — {action_info['name']}")
            print(f"        Risk Level: {action_info['risk_level']}")
            return action_info
        else:
            print(f"      ✗ Action {action_id} — not recognized")
            return None

    def _verify_platform(self, platform_id, action_info):
        """Verify platform authorization for the action."""
        if platform_id in self.KNOWN_PLATFORMS:
            platform_info = self.KNOWN_PLATFORMS[platform_id]
            print(f"      ✓ Platform {platform_id} — {platform_info['name']}")

            if action_info:
                action_name = action_info['name']
                if action_name in platform_info['allowed_actions']:
                    print(f"        Action '{action_name}' is allowed on this platform")
                    return True
                else:
                    print(f"      ✗ Action '{action_name}' is NOT allowed on this platform")
                    return False
            return True
        else:
            print(f"      ⚠️  Platform {platform_id} — not in registered platforms")
            print(f"        Allowing action (permissive mode for unregistered platforms)")
            return True


# ─── CLI Entry Point ────────────────────────────────────────────────────

def main():
    """Command-line interface for standalone policy evaluation."""
    if len(sys.argv) < 2:
        print("Usage: python examples/ras_api_demo/policy.py <cpad_file.json> [cpad_file2.json ...]")
        print("\nExample:")
        print("  python examples/ras_api_demo/policy.py ras_demo_output/Analyzer_output_files/corrected_sppr_cpad.json")
        sys.exit(1)

    engine = PolicyEngine()

    print("\n" + "=" * 80)
    print("\t\t\t\tPOLICY EVALUATION")
    print("=" * 80)

    all_allowed = True
    for cpad_file in sys.argv[1:]:
        print(f"\n{'─' * 80}")
        allowed = engine.evaluate_cpad(cpad_file)
        if not allowed:
            all_allowed = False

    print("\n" + "=" * 80)
    sys.exit(0 if all_allowed else 1)


if __name__ == "__main__":
    main()
