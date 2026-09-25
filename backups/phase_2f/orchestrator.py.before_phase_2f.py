"""Lionel V1 governed orchestration layer.

Coordinates:
request -> planning -> role/capability authorization -> tool resolution
-> executable adapter discovery.

This layer does not implement tools itself.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent.request_planner import RequestPlanner
from tools.registry import get_registry
from tools_registry.resolver import resolve_tools


@dataclass(frozen=True)
class OrchestrationResult:
    success: bool
    status: str
    message: str
    task_type: str
    capability_id: Optional[str] = None
    tool_id: Optional[str] = None
    execution_mode: str = "simulation"
    data: Optional[Dict[str, Any]] = None


class LionelOrchestrator:
    """Governed V1 orchestration boundary."""

    def __init__(
        self,
        *,
        planner: Optional[RequestPlanner] = None,
        registry=None,
    ):
        self.planner = planner or RequestPlanner()
        self.registry = registry or get_registry()

    def inspect_tools_for_capability(self, capability_id: str) -> list[str]:
        """Return implemented/enabled declared tool IDs for a capability.

        This is discovery only. It does not authorize or execute anything.
        """
        specs = resolve_tools(capability_id)

        return [
            spec.id
            for spec in specs
            if bool(getattr(spec, "implemented", False))
            and bool(getattr(spec, "enabled", False))
        ]

    def create_plan(
        self,
        task_type: str,
        objective: str,
        description: Optional[str] = None,
    ):
        """Create a deterministic plan without executing anything."""
        description = description or objective

        return self.planner.create_plan(
            task_type=task_type,
            objective=objective,
            description=description,
            requires_tool=True,
        )

    def prepare_execution(
        self,
        *,
        task_type: str,
        objective: str,
        role_id: str,
    ) -> OrchestrationResult:
        """Prepare a governed execution request.

        This method intentionally stops before policy evaluation/execution.
        """

        plan = self.create_plan(task_type, objective)

        if not plan.steps:
            return OrchestrationResult(
                success=False,
                status="PLAN_EMPTY",
                message="No executable plan steps were produced.",
                task_type=task_type,
            )

        step = plan.steps[0]
        capability_id = step.capability

        from agent_registry.authorization import authorize_role_capability

        authorization = authorize_role_capability(
            role_id=role_id,
            capability_id=capability_id,
        )

        if not authorization.allowed:
            return OrchestrationResult(
                success=False,
                status="CAPABILITY_DENIED",
                message=authorization.reason,
                task_type=task_type,
                capability_id=capability_id,
            )

        candidates = self.inspect_tools_for_capability(capability_id)

        if not candidates:
            return OrchestrationResult(
                success=False,
                status="NO_IMPLEMENTED_TOOL",
                message=(
                    f"No implemented and enabled declared tool is available "
                    f"for capability '{capability_id}'."
                ),
                task_type=task_type,
                capability_id=capability_id,
            )

        executable = [
            tool_id
            for tool_id in candidates
            if self._is_executable(tool_id)
        ]

        if not executable:
            return OrchestrationResult(
                success=False,
                status="NO_EXECUTABLE_ADAPTER",
                message=(
                    f"Declared tools exist for capability '{capability_id}', "
                    f"but no matching executable adapter is registered."
                ),
                task_type=task_type,
                capability_id=capability_id,
            )

        return OrchestrationResult(
            success=True,
            status="READY_FOR_POLICY",
            message="Plan, capability authorization, and tool selection succeeded.",
            task_type=task_type,
            capability_id=capability_id,
            tool_id=executable[0],
        )

    def _is_executable(self, tool_id: str) -> bool:
        """Check executable registry membership without executing."""
        try:
            self.registry.get(tool_id)
            return True
        except KeyError:
            return False
