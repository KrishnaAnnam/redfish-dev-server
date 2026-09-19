"""Configurable simulated memory inventory and repair state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


DEFAULT_CHANNELS_PER_CHIPLET = 2
DEFAULT_DIMMS_PER_CHANNEL = 2
DEFAULT_MAX_REPAIRS_PER_BANK = 16
DEFAULT_SPD_TEMPERATURE_CELSIUS = 40
MAX_REPAIRS_PER_BANK = 255
MAX_TOTAL_MEMORY_BYTES = (1 << 64) - 1
CONTOSO_CHIPLETS = 2
CONTOSO_CONTROLLERS_PER_CHIPLET = 1
CONTOSO_SUBCHANNELS = 2
CONTOSO_RANKS = 4
CONTOSO_DEVICES = 10
CONTOSO_BANK_GROUPS = 8
CONTOSO_BANKS_PER_GROUP = 4
MAX_SPARSE_REPAIR_ENTRIES = 255
SOFT_PPR_RUNTIME_SUPPORTED = 1 << 0
SOFT_PPR_BOOT_TIME_SUPPORTED = 1 << 1
HARD_PPR_BOOT_TIME_SUPPORTED = 1 << 2

_BANK_FIELDS = ("subchannel", "rank", "device", "bank_group", "bank")


def _require_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in the range {minimum}..{maximum}")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_bool(data: Dict[str, Any], name: str) -> bool:
    value = data.get(name, False)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _parse_manufacturer_id(value: Any, name: str) -> Tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must contain exactly two bytes")
    parsed = []
    for index, byte in enumerate(value):
        try:
            parsed_byte = int(byte, 0) if isinstance(byte, str) else byte
        except ValueError as exc:
            raise ValueError(f"{name}[{index}] must be a byte") from exc
        parsed.append(_require_int(parsed_byte, f"{name}[{index}]", 0, 255))
    continuation, manufacturer = parsed
    if (continuation.bit_count() % 2 != 1 or
            manufacturer.bit_count() % 2 != 1 or
            manufacturer & 0x7F in (0, 0x7F)):
        raise ValueError(f"{name} must be a valid odd-parity JEP106 ID")
    return continuation, manufacturer


def _parse_ascii(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must contain only ASCII characters") from exc
    if len(encoded) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value


@dataclass(frozen=True)
class DimmConfig:
    chiplet: int
    controller: int
    channel: int
    dimm: int
    size_bytes: int
    max_repairs_per_bank: int
    serial_number: str
    part_number: str
    module_manufacturer_id: Tuple[int, int]
    dram_manufacturer_id: Tuple[int, int]
    spd_temperature: int

    @property
    def key(self) -> Tuple[int, int, int, int]:
        return self.chiplet, self.controller, self.channel, self.dimm


@dataclass(frozen=True)
class MemoryRepairCapabilities:
    soft_ppr_runtime_supported: bool = False
    soft_ppr_boot_time_supported: bool = False
    hard_ppr_boot_time_supported: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRepairCapabilities":
        if not isinstance(data, dict):
            raise ValueError("memory_repair_capabilities must be an object")
        return cls(
            soft_ppr_runtime_supported=_optional_bool(
                data, "soft_ppr_runtime_supported"),
            soft_ppr_boot_time_supported=_optional_bool(
                data, "soft_ppr_boot_time_supported"),
            hard_ppr_boot_time_supported=_optional_bool(
                data, "hard_ppr_boot_time_supported"),
        )

    @property
    def bitfield(self) -> int:
        value = 0
        if self.soft_ppr_runtime_supported:
            value |= SOFT_PPR_RUNTIME_SUPPORTED
        if self.soft_ppr_boot_time_supported:
            value |= SOFT_PPR_BOOT_TIME_SUPPORTED
        if self.hard_ppr_boot_time_supported:
            value |= HARD_PPR_BOOT_TIME_SUPPORTED
        return value


class PlatformMemoryConfig:
    """Validated installed-DIMM inventory for one simulated platform."""

    def __init__(self, platform_id: str, channels_per_chiplet: int,
                 dimms_per_channel: int, dimms: Iterable[DimmConfig]):
        self.platform_id = platform_id
        self.channels_per_chiplet = channels_per_chiplet
        self.dimms_per_channel = dimms_per_channel
        self._dimms = {dimm.key: dimm for dimm in dimms}
        if self.total_memory_bytes > MAX_TOTAL_MEMORY_BYTES:
            raise ValueError("total endpoint memory exceeds uint64")

    @property
    def total_memory_bytes(self) -> int:
        return sum(dimm.size_bytes for dimm in self._dimms.values())

    @classmethod
    def load(cls, path: Path | str) -> "PlatformMemoryConfig":
        path = Path(path)
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlatformMemoryConfig":
        platform_id = data.get("platform_id")
        if not isinstance(platform_id, str) or not platform_id:
            raise ValueError("platform_id must be a non-empty string")
        channels = _require_int(
            data.get("channels_per_chiplet", DEFAULT_CHANNELS_PER_CHIPLET),
            "channels_per_chiplet", 1, 256)
        dimms_per_channel = _require_int(
            data.get("dimms_per_channel", DEFAULT_DIMMS_PER_CHANNEL),
            "dimms_per_channel", 1, 256)

        dimms = []
        seen = set()
        controllers = data.get("memory_controllers", [])
        if not isinstance(controllers, list) or not controllers:
            raise ValueError("memory_controllers must be a non-empty list")
        for controller_data in controllers:
            chiplet = _require_int(
                controller_data.get("chiplet"), "chiplet", 0,
                CONTOSO_CHIPLETS - 1)
            controller = _require_int(
                controller_data.get("controller"), "controller", 0,
                CONTOSO_CONTROLLERS_PER_CHIPLET - 1)
            if "dimms" not in controller_data:
                raise ValueError("memory controller must contain a dimms list")
            installed = controller_data["dimms"]
            if not isinstance(installed, list):
                raise ValueError("memory controller dimms must be a list")
            for dimm_data in installed:
                channel = _require_int(
                    dimm_data.get("channel"), "channel", 0, channels - 1)
                dimm_index = _require_int(
                    dimm_data.get("dimm"), "dimm", 0, dimms_per_channel - 1)
                key = chiplet, controller, channel, dimm_index
                if key in seen:
                    raise ValueError(f"duplicate DIMM address {key}")
                seen.add(key)
                size_bytes = _require_int(
                    dimm_data.get("size_bytes"), "size_bytes", 1, (1 << 64) - 1)
                limit = _require_int(
                    dimm_data.get("max_repairs_per_bank", DEFAULT_MAX_REPAIRS_PER_BANK),
                    "max_repairs_per_bank", 0, MAX_REPAIRS_PER_BANK)
                spd = dimm_data.get("spd")
                if not isinstance(spd, dict):
                    raise ValueError(f"DIMM {key} must contain an spd object")
                dimms.append(DimmConfig(
                    chiplet=chiplet,
                    controller=controller,
                    channel=channel,
                    dimm=dimm_index,
                    size_bytes=size_bytes,
                    max_repairs_per_bank=limit,
                    serial_number=_parse_ascii(
                        spd.get("serial_number"), "serial_number", 18),
                    part_number=_parse_ascii(
                        spd.get("part_number"), "part_number", 24),
                    module_manufacturer_id=_parse_manufacturer_id(
                        spd.get("module_manufacturer_id"), "module_manufacturer_id"),
                    dram_manufacturer_id=_parse_manufacturer_id(
                        spd.get("dram_manufacturer_id"), "dram_manufacturer_id"),
                    spd_temperature=_require_int(
                        spd.get(
                            "spd_temperature",
                            DEFAULT_SPD_TEMPERATURE_CELSIUS),
                        "spd_temperature", -128, 127),
                ))
        return cls(platform_id, channels, dimms_per_channel, dimms)

    def get_dimm(self, chiplet: int, controller: int, channel: int,
                 dimm: int) -> DimmConfig:
        key = chiplet, controller, channel, dimm
        try:
            return self._dimms[key]
        except KeyError as exc:
            raise ValueError(f"no DIMM is installed at {key}") from exc


@dataclass(frozen=True)
class EndpointConfig:
    id: str
    name: str
    description: str
    endpoint_type: str
    partition_id: str
    creator_id: str
    fru_id: str
    fru_text: str
    supported_queues: Tuple[str, ...]
    provider_config: Dict[str, Any]
    memory_repair_capabilities: MemoryRepairCapabilities
    memory: Optional[PlatformMemoryConfig]


class RASEndpointConfiguration:
    """Validated configuration for every RAS endpoint on one platform."""

    def __init__(self, platform_id: str, endpoints: Iterable[EndpointConfig]):
        self.platform_id = platform_id
        self.endpoints = tuple(endpoints)
        self._by_id = {endpoint.id: endpoint for endpoint in self.endpoints}
        self._by_partition = {
            endpoint.partition_id: endpoint for endpoint in self.endpoints
        }

    @classmethod
    def load(cls, path: Path | str) -> "RASEndpointConfiguration":
        with Path(path).open(encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RASEndpointConfiguration":
        platform_id = _require_string(data.get("platform_id"), "platform_id")
        endpoint_data = data.get("ras_endpoints")
        if not isinstance(endpoint_data, list) or not endpoint_data:
            raise ValueError("ras_endpoints must be a non-empty list")

        endpoints = []
        endpoint_ids = set()
        partition_ids = set()
        for index, source in enumerate(endpoint_data):
            if not isinstance(source, dict):
                raise ValueError(f"ras_endpoints[{index}] must be an object")
            endpoint_id = _require_string(source.get("id"), "endpoint id")
            partition_id = _require_string(
                source.get("partition_id"), "partition_id")
            if endpoint_id in endpoint_ids:
                raise ValueError(f"duplicate endpoint id {endpoint_id}")
            if partition_id in partition_ids:
                raise ValueError(f"duplicate partition_id {partition_id}")
            endpoint_ids.add(endpoint_id)
            partition_ids.add(partition_id)

            if "supported_queues" not in source:
                raise ValueError(
                    f"endpoint {endpoint_id} must contain supported_queues")
            queues = source["supported_queues"]
            if (not isinstance(queues, list) or
                    any(not isinstance(queue, str) or not queue for queue in queues)):
                raise ValueError("supported_queues must be a list of strings")
            memory_data = source.get("memory")
            if memory_data is not None and not isinstance(memory_data, dict):
                raise ValueError(
                    f"endpoint {endpoint_id} memory must be an object")
            provider_config = source.get("provider_config", {})
            if not isinstance(provider_config, dict):
                raise ValueError(
                    f"endpoint {endpoint_id} provider_config must be an object")
            memory_capabilities = (
                MemoryRepairCapabilities.from_dict(
                    memory_data.get("memory_repair_capabilities", {}))
                if memory_data is not None else MemoryRepairCapabilities()
            )
            memory = (
                PlatformMemoryConfig.from_dict({
                    "platform_id": platform_id,
                    **memory_data,
                })
                if memory_data is not None else None
            )
            endpoints.append(EndpointConfig(
                id=endpoint_id,
                name=_require_string(source.get("name"), "endpoint name"),
                description=_require_string(
                    source.get("description"), "endpoint description"),
                endpoint_type=_require_string(
                    source.get("endpoint_type"), "endpoint_type"),
                partition_id=partition_id,
                creator_id=_require_string(source.get("creator_id"), "creator_id"),
                fru_id=_require_string(source.get("fru_id"), "fru_id"),
                fru_text=_require_string(source.get("fru_text"), "fru_text"),
                supported_queues=tuple(queues),
                provider_config=provider_config,
                memory_repair_capabilities=memory_capabilities,
                memory=memory,
            ))
        return cls(platform_id, endpoints)

    def endpoint_by_id(self, endpoint_id: str) -> EndpointConfig:
        try:
            return self._by_id[endpoint_id]
        except KeyError as exc:
            raise ValueError(f"unknown RAS endpoint {endpoint_id}") from exc

    def endpoint_by_partition(self, partition_id: str) -> EndpointConfig:
        try:
            return self._by_partition[partition_id]
        except KeyError as exc:
            raise ValueError(
                f"no RAS endpoint has partition_id {partition_id}") from exc


class MemoryRepairState:
    """Process-lifetime sparse repair counters layered over a memory config."""

    def __init__(self, config: PlatformMemoryConfig,
                 capabilities: MemoryRepairCapabilities = None):
        self.config = config
        self.capabilities = capabilities or MemoryRepairCapabilities()
        self._counts: Dict[Tuple[int, ...], int] = {}

    @staticmethod
    def _bank_coordinates(coordinates: Dict[str, int]) -> Tuple[int, ...]:
        limits = {
            "subchannel": CONTOSO_SUBCHANNELS,
            "rank": CONTOSO_RANKS,
            "device": CONTOSO_DEVICES,
            "bank_group": CONTOSO_BANK_GROUPS,
            "bank": CONTOSO_BANKS_PER_GROUP,
        }
        values = []
        for name in _BANK_FIELDS:
            values.append(_require_int(
                coordinates.get(name), name, 0, limits[name] - 1))
        return tuple(values)

    def _keys(self, coordinates: Dict[str, int]):
        dimm_key = tuple(coordinates[name] for name in
                         ("chiplet", "controller", "channel", "dimm"))
        dimm = self.config.get_dimm(*dimm_key)
        bank = self._bank_coordinates(coordinates)
        return dimm, dimm_key + bank

    def increment(self, coordinates: Dict[str, int]) -> int:
        dimm, key = self._keys(coordinates)
        current = self._counts.get(key, 0)
        if current >= dimm.max_repairs_per_bank:
            raise ValueError(
                f"bank repair limit {dimm.max_repairs_per_bank} reached for DIMM {dimm.key}")
        if current == 0:
            dimm_entry_count = sum(
                1 for existing_key in self._counts if existing_key[:4] == dimm.key)
            if dimm_entry_count >= MAX_SPARSE_REPAIR_ENTRIES:
                raise ValueError(
                    f"DIMM {dimm.key} already has {MAX_SPARSE_REPAIR_ENTRIES} "
                    "sparse repair entries")
        updated = current + 1
        self._counts[key] = updated
        return updated

    def entries_for_dimm(self, chiplet: int, controller: int,
                         channel: int, dimm: int):
        dimm_key = chiplet, controller, channel, dimm
        self.config.get_dimm(*dimm_key)
        entries = []
        for key, count in sorted(self._counts.items()):
            if key[:4] != dimm_key or count == 0:
                continue
            entries.append(dict(zip(_BANK_FIELDS, key[4:]), count=count))
        return entries
