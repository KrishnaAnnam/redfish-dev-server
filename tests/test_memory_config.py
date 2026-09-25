#!/usr/bin/env python3
"""Focused tests for simulated platform memory configuration and repair state."""

import sys
import copy
import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.plugins.ras.memory_config import (
    MemoryRepairCapabilities,
    MemoryRepairState,
    PlatformMemoryConfig,
    RASEndpointConfiguration,
)


CONFIG_PATH = ROOT / "mockups" / "ras_gen1" / "ras_endpoint_config.json"


def _organization(size=64):
    return {
        "version": 1,
        "address_translation": "contoso-simple-v1",
        "dimm_size_gib": size,
    }


def _dimm(**overrides):
    dimm = {
        "channel": 0,
        "dimm": 0,
        "fru_id": "00000000-0000-0000-0000-000000000001",
        "fru_text": "DIMM A1",
        "spd": {
            "serial_number": "SERIAL",
            "part_number": "PART",
            "module_manufacturer_id": [4, 213],
            "dram_manufacturer_id": [4, 213],
        },
    }
    dimm.update(overrides)
    return dimm


def _address(**overrides):
    address = {
        "chiplet": 0,
        "controller": 0,
        "channel": 0,
        "dimm": 0,
        "subchannel": 0,
        "rank": 0,
        "device": 3,
        "bank_group": 2,
        "bank": 3,
    }
    address.update(overrides)
    return address


def test_loads_fully_populated_two_chiplet_inventory():
    endpoint = RASEndpointConfiguration.load(CONFIG_PATH).endpoint_by_id(
        "Endpoint-1")
    config = endpoint.memory

    assert config.channels_per_chiplet == 2
    assert config.dimms_per_channel == 2
    assert config.get_dimm(0, 0, 0, 0).serial_number == "MSFT-C0-CH0-D0"
    assert config.get_dimm(1, 0, 1, 1).serial_number == "MSFT-C1-CH1-D1"
    assert config.get_dimm(0, 0, 0, 0).spd_temperature == 40
    assert config.get_dimm(1, 0, 1, 1).spd_temperature == 40
    assert config.get_dimm(0, 0, 0, 0).fru_text == "DIMM A2"
    assert config.organization.dimm_size_gib == 64
    assert len(config._dimms) == 8
    assert config.total_memory_bytes == 512 * 1024 ** 3
    assert endpoint.memory_repair_capabilities.bitfield == 0b111


def test_defaults_topology_and_repair_limit():
    config = PlatformMemoryConfig.from_dict({
        "platform_id": "platform",
        "memory_organization": _organization(),
        "memory_controllers": [{
            "chiplet": 0,
            "controller": 0,
            "dimms": [_dimm()],
        }],
    })

    assert config.channels_per_chiplet == 2
    assert config.dimms_per_channel == 2
    assert config.get_dimm(0, 0, 0, 0).max_repairs_per_bank == 16
    assert config.get_dimm(0, 0, 0, 0).spd_temperature == 40


def test_spd_temperature_must_not_use_injection_sentinel():
    data = {
        "platform_id": "platform",
        "memory_organization": _organization(),
        "memory_controllers": [{
            "chiplet": 0,
            "controller": 0,
            "dimms": [_dimm(spd={
                **_dimm()["spd"],
                "spd_temperature": 128,
            })],
        }],
    }

    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "spd_temperature must be in the range -127..127" in str(exc)
    else:
        raise AssertionError("expected invalid SPD temperature failure")

    data["memory_controllers"][0]["dimms"][0]["spd"]["spd_temperature"] = -128
    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "spd_temperature must be in the range -127..127" in str(exc)
    else:
        raise AssertionError("expected reserved SPD temperature failure")


