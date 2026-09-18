from typing import Dict

from agent.planner import Plan, PlanStep, Planner


TASK_CAPABILITIES: Dict[str, str] = {
    "chat": "chat",
    "reconnaissance": "reconnaissance",
    "security_testing": "security_testing",
    "security_audit": "security_audit",
    "security_operations": "security_operations",
    "malware_analysis": "malware_analysis",
    "reverse_engineering": "reverse_engineering",
    "forensics": "forensics",
    "networking": "networking",
    "coding": "coding",
    "web_design": "web_design",
    "frontend": "frontend",
    "data_analysis": "data_analysis",
    "data_engineering": "data_engineering",
    "research": "research",
    "document_processing": "document_processing",
    "automation": "automation",
    "testing": "testing",
    "deployment": "deployment",
    "cloud_operations": "cloud_operations",
    "incident_response": "incident_response",
    "diagnostics": "diagnostics",
    "architecture": "architecture",
    "analytics": "analytics",
    "organization": "organization",
    "content_generation": "content_generation",
    "editing": "editing",
    "financial_analysis": "financial_analysis",
    "intelligence": "intelligence",
    "reasoning": "reasoning",
}


class RequestPlanner:
    """
    Controlled adapter from a known task type to the deterministic Planner.

    This component does not authorize capabilities and does not execute tools.
    """

    def __init__(self, planner=None):
        self.planner = planner or Planner()

    def create_plan(
        self,
        task_type: str,
        objective: str,
        description: str,
        requires_tool: bool = False,
    ) -> Plan:
        normalized = task_type.strip().lower()

        if normalized not in TASK_CAPABILITIES:
            raise ValueError(f"Unknown task type: {task_type}")

        capability = TASK_CAPABILITIES[normalized]

        step = PlanStep(
            description=description,
            capability=capability,
            requires_tool=requires_tool,
        )

        return self.planner.plan(
            task_type=normalized,
            objective=objective,
            steps=[step],
        )
