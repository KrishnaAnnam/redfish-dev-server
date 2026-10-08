import json
import logging

from src.core.discovery import PlatformDiscovery
from src.core.registry import platform_registry


def test_generic_platform_does_not_require_provider(
        tmp_path, monkeypatch, caplog):
    (tmp_path / "platform_config.json").write_text(
        json.dumps({
            "platform_id": "test",
            "platform_type": "generic",
            "display_name": "Test Platform",
        }),
        encoding="utf-8",
    )

    def fail_auto_discovery():
        raise AssertionError("generic platforms must not discover providers")

    monkeypatch.setattr(
        platform_registry, "auto_discover_providers", fail_auto_discovery)

    with caplog.at_level(logging.INFO):
        provider = PlatformDiscovery(
            str(tmp_path)).discover_and_load_platform()

    assert provider is None
    assert "no platform provider is required" in caplog.text
    assert "Failed to load platform provider" not in caplog.text