def test_sparse_counts_are_scoped_to_bank_and_dimm():
    endpoint = RASEndpointConfiguration.load(CONFIG_PATH).endpoint_by_id(
        "Endpoint-1")
    state = MemoryRepairState(endpoint.memory)

    assert state.entries_for_dimm(0, 0, 0, 0) == []
    assert state.increment(_address()) == 1
    assert state.increment(_address()) == 2
    assert state.increment(_address(bank=2)) == 1

    assert state.entries_for_dimm(0, 0, 0, 0) == [
        {"subchannel": 0, "rank": 0, "device": 3,
         "bank_group": 2, "bank": 2, "count": 1},
        {"subchannel": 0, "rank": 0, "device": 3,
         "bank_group": 2, "bank": 3, "count": 2},
    ]
    assert state.entries_for_dimm(0, 0, 0, 1) == []
    assert MemoryRepairState(state.config).entries_for_dimm(0, 0, 0, 0) == []


def test_per_dimm_limit_rejects_without_incrementing():
    data = {
        "platform_id": "platform",
        "memory_organization": _organization(),
        "memory_controllers": [{
            "chiplet": 0,
            "controller": 0,
            "dimms": [_dimm(max_repairs_per_bank=1)],
        }],
    }
    state = MemoryRepairState(PlatformMemoryConfig.from_dict(data))

    assert state.increment(_address()) == 1
    try:
        state.increment(_address())
    except ValueError as exc:
        assert "repair limit 1 reached" in str(exc)
    else:
        raise AssertionError("expected repair limit failure")
    assert state.entries_for_dimm(0, 0, 0, 0)[0]["count"] == 1


def test_rejects_invalid_topology_and_limit():
    data = {
        "platform_id": "platform",
        "memory_organization": _organization(),
        "channels_per_chiplet": 2,
        "dimms_per_channel": 2,
        "memory_controllers": [{
            "chiplet": 0,
            "controller": 0,
            "dimms": [{
                "channel": 2,
                "dimm": 0,
                "fru_id": "00000000-0000-0000-0000-000000000001",
                "fru_text": "DIMM A1",
                "max_repairs_per_bank": 256,
                "spd": {},
            }],
        }],
    }

    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "channel must be in the range 0..1" in str(exc)
    else:
        raise AssertionError("expected invalid topology failure")

    data["memory_controllers"][0]["dimms"][0].update({
        "channel": 0,
        "max_repairs_per_bank": 256,
        "spd": {
            "serial_number": "SERIAL",
            "part_number": "PART",
            "module_manufacturer_id": [4, 213],
            "dram_manufacturer_id": [4, 213],
        },
    })
    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "max_repairs_per_bank must be in the range 0..255" in str(exc)
    else:
        raise AssertionError("expected invalid repair limit failure")

    data["memory_controllers"][0].update({"chiplet": 2, "controller": 0})
    data["memory_controllers"][0]["dimms"][0]["max_repairs_per_bank"] = 16
    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "chiplet must be in the range 0..1" in str(exc)
    else:
        raise AssertionError("expected invalid chiplet failure")


def test_rejects_256th_sparse_bank_entry_without_mutation():
    endpoint = RASEndpointConfiguration.load(CONFIG_PATH).endpoint_by_id(
        "Endpoint-1")
    state = MemoryRepairState(endpoint.memory)
    addresses = product(range(2), range(4), range(10), range(8), range(4))
    for subchannel, rank, device, bank_group, bank in list(addresses)[:255]:
        state.increment(_address(
            subchannel=subchannel, rank=rank, device=device,
            bank_group=bank_group, bank=bank))

    subchannel, rank, device, bank_group, bank = list(product(
        range(2), range(4), range(10), range(8), range(4)))[255]
    try:
        state.increment(_address(
            subchannel=subchannel, rank=rank, device=device,
            bank_group=bank_group, bank=bank))
    except ValueError as exc:
        assert "already has 255 sparse repair entries" in str(exc)
    else:
        raise AssertionError("expected sparse repair entry limit failure")
    assert len(state.entries_for_dimm(0, 0, 0, 0)) == 255


