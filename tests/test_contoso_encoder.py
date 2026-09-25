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
CONTOSO_DIR = (Path(__file__).resolve().parents[1] / "examples" / "ras_api_demo" /
               "analyzers" / "contoso")
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
    assert encoder.additional_block_size(dram["additional"]) == 86
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
    # header(8) + 2 banks(80) + additional(86 + 8)
    assert len(mem_body) == 182


def test_demo_memory_injection_spec_is_valid():
    demo_spec_path = (Path(__file__).resolve().parents[1] / "examples" /
                      "ras_api_demo" / "cpad_storage" /
                      "contosoMemErrorSpoof.inject.json")
    spec = spec_model.load_spec(demo_spec_path)

    assert spec_model.validate_spec(spec) == []


def test_optional_collections_default_empty():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    del spec["section"]["additional"]["beat_mask"]
    del spec["section"]["additional"]["repairs"]

    fields = spec_model.to_encoder_fields(spec)

    assert fields["additional"]["beat_mask"] == []
    assert fields["additional"]["repairs"] == []


# ── Header endianness spot-check ────────────────────────────────────────────

def test_header_layout_and_endianness():
    fields = spec_model.to_encoder_fields(
        spec_model.build_template("CPU Core - First Generation", "Poison Consumption"))
    fields["subcomponent"] = {"chiplet": 0x0102, "core": 0x0304}
    body = encoder.pack_section_body("CPU Core - First Generation", "Core Errors", fields)
    # major=1, minor=6, num_banks=1 (u16 LE), chiplet/core as little-endian u16.
    assert body[0] == 1 and body[1] == 6
    assert body[2:4] == b"\x01\x00"          # num_banks = 1
    assert body[4:6] == b"\x02\x01"          # chiplet 0x0102 little-endian
    assert body[6:8] == b"\x04\x03"          # core    0x0304 little-endian


def test_decoder_rejects_unsupported_section_version():
    fields = spec_model.to_encoder_fields(
        spec_model.build_template("CPU Core - First Generation", "Poison Consumption"))
    body = bytearray(encoder.pack_section_body(
        "CPU Core - First Generation", "Core Errors", fields))
    body[1] = 1

    try:
        encoder.unpack_section_body("CPU Core - First Generation", bytes(body))
    except ValueError as exc:
        assert "Unsupported Contoso section format 1.1" in str(exc)
        return
    raise AssertionError("expected ValueError for legacy section version")


def _memory_body():
    fields = spec_model.to_encoder_fields(
        spec_model.build_template("Memory Controller - First Generation",
                                  "Corrected Memory ECC Error"))
    return bytearray(encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields))


def _assert_memory_decode_fails(body, expected):
    try:
        encoder.unpack_section_body("Memory Controller - First Generation", body)
    except ValueError as exc:
        assert expected in str(exc)
        return
    raise AssertionError("expected malformed memory section to be rejected")


def test_decoder_rejects_invalid_bank_geometry():
    body = _memory_body()
    body[2:4] = (3).to_bytes(2, "little")
    _assert_memory_decode_fails(body, "declares 3 banks; expected 2")

    body = _memory_body()
    body[44:48] = (1).to_bytes(4, "little")
    _assert_memory_decode_fails(body, "reserved field must be zero")

    body = _memory_body()
    body[80:84] = (88).to_bytes(4, "little")
    _assert_memory_decode_fails(body, "offsets must be increasing")

    body = _memory_body()
    body[173] = 1
    _assert_memory_decode_fails(body, "additional registers are truncated")


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
    assert "syndrome" not in spec["section"]["additional"]
    assert spec["section"]["additional"]["reserved"] == 0
    assert spec["section"]["additional"]["serial_number"] == ""
    assert spec["section"]["additional"]["part_number"] == ""
    assert spec["section"]["additional"]["dram_manufacturer_id"] == ["0x04", "0xD5"]
    assert spec["section"]["additional"]["module_manufacturer_id"] == ["0x04", "0xD5"]
    assert spec["section"]["additional"]["spd_temperature"] is None
    spec["section"]["subcomponent"] = {"chiplet": 1, "controller": 0}
    spec["section"]["additional"]["dimm"] = 1
    spec["section"]["additional"]["bank"] = 3
    spec["section"]["additional"]["row"] = 1234
    spec["section"]["additional"]["column"] = 567
    spec["section"]["additional"]["device"] = 3
    spec["section"]["additional"]["serial_number"] = "SN123456789"
    spec["section"]["additional"]["part_number"] = "PN-1234"
    spec["section"]["additional"]["dram_manufacturer_id"] = ["0x80", "0x2C"]
    spec["section"]["additional"]["module_manufacturer_id"] = ["0x80", "0xCE"]
    spec["section"]["additional"]["spd_temperature"] = -5
    spec["section"]["additional"]["total_memory_bytes"] = "0x8000000000"
    spec["section"]["additional"]["memory_repair_capabilities"] = 7
    spec["section"]["additional"]["beat_mask"][2] = 0xBEEF
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    out = encoder.unpack_section_body("Memory Controller - First Generation", body)

    # The DRAM bank carries the error; the "Other Errors" bank is zeroed out.
    assert out["bank_name"] == "DRAM Errors"
    assert out["subcomponent"] == {"chiplet": 1, "controller": 0}
    assert out["additional"]["dimm"] == 1
    assert out["additional"]["bank"] == 3
    assert out["additional"]["row"] == 1234
    assert out["additional"]["column"] == 567
    assert out["additional"]["device"] == 3
    assert out["additional"]["serial_number"] == "SN123456789"
    assert out["additional"]["part_number"] == "PN-1234"
    assert out["additional"]["dram_manufacturer_id"] == [0x80, 0x2C]
    assert out["additional"]["module_manufacturer_id"] == [0x80, 0xCE]
    assert out["additional"]["spd_temperature"] == -5
    assert out["additional"]["total_memory_bytes"] == 0x8000000000
    assert out["additional"]["memory_organization"] == {
        "version": 1,
        "address_translation": "contoso-simple-v1",
        "dimm_size_gib": 64,
    }
    assert out["additional"]["memory_repair_capabilities"] == 7
    assert out["additional"]["reserved"] == 0
    assert "syndrome" not in out["additional"]
    assert out["additional"]["beat_mask"][2] == 0xBEEF
    assert out["additional"]["beat_mask"][0] == 0


