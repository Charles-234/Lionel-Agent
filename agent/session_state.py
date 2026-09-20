"""Ephemeral working state for bounded Lionel agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Dict, Optional

from agent.runtime import AgentDecision


SESSION_ID_REQUIRED_MESSAGE = "Session identifier is required."


class SessionStateError(ValueError):
    """A deterministic validation error safe for an external adapter."""


@dataclass(frozen=True)
class SessionState:
    """The latest in-memory decision for one interface-provided session ID.

    This is short-lived working state, not chat history, persistent memory,
    identity management, authorization context, or an audit record.
    """

    session_id: str
    revision: int = 0
    latest_decision: Optional[AgentDecision] = None


class SessionStateStore:
    """Thread-safe in-memory storage for isolated working-session snapshots."""

    def __init__(self):
        self._states: Dict[str, SessionState] = {}
        self._lock = RLock()

    def get(self, session_id: str) -> SessionState:
        """Return the current snapshot, creating an empty state when needed."""
        normalized_id = _normalize_session_id(session_id)
        with self._lock:
            return self._states.setdefault(normalized_id, SessionState(normalized_id))

    def record(self, session_id: str, decision: AgentDecision) -> SessionState:
        """Store a decision as the next immutable revision for its session."""
        normalized_id = _normalize_session_id(session_id)
        if not isinstance(decision, AgentDecision):
            raise TypeError("decision must be an AgentDecision")

        with self._lock:
            previous = self._states.get(normalized_id, SessionState(normalized_id))
            state = SessionState(
                session_id=normalized_id,
                revision=previous.revision + 1,
                latest_decision=decision,
            )
            self._states[normalized_id] = state
            return state

    def clear(self, session_id: str) -> None:
        """Discard ephemeral working state for exactly one session."""
        normalized_id = _normalize_session_id(session_id)
        with self._lock:
            self._states.pop(normalized_id, None)


def _normalize_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise SessionStateError(SESSION_ID_REQUIRED_MESSAGE)
    return session_id.strip()
