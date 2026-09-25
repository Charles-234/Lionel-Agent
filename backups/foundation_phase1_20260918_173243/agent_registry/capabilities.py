"""Lionel capability registry.

Capabilities describe what Lionel can potentially do. Availability and authorization
are enforced elsewhere by the tool/policy layers.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    category: str
    description: str
    modality: List[str]
    requires_tool: bool = False
    requires_network: bool = False
    risk_level: str = "low"
    enabled: bool = True
    provenance: str = "builtin"


CAPABILITIES: Dict[str, Capability] = {
    "chat": Capability("chat", "General Conversation", "general", "General text interaction.", ["text"]),
    "reasoning": Capability("reasoning", "Reasoning", "general", "Analysis and structured problem solving.", ["text"]),
    "coding": Capability("coding", "Software Development", "software", "Write, inspect, explain, and test code.", ["text", "code"]),
    "web_design": Capability("web_design", "Web Design", "web", "Design and implement web interfaces.", ["text", "image", "code"]),
    "document_processing": Capability("document_processing", "Document Processing", "documents", "Extract, analyze, transform, and summarize documents.", ["document", "text"]),
    "data_analysis": Capability("data_analysis", "Data Analysis", "data", "Analyze structured and unstructured data.", ["text", "document", "structured_data"]),
    "research": Capability("research", "Research", "research", "Gather and synthesize information from permitted sources.", ["text", "document"], True, True, "medium"),
    "reconnaissance": Capability("reconnaissance", "Reconnaissance", "security", "Authorized reconnaissance workflows.", ["text", "structured_data"], True, True, "high"),
    "security_testing": Capability("security_testing", "Security Testing", "security", "Authorized security assessment workflows.", ["text", "structured_data"], True, True, "high"),
    "malware_analysis": Capability("malware_analysis", "Malware Analysis", "security", "Authorized malware analysis and defensive research.", ["text", "document", "structured_data"], True, False, "high"),
    "reverse_engineering": Capability("reverse_engineering", "Reverse Engineering", "security", "Authorized binary and software reverse engineering.", ["text", "code", "document"], True, False, "high"),
    "security_audit": Capability("security_audit", "Security Audit", "security", "Security control and configuration assessment.", ["text", "document", "structured_data"], True, False, "high"),
    "security_operations": Capability("security_operations", "Security Operations", "security", "SOC triage and operational analysis.", ["text", "structured_data"], True, True, "high"),
    "forensics": Capability("forensics", "Digital Forensics", "security", "Evidence-oriented forensic analysis.", ["document", "structured_data"], True, False, "high"),
    "networking": Capability("networking", "Network Diagnostics", "infrastructure", "Network troubleshooting and diagnostics.", ["text", "structured_data"], True, True, "medium"),
    "cloud_operations": Capability("cloud_operations", "Cloud Operations", "infrastructure", "Cloud infrastructure workflows.", ["text", "structured_data"], True, True, "high"),
    "automation": Capability("automation", "Automation", "engineering", "Automate repeatable workflows.", ["text", "code"], True, False, "medium"),
    "testing": Capability("testing", "Testing", "engineering", "Run and interpret controlled tests.", ["text", "code"], True, False, "medium"),
    "deployment": Capability("deployment", "Deployment", "operations", "Controlled application deployment workflows.", ["text", "code"], True, True, "high"),
    "observability": Capability("observability", "Observability", "operations", "Logs, metrics, health checks, and diagnostics.", ["text", "structured_data"], True, True, "medium"),
    "financial_analysis": Capability("financial_analysis", "Financial Analysis", "finance", "Financial calculations and analysis.", ["text", "structured_data", "document"]),
    "content_generation": Capability("content_generation", "Content Generation", "content", "Draft and transform content.", ["text"]),
    "editing": Capability("editing", "Editing", "content", "Review and improve supplied content.", ["text", "document"]),
    "organization": Capability("organization", "Organization", "productivity", "Organize information and tasks.", ["text", "structured_data"]),
    "intelligence": Capability("intelligence", "Threat Intelligence", "security", "Correlate intelligence from permitted sources.", ["text", "structured_data"], True, True, "high"),
    "architecture": Capability("architecture", "Architecture", "software", "Software and AI system architecture workflows.", ["text", "code", "structured_data"], True, False, "medium"),
    "frontend": Capability("frontend", "Frontend Engineering", "web", "Frontend implementation and interface engineering.", ["text", "image", "code"], True, False, "medium"),
    "data_engineering": Capability("data_engineering", "Data Engineering", "data", "Data processing, pipelines, and engineering workflows.", ["text", "code", "structured_data"], True, False, "medium"),
    "diagnostics": Capability("diagnostics", "Diagnostics", "infrastructure", "Infrastructure and system diagnostic workflows.", ["text", "structured_data"], True, True, "medium"),
    "analytics": Capability("analytics", "Analytics", "data", "Analytical and metrics-oriented workflows.", ["text", "structured_data"], True, False, "medium"),
    "incident_response": Capability("incident_response", "Incident Response", "security", "Authorized incident handling, containment, and recovery support.", ["text", "document", "structured_data"], True, True, "high"),
}


def get_capability(capability_id: str) -> Capability:
    return CAPABILITIES[capability_id]


def list_capabilities() -> List[Capability]:
    return list(CAPABILITIES.values())