def test_memory_string_binary_layout_and_maximum_lengths():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    spec["section"]["additional"].update({
        "serial_number": "S" * 18,
        "part_number": "P" * 24,
        "dram_manufacturer_id": ["0x80", "0xAD"],
        "module_manufacturer_id": ["0x04", "0xD5"],
        "spd_temperature": -5,
    })
    spec["section"]["additional"]["device"] = 3
    spec["section"]["additional"]["beat_mask"][0] = 0x1234
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)

    # DRAM additional registers start after header(8) + two banks(80). The
    # beat mask follows the location fields, before the SPD identity fields.
    assert body[88:95] == bytes([0, 0, 0, 0, 3, 0, 0])
    assert body[99:101] == b"\x00\x00"
    assert body[101:103] == b"\x34\x12"
    assert body[109:128] == b"S" * 18 + b"\x00"
    assert body[128:153] == b"P" * 24 + b"\x00"
    assert body[153:155] == b"\x04\xD5"
    assert body[155:157] == b"\x80\xAD"
    assert body[157] == 0xFB
    assert body[158:166] == b"\x00" * 8
    assert body[166:170] == bytes([1, 1, 64, 0])
    assert body[170] == 0


def test_memory_sparse_repairs_roundtrip_and_layout():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    repairs = [
        {"subchannel": 0, "rank": 0, "device": 3,
         "bank_group": 2, "bank": 3, "count": 1},
        {"subchannel": 1, "rank": 1, "device": 7,
         "bank_group": 4, "bank": 8, "count": 16},
    ]
    spec["section"]["additional"]["repairs"] = repairs
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    out = encoder.unpack_section_body("Memory Controller - First Generation", body)

    assert len(body) == 194
    assert body[173] == 2
    assert body[174:186] == bytes([0, 0, 3, 2, 3, 1,
                                   1, 1, 7, 4, 8, 16])
    assert out["additional"]["repairs"] == repairs


def test_memory_string_validation():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    spec["section"]["additional"]["serial_number"] = "S" * 19
    spec["section"]["additional"]["part_number"] = "part\x00number"
    spec["section"]["additional"]["dram_manufacturer_id"] = ["0x00", "0x2C"]
    spec["section"]["additional"]["module_manufacturer_id"] = ["0x80"]

    problems = spec_model.validate_spec(spec)
    assert "section.additional.serial_number must be at most 18 characters." in problems
    assert "section.additional.part_number must not contain NUL characters." in problems
    assert ("section.additional.dram_manufacturer_id must be a valid odd-parity "
            "JEP106 ID in SPD byte order.") in problems
    assert ("section.additional.module_manufacturer_id must contain exactly 2 bytes."
            in problems)


def test_spd_manufacturer_id_decoding():
    assert catalog.decode_spd_manufacturer_id([0x80, 0x2C]) == "Micron"
    assert catalog.decode_spd_manufacturer_id([0x80, 0xAD]) == "SK Hynix"
    assert catalog.decode_spd_manufacturer_id([0x80, 0xCE]) == "Samsung"
    assert catalog.decode_spd_manufacturer_id([0x04, 0xD5]) == "Microsoft"

    assert catalog.decode_spd_manufacturer_id([0x80, 0x01]) == "Unknown"
    assert catalog.decode_spd_manufacturer_id([0x00, 0x2C]) == "Invalid"


