"""Stable Python contract for Contoso memory-vendor analyzer shims."""

from __future__ import annotations

import copy
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Tuple


SHIM_API_VERSION = 5
ManufacturerId = Tuple[int, int]


class ShimContractError(ValueError):
    """Raised when a memory shim does not satisfy the integration contract."""


def _manufacturer_id(value: Any) -> ManufacturerId:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ShimContractError(
            "dram_manufacturer_ids entries must contain exactly two bytes")
    if any(not isinstance(byte, int) or isinstance(byte, bool) or
           not 0 <= byte <= 0xFF for byte in value):
        raise ShimContractError(
            "dram_manufacturer_ids entries must contain byte values")
    return value[0], value[1]


@dataclass(frozen=True)
class MemoryShim:
    """One validated memory-vendor shim implementation."""

    name: str
    version: str
    path: Path
    manufacturer_ids: Tuple[ManufacturerId, ...]
    module: ModuleType

    def analyze(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Invoke the shim with isolated input and validate its result shape."""
        try:
            result = self.module.analyze_memory_events(copy.deepcopy(events))
        except Exception as exc:
            raise ShimContractError(f"{self.name} failed: {exc}") from exc
        if not isinstance(result, list):
            raise ShimContractError(
                f"{self.name} must return a list of action requests")
        if any(not isinstance(request, dict) for request in result):
            raise ShimContractError(
                f"{self.name} returned an action request that is not an object")
        return result


def _load_shim(path: Path) -> MemoryShim:
    module_name = f"contoso_memory_shim_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ShimContractError(f"could not load shim module {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    info = getattr(module, "SHIM_INFO", None)
    if not isinstance(info, dict):
        raise ShimContractError(f"{path.name} must define SHIM_INFO")
    if info.get("api_version") != SHIM_API_VERSION:
        raise ShimContractError(
            f"{path.name} has unsupported api_version {info.get('api_version')}")
    name = info.get("name")
    version = info.get("version")
    if not isinstance(name, str) or not name:
        raise ShimContractError(f"{path.name} SHIM_INFO.name must be a string")
    if not isinstance(version, str) or not version:
        raise ShimContractError(f"{path.name} SHIM_INFO.version must be a string")
    raw_ids = info.get("dram_manufacturer_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ShimContractError(
            f"{path.name} must register at least one DRAM manufacturer ID")
    manufacturer_ids = tuple(_manufacturer_id(value) for value in raw_ids)
    if len(set(manufacturer_ids)) != len(manufacturer_ids):
        raise ShimContractError(f"{path.name} registers a duplicate manufacturer ID")
    if not callable(getattr(module, "analyze_memory_events", None)):
        raise ShimContractError(
            f"{path.name} must define analyze_memory_events(events)")
    return MemoryShim(name, version, path, manufacturer_ids, module)


def discover_memory_shims(directory: Path | str):
    """Return manufacturer-ID shim mappings plus non-fatal discovery errors."""
    directory = Path(directory)
    shims: Dict[ManufacturerId, MemoryShim] = {}
    errors = []
    for path in sorted(directory.glob("analyzer_*.py")):
        try:
            shim = _load_shim(path)
            conflicts = [
                manufacturer_id for manufacturer_id in shim.manufacturer_ids
                if manufacturer_id in shims
            ]
            if conflicts:
                manufacturer_id = conflicts[0]
                raise ShimContractError(
                    f"{path.name} duplicates manufacturer ID "
                    f"{manufacturer_id} from {shims[manufacturer_id].path.name}")
            for manufacturer_id in shim.manufacturer_ids:
                shims[manufacturer_id] = shim
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    return shims, errors
