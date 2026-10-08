#!/usr/bin/env python3
"""Guided RAS demo that routes Micron DIMM errors through MERC."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from prepare_micron_demo import read_input_modules
from ras_api_plugin_demo import RASAPIPluginDemo

CONTOSO_DIR = Path(__file__).resolve().parent / "analyzers" / "contoso"
if str(CONTOSO_DIR) not in sys.path:
    sys.path.insert(0, str(CONTOSO_DIR))

MICRON_MERC_INPUT_FILE = "MICRON_MERC_INPUT_FILE"
Module = Tuple[str, str]


class MicronRASAPIPluginDemo(RASAPIPluginDemo):
    """Run one Micron CPER trigger per DIMM represented in a MERC input file."""

    def __init__(self, input_file: Path, endpoint_config: Path):
        super().__init__()
        self.micron_input_file = input_file.resolve(strict=True)
        self.endpoint_config = endpoint_config.resolve(strict=True)
        os.environ[MICRON_MERC_INPUT_FILE] = str(self.micron_input_file)
        self.modules = read_input_modules(self.micron_input_file)
        self.targets = self._load_targets()

    def _load_targets(self) -> Dict[Module, Dict[str, Any]]:
        with self.endpoint_config.open(encoding="utf-8") as stream:
            configuration = json.load(stream)
        targets = {}
        for endpoint in configuration["ras_endpoints"]:
            memory = endpoint["memory"]
            for controller in memory["memory_controllers"]:
                for dimm in controller["dimms"]:
                    spd = dimm["spd"]
                    target = {
                        "partition_id": endpoint["partition_id"],
                        "socket": memory["socket"],
                        "chiplet": controller["chiplet"],
                        "controller": controller["controller"],
                        "channel": dimm["channel"],
                        "dimm": dimm["dimm"],
                    }
                    targets[(spd["serial_number"], spd["part_number"])] = target
        missing = [f"{serial}/{part}" for serial, part in self.modules
                   if (serial, part) not in targets]
        if missing:
            raise ValueError(
                "Micron endpoint configuration has no DIMM for: "
                + ", ".join(missing))
        return targets

    def _build_trigger_cpad(
            self, module: Module, target: Dict[str, Any], sequence: int) -> Path:
        row = 1234 + sequence
        column = 567
        output = self.generated_cpad_dir / f"micron_trigger_{sequence}.cpad"
        overrides = {
            "cpad.partitionID": target["partition_id"],
            "section.socket": target["socket"],
            "section.subcomponent.chiplet": target["chiplet"],
            "section.subcomponent.controller": target["controller"],
            "section.additional.channel": target["channel"],
            "section.additional.dimm": target["dimm"],
            "section.additional.subchannel": 0,
            "section.additional.rank": 0,
            "section.additional.device": 3,
            "section.additional.bank_group": 2,
            "section.additional.bank": 3,
            "section.additional.row": row,
            "section.additional.column": column,
        }
        command = [
            sys.executable,
            str(self.injector),
            "inject",
            "--spec", str(self.injection_spec),
            "--endpoint-config", str(self.endpoint_config),
            "--beat", "dram=3;dq=0;beats=2",
            "--out", str(output),
        ]
        for name, value in overrides.items():
            command.extend(["--set", f"{name}={value}"])
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "Contoso Error Injector failed for Micron DIMM "
                f"{module[0]}: {result.stderr.strip() or result.stdout.strip()}")
        return output

    def _inject_module(self, module: Module, sequence: int) -> None:
        target = self.targets[module]
        print("\n" + "=" * 80)
        print(f"MICRON MERC ANALYSIS TRIGGER: {module[0]} / {module[1]}")
        print("=" * 80)
        cpad_path = self._build_trigger_cpad(module, target, sequence)
        self._submit_binary_cpad(
            cpad_path,
            verbose_steps=True,
            source_label=f"Micron DIMM trigger for {module[0]} / {module[1]}",
        )

    def run(self) -> None:
        self.print_banner()
        print(f"Micron MERC input: {self.micron_input_file}")
        print(f"Micron DIMMs represented: {len(self.modules)}")
        if not self.analysis.print_discovery_report(show_memory_analyzers=True):
            raise RuntimeError("no usable analyzers were discovered")

        input("\nPress Enter to discover and start monitoring the host...")
        monitored = self.analysis.add_host(
            name="Contoso Cloud Host Gen 1 with Micron DIMMs",
            host=self.BMC_HOST,
            port=self.BMC_PORT,
            username=self.BMC_USER,
            password=self.BMC_PASSWORD,
            manager_id=self.MANAGER_ID,
        )
        if not monitored:
            raise RuntimeError("the Micron demo host is not monitorable")
        self.server_online = True

        for sequence, module in enumerate(self.modules, start=1):
            input(
                f"\nPress Enter to analyze scenario for failing "
                f"Micron DIMM {module[0]} "
                f"({sequence}/{len(self.modules)})...")
            self._inject_module(module, sequence)
            self._wait_and_analyze(
                "\nSEVERAL ERRORS HAVE GENERATED PREVIOUS CPERs THAT THE ANALYZER HAS COLLECTED "
                "\nPRESS ENTER TO RECEIVE THE LATEST CPERs FOR A "
                "RELIABLE ASSESSMENT")

        print("\n" + "=" * 80)
        print("Micron MERC RAS API Demonstration Complete")
        print("=" * 80)
        print("MERC classifications were mapped to policy-checked RAS actions.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the RAS API demo with the Micron MERC analyzer")
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--endpoint-config", required=True, type=Path)
    args = parser.parse_args()
    demo = None
    try:
        demo = MicronRASAPIPluginDemo(args.input_file, args.endpoint_config)
        demo.run()
    except KeyboardInterrupt:
        print("\nMicron demonstration cancelled.")
    finally:
        if demo is not None:
            demo.analysis.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
