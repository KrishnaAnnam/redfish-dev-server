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
from .contoso_action_parameters import (
    PAGE_OFFLINE_ACTION_ID,
    PPR_ACTION_ID,
    PPR_TYPE_HARD_BOOT_TIME,
    PPR_TYPE_SOFT_BOOT_TIME,
    PPR_TYPE_SOFT_RUNTIME,
    REBOOT_WITH_RETRAINING_ACTION_ID,
    decode_cpad_action_parameters,
    is_contoso_action_cpad,
)
from .contoso_memory import (
    decode_cpad_memory_coordinates,
)
from .memory_config import (
    EndpointConfig,
    MemoryRepairState,
    RASEndpointConfiguration,
)


CONTOSO_CREATOR_ID = "11111111-2222-3333-4444-555555555555"
SPPR_ACTION_ID = PPR_ACTION_ID

CONTOSO_ACTION_DESCRIPTIONS = {
    PPR_ACTION_ID: "PPR: post package repair operation",
    PAGE_OFFLINE_ACTION_ID: "Page Offline: forward 4 KiB pages to the OS",
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


@dataclass
class PendingResetAction:
    """Accepted action waiting for its target SoC to reset."""

    key: Tuple[str, str, int]
    manager_id: str
    cpad_data: Dict[str, Any]
    metadata: Dict[str, Any]
    kind: str
    parameters: Dict[str, int]
    result: Optional[ActionResult] = None


class ContosoActionProvider:
    """Execute proprietary actions owned by the Contoso endpoint CreatorID."""

    creator_ids = frozenset({CONTOSO_CREATOR_ID})
    action_ids = frozenset({
        PPR_ACTION_ID,
        PAGE_OFFLINE_ACTION_ID,
        REBOOT_WITH_RETRAINING_ACTION_ID,
    })

    def __init__(
            self,
            endpoint_configuration: Optional[RASEndpointConfiguration],
            memory_repair_states: Dict[str, MemoryRepairState]):
        self.endpoint_configuration = endpoint_configuration
        self.memory_repair_states = memory_repair_states
        self._pending_reset_actions: Dict[
            Tuple[str, str, int], PendingResetAction] = {}

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
        if not is_contoso_action_cpad(cpad_data):
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=(
                    "Contoso remediation action requires a Contoso "
                    "action-parameter section"
                ),
            )
        try:
            parameters = decode_cpad_action_parameters(
                cpad_data, action_id)
        except ValueError as exc:
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=str(exc),
            )

        if action_id == PPR_ACTION_ID:
            if not isinstance(endpoint, EndpointConfig):
                return ActionResult(
                    status=ACTION_FAILED,
                    return_code=0x01,
                    reason="PPR requires configured Contoso endpoint memory",
                )
            return self._perform_or_schedule_ppr(
                manager_id, cpad_data, metadata, endpoint, parameters)
        if action_id == PAGE_OFFLINE_ACTION_ID:
            return self._perform_page_offline(parameters)
        return self._schedule_retraining(
            manager_id, cpad_data, metadata, parameters)

    def perform_sppr(
            self, cpad_data: Dict[str, Any],
            partition_id: Optional[str] = None) -> Tuple[int, Optional[str], Optional[int]]:
        """Compatibility entry point for focused SPPR tests and callers."""
        try:
            endpoint = self._endpoint(partition_id)
        except ValueError as exc:
            return 0x01, str(exc), None
        try:
            parameters = decode_cpad_memory_coordinates(cpad_data)
            parameters["ppr_type"] = PPR_TYPE_SOFT_RUNTIME
        except ValueError as exc:
            return 0x01, str(exc), None
        if not endpoint.memory_repair_capabilities.soft_ppr_runtime_supported:
            return 0x01, "soft PPR is not supported at runtime", None
        result = self._apply_ppr(parameters, endpoint)
        return (
            result.return_code,
            result.reason,
            result.details.get("repair_count"),
        )

    def pending_reset_actions(
            self,
            partition_ids: Iterable[str],
            reset_type: str) -> Tuple[PendingResetAction, ...]:
        """Return actions completed by this whole-machine reset."""
        if reset_type not in RETRAINING_RESET_TYPES:
            return ()
        affected = set(partition_ids)
        return tuple(
            action for action in self._pending_reset_actions.values()
            if action.metadata["partition_id"] in affected
        )

    def complete_pending_reset_action(
            self, action: PendingResetAction,
            reset_type: str) -> ActionResult:
        """Execute a pending action once and cache its completion result."""
        if action.result is not None:
            return action.result
        if action.kind == "ppr":
            try:
                endpoint = self._endpoint(action.metadata["partition_id"])
                action.result = self._apply_ppr(action.parameters, endpoint)
            except ValueError as exc:
                action.result = ActionResult(
                    status=ACTION_FAILED,
                    return_code=0x01,
                    reason=str(exc),
                )
        else:
            action.result = ActionResult(
                status=ACTION_COMPLETED,
                context=(
                    f"All memory controllers in SoC partition "
                    f"{action.metadata['partition_id']} were retrained during "
                    f"{reset_type}"
                ),
            )
        return action.result

    def mark_reset_action_complete(
            self, action: PendingResetAction) -> None:
        """Remove a pending action after its completion event is stored."""
        self._pending_reset_actions.pop(action.key, None)

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

    @staticmethod
    def _ppr_type_name(ppr_type: int) -> str:
        return {
            PPR_TYPE_SOFT_RUNTIME: "runtime soft PPR",
            PPR_TYPE_SOFT_BOOT_TIME: "boot-time soft PPR",
            PPR_TYPE_HARD_BOOT_TIME: "boot-time hard PPR",
        }[ppr_type]

    def _perform_or_schedule_ppr(
            self,
            manager_id: str,
            cpad_data: Dict[str, Any],
            metadata: Dict[str, Any],
            endpoint: EndpointConfig,
            parameters: Dict[str, int]) -> ActionResult:
        ppr_type = parameters["ppr_type"]
        if not endpoint.memory_repair_capabilities.bitfield & ppr_type:
            return ActionResult(
                status=ACTION_FAILED,
                return_code=0x01,
                reason=f"{self._ppr_type_name(ppr_type)} is not supported",
            )
        if ppr_type == PPR_TYPE_SOFT_RUNTIME:
            return self._apply_ppr(parameters, endpoint)
        return self._schedule_reset_action(
            manager_id, cpad_data, metadata, "ppr", parameters,
            context=(
                f"{self._ppr_type_name(ppr_type)} is pending for SoC "
                f"partition {endpoint.partition_id}"
            ),
        )

    def _apply_ppr(
            self, repair_target: Dict[str, int],
            endpoint: EndpointConfig) -> ActionResult:
        try:
            state = self._memory_state(endpoint.partition_id)
            repair_count = state.increment(repair_target)
            ppr_type = repair_target["ppr_type"]
            ppr_name = self._ppr_type_name(ppr_type)
            return ActionResult(
                status=ACTION_COMPLETED,
                context=(
                    f"{ppr_name} completed for "
                    f"chiplet {repair_target['chiplet']}, "
                    f"controller {repair_target['controller']}, "
                    f"channel {repair_target['channel']}, "
                    f"DIMM {repair_target['dimm']}, "
                    f"subchannel {repair_target['subchannel']}, "
                    f"rank {repair_target['rank']}, "
                    f"DRAM device {repair_target['device']}, "
                    f"bank group {repair_target['bank_group']}, "
                    f"bank {repair_target['bank']}; "
                    f"row {repair_target['row']}; "
                    f"repair count {repair_count}"
                ),
                details={
                    **repair_target,
                    "repair_count": repair_count,
                },
                display_lines=(
                    f"{ppr_name} applied:",
                    f"Chiplet:      {repair_target['chiplet']}",
                    f"Controller:   {repair_target['controller']}",
                    f"Channel:      {repair_target['channel']}",
                    f"DIMM:         {repair_target['dimm']}",
                    f"Subchannel:   {repair_target['subchannel']}",
                    f"Rank:         {repair_target['rank']}",
                    f"DRAM device:  {repair_target['device']}",
                    f"Bank group:   {repair_target['bank_group']}",
                    f"Bank:         {repair_target['bank']}",
                    f"Row:          {repair_target['row']}",
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
    def _perform_page_offline(parameters: Dict[str, int]) -> ActionResult:
        page_count = parameters["page_count"]
        chunk_count = parameters["chunk_count"]
        if chunk_count > 1:
            context = (
                f"Offlined {page_count} physical pages for Page Offline "
                f"batch 0x{parameters['batch_id']:016x}, "
                f"chunk {parameters['chunk_index'] + 1} of {chunk_count}"
            )
        elif page_count == 1:
            address = parameters["page_ranges"][0]["start_address"]
            context = (
                f"Offlined physical page 0x{address:016x}"
            )
        else:
            context = f"Offlined {page_count} physical pages"
        return ActionResult(
            status=ACTION_COMPLETED,
            context=context,
            details=parameters,
        )

    def _schedule_retraining(
            self,
            manager_id: str,
            cpad_data: Dict[str, Any],
            metadata: Dict[str, Any],
            parameters: Dict[str, int]) -> ActionResult:
        return self._schedule_reset_action(
            manager_id, cpad_data, metadata, "retraining", parameters,
            context=(
                f"Memory retraining is pending for SoC partition "
                f"{metadata['partition_id']}"
            ),
        )

    def _schedule_reset_action(
            self,
            manager_id: str,
            cpad_data: Dict[str, Any],
            metadata: Dict[str, Any],
            kind: str,
            parameters: Dict[str, int],
            context: str) -> ActionResult:
        key = (
            metadata["partition_id"],
            metadata["creator_id"].lower(),
            metadata["record_id"],
        )
        if key not in self._pending_reset_actions:
            self._pending_reset_actions[key] = PendingResetAction(
                key=key,
                manager_id=manager_id,
                cpad_data=copy.deepcopy(cpad_data),
                metadata=copy.deepcopy(metadata),
                kind=kind,
                parameters=copy.deepcopy(parameters),
            )
        return ActionResult(
            status=ACTION_PENDING,
            context=context,
        )
