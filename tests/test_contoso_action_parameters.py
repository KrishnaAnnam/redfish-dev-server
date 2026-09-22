#!/usr/bin/env python3
"""Focused tests for Contoso CPAD action-parameter codecs."""

import base64
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTOSO_DIR = (
    ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CONTOSO_DIR))

import contoso_action_parameters as analyzer_codec  # noqa: E402
from src.plugins.ras import contoso_action_parameters as endpoint_codec  # noqa: E402


def _ppr_parameters(ppr_type=analyzer_codec.PPR_TYPE_SOFT_RUNTIME):
    return {
        "ppr_type": ppr_type,
        "chiplet": 1,
        "controller": 0,
        "channel": 1,
        "dimm": 0,
        "subchannel": 1,
        "rank": 2,
        "device": 3,
        "bank_group": 4,
        "bank": 2,
        "row": 1234,
    }


def _cpad(action_id, body):
    return {
        "sectionDescriptors": [{
            "sectionType": {
                "data": endpoint_codec.CONTOSO_ACTION_PARAMETER_GUID,
                "type": "Unknown",
            },
            "actionID": {"code": action_id},
        }],
        "sections": [{
            "Unknown": {
                "data": base64.b64encode(body).decode("ascii"),
            },
        }],
    }


def test_ppr_roundtrip_matches_endpoint_codec_for_every_type():
    for ppr_type in analyzer_codec.PPR_TYPES:
        body = analyzer_codec.encode_action_parameters(
            analyzer_codec.PPR_ACTION_ID,
            _ppr_parameters(ppr_type),
        )

        analyzer_parameters = analyzer_codec.decode_action_parameters(
            analyzer_codec.PPR_ACTION_ID, body)
        endpoint_parameters = endpoint_codec.decode_cpad_action_parameters(
            _cpad(endpoint_codec.PPR_ACTION_ID, body),
            endpoint_codec.PPR_ACTION_ID,
        )

        assert len(body) == 24
        assert analyzer_parameters == endpoint_parameters
        assert endpoint_parameters == {
            "ppr_type": ppr_type,
            "chiplet": 1,
            "controller": 0,
            "channel": 1,
            "dimm": 0,
            "subchannel": 1,
            "rank": 2,
            "device": 3,
            "bank_group": 4,
            "bank": 2,
            "row": 1234,
        }


def test_single_page_and_retraining_payloads_are_independent():
    page_body = analyzer_codec.encode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        {
            "page_ranges": [{
                "start_address": 0x12345000,
                "page_count": 1,
            }],
        },
    )
    retrain_body = analyzer_codec.encode_action_parameters(
        analyzer_codec.REBOOT_WITH_RETRAINING_ACTION_ID, {})

    assert len(page_body) == 21
    page_parameters = endpoint_codec.decode_cpad_action_parameters(
        _cpad(endpoint_codec.PAGE_OFFLINE_ACTION_ID, page_body),
        endpoint_codec.PAGE_OFFLINE_ACTION_ID,
    )
    assert page_parameters == {
        "encoding": endpoint_codec.PAGE_ENCODING_PFN_LIST,
        "page_count": 1,
        "page_ranges": [{
            "start_address": 0x12345000,
            "page_count": 1,
        }],
        "batch_id": None,
        "chunk_index": 0,
        "chunk_count": 1,
    }
    assert len(retrain_body) == 8
    assert endpoint_codec.decode_cpad_action_parameters(
        _cpad(endpoint_codec.REBOOT_WITH_RETRAINING_ACTION_ID, retrain_body),
        endpoint_codec.REBOOT_WITH_RETRAINING_ACTION_ID,
    ) == {}


