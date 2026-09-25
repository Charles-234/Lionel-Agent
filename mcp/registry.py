"""MCP server registry with explicit allowlisting and approval metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from lionel_platform.definitions import MCPServerSpec


@dataclass(frozen=True)
class MCPToolGrant:
    server_name: str
    tool_name: str
    role_id: str
    approved: bool = False


class MCPRegistry:
    """Register MCP endpoints; transport and tool calls stay policy-gated."""

    def __init__(self) -> None:
        self._servers: Dict[str, MCPServerSpec] = {}
        self._grants: Dict[tuple[str, str, str], MCPToolGrant] = {}

    def register(self, server: MCPServerSpec) -> None:
        if server.enabled and not server.requires_approval:
            raise ValueError("enabled MCP servers must require approval")
        self._servers[server.name] = server

    def get(self, name: str) -> MCPServerSpec:
        server = self._servers.get(name)
        if server is None or not server.enabled:
            raise KeyError("MCP server unavailable")
        return server

    def grant_tool(self, server_name: str, tool_name: str, role_id: str, approved: bool = False) -> None:
        server = self.get(server_name)
        if server.allowed_tools and tool_name not in server.allowed_tools:
            raise ValueError("MCP tool is outside the server allowlist")
        self._grants[(server_name, tool_name, role_id)] = MCPToolGrant(
            server_name, tool_name, role_id, approved
        )

    def can_use(self, server_name: str, tool_name: str, role_id: str) -> bool:
        grant = self._grants.get((server_name, tool_name, role_id))
        return bool(grant and grant.approved and self.get(server_name).enabled)

    def list(self) -> list[MCPServerSpec]:
        return list(self._servers.values())
