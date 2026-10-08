"""Shared state-reset helpers for the RAS API demos."""

from urllib.parse import urljoin

import requests

from init_error_pipeline import init_error_pipeline
from reset_server import clean_temp_cper_dirs, reset_log_entries


EVENT_SUBSCRIPTIONS_PATH = "/redfish/v1/EventService/Subscriptions"
DEMO_EVENT_DESTINATION = "http://localhost:8888/events"
DEMO_SUBSCRIPTION_CONTEXT = "RAS Events Subscription"
DEMO_REGISTRY_PREFIX = "OCPRAS"
DEMO_RESOURCE_TYPE = "LogEntry"


class DemoStateError(RuntimeError):
    """Raised when demo state cannot be reset safely."""


def _request_json(http_client, url, *, auth, timeout):
    try:
        response = http_client.get(url, auth=auth, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DemoStateError(f"GET {url} failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise DemoStateError(f"GET {url} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise DemoStateError(f"GET {url} returned a non-object JSON response")
    return payload


def _delete(http_client, url, *, auth, timeout):
    try:
        response = http_client.delete(url, auth=auth, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DemoStateError(f"DELETE {url} failed: {exc}") from exc


def is_demo_event_subscription(subscription, destination):
    """Return whether a Redfish subscription belongs to this demo listener."""
    if not isinstance(subscription, dict):
        return False
    registry_prefixes = subscription.get("RegistryPrefixes", [])
    resource_types = subscription.get("ResourceTypes", [])
    return (
        subscription.get("Destination", "").rstrip("/")
        == destination.rstrip("/")
        and subscription.get("Context") == DEMO_SUBSCRIPTION_CONTEXT
        and isinstance(registry_prefixes, list)
        and DEMO_REGISTRY_PREFIX in registry_prefixes
        and isinstance(resource_types, list)
        and DEMO_RESOURCE_TYPE in resource_types
    )


def remove_demo_event_subscriptions(
        base_url, username, password, *,
        destination=DEMO_EVENT_DESTINATION, timeout=5, http_client=requests):
    """Delete stale subscriptions owned by the local RAS demo listener."""
    collection_url = urljoin(
        f"{base_url.rstrip('/')}/", EVENT_SUBSCRIPTIONS_PATH.lstrip("/"))
    auth = (username, password)
    collection = _request_json(
        http_client, collection_url, auth=auth, timeout=timeout)
    members = collection.get("Members")
    if not isinstance(members, list):
        raise DemoStateError(
            f"GET {collection_url} returned an invalid Members collection")

    removed = 0
    for member in members:
        if not isinstance(member, dict) or not isinstance(
                member.get("@odata.id"), str):
            raise DemoStateError(
                f"GET {collection_url} returned an invalid member reference")
        member_url = urljoin(
            f"{base_url.rstrip('/')}/", member["@odata.id"].lstrip("/"))
        subscription = _request_json(
            http_client, member_url, auth=auth, timeout=timeout)
        if not is_demo_event_subscription(subscription, destination):
            continue
        _delete(http_client, member_url, auth=auth, timeout=timeout)
        removed += 1
    return removed


def reset_demo_state(
        entries_path, manager_id, output_dir, base_url, username, password,
        *, destination=DEMO_EVENT_DESTINATION, http_client=requests):
    """Reset server, client, and demo-owned EventService state."""
    reset_log_entries(entries_path, manager_id)
    clean_temp_cper_dirs()
    init_error_pipeline(output_dir)
    return remove_demo_event_subscriptions(
        base_url,
        username,
        password,
        destination=destination,
        http_client=http_client,
    )
