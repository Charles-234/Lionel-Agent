"""Bounded, ephemeral session memory for safe Lionel decision summaries."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Deque, Dict, Optional, Tuple

from agent.runtime import AgentDecision


SESSION_MEMORY_ID_REQUIRED_MESSAGE = "Session identifier is required."


class SessionMemoryError(ValueError):
    """A deterministic validation error suitable for an external adapter."""


@dataclass(frozen=True)
class SessionMemoryEntry:
    """A compact decision summary that deliberately excludes raw user text."""

    status: str
    task_type: Optional[str]
    role_id: Optional[str]
    plan_step_count: int


@dataclass(frozen=True)
class SessionMemorySnapshot:
    session_id: str
    revision: int = 0
    entries: Tuple[SessionMemoryEntry, ...] = ()


class SessionMemoryStore:
    """Thread-safe bounded history of non-sensitive session decision metadata.

    This is in-memory state only. It is not raw chat history, working-memory
    facts, persistent memory, identity management, authorization state, or an
    audit ledger.
    """

    def __init__(self, *, max_entries: int = 20):
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self._max_entries = max_entries
        self._entries: Dict[str, Deque[SessionMemoryEntry]] = {}
        self._revisions: Dict[str, int] = {}
        self._lock = RLock()

    def record(self, session_id: str, decision: AgentDecision) -> SessionMemorySnapshot:
        """Append one compact decision summary to a session's bounded history."""
        normalized_session_id = _normalize_session_id(session_id)
        if not isinstance(decision, AgentDecision):
            raise TypeError("decision must be an AgentDecision")

        entry = SessionMemoryEntry(
            status=decision.status,
            task_type=decision.request.task_type,
            role_id=decision.role_selection.role_id,
            plan_step_count=len(decision.plan.steps) if decision.plan else 0,
        )
        with self._lock:
            entries = self._entries.setdefault(
                normalized_session_id,
                deque(maxlen=self._max_entries),
            )
            entries.append(entry)
            self._revisions[normalized_session_id] = self._revisions.get(normalized_session_id, 0) + 1
            return self._snapshot(normalized_session_id)

    def snapshot(self, session_id: str) -> SessionMemorySnapshot:
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            return self._snapshot(normalized_session_id)

    def clear(self, session_id: str) -> None:
        """Discard all ephemeral summaries for exactly one session."""
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            self._entries.pop(normalized_session_id, None)
            self._revisions.pop(normalized_session_id, None)

    def _snapshot(self, session_id: str) -> SessionMemorySnapshot:
        return SessionMemorySnapshot(
            session_id=session_id,
            revision=self._revisions.get(session_id, 0),
            entries=tuple(self._entries.get(session_id, ())),
        )


def _normalize_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise SessionMemoryError(SESSION_MEMORY_ID_REQUIRED_MESSAGE)
    return session_id.strip()
