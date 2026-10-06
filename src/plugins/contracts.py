#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.

"""Public contracts for simulator feature plugins."""

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Iterable


_SUPPORTED_METHODS = frozenset({'GET', 'POST', 'PATCH', 'DELETE'})


def _normalize_path(path: str) -> str:
    if path != '/':
        return path.rstrip('/')
    return path


@dataclass(frozen=True)
class PluginRoute:
    """One plugin-owned Redfish route and its supported HTTP methods."""

    path: str
    methods: FrozenSet[str]

    def __init__(self, path: str, methods: Iterable[str]):
        normalized_path = _normalize_path(path)
        normalized_methods = frozenset(method.upper() for method in methods)

        if not normalized_path.startswith('/'):
            raise ValueError("Plugin route paths must start with '/'")
        if not normalized_methods:
            raise ValueError("Plugin routes must declare at least one method")

        unsupported = normalized_methods - _SUPPORTED_METHODS
        if unsupported:
            methods_list = ', '.join(sorted(unsupported))
            raise ValueError(
                f"Unsupported plugin route methods: {methods_list}"
            )

        object.__setattr__(self, 'path', normalized_path)
        object.__setattr__(self, 'methods', normalized_methods)

    @property
    def specificity(self) -> tuple:
        """Sort fixed, longer paths before parameterized paths."""
        wildcard_count = self.path.count('*') + self.path.count('{')
        return (-wildcard_count, len(self.path))

    @property
    def conflict_key(self) -> str:
        """Canonicalize equivalent single-segment wildcard routes."""
        segments = self.path.split('/')
        canonical_segments = [
            '*'
            if segment == '*' or (
                segment.startswith('{') and segment.endswith('}')
            )
            else segment
            for segment in segments
        ]
        return '/'.join(canonical_segments)

    def matches(self, request_path: str) -> bool:
        """Return whether a request path matches this route pattern."""
        pattern = re.escape(self.path)
        pattern = pattern.replace(r'\*', r'[^/]+')
        pattern = re.sub(r'\\\{[^{}]+\\\}', r'[^/]+', pattern)
        return re.fullmatch(pattern, _normalize_path(request_path)) is not None


class PluginContext:
    """Narrow access to shared simulator capabilities."""

    def __init__(
        self,
        server_config: Any,
        publish_event: Callable[[Dict[str, Any]], int],
    ):
        self.server_config = server_config
        self._publish_event = publish_event

    def publish_event(self, event: Dict[str, Any]) -> int:
        """Publish a Redfish event through the core EventService."""
        return self._publish_event(event)
