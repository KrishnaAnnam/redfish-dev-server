#!/usr/bin/env python3
"""Stage a Micron endpoint inventory from a MERC retry-read input CSV."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


RETRY_READ_FIELDS = (
    "msn",
    "mpn",
    "rr_log",
    "rr_addr1",
    "rr_addr2",
    "rr_parity",
    "intel_hw_gen",
)
MICRON_MANUFACTURER_ID = ["0x80", "0x2C"]
Module = Tuple[str, str]


def read_input_modules(path: Path) -> List[Module]:
    """Return unique (serial number, part number) pairs in input order."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = [field for field in RETRY_READ_FIELDS
                       if field not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(
                    f"input CSV is missing columns: {', '.join(missing)}")
            modules = []
            parts_by_serial: Dict[str, str] = {}
            for line_number, row in enumerate(reader, start=2):
                empty = [
                    field for field in RETRY_READ_FIELDS
                    if not str(row.get(field, "")).strip()
                ]
                if empty:
                    raise ValueError(
                        f"input CSV line {line_number} has empty fields: "
                        f"{', '.join(empty)}")
                module = (
                    str(row["msn"]).strip(),
                    str(row["mpn"]).strip(),
                )
                serial, part = module
                if len(serial.encode("ascii", errors="ignore")) != len(serial):
                    raise ValueError(f"input CSV line {line_number} msn must be ASCII")
                if len(part.encode("ascii", errors="ignore")) != len(part):
                    raise ValueError(f"input CSV line {line_number} mpn must be ASCII")
                if len(serial) > 18:
                    raise ValueError(
                        f"input CSV line {line_number} msn exceeds 18 characters")
                if len(part) > 24:
                    raise ValueError(
                        f"input CSV line {line_number} mpn exceeds 24 characters")
                previous = parts_by_serial.setdefault(serial, part)
                if previous != part:
                    raise ValueError(
                        f"module serial {serial} has multiple part numbers")
                if module not in modules:
                    modules.append(module)
    except OSError as exc:
        raise ValueError(f"cannot read input CSV {path}: {exc}") from exc
    if not modules:
        raise ValueError("input CSV contains no error rows")
    return modules


def iter_dimms(configuration: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for endpoint in configuration.get("ras_endpoints", []):
        memory = endpoint.get("memory", {})
        socket = memory.get("socket")
        for controller in memory.get("memory_controllers", []):
            for dimm in controller.get("dimms", []):
                yield {
                    "socket": socket,
                    "chiplet": controller.get("chiplet"),
                    "controller": controller.get("controller"),
                    "dimm_config": dimm,
                }


def _add_second_socket(configuration: Dict[str, Any]) -> None:
    endpoints = configuration.get("ras_endpoints", [])
    if len(endpoints) != 1:
        raise ValueError(
            "Micron demo can expand only a single-endpoint template")
    endpoint = copy.deepcopy(endpoints[0])
    endpoint["id"] = "Endpoint-2"
    endpoint["name"] = "Contoso CPU Socket 1 RAS Endpoint with Micron DIMMs"
    endpoint["description"] = (
        "RAS API-capable endpoint for Contoso CPU socket 1 "
        "with Micron DDR5 DIMMs")
    endpoint["partition_id"] = str(uuid.uuid5(
        uuid.NAMESPACE_URL, "ras-api-demo-micron-socket-1"))
    endpoint["fru_id"] = str(uuid.uuid5(
        uuid.NAMESPACE_URL, "ras-api-demo-micron-processor-socket-1"))
    endpoint["fru_text"] = "Contoso CPU Socket 1"
    endpoint["memory"]["socket"] = 1
    for controller in endpoint["memory"]["memory_controllers"]:
        for dimm in controller["dimms"]:
            slot = (
                f"s1-c{controller['chiplet']}-mc{controller['controller']}"
                f"-ch{dimm['channel']}-d{dimm['dimm']}")
            dimm["fru_id"] = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"ras-api-demo-micron-{slot}"))
            dimm["fru_text"] = (
                f"DIMM S1 C{controller['chiplet']}"
                f"H{dimm['channel']}D{dimm['dimm']}")
            dimm["spd"]["serial_number"] = (
                f"MICRON-S1-C{controller['chiplet']}"
                f"H{dimm['channel']}D{dimm['dimm']}")
    endpoints.append(endpoint)


def stage_configuration(
        template_path: Path,
        input_path: Path,
        output_path: Path) -> None:
    modules = read_input_modules(input_path)
    try:
        with template_path.open(encoding="utf-8") as stream:
            configuration = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read Micron endpoint template {template_path}: {exc}") from exc

    slots = list(iter_dimms(configuration))
    if len(modules) > len(slots):
        _add_second_socket(configuration)
        slots = list(iter_dimms(configuration))
    if len(modules) > len(slots):
        raise ValueError(
            f"input references {len(modules)} DIMMs, but the demo has "
            f"only {len(slots)} DIMM slots")
    for module, slot in zip(modules, slots):
        serial, part = module
        spd = slot["dimm_config"]["spd"]
        spd.update({
            "serial_number": serial,
            "part_number": part,
            "module_manufacturer_id": MICRON_MANUFACTURER_ID,
            "dram_manufacturer_id": MICRON_MANUFACTURER_ID,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(configuration, stream, indent=3)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage Micron DIMMs from a MERC retry-read CSV")
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        stage_configuration(args.template, args.input_file, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
