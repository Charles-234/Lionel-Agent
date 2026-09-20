"""Deterministic run budgets for bounded Lionel autonomy.

Limits account for what a run has already spent.  They never authorize work:
every step still passes through the single governance boundary.  Risk ordering
is imported from that boundary so the sequence is never restated here, and
reading a declared risk level is accounting only, never permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tools.policy import RISK_ORDER


DEFAULT_MAX_STEPS = 8
DEFAULT_MAX_HIGH_RISK_STEPS = 2
DEFAULT_MAX_FAILED_STEPS = 0
DEFAULT_MAX_DURATION_SECONDS = 120.0

HIGH_RISK_LEVELS = frozenset({"high", "critical"})

LIMIT_STEPS = "STEP_LIMIT_REACHED"
LIMIT_HIGH_RISK = "HIGH_RISK_STEP_LIMIT_REACHED"
LIMIT_FAILURES = "FAILED_STEP_LIMIT_REACHED"
LIMIT_DURATION = "DURATION_LIMIT_REACHED"


@dataclass(frozen=True)
class RunLimits:
    """Hard ceilings for one bounded run.  Defaults are deliberately small."""

    max_steps: int = DEFAULT_MAX_STEPS
    max_high_risk_steps: int = DEFAULT_MAX_HIGH_RISK_STEPS
    max_failed_steps: int = DEFAULT_MAX_FAILED_STEPS
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS

    def __post_init__(self) -> None:
        _require_int("max_steps", self.max_steps, minimum=1)
        _require_int("max_high_risk_steps", self.max_high_risk_steps, minimum=0)
        _require_int("max_failed_steps", self.max_failed_steps, minimum=0)
        if isinstance(self.max_duration_seconds, bool) or not isinstance(
            self.max_duration_seconds, (int, float)
        ):
            raise ValueError("max_duration_seconds must be a positive number")
        if not self.max_duration_seconds > 0:
            raise ValueError("max_duration_seconds must be a positive number")


@dataclass(frozen=True)
class RunUsage:
    """What one bounded run has consumed so far."""

    steps_started: int = 0
    high_risk_steps: int = 0
    failed_steps: int = 0
    elapsed_seconds: float = 0.0


def is_high_risk(risk_level: str) -> bool:
    """Report whether a declared risk level counts against the risk budget.

    An unrecognised level counts as high risk, so an unknown or malformed
    declaration is never treated as cheap.
    """
    if risk_level not in RISK_ORDER:
        return True
    return risk_level in HIGH_RISK_LEVELS


def check_limits(
    limits: RunLimits,
    usage: RunUsage,
    *,
    next_step_risk: Optional[str] = None,
) -> Optional[str]:
    """Return the exhausted limit's reason code, or None when a step may start.

    The check order is fixed so the reported reason stays deterministic across
    runs.  ``max_failed_steps`` is a tolerance: zero means no failed step is
    accepted, while ``max_steps`` and ``max_high_risk_steps`` are ceilings where
    zero means none may start.  ``next_step_risk`` is only consulted for budget
    accounting; policy still decides whether the step may run.
    """
    if usage.elapsed_seconds >= limits.max_duration_seconds:
        return LIMIT_DURATION
    if usage.steps_started >= limits.max_steps:
        return LIMIT_STEPS
    if usage.failed_steps > limits.max_failed_steps:
        return LIMIT_FAILURES
    if next_step_risk is not None and is_high_risk(next_step_risk):
        if usage.high_risk_steps >= limits.max_high_risk_steps:
            return LIMIT_HIGH_RISK
    return None


def _require_int(name: str, value: int, *, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
