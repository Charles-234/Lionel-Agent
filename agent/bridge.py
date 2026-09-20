"""Bridge from a ready agent decision to the bounded runner.

The bridge carries a finished plan from one desk to the other. It adds no
permission, makes no choices, and repeats no safety checks. Every step still
passes through the single governed executor with its existing limits,
confirmation pauses, and audit notes.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence


BRIDGE_DECISION_REQUIRED_MESSAGE = "A finished agent decision is required."
BRIDGE_DECISION_NOT_READY_MESSAGE = (
    "The decision is not ready to run. It must be planned first."
)
BRIDGE_ROLE_REQUIRED_MESSAGE = (
    "The decision has no single selected role and cannot run."
)
BRIDGE_PLAN_REQUIRED_MESSAGE = "The decision has no plan steps to run."
BRIDGE_SESSION_REQUIRED_MESSAGE = "Session identifier is required."
BRIDGE_EXECUTION_MODE_MESSAGE = "Unsupported execution mode."


class BridgeError(ValueError):
    """A plain, safe error an outside screen can show as-is."""


def run_decision(
    decision,
    *,
    session_id: str,
    arguments: Optional[Sequence[dict]] = None,
    scope: Any = None,
    execution_mode: str = "simulation",
    limits=None,
    usage=None,
    start_step: int = 0,
    runner=None,
    confirmations=None,
    clock=None,
):
    """Carry one ready decision to the bounded runner.

    Only a decision marked PLAN_READY with one chosen role and a real plan
    is accepted. Anything else is refused with a safe message, and nothing
    is started. The runner itself still enforces every safety stop.
    """
    from agent.runtime import AgentDecision
    from agent.runner import BoundedRunner

    if not isinstance(decision, AgentDecision):
        raise BridgeError(BRIDGE_DECISION_REQUIRED_MESSAGE)
    if not isinstance(session_id, str) or not session_id.strip():
        raise BridgeError(BRIDGE_SESSION_REQUIRED_MESSAGE)
    if execution_mode not in ("real", "simulation"):
        raise BridgeError(BRIDGE_EXECUTION_MODE_MESSAGE)
    if decision.status != "PLAN_READY":
        raise BridgeError(BRIDGE_DECISION_NOT_READY_MESSAGE)
    if decision.plan is None or not decision.plan.steps:
        raise BridgeError(BRIDGE_PLAN_REQUIRED_MESSAGE)
    role_id = decision.role_selection.role_id
    if decision.role_selection.status != "SELECTED" or not role_id:
        raise BridgeError(BRIDGE_ROLE_REQUIRED_MESSAGE)

    active_runner = runner if runner is not None else BoundedRunner(
        confirmations=confirmations,
        clock=clock,
    ) if (confirmations is not None or clock is not None) else BoundedRunner()
    return active_runner.run(
        session_id=session_id,
        role_id=role_id,
        plan=decision.plan,
        arguments=arguments,
        scope=scope,
        execution_mode=execution_mode,
        limits=limits,
        usage=usage,
        start_step=start_step,
    )


def describe_decision(decision) -> str:
    """Return one plain line saying why a decision cannot run, or that it can.

    A helper for outside screens only. It never authorizes, plans, or runs
    anything. An empty reason is never returned; a ready decision gets a
    short ready line instead.
    """
    from agent.runtime import AgentDecision

    if not isinstance(decision, AgentDecision):
        return BRIDGE_DECISION_REQUIRED_MESSAGE
    if decision.status != "PLAN_READY":
        return BRIDGE_DECISION_NOT_READY_MESSAGE
    if decision.plan is None or not decision.plan.steps:
        return BRIDGE_PLAN_REQUIRED_MESSAGE
    if decision.role_selection.status != "SELECTED" or not decision.role_selection.role_id:
        return BRIDGE_ROLE_REQUIRED_MESSAGE
    count = len(decision.plan.steps)
    step_word = "step" if count == 1 else "steps"
    return (
        f"Ready to run {count} {step_word} "
        f"as role '{decision.role_selection.role_id}'."
    )


def can_run(decision) -> bool:
    """Report whether a decision looks ready, without starting anything."""
    return describe_decision(decision).startswith("Ready to run")


def summarize_run(result) -> str:
    """Return one plain line describing a finished run.

    Reads counts and status only. Never touches raw targets, secrets, or
    full reasoning, so the line is safe to show on an outside screen.
    """
    steps = list(getattr(result, "steps", []) or ())
    done = sum(1 for s in steps if getattr(s, "success", False))
    total = len(steps)
    status = str(getattr(result, "status", "UNKNOWN"))
    if total == 0 and status == "COMPLETED":
        return "Finished with nothing to do."
    if status == "COMPLETED" and done == total:
        step_word = "step" if total == 1 else "steps"
        return f"Finished all {total} {step_word} with no problems."
    if status == "AWAITING_CONFIRMATION":
        return (
            f"Paused after {done} of {total} steps. "
            "Needs a person to say yes before going on."
        )
    failed = total - done
    fail_word = "step" if failed == 1 else "steps"
    if status.startswith("STOPPED_"):
        return (
            f"Stopped safely after {done} of {total} steps. "
            f"{failed} {fail_word} did not finish."
        )
    return f"Finished with {done} of {total} steps done well."
