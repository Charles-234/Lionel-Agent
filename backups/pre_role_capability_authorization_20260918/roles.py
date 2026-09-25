"""Lionel role registry.

Roles are declarative metadata used by the runtime for routing and policy.
They do not create separate LLM agents.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    description: str
    skill_categories: List[str] = field(default_factory=list)
    capability_categories: List[str] = field(default_factory=list)
    preferred_task_types: List[str] = field(default_factory=list)
    risk_level: str = "low"
    output_expectations: List[str] = field(default_factory=list)


ROLES: Dict[str, Role] = {
    "offensive_security": Role(
        "offensive_security", "Offensive Security & Penetration Testing",
        "Authorized security assessment, penetration testing, and adversary simulation.",
        ["cybersecurity", "offensive_security"], ["reconnaissance", "security_testing"],
        ["reasoning", "tool_use"], "high", ["scope", "evidence", "findings", "remediation"]
    ),
    "digital_forensics_soc": Role(
        "digital_forensics_soc", "Digital Forensics & SOC Operations",
        "Defensive monitoring, triage, investigation, and forensic workflows.",
        ["cybersecurity", "defensive_security"], ["forensics", "security_operations"],
        ["reasoning", "tool_use"], "high", ["timeline", "evidence", "confidence", "actions"]
    ),
    "software_ai_architecture": Role(
        "software_ai_architecture", "Software Engineering & AI Architecture",
        "Software development, architecture, automation, and AI-system engineering.",
        ["software_engineering", "ai"], ["coding", "architecture", "automation"],
        ["coding", "reasoning"], "medium", ["design", "implementation", "tests", "tradeoffs"]
    ),
    "ui_ux_3d_web": Role(
        "ui_ux_3d_web", "UI/UX & 3D Web Development",
        "Web interfaces, interaction design, frontend engineering, and 3D web experiences.",
        ["web_design", "ui_ux"], ["web_design", "frontend"],
        ["coding", "vision"], "medium", ["structure", "accessibility", "implementation"]
    ),
    "data_engineering_analytics": Role(
        "data_engineering_analytics", "Data Engineering & Analytics",
        "Data processing, analysis, pipelines, and analytical workflows.",
        ["data", "analytics"], ["data_analysis", "data_engineering"],
        ["coding", "reasoning"], "medium", ["method", "results", "validation"]
    ),
    "cloud_infrastructure_security": Role(
        "cloud_infrastructure_security", "Cloud Infrastructure & Security",
        "Cloud architecture, infrastructure operations, and cloud security.",
        ["cloud", "infrastructure", "security"], ["cloud_operations", "security_testing"],
        ["reasoning", "tool_use"], "high", ["architecture", "controls", "evidence"]
    ),
    "optical_fiber_network": Role(
        "optical_fiber_network", "Optical Fiber & Network Infrastructure",
        "Networking, network infrastructure, fiber optics, and troubleshooting.",
        ["networking", "fiber"], ["networking", "diagnostics"],
        ["reasoning", "tool_use"], "medium", ["topology", "diagnosis", "procedure"]
    ),
    "growth_business": Role(
        "growth_business", "Growth Automation & Business Engineering",
        "Business workflows, growth systems, process automation, and optimization.",
        ["business", "automation"], ["automation", "analytics"],
        ["reasoning", "coding"], "medium", ["process", "metrics", "implementation"]
    ),
    "content_copywriting": Role(
        "content_copywriting", "Content Creation & Copywriting",
        "Content planning, drafting, editing, and communication.",
        ["content", "writing"], ["content_generation", "editing"],
        ["chat", "reasoning"], "low", ["audience", "clarity", "tone"]
    ),
    "virtual_assistant": Role(
        "virtual_assistant", "Virtual Assistant & Personal AI",
        "General assistance, organization, research, and task support.",
        ["productivity", "general"], ["organization", "research"],
        ["chat", "reasoning"], "medium", ["clear_actions", "status", "next_steps"]
    ),
    "financial_analysis": Role(
        "financial_analysis", "Financial Analysis & Investment",
        "Financial analysis, modeling, research, and decision-support calculations.",
        ["finance", "analytics"], ["financial_analysis", "data_analysis"],
        ["reasoning", "coding"], "medium", ["assumptions", "calculations", "sources"]
    ),
    "legal_compliance": Role(
        "legal_compliance", "Legal Advisory & Compliance",
        "Legal-information research, compliance workflows, and documentation support.",
        ["legal", "compliance"], ["research", "document_processing"],
        ["reasoning", "document_processing"], "medium", ["jurisdiction", "sources", "caveats"]
    ),
    "security_gRC": Role(
        "security_grc", "Security Auditing & GRC",
        "Security controls, governance, risk, compliance, and audit support.",
        ["security", "grc"], ["security_audit", "document_processing"],
        ["reasoning", "document_processing"], "high", ["control", "evidence", "gap", "recommendation"]
    ),
    "test_automation": Role(
        "test_automation", "Test Automation & Practicals",
        "Testing, practical exercises, validation, and repeatable automation.",
        ["testing", "automation"], ["testing", "automation"],
        ["coding", "tool_use"], "medium", ["test_case", "result", "failure", "fix"]
    ),
    "deployment_operations": Role(
        "deployment_operations", "Deployment & Operations",
        "Deployment, CI/CD, reliability, observability, and operational workflows.",
        ["devops", "operations"], ["deployment", "observability"],
        ["coding", "tool_use"], "high", ["preflight", "change", "verification", "rollback"]
    ),
    "malware_reverse_engineering": Role(
        "malware_reverse_engineering", "Advanced Malware Reverse Engineering",
        "Authorized malware analysis, reverse engineering, and defensive research.",
        ["malware", "reverse_engineering"], ["malware_analysis", "reverse_engineering"],
        ["reasoning", "tool_use"], "high", ["sample", "evidence", "behavior", "indicators"]
    ),
    "threat_intelligence": Role(
        "threat_intelligence", "Cyber Threat Intelligence",
        "Threat intelligence collection, analysis, correlation, and reporting.",
        ["threat_intelligence", "cybersecurity"], ["reconnaissance", "intelligence"],
        ["reasoning", "tool_use"], "high", ["source", "confidence", "indicators", "assessment"]
    ),
    "malware_defensive_evasion": Role(
        "malware_defensive_evasion", "Malware Analysis & Defensive Evasion Research",
        "Defensive research into malware behavior and evasion techniques.",
        ["malware", "defensive_research"], ["malware_analysis", "research"],
        ["reasoning", "tool_use"], "high", ["scope", "evidence", "defensive_context"]
    ),
    "enterprise_incident_response": Role(
        "enterprise_incident_response", "Enterprise Incident Response",
        "Incident handling, containment planning, investigation, and recovery support.",
        ["incident_response", "security"], ["incident_response", "forensics"],
        ["reasoning", "tool_use"], "high", ["timeline", "evidence", "containment", "recovery"]
    ),
}


def get_role(role_id: str) -> Role:
    return ROLES[role_id]


def list_roles() -> List[Role]:
    return list(ROLES.values())
