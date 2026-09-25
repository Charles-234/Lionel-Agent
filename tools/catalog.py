"""Skill-to-tool binding catalog.

Maps skills and capability IDs to the governed tools that implement them.
This closes the gap between the informational skill retriever and actual
tool execution: when the LLM references a skill, this catalog provides the
tool ID and required capability context so the governed executor can run it.

Uses declarative mapping only. Authorization still flows through PolicyGateway.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Mapping: capability_id -> list of tool IDs that implement it
CAPABILITY_TO_TOOLS: Dict[str, List[str]] = {
    "reconnaissance": ["subfinder", "httpx"],
    "security_testing": ["nuclei"],
    "networking": ["httpx", "nmap"],
    "research": ["web_fetch"],
    "intelligence": ["ip_lookup"],
    "automation": ["filesystem", "e2b_sandbox"],
    "coding": ["e2b_sandbox"],
    "data_engineering": ["filesystem"],
    "document_processing": ["filesystem"],
    "security_audit": [],           # No dedicated tool yet
    "forensics": [],                # No dedicated tool yet
    "malware_analysis": [],         # No dedicated tool yet
    "reverse_engineering": [],      # No dedicated tool yet
    "cloud_operations": [],         # No dedicated tool yet
    "deployment": [],               # No dedicated tool yet
    "observability": [],            # No dedicated tool yet
    "incident_response": [],        # No dedicated tool yet
    "intelligence": ["ip_lookup"],
}

# Mapping: skill name keyword -> suggestion of tool to use
# Loose matching: the LLM uses this as a hint, not a hard rule.
SKILL_TO_TOOL_HINTS: Dict[str, str] = {
    "subdomain": "subfinder",
    "subdomain_enumeration": "subfinder",
    "http_probing": "httpx",
    "service_discovery": "httpx",
    "vulnerability_scan": "nuclei",
    "vuln_scan": "nuclei",
    "web_fetch": "web_fetch",
    "web_page": "web_fetch",
    "public_research": "web_fetch",
    "ip_lookup": "ip_lookup",
    "ip_geolocation": "ip_lookup",
    "ip_intelligence": "ip_lookup",
    "file_read": "filesystem",
    "file_write": "filesystem",
    "file_edit": "filesystem",
    "sandbox": "e2b_sandbox",
    "code_execution": "e2b_sandbox",
    "run_code": "e2b_sandbox",
    "execute_code": "e2b_sandbox",
    "nmap": "nmap",
    "network_scan": "nmap",
}


@dataclass
class ToolBinding:
    """One binding from a capability/skill to a tool."""
    capability_id: str
    tool_id: str
    requires_scope: bool = False
    requires_confirmation: bool = False
    risk_level: str = "low"


def get_tools_for_capability(capability_id: str) -> List[str]:
    """Return tool IDs that implement a capability."""
    return CAPABILITY_TO_TOOLS.get(capability_id, [])


def suggest_tool_for_skill(skill_name: str) -> Optional[str]:
    """Suggest a tool ID based on a skill name keyword match."""
    name_lower = skill_name.lower()
    for keyword, tool_id in SKILL_TO_TOOL_HINTS.items():
        if keyword in name_lower:
            return tool_id
    return None


def suggest_tool_for_query(query: str) -> List[str]:
    """Return suggested tool IDs for a free-text query."""
    query_lower = query.lower()
    suggestions: Dict[str, float] = {}
    for keyword, tool_id in SKILL_TO_TOOL_HINTS.items():
        if keyword in query_lower:
            suggestions[tool_id] = suggestions.get(tool_id, 0) + 1
    # Sort by frequency, most suggested first
    return sorted(suggestions, key=suggestions.get, reverse=True)


def get_binding(capability_id: str, tool_id: str) -> Optional[ToolBinding]:
    """Get the full binding metadata for a capability+tool pair."""
    if tool_id not in get_tools_for_capability(capability_id):
        return None
    # Derive risk level from the tool registry if available
    try:
        from tools_registry import get_tool as get_spec
        spec = get_spec(tool_id)
        return ToolBinding(
            capability_id=capability_id,
            tool_id=tool_id,
            requires_scope=spec.requires_authorized_target or spec.network_access,
            requires_confirmation=spec.confirmation_required,
            risk_level=spec.risk_level,
        )
    except Exception:
        return ToolBinding(
            capability_id=capability_id,
            tool_id=tool_id,
            requires_scope=True,
            requires_confirmation=True,
            risk_level="medium",
        )


def list_capability_gaps() -> Dict[str, List[str]]:
    """Return capabilities that have no implemented tools.

    Useful for planning which tools to build next.
    """
    from tools_registry.base import TOOLS
    gaps: Dict[str, List[str]] = {}
    for cap_id, tool_ids in CAPABILITY_TO_TOOLS.items():
        implemented = [
            tid for tid in tool_ids
            if tid in TOOLS and TOOLS[tid].implemented
        ]
        if not implemented:
            gaps[cap_id] = tool_ids
    return gaps


def list_tool_gaps_for_capability(capability_id: str) -> List[str]:
    """Return tool IDs registered for a capability but not yet implemented."""
    from tools_registry.base import TOOLS
    result: List[str] = []
    for tid in CAPABILITY_TO_TOOLS.get(capability_id, []):
        spec = TOOLS.get(tid)
        if spec is None or not spec.implemented:
            result.append(tid)
    return result
