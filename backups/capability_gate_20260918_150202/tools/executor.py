"""Small execution facade used by chains and future agent tool calls."""
from typing import Any, Dict, Optional
from tools.base import ToolResult
from tools.policy import AuthorizationScope
from tools.registry import get_registry


def execute(
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    scope: Optional[AuthorizationScope] = None,
    execution_mode: str = "real",
    confirmed: bool = False,
) -> ToolResult:
    return get_registry().authorize_and_run(
        tool_name,
        arguments,
        scope=scope,
        execution_mode=execution_mode,
        confirmed=confirmed,
    )