def test_page_offline_selects_smallest_encoding():
    scattered = [{
        "start_address": 0x10000000 + index * 0x100000,
        "page_count": 1,
    } for index in range(10)]
    scattered_body = analyzer_codec.encode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        {"page_ranges": scattered},
    )
    contiguous_body = analyzer_codec.encode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        {
            "page_ranges": [{
                "start_address": 0x20000000,
                "page_count": 1000,
            }],
        },
    )
    alternating = [{
        "start_address": 0x30000000 + index * 2 * 4096,
        "page_count": 1,
    } for index in range(2048)]
    bitmap_body = analyzer_codec.encode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        {"page_ranges": alternating},
    )

    assert len(scattered_body) == 66
    assert analyzer_codec.decode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        scattered_body)["encoding"] == analyzer_codec.PAGE_ENCODING_PFN_LIST
    assert len(contiguous_body) == 25
    assert analyzer_codec.decode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        contiguous_body)["encoding"] == analyzer_codec.PAGE_ENCODING_RANGES
    assert len(bitmap_body) == 533
    assert analyzer_codec.decode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        bitmap_body)["encoding"] == analyzer_codec.PAGE_ENCODING_BITMAP


def test_large_sparse_page_request_is_split_into_correlated_chunks():
    pages = [{
        "start_address": 0x10000000 + index * 0x100000,
        "page_count": 1,
    } for index in range(10_000)]

    bodies = analyzer_codec.encode_action_parameter_bodies(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        {"page_ranges": pages},
    )
    decoded = [
        endpoint_codec.decode_cpad_action_parameters(
            _cpad(endpoint_codec.PAGE_OFFLINE_ACTION_ID, body),
            endpoint_codec.PAGE_OFFLINE_ACTION_ID,
        )
        for body in bodies
    ]

    assert len(bodies) == 4
    assert all(
        len(body) <= analyzer_codec.MAX_PAGE_OFFLINE_BODY_BYTES
        for body in bodies)
    assert sum(item["page_count"] for item in decoded) == 10_000
    assert len({item["batch_id"] for item in decoded}) == 1
    assert [item["chunk_index"] for item in decoded] == [0, 1, 2, 3]
    assert all(item["chunk_count"] == 4 for item in decoded)


def test_page_ranges_are_canonicalized_and_bounded_to_52_bits():
    body = analyzer_codec.encode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID,
        {
            "page_ranges": [
                {"start_address": 0x2000, "page_count": 2},
                {"start_address": 0x1000, "page_count": 2},
            ],
        },
    )
    decoded = analyzer_codec.decode_action_parameters(
        analyzer_codec.PAGE_OFFLINE_ACTION_ID, body)
    assert decoded["page_ranges"] == [{
        "start_address": 0x1000,
        "page_count": 3,
    }]

    try:
        analyzer_codec.encode_action_parameters(
            analyzer_codec.PAGE_OFFLINE_ACTION_ID,
            {
                "page_ranges": [{
                    "start_address": 1 << 52,
                    "page_count": 1,
                }],
            },
        )
    except ValueError as exc:
        assert "start_address must be in the range" in str(exc)
    else:
        raise AssertionError("52-bit address overflow was accepted")

    try:
        analyzer_codec.encode_action_parameters(
            analyzer_codec.PAGE_OFFLINE_ACTION_ID,
            {
                "page_ranges": [{
                    "start_address": 0x1001,
                    "page_count": 1,
                }],
            },
        )
    except ValueError as exc:
        assert "must be 4 KiB aligned" in str(exc)
    else:
        raise AssertionError("unaligned physical page was accepted")


def test_ppr_requires_exactly_one_capability_bit():
    try:
        analyzer_codec.encode_action_parameters(
            analyzer_codec.PPR_ACTION_ID,
            _ppr_parameters(0x03),
        )
    except ValueError as exc:
        assert "one of 0x01, 0x02, or 0x04" in str(exc)
    else:
        raise AssertionError("combined PPR type bits were accepted")


def test_ppr_requires_every_explicit_parameter():
    parameters = _ppr_parameters()
    del parameters["row"]

    try:
        analyzer_codec.encode_action_parameters(
            analyzer_codec.PPR_ACTION_ID, parameters)
    except ValueError as exc:
        assert "must contain exactly" in str(exc)
        assert "row" in str(exc)
    else:
        raise AssertionError("PPR request missing row was accepted")


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
