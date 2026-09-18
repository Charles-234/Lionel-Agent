"""Resolve capabilities to currently executable registered tools."""
from typing import List
from .base import ToolSpec, tools_for_capability


def resolve_tools(capability_id: str, *, include_unimplemented: bool = False) -> List[ToolSpec]:
    tools = tools_for_capability(capability_id)
    if include_unimplemented:
        from .base import TOOLS
        return [
            t for t in TOOLS.values()
            if capability_id in t.capabilities and t.enabled
        ]
    return [t for t in tools if t.implemented]
