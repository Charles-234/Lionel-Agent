"""Declarative platform capability definitions.

These definitions describe selectable capabilities. They do not execute
external tools; execution remains behind Lionel's policy gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    task_types: tuple[str, ...] = ("chat",)
    local: bool = False
    configured: bool = False


@dataclass(frozen=True)
class ConnectorSpec:
    name: str
    kind: str
    enabled: bool = False
    inbound: bool = False
    outbound: bool = False
    requires_approval: bool = True


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    command: str
    args: tuple[str, ...] = ()
    transport: str = "stdio"
    endpoint: str = ""
    enabled: bool = False
    requires_approval: bool = True
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxProfile:
    name: str
    backend: str
    network: bool = False
    filesystem: bool = False
    timeout_seconds: int = 60
    enabled: bool = False


@dataclass
class CapabilityCatalog:
    models: Dict[str, ModelProfile] = field(default_factory=dict)
    connectors: Dict[str, ConnectorSpec] = field(default_factory=dict)
    mcp_servers: Dict[str, MCPServerSpec] = field(default_factory=dict)
    sandboxes: Dict[str, SandboxProfile] = field(default_factory=dict)

    def add_model(self, profile: ModelProfile) -> None:
        self.models[profile.name] = profile

    def add_connector(self, connector: ConnectorSpec) -> None:
        self.connectors[connector.name] = connector

    def add_mcp_server(self, server: MCPServerSpec) -> None:
        if not server.name or not server.command:
            raise ValueError("MCP server name and command are required")
        self.mcp_servers[server.name] = server

    def add_sandbox(self, sandbox: SandboxProfile) -> None:
        if sandbox.timeout_seconds <= 0 or sandbox.timeout_seconds > 3600:
            raise ValueError("sandbox timeout must be between 1 and 3600 seconds")
        self.sandboxes[sandbox.name] = sandbox

    def enabled_for(self, task_type: str) -> list[ModelProfile]:
        return [
            profile for profile in self.models.values()
            if profile.configured and task_type in profile.task_types
        ]


def default_catalog() -> CapabilityCatalog:
    catalog = CapabilityCatalog()
    catalog.add_connector(ConnectorSpec("telegram", "messaging", enabled=True, inbound=True, outbound=True, requires_approval=False))
    for name in ("discord", "slack", "whatsapp", "signal", "email", "cli", "home_assistant"):
        catalog.add_connector(ConnectorSpec(name, "messaging" if name != "home_assistant" else "operations"))
    catalog.add_connector(ConnectorSpec("browser", "automation", requires_approval=True))
    catalog.add_connector(ConnectorSpec("web_search", "search", requires_approval=True))
    catalog.add_sandbox(SandboxProfile("local", "local", network=False, filesystem=False))
    catalog.add_sandbox(SandboxProfile("docker", "docker", network=False, filesystem=False))
    catalog.add_sandbox(SandboxProfile("ssh", "ssh", network=True, filesystem=False))
    catalog.add_sandbox(SandboxProfile("modal", "modal", network=True, filesystem=False))
    return catalog
