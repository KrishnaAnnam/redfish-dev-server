"""Common result types for endpoint-specific CPAD action providers."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


ACTION_COMPLETED = "completed"
ACTION_FAILED = "failed"
ACTION_PENDING = "pending"


@dataclass(frozen=True)
class ActionResult:
    """Result returned after an endpoint accepts a CPAD for execution."""

    status: str
    return_code: int = 0x00
    reason: Optional[str] = None
    context: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    display_lines: Tuple[str, ...] = ()
