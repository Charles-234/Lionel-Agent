"""Execution registry bridge with capability-aware authorization."""
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
        if not tool.name:
            raise ValueError("Tool must have a name")
        if tool.name in self._records:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._records[tool.name] = ToolRecord(tool, enabled, source)

    def get(self, name: str) -> Tool:
        record = self._records.get(name)
        if not record or not record.enabled:
            raise KeyError(f"Tool unavailable: {name}")
        return record.tool

    def list(self) -> list[Dict[str, Any]]:
        return [
            {**r.tool.manifest(), "enabled": r.enabled, "registry_source": r.source}
            for r in self._records.values()
        ]

    def authorize_and_run(
        self,
        name: str,
        arguments: Dict[str, Any],
        *,
        capability_id: Optional[str] = None,
        role_id: Optional[str] = None,
        scope: Optional[AuthorizationScope] = None,
        execution_mode: str = "real",
        confirmed: bool = False,
    ) -> ToolResult:
        if not isinstance(name, str) or not name.strip():
            return ToolResult(
                success=False,
                error="Unknown tool requested.",
                tool_name="",
                execution_mode=execution_mode,
                verified=False,
            )
        if not isinstance(arguments, dict):
            return ToolResult(
                success=False,
                error="Tool arguments must be supplied as a mapping.",
                tool_name=name,
                execution_mode=execution_mode,
                verified=False,
            )
        if len(arguments) > 32:
            return ToolResult(
                success=False,
                error="Too many tool arguments supplied.",
                tool_name=name,
                execution_mode=execution_mode,
                verified=False,
            )
        for key, value in arguments.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                return ToolResult(
                    success=False,
                    error="Invalid tool argument name.",
                    tool_name=name,
                    execution_mode=execution_mode,
                    verified=False,
                )
            if isinstance(value, str) and len(value) > 10_000:
                return ToolResult(
                    success=False,
                    error="Tool argument value is too large.",
                    tool_name=name,
                    execution_mode=execution_mode,
                    verified=False,
                )
            if isinstance(value, (list, tuple)) and len(value) > 256:
                return ToolResult(
                    success=False,
                    error="Tool argument list is too large.",
                    tool_name=name,
                    execution_mode=execution_mode,
                    verified=False,
                )
        try:
            tool = self.get(name)
        except KeyError:
            return ToolResult(
                success=False,
                error="Tool unavailable.",
                tool_name=name,
                execution_mode=execution_mode,
                verified=False,
            )
        decision = self.policy.evaluate(
            tool,
            arguments,
            scope=scope,
            execution_mode=execution_mode,
            confirmed=confirmed,
            capability_id=capability_id,
            role_id=role_id,
        )
        if not decision.allowed:
            return ToolResult(
                success=False,
                error=decision.reason,
                tool_name=name,
                execution_mode=execution_mode,
                verified=False,
                requires_confirmation=bool(decision.requires_confirmation),
            )

        if execution_mode == "simulation":
            from tools.mocks import MOCK_TOOLS
            mock_cls = MOCK_TOOLS.get(name)
            if not mock_cls:
                return ToolResult(
                    success=False,
                    error="Simulation implementation is unavailable.",
                    tool_name=name,
                    execution_mode="simulation",
                    verified=False,
                )
            try:
                result = mock_cls().run(**arguments)
            except TypeError:
                return ToolResult(
                    success=False,
                    error="Tool arguments did not match the tool schema.",
                    tool_name=name,
                    execution_mode="simulation",
                    verified=False,
                )
            except Exception:
                return ToolResult(
                    success=False,
                    error="Tool execution failed safely without details.",
                    tool_name=name,
                    execution_mode="simulation",
                    verified=False,
                )
            result.execution_mode = "simulation"
            result.verified = False
            return result

        try:
            result = tool.run(**arguments)
        except TypeError:
            return ToolResult(
                success=False,
                error="Tool arguments did not match the tool schema.",
                tool_name=name,
                execution_mode=execution_mode,
                verified=False,
            )
        except Exception:
            # Never echo tool internals, paths, or stderr text to callers.
            return ToolResult(
                success=False,
                error="Tool execution failed safely without details.",
                tool_name=name,
                execution_mode=execution_mode,
                verified=False,
            )
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
        from tools.web_fetcher import WebFetcher
        from tools.ip_lookup import IPLookup
        from tools.filesystem import FileSystemTool
        from tools.e2b_sandbox import E2BSandboxTool

        _default_registry = ToolRegistry()
        for tool in (Subfinder(), Httpx(), Nuclei(), WebFetcher(), IPLookup()):
            _default_registry.register(tool)
        _default_registry.register(FileSystemTool(), source="builtin")
        _default_registry.register(E2BSandboxTool(), source="builtin")
    return _default_registry
