from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class PlanStep:
    description: str
    capability: str
    requires_tool: bool = False


@dataclass(frozen=True)
class Plan:
    task_type: str
    objective: str
    steps: List[PlanStep]
    execution_allowed: bool = False


class Planner:
    """
    Deterministic planning layer.

    The planner describes what should happen.
    It does not authorize or execute tools.
    """

    def plan(
        self,
        task_type: str,
        objective: str,
        steps: List[PlanStep],
    ) -> Plan:
        if not task_type.strip():
            raise ValueError("task_type is required")

        if not objective.strip():
            raise ValueError("objective is required")

        if not steps:
            raise ValueError("at least one plan step is required")

        return Plan(
            task_type=task_type,
            objective=objective,
            steps=list(steps),
            execution_allowed=False,
        )