def test_memory_reserved_field_must_be_zero():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    spec["section"]["additional"]["reserved"] = 1

    assert "section.additional.reserved must be zero." in spec_model.validate_spec(spec)


def test_memory_repair_capability_reserved_bits_are_rejected():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    spec["section"]["additional"]["memory_repair_capabilities"] = 0x80

    assert ("section.additional.memory_repair_capabilities has reserved bits set."
            in spec_model.validate_spec(spec))


def test_spd_temperature_range_is_validated():
    spec = spec_model.build_template("Memory Controller - First Generation",
                                     "Corrected Memory ECC Error")
    spec["section"]["additional"]["spd_temperature"] = 128

    assert (
        "section.additional.spd_temperature must be null or in the range "
        "-127..127 degrees Celsius."
    ) in spec_model.validate_spec(spec)

    spec["section"]["additional"]["spd_temperature"] = -128
    assert (
        "section.additional.spd_temperature must be null or in the range "
        "-127..127 degrees Celsius."
    ) in spec_model.validate_spec(spec)


def test_unspecified_spd_temperature_roundtrips_as_none():
    spec = spec_model.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)

    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)

    assert decoded["additional"]["spd_temperature"] is None


def test_omitted_spd_temperature_roundtrips_as_none():
    spec = spec_model.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    del spec["section"]["additional"]["spd_temperature"]

    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)

    assert decoded["additional"]["spd_temperature"] is None


def test_encoder_defaults_missing_spd_temperature_to_none():
    spec = spec_model.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    fields = spec_model.to_encoder_fields(spec)
    del fields["additional"]["spd_temperature"]

    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)

    assert decoded["additional"]["spd_temperature"] is None


def test_explicit_zero_spd_temperature_roundtrips_as_zero():
    spec = spec_model.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    spec["section"]["additional"]["spd_temperature"] = 0

    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", body)

    assert decoded["additional"]["spd_temperature"] == 0


def test_decoder_accepts_v14_memory_section_without_temperature():
    body = _memory_body()
    del body[157]
    del body[165:169]
    body[1] = 4
    body[80:84] = (169).to_bytes(4, "little")

    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", bytes(body))

    assert decoded["additional"]["spd_temperature"] is None
    assert decoded["additional"]["memory_organization"] is None


def test_decoder_accepts_v15_memory_section_without_organization():
    body = _memory_body()
    del body[166:170]
    body[1] = 5
    body[80:84] = (170).to_bytes(4, "little")

    decoded = encoder.unpack_section_body(
        "Memory Controller - First Generation", bytes(body))

    assert decoded["additional"]["spd_temperature"] is None
    assert decoded["additional"]["memory_organization"] is None


def test_decoder_rejects_invalid_memory_organization():
    for offset, value, expected in (
            (166, 2, "version"),
            (167, 2, "address translation scheme"),
            (168, 48, "32, 64, or 128"),
            (169, 1, "reserved")):
        body = _memory_body()
        body[offset] = value
        _assert_memory_decode_fails(body, expected)


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
    masks = fields["additional"]["beat_mask"]
    assert fields["additional"]["device"] == 3
    assert masks[2] == (1 << 5)
    assert masks[0] == 0


def test_beat_errors_all_dqs_and_beat_list():
    spec = _mem_template_with_beats([{"dram": 3, "dq": "all", "beats": "0,15"}])
    additional = spec_model.to_encoder_fields(spec)["additional"]
    masks = additional["beat_mask"]
    assert additional["device"] == 3
    for q in range(4):
        assert masks[q] == ((1 << 0) | (1 << 15))


def test_beat_errors_multiple_entries_or_together():
    spec = _mem_template_with_beats([
        {"dram": 3, "dq": 2, "beats": "5"},
        {"dram": 3, "dq": 2, "beats": "7"},
        {"dram": 3, "dq": "all", "beats": "0"},
    ])
    masks = spec_model.to_encoder_fields(spec)["additional"]["beat_mask"]
    assert masks[2] == ((1 << 0) | (1 << 5) | (1 << 7))
    assert masks[0] == 1 and masks[3] == 1


def test_beat_errors_roundtrip_through_encoder():
    spec = _mem_template_with_beats([{"dram": 7, "dq": 1, "beats": "2,9"}])
    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors", fields)
    out = encoder.unpack_section_body("Memory Controller - First Generation", body)
    assert out["additional"]["device"] == 7
    assert out["additional"]["beat_mask"][1] == ((1 << 2) | (1 << 9))


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
