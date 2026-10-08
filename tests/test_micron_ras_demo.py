import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
sys.path.insert(0, str(RAS_DEMO_DIR))

import ras_api_plugin_demo_micron as micron_demo  # noqa: E402


def test_micron_demo_preserves_staged_endpoint_config(
        tmp_path, monkeypatch):
    input_path = tmp_path / "retry.csv"
    input_path.write_text(
        "msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen\n"
        "SERIAL,PART,1,2,3,4,2\n",
        encoding="utf-8",
    )
    endpoint_config = tmp_path / "ras_endpoint_config.json"
    endpoint_config.write_text(
        json.dumps({
            "ras_endpoints": [{
                "partition_id": "partition",
                "memory": {
                    "socket": 0,
                    "memory_organization": {
                        "version": 1,
                        "address_translation": "contoso-simple-v1",
                        "dimm_size_gib": 128,
                    },
                    "memory_controllers": [{
                        "chiplet": 0,
                        "controller": 0,
                        "dimms": [{
                            "channel": 0,
                            "dimm": 0,
                            "spd": {
                                "serial_number": "SERIAL",
                                "part_number": "PART",
                            },
                        }],
                    }],
                },
            }],
        }),
        encoding="utf-8",
    )

    default_config = tmp_path / "default_endpoint_config.json"

    def initialize_base(instance):
        instance.endpoint_config = default_config

    monkeypatch.setattr(
        micron_demo.RASAPIPluginDemo, "__init__", initialize_base)

    demo = micron_demo.MicronRASAPIPluginDemo(
        input_path, endpoint_config)

    assert demo.endpoint_config == endpoint_config.resolve()
    assert demo.targets[("SERIAL", "PART")]["dimm"] == 0

    demo.generated_cpad_dir = tmp_path
    demo.injector = tmp_path / "injector-contoso.py"
    demo.injection_spec = tmp_path / "memory.inject.json"
    invocation = {}

    def capture_run(command, **_kwargs):
        invocation["command"] = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(micron_demo.subprocess, "run", capture_run)

    demo._build_trigger_cpad(
        ("SERIAL", "PART"), demo.targets[("SERIAL", "PART")], 1)

    command = invocation["command"]
    config_index = command.index("--endpoint-config") + 1
    assert command[config_index] == str(endpoint_config.resolve())
    assert not any(
        argument.startswith("section.errorAddress=")
        for argument in command
    )
