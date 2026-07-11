#!/usr/bin/env python3
"""
Unit tests for the Contoso section body encoder/decoder.
========================================================

These tests exercise the proprietary Contoso CPER section codec in isolation —
pure ``struct`` packing, no libcper dependency — so they are fast and CI-safe.
They lock down the byte layout described in ``contoso-cper-sections.md``.

Run with:
    pytest tests/test_contoso_encoder.py
    # or standalone:
    python3 tests/test_contoso_encoder.py
"""

import sys
from pathlib import Path

# The Contoso codec lives next to the analyzer, not on the default path.
CONTOSO_DIR = Path(__file__).resolve().parents[1] / "Demos" / "RasApi" / "analyzers" / "contoso"
sys.path.insert(0, str(CONTOSO_DIR))

import contoso_catalog as catalog        # noqa: E402
import contoso_encoder as encoder        # noqa: E402
import injection_spec as spec_model      # noqa: E402


# ── Error Status Register bitfields ─────────────────────────────────────────

def test_error_status_bit_positions():
    # Address Valid → bit 63, Overflow → bit 62.
    assert encoder.pack_error_status(True, False, 0, 0) == (1 << 63)
    assert encoder.pack_error_status(False, True, 0, 0) == (1 << 62)
    # Severity occupies bits 61:59.
    assert encoder.pack_error_status(False, False, 0x5, 0) == (0x5 << 59)
    # errorID occupies the low 16 bits.
    assert encoder.pack_error_status(False, False, 0, 0xABCD) == 0xABCD


def test_error_status_roundtrip():
    for addr, ovf, sev, eid in [
        (True, True, 0x3, 0x0001),
        (False, True, 0x7, 0xFFFF),
        (True, False, 0x0, 0x0000),
    ]:
        packed = encoder.pack_error_status(addr, ovf, sev, eid)
        out = encoder.unpack_error_status(packed)
        assert out["addressValid"] is addr
        assert out["overflow"] is ovf
        assert out["severity_value"] == sev
        assert out["error_id"] == eid


# ── Misc 0 bitfields ────────────────────────────────────────────────────────

def test_misc0_bit_positions_and_roundtrip():
    assert encoder.pack_misc0(True, 0) == (1 << 63)
    assert encoder.pack_misc0(False, 0xFFFF) == 0xFFFF
    out = encoder.unpack_misc0(encoder.pack_misc0(True, 0x1234, impl=0x5))
    assert out["injected"] is True
    assert out["ce_count"] == 0x1234
    assert out["impl"] == 0x5


# ── Additional-register and body sizes (from the spec doc) ──────────────────

def test_additional_block_sizes():
    core = catalog.SECTION_TYPES["CPU Core - First Generation"]["banks"][0]
    dram = catalog.SECTION_TYPES["Memory Controller - First Generation"]["banks"][0]
    other = catalog.SECTION_TYPES["Memory Controller - First Generation"]["banks"][1]
    assert encoder.additional_block_size(core["additional"]) == 40
    assert encoder.additional_block_size(dram["additional"]) == 94   # incl. beat_mask[10][4]
    assert encoder.additional_block_size(other["additional"]) == 8


def test_full_body_sizes():
    core_fields = spec_model.to_encoder_fields(
        spec_model.build_template("CPU Core - First Generation", "Poison Consumption"))
    core_body = encoder.pack_section_body(
        "CPU Core - First Generation", "Core Errors", core_fields)
    # header(8) + 1 bank(40) + additional(40)
    assert len(core_body) == 88

    mem_fields = spec_model.to_encoder_fields(
        spec_model.build_template("Memory Controller - First Generation",
                                  "Corrected Memory ECC Error"))
    mem_body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", mem_fields)
    # header(8) + 2 banks(80) + additional(94 + 8)
    assert len(mem_body) == 190


# ── Header endianness spot-check ────────────────────────────────────────────

def test_header_layout_and_endianness():
    fields = spec_model.to_encoder_fields(
        spec_model.build_template("CPU Core - First Generation", "Poison Consumption"))
    fields["subcomponent"] = {"chiplet": 0x0102, "core": 0x0304}
    body = encoder.pack_section_body("CPU Core - First Generation", "Core Errors", fields)
    # major=1, minor=0, num_banks=1 (u16 LE), chiplet/core as little-endian u16.
    assert body[0] == 1 and body[1] == 0
    assert body[2:4] == b"\x01\x00"          # num_banks = 1
    assert body[4:6] == b"\x02\x01"          # chiplet 0x0102 little-endian
    assert body[6:8] == b"\x04\x03"          # core    0x0304 little-endian


# ── Full pack → unpack round-trips ──────────────────────────────────────────

