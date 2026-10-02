#!/usr/bin/env python3
"""Focused tests for the simple Contoso memory-address translator."""

import random
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.ras.memory_address_translation import (
    MEMORY_ORGANIZATION_VERSION,
    TRANSLATION_SCHEME,
    MemoryAddressConfiguration,
    MemoryChannelAddress,
    MemoryOrganization,
    memory_address_to_cacheline_base,
    memory_address_to_physical_address,
    organization_for_size,
    physical_address_to_memory_address,
)
from src.plugins.ras.memory_config import RASEndpointConfiguration


def _configuration(size):
    return MemoryAddressConfiguration(MemoryOrganization(
        version=MEMORY_ORGANIZATION_VERSION,
        address_translation=TRANSLATION_SCHEME,
        dimm_size_gib=size,
    ))


def test_supported_dimm_organizations_match_capacity():
    expected = {
        32: (1, 16),
        64: (2, 16),
        128: (2, 17),
    }
    for size, (ranks, row_bits) in expected.items():
        organization = organization_for_size(size)
        assert organization.ranks == ranks
        assert organization.row_bits == row_bits
        assert organization.calculated_size_bytes == size * 1024 ** 3


def test_roundtrips_random_locations_for_all_dimm_sizes():
    rng = random.Random(20260925)
    for size in (32, 64, 128):
        configuration = _configuration(size)
        organization = configuration.organization.dimm
        for _ in range(500):
            location = MemoryChannelAddress(
                socket=rng.randrange(configuration.sockets),
                chiplet=rng.randrange(configuration.chiplets_per_socket),
                memory_controller=rng.randrange(
                    configuration.controllers_per_chiplet),
                channel=rng.randrange(
                    configuration.channels_per_controller),
                dimm=rng.randrange(configuration.dimms_per_channel),
                subchannel=rng.randrange(organization.subchannels),
                rank=rng.randrange(organization.ranks),
                bank_group=rng.randrange(organization.bank_groups),
                bank=rng.randrange(organization.banks_per_group),
                row=rng.randrange(organization.rows_per_bank),
                column=rng.randrange(organization.columns_per_row),
                byte_in_column=rng.randrange(
                    organization.bytes_per_column),
            )
            physical = memory_address_to_physical_address(
                location, configuration)
            assert physical_address_to_memory_address(
                physical, configuration) == location


def test_column_and_row_strides_are_simple():
    configuration = _configuration(64)
    base = MemoryChannelAddress(
        socket=0, chiplet=0, memory_controller=0, channel=0, dimm=0,
        subchannel=0, rank=0, bank_group=0, bank=0, row=0, column=0,
    )
    next_column = MemoryChannelAddress(
        **{**base.__dict__, "column": 1})
    next_cacheline = MemoryChannelAddress(
        **{**base.__dict__, "column": 16})
    next_row = MemoryChannelAddress(
        **{**base.__dict__, "row": 1})

    base_address = memory_address_to_physical_address(base, configuration)
    assert memory_address_to_physical_address(
        next_column, configuration) - base_address == 4
    assert memory_address_to_physical_address(
        next_cacheline, configuration) - base_address == 64
    assert memory_address_to_physical_address(
        next_row, configuration) - base_address == 8192
    assert memory_address_to_cacheline_base(
        MemoryChannelAddress(**{
            **base.__dict__, "column": 31, "byte_in_column": 3}),
        configuration,
    ) == 64


def test_rank_and_row_limits_follow_dimm_size():
    for size in (32, 64, 128):
        configuration = _configuration(size)
        organization = configuration.organization.dimm
        maximum = MemoryChannelAddress(
            socket=1, chiplet=1, memory_controller=0, channel=1, dimm=1,
            subchannel=1, rank=organization.ranks - 1,
            bank_group=7, bank=3, row=organization.rows_per_bank - 1,
            column=2047, byte_in_column=3,
        )
        address = memory_address_to_physical_address(
            maximum, configuration)
        assert physical_address_to_memory_address(
            address, configuration) == maximum

    try:
        memory_address_to_physical_address(
            MemoryChannelAddress(
                socket=0, chiplet=0, memory_controller=0, channel=0,
                dimm=0, subchannel=0, rank=1, bank_group=0, bank=0,
                row=0, column=0),
            _configuration(32),
        )
    except ValueError as exc:
        assert "rank" in str(exc)
    else:
        raise AssertionError("rank 1 was accepted for a 32 GiB DIMM")


