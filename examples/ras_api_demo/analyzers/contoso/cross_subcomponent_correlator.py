"""Cross-subcomponent correlation seam for Contoso analyzer results."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List


def correlate_subcomponent_results(
        results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine independent results without changing their findings or CPADs."""
    subcomponents: List[Dict[str, Any]] = [copy.deepcopy(result)
                                           for result in results]
    return {
        "subcomponents": subcomponents,
        "findings": [
            finding
            for result in subcomponents
            for finding in result.get("findings", [])
        ],
        "cpads": [
            cpad
            for result in subcomponents
            for cpad in result.get("cpads", [])
        ],
        "correlations": [],
    }
