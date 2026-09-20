"""Bounded multi-step runner: walks plan steps through the governed executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from agent.confirmations import ConfirmationRequest
from agent.planner import Plan
from agent.run_limits import RunUsage


@dataclass(frozen=True)
class StepOutcome:
    step_index: int
    capability_id: str
    tool_id: Optional[str] = None
    success: bool = False
    status: str = "NOT_ATTEMPTED"
    error: Optional[str] = None
    result: Any = None


@dataclass(frozen=True)
class RunResult:
    status: str
    session_id: str
    usage: RunUsage
    steps: List[StepOutcome] = field(default_factory=list)
    pending_confirmation: Optional[ConfirmationRequest] = None

    @property
    def all_succeeded(self) -> bool:
        return bool(self.steps) and all(s.success for s in self.steps)


_LIMIT_STATUS = {
    "STEP_LIMIT_REACHED": "STOPPED_STEP_LIMIT",
    "HIGH_RISK_STEP_LIMIT_REACHED": "STOPPED_HIGH_RISK_LIMIT",
    "FAILED_STEP_LIMIT_REACHED": "STOPPED_FAILURE_LIMIT",
    "DURATION_LIMIT_REACHED": "STOPPED_DURATION_LIMIT",
}


class BoundedRunner:
    """Walk plan steps via the governed executor until a bound stops us."""

    def __init__(self, *, orchestrator=None, confirmations=None, clock=None):
        from agent.orchestrator import LionelOrchestrator
        from agent.confirmations import ConfirmationStore
        import time as _time

        self.orchestrator = orchestrator or LionelOrchestrator()
        self.confirmations = confirmations or ConfirmationStore()
        self.clock = clock or _time.monotonic

    def run(
        self,
        *,
        session_id,
        role_id,
        plan,
        arguments=None,
        scope=None,
        execution_mode="simulation",
        limits=None,
        usage=None,
        start_step=0,
    ):
        from agent.run_limits import RunLimits, RunUsage, check_limits

        session_id = _require_session(session_id)
        limits = limits or RunLimits()
        spent = usage or RunUsage()
        started = self.clock()
        outcomes = []
        if start_step < 0 or start_step > len(plan.steps):
            raise ValueError("start_step is outside the plan")
        args = _arguments_for(plan, arguments)
        for index in range(start_step, len(plan.steps)):
            step = plan.steps[index]
            declared = _declared_risk(self.orchestrator, step.capability, role_id)
            current = _usage_now(spent, started, self.clock())
            hit = check_limits(limits, current, next_step_risk=declared)
            if hit is not None:
                return RunResult(
                    status=_LIMIT_STATUS[hit],
                    session_id=session_id,
                    usage=current,
                    steps=outcomes,
                )
            stop = self._attempt_step(
                plan, session_id, role_id, args, scope,
                execution_mode, index, declared, spent, started,
            )
            if isinstance(stop, RunResult):
                pending_steps = list(stop.steps) or []
                return RunResult(
                    status=stop.status,
                    session_id=stop.session_id,
                    usage=stop.usage,
                    steps=outcomes + pending_steps,
                    pending_confirmation=stop.pending_confirmation,
                )
            outcome, spent = stop
            outcomes.append(outcome)
        return RunResult(
            status="COMPLETED", session_id=session_id,
            usage=spent, steps=outcomes,
        )

    def _attempt_step(
        self, plan, session_id, role_id, args, scope,
        execution_mode, index, declared, spent, started,
    ):
        """Run one step via governance; RunResult pauses, tuple continues."""
        from tools.executor import execute as execute_tool

        step = plan.steps[index]
        selected = self.orchestrator.select_tool_for_capability(
            capability_id=step.capability,
            role_id=role_id,
            task_type=plan.task_type,
        )
        if not selected.success:
            outcome = StepOutcome(
                step_index=index, capability_id=step.capability,
                success=False, status=selected.status,
                error=selected.message,
            )
            return outcome, _spent_after(
                spent, started, self.clock(), declared, False)
        tool_id = selected.tool_id or ""
        confirmed = False
        if _tool_requires_confirmation(self.orchestrator, tool_id):
            grant = self.confirmations.consume(
                session_id,
                _request_id(session_id, index, step.capability, tool_id),
                step_index=index, capability_id=step.capability,
                tool_id=tool_id,
            )
            if grant is None:
                pending = self.confirmations.request(
                    session_id, step_index=index,
                    capability_id=step.capability, tool_id=tool_id,
                    reason="Policy requires explicit confirmation.",
                )
                return RunResult(
                    status="AWAITING_CONFIRMATION", session_id=session_id,
                    usage=_usage_now(spent, started, self.clock()),
                    steps=[], pending_confirmation=pending,
                )
            confirmed = True
        result = execute_tool(
            tool_id, args[index], capability_id=step.capability,
            scope=scope, execution_mode=execution_mode,
            confirmed=confirmed, session_id=session_id, role=role_id,
        )
        if bool(getattr(result, "requires_confirmation", False)):
            pending = self.confirmations.request(
                session_id, step_index=index,
                capability_id=step.capability, tool_id=tool_id,
                reason="Policy requires explicit confirmation.",
            )
            return RunResult(
                status="AWAITING_CONFIRMATION", session_id=session_id,
                usage=_usage_now(spent, started, self.clock()),
                steps=[], pending_confirmation=pending,
            )
        ok = bool(getattr(result, "success", False))
        outcome = StepOutcome(
            step_index=index, capability_id=step.capability,
            tool_id=tool_id, success=ok,
            status="SUCCEEDED" if ok else "FAILED",
            error=None if ok else getattr(result, "error", None),
            result=result,
        )
        return outcome, _spent_after(
            spent, started, self.clock(), declared, ok)


def _usage_now(spent, started, now):
    from agent.run_limits import RunUsage

    return RunUsage(
        steps_started=spent.steps_started,
        high_risk_steps=spent.high_risk_steps,
        failed_steps=spent.failed_steps,
        elapsed_seconds=(now - started) + spent.elapsed_seconds,
    )


def _spent_after(spent, started, now, declared, succeeded):
    from agent.run_limits import RunUsage, is_high_risk

    return RunUsage(
        steps_started=spent.steps_started + 1,
        high_risk_steps=spent.high_risk_steps
        + (1 if is_high_risk(declared) else 0),
        failed_steps=spent.failed_steps + (0 if succeeded else 1),
        elapsed_seconds=(now - started) + spent.elapsed_seconds,
    )


def _require_session(session_id):
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Session identifier is required.")
    return session_id.strip()


def _arguments_for(plan, arguments):
    if arguments is None:
        return [{} for _ in plan.steps]
    if len(arguments) != len(plan.steps):
        raise ValueError("arguments must supply one mapping per plan step")
    return [dict(a) for a in arguments]


def _declared_risk(orchestrator, capability_id, role_id):
    try:
        selected = orchestrator.select_tool_for_capability(
            capability_id=capability_id, role_id=role_id)
    except Exception:
        return "unknown"
    if not selected.success or not selected.tool_id:
        return "unknown"
    try:
        from tools_registry import get_tool

        return str(get_tool(selected.tool_id).risk_level)
    except Exception:
        return "unknown"


def _tool_requires_confirmation(orchestrator, tool_id):
    try:
        return bool(orchestrator.registry.get(tool_id).confirmation_required)
    except Exception:
        return False


def _request_id(session_id, step_index, capability_id, tool_id):
    return f"{session_id}|{step_index}|{capability_id}|{tool_id}"
