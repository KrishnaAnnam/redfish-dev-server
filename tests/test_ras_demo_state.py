#!/usr/bin/env python3
"""Tests for shared RAS demo state cleanup."""

import sys
from pathlib import Path

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
RAS_DEMO_DIR = ROOT / "examples" / "ras_api_demo"
sys.path.insert(0, str(RAS_DEMO_DIR))

import demo_state  # noqa: E402


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, get_responses, delete_responses=None):
        self.get_responses = get_responses
        self.delete_responses = delete_responses or {}
        self.get_calls = []
        self.delete_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses[url]

    def delete(self, url, **kwargs):
        self.delete_calls.append((url, kwargs))
        return self.delete_responses[url]


def _subscription(destination=demo_state.DEMO_EVENT_DESTINATION, **overrides):
    subscription = {
        "Destination": destination,
        "Context": demo_state.DEMO_SUBSCRIPTION_CONTEXT,
        "RegistryPrefixes": [demo_state.DEMO_REGISTRY_PREFIX],
        "ResourceTypes": [demo_state.DEMO_RESOURCE_TYPE],
    }
    subscription.update(overrides)
    return subscription


def test_remove_demo_subscriptions_preserves_other_clients():
    base_url = "http://bmc.example"
    collection_url = (
        f"{base_url}{demo_state.EVENT_SUBSCRIPTIONS_PATH}")
    owned_url = f"{collection_url}/owned"
    other_destination_url = f"{collection_url}/other-destination"
    other_context_url = f"{collection_url}/other-context"
    client = FakeHttpClient(
        {
            collection_url: FakeResponse({
                "Members": [
                    {"@odata.id": (
                        f"{demo_state.EVENT_SUBSCRIPTIONS_PATH}/owned")},
                    {"@odata.id": (
                        f"{demo_state.EVENT_SUBSCRIPTIONS_PATH}/"
                        "other-destination")},
                    {"@odata.id": (
                        f"{demo_state.EVENT_SUBSCRIPTIONS_PATH}/other-context")},
                ],
            }),
            owned_url: FakeResponse(_subscription()),
            other_destination_url: FakeResponse(
                _subscription("http://other.example/events")),
            other_context_url: FakeResponse(
                _subscription(Context="another-client")),
        },
        {owned_url: FakeResponse(status_code=204)},
    )

    removed = demo_state.remove_demo_event_subscriptions(
        base_url, "demo", "secret", http_client=client)

    assert removed == 1
    assert [call[0] for call in client.delete_calls] == [owned_url]
    assert all(call[1] == {
        "auth": ("demo", "secret"),
        "timeout": 5,
    } for call in client.get_calls + client.delete_calls)


def test_remove_demo_subscriptions_reports_collection_http_failure():
    collection_url = (
        f"http://bmc.example{demo_state.EVENT_SUBSCRIPTIONS_PATH}")
    client = FakeHttpClient({
        collection_url: FakeResponse(status_code=503),
    })

    with pytest.raises(
            demo_state.DemoStateError,
            match=r"GET .*Subscriptions failed: HTTP 503"):
        demo_state.remove_demo_event_subscriptions(
            "http://bmc.example", "demo", "secret", http_client=client)


def test_remove_demo_subscriptions_reports_delete_http_failure():
    base_url = "http://bmc.example"
    collection_url = (
        f"{base_url}{demo_state.EVENT_SUBSCRIPTIONS_PATH}")
    owned_url = f"{collection_url}/owned"
    client = FakeHttpClient(
        {
            collection_url: FakeResponse({
                "Members": [{
                    "@odata.id": (
                        f"{demo_state.EVENT_SUBSCRIPTIONS_PATH}/owned"),
                }],
            }),
            owned_url: FakeResponse(_subscription()),
        },
        {owned_url: FakeResponse(status_code=500)},
    )

    with pytest.raises(
            demo_state.DemoStateError,
            match=r"DELETE .*owned failed: HTTP 500"):
        demo_state.remove_demo_event_subscriptions(
            base_url, "demo", "secret", http_client=client)


def test_reset_demo_state_runs_all_shared_cleanup(monkeypatch, tmp_path):
    calls = []
    entries_path = tmp_path / "Entries"
    output_dir = tmp_path / "output"
    http_client = object()

    monkeypatch.setattr(
        demo_state,
        "reset_log_entries",
        lambda path, manager: calls.append(
            ("reset_log_entries", path, manager)),
    )
    monkeypatch.setattr(
        demo_state,
        "clean_temp_cper_dirs",
        lambda: calls.append(("clean_temp_cper_dirs",)),
    )
    monkeypatch.setattr(
        demo_state,
        "init_error_pipeline",
        lambda path: calls.append(("init_error_pipeline", path)),
    )
    monkeypatch.setattr(
        demo_state,
        "remove_demo_event_subscriptions",
        lambda *args, **kwargs:
        calls.append(("remove_demo_event_subscriptions", args, kwargs)) or 2,
    )

    removed = demo_state.reset_demo_state(
        entries_path,
        "System",
        output_dir,
        "http://bmc.example",
        "demo",
        "secret",
        destination="http://listener.example/events",
        http_client=http_client,
    )

    assert removed == 2
    assert calls == [
        ("reset_log_entries", entries_path, "System"),
        ("clean_temp_cper_dirs",),
        ("init_error_pipeline", output_dir),
        (
            "remove_demo_event_subscriptions",
            ("http://bmc.example", "demo", "secret"),
            {
                "destination": "http://listener.example/events",
                "http_client": http_client,
            },
        ),
    ]
