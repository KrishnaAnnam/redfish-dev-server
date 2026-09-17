#!/usr/bin/env python3
"""Focused tests for the OpenCompute_FaultMgmt OEM URI namespace."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.ras.discovery import RASDiscoveryHandler, RAS_SERVICE_URI  # noqa: E402
from src.plugins.ras.plugin import RASPlugin  # noqa: E402
from src.plugins.ras.provider import RASHandler  # noqa: E402


NAMESPACE = "OpenCompute_FaultMgmt"
RETIRED_NAMESPACE = "OCPRASAPIWS"
SERVICE_URI = f"/redfish/v1/Oem/{NAMESPACE}/RASService"


def test_service_root_advertises_new_namespace_only():
    root_path = ROOT / "mockups" / "ras_gen1" / "redfish" / "v1" / "index.json"
    with root_path.open(encoding="utf-8") as stream:
        service_root = json.load(stream)

    oem = service_root["Oem"]
    assert NAMESPACE in oem
    assert RETIRED_NAMESPACE not in oem
    assert oem[NAMESPACE]["RASService"]["@odata.id"] == SERVICE_URI


def test_discovery_resources_use_new_namespace():
    discovery = RASDiscoveryHandler()

    assert RAS_SERVICE_URI == SERVICE_URI
    assert discovery.service_root_extension()["RASService"]["@odata.id"] == SERVICE_URI
    assert discovery.ras_service()[1]["@odata.id"] == SERVICE_URI
    assert discovery.endpoint_collection()[1]["@odata.id"] == f"{SERVICE_URI}/RASEndpoints"
    assert discovery.endpoint("Endpoint-1")[1]["@odata.id"] == \
        f"{SERVICE_URI}/RASEndpoints/Endpoint-1"
    assert discovery.submit_cpad_action_info()[1]["@odata.id"] == \
        f"{SERVICE_URI}/SubmitCPADActionInfo"
    assert discovery.ras_service()[1]["Actions"]["#RASService.SubmitCPAD"]["target"] == \
        f"{SERVICE_URI}/Actions/RASService.SubmitCPAD"


def test_configured_endpoint_does_not_publish_memory_repair_capabilities():
    discovery = RASDiscoveryHandler(
        mockup_dir=str(ROOT / "mockups" / "ras_gen1"))

    endpoint = discovery.endpoint("Endpoint-1")[1]

    assert endpoint["PartitionID"] == "22222222-3333-4444-5555-666666666666"
    assert endpoint["CreatorID"] == "11111111-2222-3333-4444-555555555555"
    assert "MemoryRepairCapabilities" not in endpoint
    assert "memory_repair_capabilities" not in endpoint


def test_plugin_routes_accept_new_and_reject_retired_namespace():
    plugin = RASPlugin()
    routes = plugin.get_routes()

    assert routes
    assert all(NAMESPACE in route for route in routes)
    assert all(RETIRED_NAMESPACE not in route for route in routes)
    assert plugin.handles_path(SERVICE_URI)
    assert plugin.handles_path(f"{SERVICE_URI}/RASEndpoints/Endpoint-1")
    assert plugin.handles_path(f"{SERVICE_URI}/SubmitCPADActionInfo")
    assert plugin.handles_path(f"{SERVICE_URI}/Actions/RASService.SubmitCPAD")
    assert plugin.handles_path(f"{SERVICE_URI}/Actions/RASService.SubmitCPAD/")
    assert not plugin.handles_path(
        f"/redfish/v1/Oem/{RETIRED_NAMESPACE}/RASService")


def test_provider_routes_accept_new_and_reject_retired_namespace():
    provider = RASHandler()

    assert provider.can_handle_path(SERVICE_URI)
    assert provider.can_handle_path(f"{SERVICE_URI}/RASEndpoints/Endpoint-1")
    assert provider.can_handle_path(f"{SERVICE_URI}/SubmitCPADActionInfo")
    assert provider.can_handle_path(f"{SERVICE_URI}/Actions/RASService.SubmitCPAD")
    assert not provider.can_handle_path(
        f"/redfish/v1/Oem/{RETIRED_NAMESPACE}/RASService")


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