def test_core_roundtrip_selects_bank_and_fields():
    spec = spec_model.build_template("CPU Core - First Generation", "Transaction Timeout")
    spec["section"]["subcomponent"] = {"chiplet": 0, "core": 3}
    spec["section"]["errorAddress"] = "0xDEADBEEF00"
    spec["section"]["additional"]["assert_details"] = "0x1234"
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body("CPU Core - First Generation", "Core Errors", fields)
    out = encoder.unpack_section_body("CPU Core - First Generation", body)

    assert out["bank_name"] == "Core Errors"
    assert out["subcomponent"] == {"chiplet": 0, "core": 3}
    assert out["error_address"] == 0xDEADBEEF00
    assert out["error_status"]["error_id"] == 0x02          # Transaction Timeout
    assert out["additional"]["assert_details"] == 0x1234


def test_memory_roundtrip_including_beat_mask_and_zeroed_bank():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    spec["section"]["subcomponent"] = {"chiplet": 1, "controller": 0}
    spec["section"]["additional"]["dimm"] = 2
    spec["section"]["additional"]["bank"] = 3
    spec["section"]["additional"]["row"] = 1234
    spec["section"]["additional"]["column"] = 567
    spec["section"]["additional"]["beat_mask"][3][2] = 0xBEEF
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    out = encoder.unpack_section_body("Memory Controller - First Generation", body)

    # The DRAM bank carries the error; the "Other Errors" bank is zeroed out.
    assert out["bank_name"] == "DRAM Errors"
    assert out["subcomponent"] == {"chiplet": 1, "controller": 0}
    assert out["additional"]["dimm"] == 2
    assert out["additional"]["bank"] == 3
    assert out["additional"]["row"] == 1234
    assert out["additional"]["column"] == 567
    assert out["additional"]["beat_mask"][3][2] == 0xBEEF
    assert out["additional"]["beat_mask"][0][0] == 0


# ── Catalog integrity ───────────────────────────────────────────────────────

def test_catalog_integrity():
    import re
    guid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    for name, section in catalog.SECTION_TYPES.items():
        assert guid_re.match(section["guid"].lower()), f"bad GUID for {name}"
        for bank in section["banks"]:
            ids = [eid for eid, _sev in bank["errors"].values()]
            assert len(ids) == len(set(ids)), f"duplicate errorID in {name}/{bank['name']}"
            for _eid, sev in bank["errors"].values():
                assert sev in catalog.SEVERITY_VALUES, f"unknown severity '{sev}'"


# ── Beat-error authoring (beatErrors → beat_mask) ───────────────────────────

def _mem_template_with_beats(entries):
    spec = spec_model.build_template(
        "Memory Controller - First Generation", "Corrected Memory ECC Error")
    spec["section"]["beatErrors"] = entries
    return spec


def test_parse_index_set_forms():
    p = spec_model.parse_index_set
    assert p(3, 0, 9) == [3]
    assert p("all", 0, 3) == [0, 1, 2, 3]
    assert p("0,5,15", 0, 15) == [0, 5, 15]
    assert p("0-3", 0, 15) == [0, 1, 2, 3]
    assert p("0,3-5,9", 0, 9) == [0, 3, 4, 5, 9]
    assert p([3, 7], 0, 9) == [3, 7]


def test_parse_index_set_bounds_raise():
    try:
        spec_model.parse_index_set("10", 0, 3)   # DQ max is 3
    except ValueError:
        return
    raise AssertionError("expected ValueError for out-of-range index")


def test_beat_errors_single_bit():
    spec = _mem_template_with_beats([{"dram": 3, "dq": 2, "beats": "5"}])
    fields = spec_model.to_encoder_fields(spec)
    grid = fields["additional"]["beat_mask"]
    assert grid[3][2] == (1 << 5)
    assert grid[0][0] == 0


def test_beat_errors_all_dqs_and_beat_list():
    spec = _mem_template_with_beats([{"dram": 3, "dq": "all", "beats": "0,15"}])
    grid = spec_model.to_encoder_fields(spec)["additional"]["beat_mask"]
    for q in range(4):
        assert grid[3][q] == ((1 << 0) | (1 << 15))


def test_beat_errors_multiple_entries_or_together():
    spec = _mem_template_with_beats([
        {"dram": 3, "dq": 2, "beats": "5"},
        {"dram": 3, "dq": 2, "beats": "7"},
        {"dram": "0-1", "dq": "all", "beats": "all"},
    ])
    grid = spec_model.to_encoder_fields(spec)["additional"]["beat_mask"]
    assert grid[3][2] == ((1 << 5) | (1 << 7))
    assert grid[0][0] == 0xFFFF and grid[1][3] == 0xFFFF


def test_beat_errors_roundtrip_through_encoder():
    spec = _mem_template_with_beats([{"dram": 7, "dq": 1, "beats": "2,9"}])
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    out = encoder.unpack_section_body("Memory Controller - First Generation", body)
    assert out["additional"]["beat_mask"][7][1] == ((1 << 2) | (1 << 9))


if __name__ == "__main__":
    failures = 0
    for fn_name, fn in sorted(globals().items()):
        if fn_name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  [PASS] {fn_name}")
            except AssertionError as exc:
                failures += 1
                print(f"  [FAIL] {fn_name}: {exc}")
    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILURE(S)'}")
    sys.exit(1 if failures else 0)
