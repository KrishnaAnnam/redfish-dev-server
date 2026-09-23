#!/usr/bin/env python3
"""Focused tests for binary CPAD policy evaluation."""

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
sys.path.insert(0, str(RAS_DEMO_DIR))

from policy import PolicyEngine  # noqa: E402


CREATOR_ID = "11111111-2222-3333-4444-555555555555"
PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"


def _decoded_cpad(confidence=90):
    return {
        "header": {
            "creatorID": CREATOR_ID,
            "platformID": PLATFORM_ID,
            "partitionID": "22222222-3333-4444-5555-666666666666",
        },
        "sectionDescriptors": [{
            "actionID": {"code": "0x8001"},
            "confidence": confidence,
            "fruText": "DIMM A1",
        }],
        "sections": [{"Unknown": {"data": "opaque"}}],
    }


def test_policy_decodes_binary_cpad_and_returns_action_context():
    decoded = _decoded_cpad()

    class Decoder:
        def __init__(self):
            self.paths = []

        def extract_cpad_data(self, path):
            self.paths.append(path)
            return decoded

    decoder = Decoder()
    engine = PolicyEngine(verbose=False, decoder=decoder)
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "repair.cpad"
        binary.write_bytes(b"CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decoder.paths == [str(binary)]
    assert decision.allowed is True
    assert decision.action_id == "0x8001"
    assert decision.action_name == "PPR (Post Package Repair)"
    assert decision.fru_text == "DIMM A1"


def test_policy_denies_binary_cpad_that_cannot_be_decoded():
    class Decoder:
        @staticmethod
        def extract_cpad_data(_path):
            return None

    engine = PolicyEngine(verbose=False, decoder=Decoder())
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "invalid.cpad"
        binary.write_bytes(b"not a CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decision.allowed is False
    assert decision.reason == f"Could not decode binary CPAD: {binary}"


def test_policy_does_not_invoke_decoder_for_missing_binary():
    class Decoder:
        @staticmethod
        def extract_cpad_data(_path):
            raise AssertionError("decoder should not be called")

    engine = PolicyEngine(verbose=False, decoder=Decoder())
    with tempfile.TemporaryDirectory() as directory:
        missing = Path(directory) / "missing.cpad"

        decision = engine.evaluate_cpad(missing)

    assert decision.allowed is False
    assert decision.reason == f"CPAD file not found: {missing}"


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"  [PASS] {name}")
            except Exception as exc:
                failures += 1
                print(f"  [FAIL] {name}: {exc}")
    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILURE(S)'}")
    raise SystemExit(1 if failures else 0)
