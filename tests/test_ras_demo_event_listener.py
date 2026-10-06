#!/usr/bin/env python3
"""Focused tests for RAS demo event classification."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "examples" / "ras_api_demo"
sys.path.insert(0, str(DEMO_DIR))

from event_listener_utils import cper_download_uri  # noqa: E402


def test_cpad_lifecycle_event_has_no_cper_download_uri():
    assert cper_download_uri(
        None,
        "/redfish/v1/Oem/OpenCompute_FaultMgmt/RASService",
    ) is None


def test_cper_event_uses_explicit_additional_data_uri():
    assert cper_download_uri(
        "/redfish/v1/cper-attachments/1",
        "/redfish/v1/Managers/System/LogServices/CPER/Entries/1",
    ) == "/redfish/v1/cper-attachments/1"


def test_cper_log_entry_origin_falls_back_to_attachment_uri():
    assert cper_download_uri(
        None,
        "/redfish/v1/Managers/System/LogServices/CPER/Entries/2/",
    ) == (
        "/redfish/v1/Managers/System/LogServices/CPER/Entries/2/Attachment")
