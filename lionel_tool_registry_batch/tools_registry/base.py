"""Machine-readable tool contracts for Lionel.

The registry describes tools; it does not itself authorize execution.
PolicyGateway remains the enforcement point.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    category: str
    description: str
    capabilities: List[str] = field(default_factory=list)
    risk_level: str = "low"
    network_access: bool = False
    filesystem_access: bool = False
    credentials_required: bool = False
    requires_authorized_target: bool = False
    supports_simulation: bool = False
    confirmation_required: bool = False
    execution_modes: List[str] = field(default_factory=lambda: ["real"])
    provenance: str = "builtin"
    implemented: bool = True
    enabled: bool = True
    binary: Optional[str] = None


TOOLS: Dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> None:
    if spec.id in TOOLS:
        raise ValueError(f"Duplicate tool id: {spec.id}")
    TOOLS[spec.id] = spec


def get_tool(tool_id: str) -> ToolSpec:
    return TOOLS[tool_id]


def list_tools() -> List[ToolSpec]:
    return list(TOOLS.values())


def tools_for_capability(capability_id: str) -> List[ToolSpec]:
    return [t for t in TOOLS.values() if capability_id in t.capabilities and t.enabled]
