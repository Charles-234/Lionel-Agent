"""Explicit, single-use confirmation for steps that policy requires a human to approve.

The agent may ask for confirmation and may consume a confirmation, but it can
never create one.  Every grant must name the principal that granted it, a grant
is bound to the exact step, capability, and tool it was issued for, and a grant
is destroyed the moment it is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Dict, Optional, Tuple


CONFIRMATION_SESSION_REQUIRED_MESSAGE = "Session identifier is required."
CONFIRMATION_GRANTER_REQUIRED_MESSAGE = (
    "A confirming principal is required to grant confirmation."
)
CONFIRMATION_UNKNOWN_MESSAGE = (
    "No matching confirmation request exists for this session."
)


class ConfirmationError(ValueError):
    """A deterministic validation error suitable for an external adapter."""


@dataclass(frozen=True)
class ConfirmationRequest:
    """A pending request for approval.  It grants nothing on its own."""

    request_id: str
    session_id: str
    step_index: int
    capability_id: str
    tool_id: str
    reason: str


@dataclass(frozen=True)
class ConfirmationGrant:
    """An explicit approval that may be consumed by exactly one step."""

    request_id: str
    session_id: str
    granted_by: str
    step_index: int
    capability_id: str
    tool_id: str


class ConfirmationStore:
    """Thread-safe, session-scoped confirmation requests and one-time grants.

    This store holds no chat text, no credentials, no working memory, and no
    audit record.  It is not an identity system: ``granted_by`` is a caller
    supplied label, and authenticating that principal remains an interface or
    deployment responsibility.
    """

    def __init__(self):
        self._requests: Dict[str, Dict[str, ConfirmationRequest]] = {}
        self._grants: Dict[str, Dict[str, ConfirmationGrant]] = {}
        self._lock = RLock()

    def request(
        self,
        session_id: str,
        *,
        step_index: int,
        capability_id: str,
        tool_id: str,
        reason: str,
    ) -> ConfirmationRequest:
        """Record that one step needs approval.

        Re-requesting the same step discards any earlier unconsumed grant, so an
        approval must always be re-stated after a repeated request.
        """
        normalized_session_id = _normalize_session_id(session_id)
        request_id = _request_id(normalized_session_id, step_index, capability_id, tool_id)
        entry = ConfirmationRequest(
            request_id=request_id,
            session_id=normalized_session_id,
            step_index=step_index,
            capability_id=capability_id,
            tool_id=tool_id,
            reason=reason,
        )
        with self._lock:
            self._requests.setdefault(normalized_session_id, {})[request_id] = entry
            self._grants.get(normalized_session_id, {}).pop(request_id, None)
        return entry

    def grant(
        self,
        session_id: str,
        request_id: str,
        *,
        granted_by: str,
    ) -> ConfirmationGrant:
        """Explicitly approve one pending request on behalf of a named principal."""
        normalized_session_id = _normalize_session_id(session_id)
        if not isinstance(granted_by, str) or not granted_by.strip():
            raise ConfirmationError(CONFIRMATION_GRANTER_REQUIRED_MESSAGE)

        with self._lock:
            request = self._requests.get(normalized_session_id, {}).get(request_id)
            if request is None:
                raise ConfirmationError(CONFIRMATION_UNKNOWN_MESSAGE)
            grant = ConfirmationGrant(
                request_id=request.request_id,
                session_id=normalized_session_id,
                granted_by=granted_by.strip(),
                step_index=request.step_index,
                capability_id=request.capability_id,
                tool_id=request.tool_id,
            )
            self._grants.setdefault(normalized_session_id, {})[request_id] = grant
            return grant

    def pending(self, session_id: str) -> Tuple[ConfirmationRequest, ...]:
        """Return unanswered requests for exactly one session, in stable order."""
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            requests = self._requests.get(normalized_session_id, {})
            grants = self._grants.get(normalized_session_id, {})
            return tuple(
                request
                for request_id, request in sorted(requests.items())
                if request_id not in grants
            )

    def consume(
        self,
        session_id: str,
        request_id: str,
        *,
        step_index: int,
        capability_id: str,
        tool_id: str,
    ) -> Optional[ConfirmationGrant]:
        """Burn a matching grant, or return None when no valid grant applies.

        The grant is removed before it is validated, so an approval can never be
        replayed.  A mismatch is refused rather than repaired, which keeps the
        failure closed instead of granting a broader approval than was given.
        """
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            grant = self._grants.get(normalized_session_id, {}).pop(request_id, None)
        if grant is None:
            return None
        if (grant.step_index, grant.capability_id, grant.tool_id) != (
            step_index,
            capability_id,
            tool_id,
        ):
            return None
        return grant

    def clear(self, session_id: str) -> None:
        """Discard all confirmation state for exactly one session."""
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            self._requests.pop(normalized_session_id, None)
            self._grants.pop(normalized_session_id, None)


def _normalize_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ConfirmationError(CONFIRMATION_SESSION_REQUIRED_MESSAGE)
    return session_id.strip()


def _request_id(
    session_id: str,
    step_index: int,
    capability_id: str,
    tool_id: str,
) -> str:
    """Build a deterministic, non-secret identifier for one pending approval."""
    return f"{session_id}|{step_index}|{capability_id}|{tool_id}"