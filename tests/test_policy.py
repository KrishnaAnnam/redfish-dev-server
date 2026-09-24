#!/usr/bin/env python3
"""Focused tests for binary CPAD policy evaluation."""

import sys
import tempfile
import contextlib
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
sys.path.insert(0, str(RAS_DEMO_DIR))

from policy import PolicyEngine  # noqa: E402


CREATOR_ID = "11111111-2222-3333-4444-555555555555"
PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"
FRU_ID = "75824856-bd36-2cc8-61f4-39bb3276da2a"


def _decoded_cpad(confidence=90, urgency=False, descriptor_urgency=None):
    descriptor = {
        "actionID": {"code": "0x8001"},
        "confidence": confidence,
        "fruID": FRU_ID,
        "fruText": "DIMM A1",
    }
    if descriptor_urgency is None:
        descriptor["urgency"] = int(urgency)
    elif descriptor_urgency is not ...:
        descriptor["urgency"] = descriptor_urgency
    return {
        "header": {
            "creatorID": CREATOR_ID,
            "platformID": PLATFORM_ID,
            "partitionID": "22222222-3333-4444-5555-666666666666",
            "urgency": int(urgency),
        },
        "sectionDescriptors": [descriptor],
        "sections": [{"Unknown": {"data": "opaque"}}],
    }


class Decoder:
    def __init__(self, decoded):
        self.decoded = decoded
        self.paths = []

    def extract_cpad_data(self, path):
        self.paths.append(path)
        return self.decoded


def test_policy_decodes_binary_cpad_and_returns_action_context():
    decoded = _decoded_cpad()

    decoder = Decoder(decoded)
    engine = PolicyEngine(verbose=False, decoder=decoder)
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "repair.cpad"
        binary.write_bytes(b"CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decoder.paths == [str(binary)]
    assert decision.allowed is True
    assert decision.action_id == "0x8001"
    assert decision.action_name == "PPR (Post Package Repair)"
    assert decision.fru_id == FRU_ID
    assert decision.fru_text == "DIMM A1"
    assert decision.urgency is False
    assert decision.prioritized is False


def test_policy_prioritizes_allowed_urgent_action():
    decoder = Decoder(_decoded_cpad(urgency=True))
    engine = PolicyEngine(verbose=True, decoder=decoder)
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "urgent-repair.cpad"
        binary.write_bytes(b"CPAD")

        with contextlib.redirect_stdout(output):
            decision = engine.evaluate_cpad(binary)

    assert decision.allowed is True
    assert decision.urgency is True
    assert decision.prioritized is True
    report = output.getvalue()
    assert "Prioritizing approved urgent action" in report
    assert "Action: PPR (Post Package Repair) (0x8001)" in report
    assert "FRU Text: DIMM A1" in report
    assert f"FRU ID: {FRU_ID}" in report


def test_policy_does_not_prioritize_allowed_non_urgent_action():
    decoder = Decoder(_decoded_cpad(urgency=False))
    engine = PolicyEngine(verbose=True, decoder=decoder)
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "routine-repair.cpad"
        binary.write_bytes(b"CPAD")

        with contextlib.redirect_stdout(output):
            decision = engine.evaluate_cpad(binary)

    assert decision.allowed is True
    assert decision.prioritized is False
    assert "Policy Priority" not in output.getvalue()


def test_policy_applies_urgency_criteria_without_bypassing_confidence():
    decoder = Decoder(_decoded_cpad(confidence=79, urgency=True))
    engine = PolicyEngine(verbose=True, decoder=decoder)
    engine.actions[CREATOR_ID]["0x8001"]["urgency_policy"] = "urgent_only"
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "low-confidence-urgent.cpad"
        binary.write_bytes(b"CPAD")

        with contextlib.redirect_stdout(output):
            decision = engine.evaluate_cpad(binary)

    assert decision.allowed is False
    assert decision.urgency is True
    assert decision.prioritized is False
    assert "below threshold" in decision.reason
    assert "Policy Priority" not in output.getvalue()


def test_policy_supports_urgent_only_and_non_urgent_only_actions():
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "repair.cpad"
        binary.write_bytes(b"CPAD")

        non_urgent_engine = PolicyEngine(
            verbose=False, decoder=Decoder(_decoded_cpad(urgency=False)))
        non_urgent_engine.actions[CREATOR_ID]["0x8001"][
            "urgency_policy"] = "urgent_only"
        non_urgent = non_urgent_engine.evaluate_cpad(binary)

        urgent_engine = PolicyEngine(
            verbose=False, decoder=Decoder(_decoded_cpad(urgency=True)))
        urgent_engine.actions[CREATOR_ID]["0x8001"][
            "urgency_policy"] = "non_urgent_only"
        urgent = urgent_engine.evaluate_cpad(binary)

    assert non_urgent.allowed is False
    assert "requires an urgent recommendation" in non_urgent.reason
    assert urgent.allowed is False
    assert "does not permit urgent recommendations" in urgent.reason


def test_policy_rejects_invalid_urgency_policy():
    engine = PolicyEngine(
        verbose=False, decoder=Decoder(_decoded_cpad(urgency=True)))
    engine.actions[CREATOR_ID]["0x8001"]["urgency_policy"] = "fast"
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "repair.cpad"
        binary.write_bytes(b"CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decision.allowed is False
    assert "invalid urgency_policy" in decision.reason


def test_policy_rejects_conflicting_urgency_values():
    decoder = Decoder(_decoded_cpad(
        urgency=True, descriptor_urgency=0))
    engine = PolicyEngine(verbose=False, decoder=decoder)
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "conflicting.cpad"
        binary.write_bytes(b"CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decision.allowed is False
    assert "aggregate section urgency" in decision.reason


def test_policy_rejects_invalid_urgency_encoding():
    decoded = _decoded_cpad()
    decoded["header"]["urgency"] = 2
    engine = PolicyEngine(verbose=False, decoder=Decoder(decoded))
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "invalid-urgency.cpad"
        binary.write_bytes(b"CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decision.allowed is False
    assert decision.reason == "CPAD header urgency must be 0 or 1"


def test_policy_accepts_legacy_header_only_urgency():
    decoder = Decoder(_decoded_cpad(
        urgency=True, descriptor_urgency=...))
    engine = PolicyEngine(verbose=False, decoder=decoder)
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "legacy.cpad"
        binary.write_bytes(b"CPAD")

        decision = engine.evaluate_cpad(binary)

    assert decision.allowed is True
    assert decision.urgency is True


def test_policy_evaluates_and_prioritizes_each_section():
    decoded = _decoded_cpad(urgency=True)
    decoded["sectionDescriptors"].append({
        "actionID": {"code": "0x8001"},
        "confidence": 91,
        "urgency": 1,
        "fruID": "97fb9d52-b648-497d-b092-903b8925f6e8",
        "fruText": "DIMM B1",
    })
    decoded["header"]["sectionCount"] = 2
    engine = PolicyEngine(verbose=True, decoder=Decoder(decoded))
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "multi-fru.cpad"
        binary.write_bytes(b"CPAD")

        with contextlib.redirect_stdout(output):
            decision = engine.evaluate_cpad(binary)

    assert decision.allowed is True
    assert decision.prioritized is True
    assert len(decision.section_decisions) == 2
    report = output.getvalue()
    assert report.count("Prioritizing approved urgent action") == 2
    assert "FRU Text: DIMM A1" in report
    assert "FRU Text: DIMM B1" in report
    assert f"FRU ID: {FRU_ID}" in report
    assert "FRU ID: 97fb9d52-b648-497d-b092-903b8925f6e8" in report


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
