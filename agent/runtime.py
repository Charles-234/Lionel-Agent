"""Bounded preparation runtime for Lionel's agent-brain layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from agent.planner import Plan
from agent.request_normalizer import NormalizedRequest, normalize_request
from agent.request_planner import RequestPlanner
from agent.role_selector import RoleSelection, select_role


DecisionStatus = Literal[
    "NEEDS_TASK_TYPE",
    "ROLE_AMBIGUOUS",
    "ROLE_UNAVAILABLE",
    "PLAN_REQUIRED",
    "PLAN_READY",
]


@dataclass(frozen=True)
class AgentDecision:
    """The result of one bounded, non-executing agent preparation pass."""

    status: DecisionStatus
    message: str
    request: NormalizedRequest
    role_selection: RoleSelection
    plan: Optional[Plan] = None


class AgentRuntime:
    """Coordinate normalization, role selection, and planning without acting.

    Each call performs exactly one preparation pass.  This is intentionally
    not an autonomous loop: it neither retries nor invokes authorization,
    tools, policy, execution, or audit infrastructure.
    """

    def __init__(self, *, planner: Optional[RequestPlanner] = None):
        self.planner = planner or RequestPlanner()

    def decide(
        self,
        raw_text: str,
        *,
        task_type: Optional[str] = None,
        step_descriptions: Optional[Sequence[str]] = None,
        requires_tool: bool = False,
    ) -> AgentDecision:
        """Prepare a deterministic plan only after task and role are resolved."""
        request = normalize_request(raw_text, task_type=task_type)
        role_selection = select_role(request)

        if request.task_type is None:
            return AgentDecision(
                "NEEDS_TASK_TYPE",
                "A task type is required before planning.",
                request,
                role_selection,
            )
        if role_selection.status == "AMBIGUOUS":
            return AgentDecision(
                "ROLE_AMBIGUOUS",
                "Role selection is ambiguous and requires resolution before planning.",
                request,
                role_selection,
            )
        if role_selection.status == "NO_MATCH":
            return AgentDecision(
                "ROLE_UNAVAILABLE",
                "No declared role matches the task type.",
                request,
                role_selection,
            )
        if step_descriptions is None:
            return AgentDecision(
                "PLAN_REQUIRED",
                "Explicit plan step descriptions are required before planning.",
                request,
                role_selection,
            )

        plan = self.planner.create_multi_step_plan(
            task_type=request.task_type,
            objective=request.objective,
            descriptions=step_descriptions,
            requires_tool=requires_tool,
        )
        return AgentDecision(
            "PLAN_READY",
            "A non-executable plan is ready for downstream governance.",
            request,
            role_selection,
            plan,
        )