def test_rejects_per_dimm_size_and_unsupported_uniform_size():
    data = {
        "platform_id": "platform",
        "memory_organization": _organization(),
        "memory_controllers": [{
            "chiplet": 0,
            "controller": 0,
            "dimms": [_dimm(size_bytes=64 * 1024 ** 3)],
        }],
    }
    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "size_bytes is not supported" in str(exc)
    else:
        raise AssertionError("per-DIMM size was accepted")

    data["memory_controllers"][0]["dimms"][0].pop("size_bytes")
    data["memory_organization"]["dimm_size_gib"] = 48
    try:
        PlatformMemoryConfig.from_dict(data)
    except ValueError as exc:
        assert "32, 64, or 128" in str(exc)
    else:
        raise AssertionError("unsupported uniform DIMM size was accepted")


def test_accepts_every_supported_uniform_dimm_size():
    for size in (32, 64, 128):
        config = PlatformMemoryConfig.from_dict({
            "platform_id": "platform",
            "memory_organization": _organization(size),
            "memory_controllers": [{
                "chiplet": 0,
                "controller": 0,
                "dimms": [_dimm()],
            }],
        })

        assert config.organization.dimm_size_gib == size
        assert config.total_memory_bytes == size * 1024 ** 3


def test_endpoint_capabilities_default_false_and_require_booleans():
    assert MemoryRepairCapabilities.from_dict({}).bitfield == 0
    try:
        MemoryRepairCapabilities.from_dict({
            "soft_ppr_runtime_supported": 1,
        })
    except ValueError as exc:
        assert "soft_ppr_runtime_supported must be a boolean" in str(exc)
    else:
        raise AssertionError("expected invalid capability failure")


def test_endpoint_ids_and_partitions_must_be_unique():
    endpoint = {
        "id": "Endpoint-1",
        "name": "Endpoint",
        "description": "Endpoint",
        "endpoint_type": "Processor",
        "partition_id": "partition",
        "creator_id": "creator",
        "fru_id": "fru",
        "fru_text": "FRU",
        "supported_queues": [],
        "memory": {
            "memory_organization": _organization(),
            "memory_controllers": [{
                "chiplet": 0,
                "controller": 0,
                "dimms": [],
            }],
        },
    }
    data = {
        "platform_id": "platform",
        "ras_endpoints": [endpoint, dict(endpoint)],
    }
    try:
        RASEndpointConfiguration.from_dict(data)
    except ValueError as exc:
        assert "duplicate endpoint id Endpoint-1" in str(exc)
    else:
        raise AssertionError("expected duplicate endpoint failure")

    data["ras_endpoints"][1] = dict(endpoint, id="Endpoint-2")
    try:
        RASEndpointConfiguration.from_dict(data)
    except ValueError as exc:
        assert "duplicate partition_id partition" in str(exc)
    else:
        raise AssertionError("expected duplicate partition failure")


def test_non_contoso_endpoint_can_omit_memory_configuration():
    config = RASEndpointConfiguration.from_dict({
        "platform_id": "platform",
        "ras_endpoints": [{
            "id": "Endpoint-1",
            "name": "Fabrikam Endpoint",
            "description": "Endpoint owned by another vendor",
            "endpoint_type": "Processor",
            "partition_id": "partition",
            "creator_id": "fabrikam",
            "fru_id": "fru",
            "fru_text": "Fabrikam SoC",
            "supported_queues": ["Corrected"],
            "provider_config": {"action_mode": "demo"},
        }],
    })

    endpoint = config.endpoint_by_partition("partition")
    assert endpoint.creator_id == "fabrikam"
    assert endpoint.provider_config == {"action_mode": "demo"}
    assert endpoint.memory is None
    assert endpoint.memory_repair_capabilities.bitfield == 0


def test_platform_rejects_mixed_dimm_sizes_across_endpoints():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream)
    second = copy.deepcopy(data["ras_endpoints"][0])
    second["id"] = "Endpoint-2"
    second["partition_id"] = "partition-2"
    second["memory"]["memory_organization"]["dimm_size_gib"] = 32
    data["ras_endpoints"].append(second)

    try:
        RASEndpointConfiguration.from_dict(data)
    except ValueError as exc:
        assert "must use the same memory_organization" in str(exc)
    else:
        raise AssertionError("mixed platform DIMM sizes were accepted")


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
