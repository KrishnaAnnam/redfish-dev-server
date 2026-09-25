"""Simple reversible Contoso memory-address translation for the RAS demo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


TRANSLATION_SCHEME = "contoso-simple-v1"
MEMORY_ORGANIZATION_VERSION = 1
SUPPORTED_DIMM_SIZES_GIB = frozenset({32, 64, 128})
GIB = 1024 ** 3


def _require_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in the range {minimum}..{maximum}")
    return value


def _require_power_of_two(value: Any, name: str) -> int:
    value = _require_int(value, name, 1, 1 << 16)
    if value & (value - 1):
        raise ValueError(f"{name} must be a power of two")
    return value


@dataclass(frozen=True)
class DimmOrganization:
    """DIMM-local DDR5 x4 geometry derived from capacity."""

    dimm_size_gib: int
    ranks: int
    row_bits: int
    subchannels: int = 2
    bank_groups: int = 8
    banks_per_group: int = 4
    columns_per_row: int = 2048
    bytes_per_column: int = 4

    @property
    def rows_per_bank(self) -> int:
        return 1 << self.row_bits

    @property
    def dimm_size_bytes(self) -> int:
        return self.dimm_size_gib * GIB

    @property
    def calculated_size_bytes(self) -> int:
        return (
            self.bytes_per_column
            * self.columns_per_row
            * self.rows_per_bank
            * self.banks_per_group
            * self.bank_groups
            * self.ranks
            * self.subchannels
        )


DIMM_ORGANIZATIONS: Dict[int, DimmOrganization] = {
    32: DimmOrganization(dimm_size_gib=32, ranks=1, row_bits=16),
    64: DimmOrganization(dimm_size_gib=64, ranks=2, row_bits=16),
    128: DimmOrganization(dimm_size_gib=128, ranks=2, row_bits=17),
}


def organization_for_size(dimm_size_gib: int) -> DimmOrganization:
    """Return the supported DDR5 x4 organization for one DIMM size."""
    try:
        organization = DIMM_ORGANIZATIONS[dimm_size_gib]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "dimm_size_gib must be one of 32, 64, or 128") from exc
    if organization.calculated_size_bytes != organization.dimm_size_bytes:
        raise RuntimeError(
            f"{dimm_size_gib} GiB DIMM organization has inconsistent capacity")
    return organization


@dataclass(frozen=True)
class MemoryOrganization:
    """Versioned platform-wide DIMM organization."""

    version: int
    address_translation: str
    dimm_size_gib: int

    def __post_init__(self) -> None:
        _require_int(
            self.version, "memory organization version",
            MEMORY_ORGANIZATION_VERSION, MEMORY_ORGANIZATION_VERSION)
        if self.version != MEMORY_ORGANIZATION_VERSION:
            raise ValueError(
                f"memory organization version must be "
                f"{MEMORY_ORGANIZATION_VERSION}")
        if self.address_translation != TRANSLATION_SCHEME:
            raise ValueError(
                f"address_translation must be {TRANSLATION_SCHEME}")
        organization_for_size(self.dimm_size_gib)

    @property
    def dimm(self) -> DimmOrganization:
        return organization_for_size(self.dimm_size_gib)

    @property
    def dimm_size_bytes(self) -> int:
        return self.dimm.dimm_size_bytes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "address_translation": self.address_translation,
            "dimm_size_gib": self.dimm_size_gib,
        }


@dataclass(frozen=True)
class MemoryAddressConfiguration:
    """Outer topology plus one uniform DIMM organization."""

    organization: MemoryOrganization
    sockets: int = 2
    chiplets_per_socket: int = 2
    controllers_per_chiplet: int = 1
    channels_per_controller: int = 2
    dimms_per_channel: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.organization, MemoryOrganization):
            raise ValueError("organization must be a MemoryOrganization")
        for name in (
                "sockets", "chiplets_per_socket", "controllers_per_chiplet",
                "channels_per_controller", "dimms_per_channel"):
            _require_power_of_two(getattr(self, name), name)

    @property
    def installed_address_space_bytes(self) -> int:
        return (
            self.sockets
            * self.chiplets_per_socket
            * self.controllers_per_chiplet
            * self.channels_per_controller
            * self.dimms_per_channel
            * self.organization.dimm_size_bytes
        )


@dataclass(frozen=True)
class MemoryChannelAddress:
    """One byte in the demo DDR5 hierarchy."""

    socket: int
    chiplet: int
    memory_controller: int
    channel: int
    dimm: int
    subchannel: int
    rank: int
    bank_group: int
    bank: int
    row: int
    column: int
    byte_in_column: int = 0


def _validate_location(
        location: MemoryChannelAddress,
        configuration: MemoryAddressConfiguration) -> None:
    organization = configuration.organization.dimm
    bounds = {
        "socket": configuration.sockets,
        "chiplet": configuration.chiplets_per_socket,
        "memory_controller": configuration.controllers_per_chiplet,
        "channel": configuration.channels_per_controller,
        "dimm": configuration.dimms_per_channel,
        "subchannel": organization.subchannels,
        "rank": organization.ranks,
        "bank_group": organization.bank_groups,
        "bank": organization.banks_per_group,
        "row": organization.rows_per_bank,
        "column": organization.columns_per_row,
        "byte_in_column": organization.bytes_per_column,
    }
    for name, maximum in bounds.items():
        _require_int(getattr(location, name), name, 0, maximum - 1)


def memory_address_to_physical_address(
        location: MemoryChannelAddress,
        configuration: MemoryAddressConfiguration) -> int:
    """Encode a DDR5 hierarchy location as an OS byte physical address."""
    if not isinstance(location, MemoryChannelAddress):
        raise ValueError("location must be a MemoryChannelAddress")
    if not isinstance(configuration, MemoryAddressConfiguration):
        raise ValueError(
            "configuration must be a MemoryAddressConfiguration")
    _validate_location(location, configuration)
    organization = configuration.organization.dimm

    within_dimm = location.subchannel
    within_dimm = within_dimm * organization.ranks + location.rank
    within_dimm = (
        within_dimm * organization.bank_groups + location.bank_group)
    within_dimm = (
        within_dimm * organization.banks_per_group + location.bank)
    within_dimm = within_dimm * organization.rows_per_bank + location.row
    within_dimm = (
        within_dimm * organization.columns_per_row + location.column)
    within_dimm = (
        within_dimm * organization.bytes_per_column
        + location.byte_in_column)

    dimm_number = location.socket
    dimm_number = (
        dimm_number * configuration.chiplets_per_socket + location.chiplet)
    dimm_number = (
        dimm_number * configuration.controllers_per_chiplet
        + location.memory_controller)
    dimm_number = (
        dimm_number * configuration.channels_per_controller
        + location.channel)
    dimm_number = (
        dimm_number * configuration.dimms_per_channel + location.dimm)
    return dimm_number * organization.dimm_size_bytes + within_dimm


def physical_address_to_memory_address(
        physical_address: int,
        configuration: MemoryAddressConfiguration) -> MemoryChannelAddress:
    """Decode an OS byte physical address into its DDR5 hierarchy."""
    if not isinstance(configuration, MemoryAddressConfiguration):
        raise ValueError(
            "configuration must be a MemoryAddressConfiguration")
    physical_address = _require_int(
        physical_address, "physical_address", 0,
        configuration.installed_address_space_bytes - 1)
    organization = configuration.organization.dimm

    dimm_number, within_dimm = divmod(
        physical_address, organization.dimm_size_bytes)
    within_dimm, byte_in_column = divmod(
        within_dimm, organization.bytes_per_column)
    within_dimm, column = divmod(
        within_dimm, organization.columns_per_row)
    within_dimm, row = divmod(
        within_dimm, organization.rows_per_bank)
    within_dimm, bank = divmod(
        within_dimm, organization.banks_per_group)
    within_dimm, bank_group = divmod(
        within_dimm, organization.bank_groups)
    subchannel, rank = divmod(
        within_dimm, organization.ranks)
    if subchannel >= organization.subchannels:
        raise ValueError("physical_address exceeds the DIMM organization")

    dimm_number, dimm = divmod(
        dimm_number, configuration.dimms_per_channel)
    dimm_number, channel = divmod(
        dimm_number, configuration.channels_per_controller)
    dimm_number, memory_controller = divmod(
        dimm_number, configuration.controllers_per_chiplet)
    socket, chiplet = divmod(
        dimm_number, configuration.chiplets_per_socket)
    if socket >= configuration.sockets:
        raise ValueError("physical_address exceeds the platform topology")

    return MemoryChannelAddress(
        socket=socket,
        chiplet=chiplet,
        memory_controller=memory_controller,
        channel=channel,
        dimm=dimm,
        subchannel=subchannel,
        rank=rank,
        bank_group=bank_group,
        bank=bank,
        row=row,
        column=column,
        byte_in_column=byte_in_column,
    )


def physical_cacheline_base(physical_address: int) -> int:
    """Return the 64-byte cacheline base containing a physical address."""
    return _require_int(
        physical_address, "physical_address", 0, (1 << 64) - 1) & ~0x3F


def physical_page_base(physical_address: int) -> int:
    """Return the 4 KiB page base containing a physical address."""
    return _require_int(
        physical_address, "physical_address", 0, (1 << 64) - 1) & ~0xFFF


def memory_address_to_cacheline_base(
        location: MemoryChannelAddress,
        configuration: MemoryAddressConfiguration) -> int:
    """Encode the base address of the cacheline containing a location."""
    return memory_address_to_physical_address(
        MemoryChannelAddress(
            **{
                **location.__dict__,
                "column": location.column & ~0xF,
                "byte_in_column": 0,
            },
        ),
        configuration,
    )


class ContosoMemoryAddressTranslator:
    """Translation plus optional installed-DIMM and FRU validation."""

    def __init__(
            self,
            configuration: MemoryAddressConfiguration,
            inventory: Optional[Any] = None):
        self.configuration = configuration
        self.inventory = inventory

    def to_physical(
            self, location: MemoryChannelAddress,
            *, require_installed: bool = True) -> int:
        address = memory_address_to_physical_address(
            location, self.configuration)
        if require_installed:
            self._installed_dimm(location)
        return address

    def from_physical(
            self, physical_address: int,
            *, require_installed: bool = True) -> MemoryChannelAddress:
        location = physical_address_to_memory_address(
            physical_address, self.configuration)
        if require_installed:
            self._installed_dimm(location)
        return location

    def fru_for_physical_address(
            self, physical_address: int) -> tuple[str, str]:
        dimm = self._installed_dimm(self.from_physical(
            physical_address, require_installed=False))
        return dimm.fru_id, dimm.fru_text

    def _installed_dimm(self, location: MemoryChannelAddress):
        if self.inventory is None:
            raise ValueError(
                "installed-DIMM validation requires a memory inventory")
        if location.socket != self.inventory.socket:
            raise ValueError(
                f"no memory inventory for socket {location.socket}")
        return self.inventory.get_dimm(
            location.chiplet,
            location.memory_controller,
            location.channel,
            location.dimm,
        )
