"""Central governed registry for Lionel tools."""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from tools.base import Tool, ToolResult
from tools.policy import AuthorizationScope, PolicyGateway

@dataclass
class ToolRecord:
    tool: Tool
    enabled: bool = True
    source: str = "builtin"

class ToolRegistry:
    def __init__(self, policy: Optional[PolicyGateway] = None):
        self.policy = policy or PolicyGateway()
        self._records: Dict[str, ToolRecord] = {}

    def register(self, tool: Tool, *, source: str = "builtin", enabled: bool = True) -> None:
        if not tool.name: raise ValueError("Tool must have a name")
        if tool.name in self._records: raise ValueError(f"Tool already registered: {tool.name}")
        self._records[tool.name] = ToolRecord(tool, enabled, source)

    def get(self, name: str) -> Tool:
        record = self._records.get(name)
        if not record or not record.enabled: raise KeyError(f"Tool unavailable: {name}")
        return record.tool

    def list(self) -> list[Dict[str, Any]]:
        return [{**r.tool.manifest(), "enabled": r.enabled, "registry_source": r.source} for r in self._records.values()]

    def authorize_and_run(self, name: str, arguments: Dict[str, Any], *, scope: Optional[AuthorizationScope] = None, execution_mode: str = "real", confirmed: bool = False) -> ToolResult:
        tool = self.get(name)
        decision = self.policy.evaluate(tool, arguments, scope, execution_mode, confirmed)
        if not decision.allowed:
            return ToolResult(False, error=decision.reason, tool_name=name, execution_mode=execution_mode, verified=False)
        if execution_mode == "simulation":
            from tools.mocks import MOCK_TOOLS
            mock_cls = MOCK_TOOLS.get(name)
            if not mock_cls:
                return ToolResult(False, error="Simulation implementation is unavailable.", tool_name=name, execution_mode="simulation", verified=False)
            result = mock_cls().run(**arguments)
            result.execution_mode = "simulation"; result.verified = False
            if not result.evidence: result.evidence = [{"source":"mock", "verified":False}]
            return result
        result = tool.run(**arguments)
        result.execution_mode = "real"
        result.verified = bool(decision.metadata.get("verified", False))
        return result

_default_registry: Optional[ToolRegistry] = None
def get_registry() -> ToolRegistry:
    global _default_registry
    if _default_registry is None:
        from tools.recon.subfinder import Subfinder
        from tools.recon.httpx import Httpx
        from tools.recon.nuclei import Nuclei
        _default_registry = ToolRegistry()
        for tool in (Subfinder(), Httpx(), Nuclei()): _default_registry.register(tool)
    return _default_registry
