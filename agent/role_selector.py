"""Deterministic, non-authorizing role selection for normalized requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

from agent.request_normalizer import NormalizedRequest
from agent.request_planner import TASK_CAPABILITIES
from agent_registry.roles import ROLES


RoleSelectionStatus = Literal["SELECTED", "AMBIGUOUS", "UNSPECIFIED", "NO_MATCH"]


@dataclass(frozen=True)
class RoleSelection:
    """A routing recommendation, never an authorization decision.

    Multiple matching roles remain explicit so a later runtime layer can make
    an informed, governed choice rather than silently assuming authority.
    """

    status: RoleSelectionStatus
    task_type: Optional[str]
    role_id: Optional[str]
    candidate_role_ids: Tuple[str, ...]


def select_role(request: NormalizedRequest) -> RoleSelection:
    """Select a unique declared role only when the task mapping is unambiguous.

    This function uses registry metadata solely for deterministic routing.  It
    does not call role/capability authorization, select tools, plan work, or
    execute anything.
    """
    if request.task_type is None:
        return RoleSelection("UNSPECIFIED", None, None, ())

    capability_id = TASK_CAPABILITIES[request.task_type]
    candidates = tuple(sorted(
        role.id
        for role in ROLES.values()
        if capability_id in role.capability_categories
    ))

    if not candidates:
        return RoleSelection("NO_MATCH", request.task_type, None, ())
    if len(candidates) > 1:
        return RoleSelection("AMBIGUOUS", request.task_type, None, candidates)
    return RoleSelection("SELECTED", request.task_type, candidates[0], candidates)
