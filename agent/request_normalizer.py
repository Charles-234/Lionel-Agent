"""Pure normalization for external natural-language request inputs.

This module deliberately stops before planning and governance.  It preserves
the user's original text while producing deterministic, provider- and
interface-independent metadata for a later request-planning boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent.request_planner import TASK_CAPABILITIES


EMPTY_REQUEST_MESSAGE = "Request text is required."
INVALID_TASK_TYPE_MESSAGE = "Task type is not recognized."


class RequestNormalizationError(ValueError):
    """A deterministic validation error safe to return from an external UI."""


@dataclass(frozen=True)
class NormalizedRequest:
    """A raw user request plus non-authoritative normalized task metadata.

    ``task_type`` is ``None`` when no task type was supplied.  The normalizer
    never infers a task type from wording, so later layers must handle that
    state explicitly rather than treating it as an authorized capability.
    """

    raw_text: str
    objective: str
    task_type: Optional[str]


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_task_type(task_type: str) -> str:
    normalized = _normalize_whitespace(task_type).casefold()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return normalized


def normalize_request(
    raw_text: str,
    *,
    task_type: Optional[str] = None,
) -> NormalizedRequest:
    """Normalize one user request without planning, authorization, or execution.

    The original user text remains unchanged in ``raw_text``.  The normalized
    ``objective`` is whitespace-collapsed for deterministic downstream use.
    ``task_type`` is accepted only when it names an existing planner task type.
    """
    if not isinstance(raw_text, str) or not _normalize_whitespace(raw_text):
        raise RequestNormalizationError(EMPTY_REQUEST_MESSAGE)

    normalized_task_type: Optional[str] = None
    if task_type is not None:
        if not isinstance(task_type, str):
            raise RequestNormalizationError(INVALID_TASK_TYPE_MESSAGE)
        normalized_task_type = _normalize_task_type(task_type)
        if normalized_task_type not in TASK_CAPABILITIES:
            raise RequestNormalizationError(INVALID_TASK_TYPE_MESSAGE)

    return NormalizedRequest(
        raw_text=raw_text,
        objective=_normalize_whitespace(raw_text),
        task_type=normalized_task_type,
    )
