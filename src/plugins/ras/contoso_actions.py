"""Contoso-specific CPAD action execution for the simulated RAS endpoint."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from .action_provider import (
    ACTION_COMPLETED,
    ACTION_FAILED,
    ACTION_PENDING,
    ActionResult,
)
from .contoso_memory import (
    active_cpad_memory_bank,
    decode_cpad_memory_coordinates,
    decode_cpad_memory_error_address,
    is_contoso_memory_cpad,
)
from .memory_config import (
    EndpointConfig,
    MemoryRepairState,
    RASEndpointConfiguration,
)


CONTOSO_CREATOR_ID = "11111111-2222-3333-4444-555555555555"
SPPR_ACTION_ID = "0x8001"
PAGE_OFFLINE_ACTION_ID = "0x8002"
REBOOT_WITH_RETRAINING_ACTION_ID = "0x8003"
PAGE_SIZE_BYTES = 4096

CONTOSO_ACTION_DESCRIPTIONS = {
    SPPR_ACTION_ID: "SPPR: soft post package repair operation",
    PAGE_OFFLINE_ACTION_ID: "Page Offline: forward a 4 KiB page to the OS",
    REBOOT_WITH_RETRAINING_ACTION_ID: (
        "Reboot with Memory Retraining: retrain the SoC on its next reset"
    ),
}

RETRAINING_RESET_TYPES = frozenset({
    "On",
    "GracefulRestart",
    "ForceRestart",
    "PowerCycle",
})


@dataclass(frozen=True)
class PendingRetrainingAction:
    """Accepted retraining CPAD waiting for its target SoC to reset."""

    key: Tuple[str, str, int]
    manager_id: str
    cpad_data: Dict[str, Any]
    metadata: Dict[str, Any]


class ContosoActionProvider:
    """Execute proprietary actions owned by the Contoso endpoint CreatorID."""

    creator_ids = frozenset({CONTOSO_CREATOR_ID})
    action_ids = frozenset({
        SPPR_ACTION_ID,
        PAGE_OFFLINE_ACTION_ID,
        REBOOT_WITH_RETRAINING_ACTION_ID,
    })

    def __init__(
            self,
            endpoint_configuration: Optional[RASEndpointConfiguration],
            memory_repair_states: Dict[str, MemoryRepairState]):
        self.endpoint_configuration = endpoint_configuration
        self.memory_repair_states = memory_repair_states
        self._pending_retraining: Dict[
            Tuple[str, str, int], PendingRetrainingAction] = {}

    def execute(
            self,
            manager_id: str,
            action_id: str,
            cpad_data: Dict[str, Any],
            metadata: Dict[str, Any],
            endpoint: EndpointConfig) -> ActionResult:
        """Execute or schedule one Contoso proprietary action."""
        if action_id not in self.action_ids:
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=f"unsupported Contoso action {action_id}",
            )
        if not is_contoso_memory_cpad(cpad_data):
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason="Contoso memory action requires a Contoso memory section",
            )

        if action_id == SPPR_ACTION_ID:
            if not isinstance(endpoint, EndpointConfig):
                return ActionResult(
                    status=ACTION_FAILED,
                    return_code=0x01,
                    reason=(
                        "SPPR requires configured Contoso endpoint memory"
                    ),
                )
            return self._perform_sppr(cpad_data, endpoint)
        if action_id == PAGE_OFFLINE_ACTION_ID:
            return self._perform_page_offline(cpad_data)
        return self._schedule_retraining(
            manager_id, cpad_data, metadata)

    def perform_sppr(
            self, cpad_data: Dict[str, Any],
            partition_id: Optional[str] = None) -> Tuple[int, Optional[str], Optional[int]]:
        """Compatibility entry point for focused SPPR tests and callers."""
        try:
            endpoint = self._endpoint(partition_id)
        except ValueError as exc:
            return 0x01, str(exc), None
        result = self._perform_sppr(cpad_data, endpoint)
        return (
            result.return_code,
            result.reason,
            result.details.get("repair_count"),
        )

    def pending_retraining(
            self,
            partition_ids: Iterable[str],
            reset_type: str) -> Tuple[PendingRetrainingAction, ...]:
        """Return retraining actions completed by this whole-machine reset."""
        if reset_type not in RETRAINING_RESET_TYPES:
            return ()
        affected = set(partition_ids)
        return tuple(
            action for action in self._pending_retraining.values()
            if action.metadata["partition_id"] in affected
        )

    def mark_retraining_complete(
            self, action: PendingRetrainingAction) -> None:
        """Remove a pending action after its completion event is stored."""
        self._pending_retraining.pop(action.key, None)

    def _endpoint(self, partition_id: Optional[str]) -> EndpointConfig:
        if self.endpoint_configuration is None:
            raise ValueError(
                f"no endpoint configuration for partition {partition_id}")
        if partition_id is None and len(
                self.endpoint_configuration.endpoints) == 1:
            return self.endpoint_configuration.endpoints[0]
        return self.endpoint_configuration.endpoint_by_partition(partition_id)

    def _memory_state(self, partition_id: str) -> MemoryRepairState:
        try:
            return self.memory_repair_states[partition_id]
        except KeyError as exc:
            raise ValueError(
                f"no memory configuration for partition {partition_id}") from exc

    def _perform_sppr(
            self, cpad_data: Dict[str, Any],
            endpoint: EndpointConfig) -> ActionResult:
        try:
            if not endpoint.memory_repair_capabilities.soft_ppr_runtime_supported:
                raise ValueError("soft PPR is not supported at runtime")
            state = self._memory_state(endpoint.partition_id)
            repair_target = decode_cpad_memory_coordinates(cpad_data)
            repair_count = state.increment(repair_target)
            return ActionResult(
                status=ACTION_COMPLETED,
                context=(
                    "SPPR completed for "
                    f"chiplet {repair_target['chiplet']}, "
                    f"controller {repair_target['controller']}, "
                    f"channel {repair_target['channel']}, "
                    f"DIMM {repair_target['dimm']}, "
                    f"subchannel {repair_target['subchannel']}, "
                    f"rank {repair_target['rank']}, "
                    f"DRAM device {repair_target['device']}, "
                    f"bank group {repair_target['bank_group']}, "
                    f"bank {repair_target['bank']}; "
                    f"repair count {repair_count}"
                ),
                details={
                    **repair_target,
                    "repair_count": repair_count,
                },
                display_lines=(
                    "SPPR applied:",
                    f"Chiplet:      {repair_target['chiplet']}",
                    f"Controller:   {repair_target['controller']}",
                    f"Channel:      {repair_target['channel']}",
                    f"DIMM:         {repair_target['dimm']}",
                    f"Subchannel:   {repair_target['subchannel']}",
                    f"Rank:         {repair_target['rank']}",
                    f"DRAM device:  {repair_target['device']}",
                    f"Bank group:   {repair_target['bank_group']}",
                    f"Bank:         {repair_target['bank']}",
                    f"Repair count: {repair_count}",
                ),
            )
        except ValueError as exc:
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=str(exc),
            )

    @staticmethod
    def _perform_page_offline(cpad_data: Dict[str, Any]) -> ActionResult:
        try:
            address = decode_cpad_memory_error_address(cpad_data)
            if address % PAGE_SIZE_BYTES:
                raise ValueError(
                    "Page Offline physical address must be 4 KiB aligned")
            return ActionResult(
                status=ACTION_COMPLETED,
                context=(
                    f"Page Offline request for physical address "
                    f"0x{address:016x} was forwarded to the OS"
                ),
                details={"physical_address": address},
            )
        except ValueError as exc:
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=str(exc),
            )

    def _schedule_retraining(
            self,
            manager_id: str,
            cpad_data: Dict[str, Any],
            metadata: Dict[str, Any]) -> ActionResult:
        try:
            active_cpad_memory_bank(cpad_data)
        except ValueError as exc:
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=str(exc),
            )

        key = (
            metadata["partition_id"],
            metadata["creator_id"].lower(),
            metadata["record_id"],
        )
        if key not in self._pending_retraining:
            self._pending_retraining[key] = PendingRetrainingAction(
                key=key,
                manager_id=manager_id,
                cpad_data=copy.deepcopy(cpad_data),
                metadata=copy.deepcopy(metadata),
            )
        return ActionResult(
            status=ACTION_PENDING,
            context=(
                f"Memory retraining is pending for SoC partition "
                f"{metadata['partition_id']}"
            ),
        )
