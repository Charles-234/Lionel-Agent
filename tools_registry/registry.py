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

register_tool(ToolSpec(
    id="ip_lookup",
    name="IP Lookup",
    category="intelligence",
    description="Resolve a public IP to coarse location and network metadata",
    capabilities=["intelligence"],
    risk_level="low",
    network_access=True,
    credentials_required=True,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="builtin",
    implemented=True,
    enabled=True,
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

# Governed filesystem tool — sandboxed read/write within a scoped directory.
register_tool(ToolSpec(
    id="filesystem",
    name="FileSystem",
    category="filesystem",
    description="Read, write, list, and delete files within a sandboxed directory.",
    capabilities=["automation", "data_engineering", "document_processing"],
    risk_level="medium",
    network_access=False,
    filesystem_access=True,
    supports_simulation=True,
    execution_modes=["real", "simulation"],
    provenance="builtin",
    binary="",
))

# Governed E2B code execution sandbox — isolated code execution.
# Requires E2B_API_KEY in .env and the e2b SDK installed.
register_tool(ToolSpec(
    id="e2b_sandbox",
    name="E2B Sandbox",
    category="code_execution",
    description="Execute code in an isolated E2B sandbox. Requires E2B_API_KEY.",
    capabilities=["coding", "automation"],
    risk_level="high",
    network_access=False,
    filesystem_access=False,
    credentials_required=True,
    supports_simulation=False,
    execution_modes=["real"],
    confirmation_required=True,
    provenance="builtin",
    binary="",
    implemented=True,
    enabled=True,
))
