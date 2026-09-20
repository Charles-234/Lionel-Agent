"""Lionel's initial tool registry.

Only tools already represented by the current project are marked implemented.
Future tools are intentionally not registered as executable merely because an
external repository exists.
"""
from .base import ToolSpec, register_tool

# Existing governed reconnaissance tools.
register_tool(ToolSpec(
    id="subfinder",
    name="Subfinder",
    category="reconnaissance",
    description="Subdomain discovery through the existing governed adapter.",
    capabilities=["reconnaissance"],
    risk_level="high",
    network_access=True,
    requires_authorized_target=True,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="existing_project_adapter",
    binary="subfinder",
))

register_tool(ToolSpec(
    id="httpx",
    name="httpx",
    category="reconnaissance",
    description="HTTP service probing through the existing governed adapter.",
    capabilities=["reconnaissance", "networking"],
    risk_level="high",
    network_access=True,
    requires_authorized_target=True,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="existing_project_adapter",
    binary="httpx",
))

register_tool(ToolSpec(
    id="nuclei",
    name="Nuclei",
    category="security_testing",
    description="Template-based security testing through the existing governed adapter.",
    capabilities=["security_testing", "reconnaissance"],
    risk_level="high",
    network_access=True,
    requires_authorized_target=True,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="existing_project_adapter",
    binary="nuclei",
))

register_tool(ToolSpec(
    id="nmap",
    name="Nmap",
    category="networking",
    description="Network discovery and service enumeration.",
    capabilities=["networking", "reconnaissance", "security_testing"],
    risk_level="high",
    network_access=True,
    requires_authorized_target=True,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="environment_detected",
    binary="nmap",
))

# Governed public-research fetcher (reads text only, never executes content).
register_tool(ToolSpec(
    id="web_fetch",
    name="Web Fetcher",
    category="research",
    description="Fetch and clean public web page text for research workflows.",
    capabilities=["research"],
    risk_level="medium",
    network_access=True,
    requires_authorized_target=False,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="builtin",
))

# Explicit capability placeholders: visible to the architecture, but not executable.
for tool_id, name, category, capability in (
    ("amass", "Amass", "reconnaissance", "reconnaissance"),
    ("recon_ng", "recon-ng", "reconnaissance", "reconnaissance"),
    ("spiderfoot", "SpiderFoot", "reconnaissance", "reconnaissance"),
    ("ghidra", "Ghidra", "reverse_engineering", "reverse_engineering"),
):
    register_tool(ToolSpec(
        id=tool_id,
        name=name,
        category=category,
        description=f"Planned integration: {name}. Not executable until an adapter is implemented and verified.",
        capabilities=[capability],
        risk_level="high",
        provenance="planned_external_integration",
        implemented=False,
        enabled=False,
    ))