def test_rejects_unsupported_size_and_boolean_coordinate():
    try:
        _configuration(48)
    except ValueError as exc:
        assert "32, 64, or 128" in str(exc)
    else:
        raise AssertionError("unsupported DIMM size was accepted")

    try:
        memory_address_to_physical_address(
            MemoryChannelAddress(
                socket=False, chiplet=0, memory_controller=0, channel=0,
                dimm=0, subchannel=0, rank=0, bank_group=0, bank=0,
                row=0, column=0),
            _configuration(64),
        )
    except ValueError as exc:
        assert "socket must be an integer" in str(exc)
    else:
        raise AssertionError("boolean socket was accepted")


def test_injector_cli_roundtrips_hierarchy_and_physical_address():
    injector = (
        ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso"
        / "injector-contoso.py"
    )
    common = [
        "--dimm-size-gib", "64",
        "--socket", "0",
        "--chiplet", "0",
        "--memory-controller", "0",
        "--channel", "0",
        "--dimm", "1",
        "--subchannel", "0",
        "--rank", "0",
        "--bank-group", "2",
        "--bank", "3",
        "--row", "0x4d2",
        "--column", "0x237",
    ]
    encoded = subprocess.run(
        [sys.executable, str(injector), "address-encode", *common],
        check=True, capture_output=True, text=True)
    encoded_data = json.loads(encoded.stdout)
    decoded = subprocess.run(
        [
            sys.executable, str(injector), "address-decode",
            "--dimm-size-gib", "64",
            "--physical-address", encoded_data["physical_address"],
        ],
        check=True, capture_output=True, text=True)
    decoded_data = json.loads(decoded.stdout)

    assert decoded_data["memory_address"] == encoded_data["memory_address"]


def test_injection_spec_rejects_inconsistent_address_representations():
    contoso = (
        ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso")
    sys.path.insert(0, str(contoso))
    import injection_spec

    spec = injection_spec.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    spec["section"]["addressSource"] = "both"
    spec["section"]["errorAddress"] = "0x1234"

    problems = injection_spec.validate_spec(spec)

    assert any(
        "does not match hierarchy address" in problem
        for problem in problems)


def test_physical_and_hierarchy_injection_modes_encode_identically():
    contoso = (
        ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso")
    sys.path.insert(0, str(contoso))
    import contoso_encoder
    import injection_spec

    hierarchy = injection_spec.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    hierarchy["section"]["additional"].update({
        "dimm": 1,
        "bank_group": 2,
        "bank": 3,
        "row": 1234,
        "column": 567,
    })
    hierarchy_fields = injection_spec.to_encoder_fields(hierarchy)

    physical = injection_spec.build_template(
        "Memory Controller - First Generation",
        "Corrected Memory ECC Error")
    physical["section"]["addressSource"] = "physical"
    physical["section"]["errorAddress"] = hierarchy["section"]["errorAddress"]
    physical_fields = injection_spec.to_encoder_fields(physical)

    hierarchy_body = contoso_encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors",
        hierarchy_fields)
    physical_body = contoso_encoder.pack_section_body(
        "Memory Controller - First Generation", "DRAM Errors",
        physical_fields)
    assert hierarchy_body == physical_body


def test_inventory_resolves_physical_address_to_dimm_fru():
    endpoint = RASEndpointConfiguration.load(
        ROOT / "mockups" / "ras_gen1" / "ras_endpoint_config.json"
    ).endpoint_by_id("Endpoint-1")
    from src.plugins.ras.memory_address_translation import (
        ContosoMemoryAddressTranslator,
    )
    translator = ContosoMemoryAddressTranslator(
        endpoint.memory.address_configuration,
        endpoint.memory,
    )
    location = MemoryChannelAddress(
        socket=0, chiplet=0, memory_controller=0, channel=0, dimm=1,
        subchannel=0, rank=0, bank_group=2, bank=3, row=1234, column=0,
    )
    physical = translator.to_physical(location)

    assert translator.fru_for_physical_address(physical) == (
        "75824856-bd36-2cc8-61f4-39bb3276da2a", "DIMM A1")


def test_memory_shim_package_exports_translation_api():
    contoso = (
        ROOT / "examples" / "ras_api_demo" / "analyzers" / "contoso")
    sys.path.insert(0, str(contoso))
    import memory_shims

    assert callable(memory_shims.memory_address_to_physical_address)
    assert callable(memory_shims.physical_address_to_memory_address)
    assert memory_shims.TRANSLATION_SCHEME == "contoso-simple-v1"


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
    raise SystemExit(1 if failures else 0)
