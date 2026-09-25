"""Single execution facade for all current and future tool calls."""
from typing import Any, Dict, Optional

from tools.base import ToolResult
from tools.policy import AuthorizationScope
from tools.registry import get_registry


def execute(
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    capability_id: Optional[str] = None,
    scope: Optional[AuthorizationScope] = None,
    execution_mode: str = "real",
    confirmed: bool = False,
) -> ToolResult:
    return get_registry().authorize_and_run(
        tool_name,
        arguments,
        capability_id=capability_id,
        scope=scope,
        execution_mode=execution_mode,
        confirmed=confirmed,
    )
