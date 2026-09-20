"""Bounded, ephemeral working memory for one Lionel session."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Dict, Tuple


WORKING_MEMORY_SESSION_REQUIRED_MESSAGE = "Session identifier is required."
WORKING_MEMORY_KEY_REQUIRED_MESSAGE = "Working-memory key is required."
WORKING_MEMORY_VALUE_REQUIRED_MESSAGE = "Working-memory value is required."


class WorkingMemoryError(ValueError):
    """A deterministic validation error suitable for an external adapter."""


@dataclass(frozen=True)
class WorkingMemoryEntry:
    key: str
    value: str


@dataclass(frozen=True)
class WorkingMemorySnapshot:
    """An immutable view of a session's bounded, in-memory facts."""

    session_id: str
    revision: int = 0
    entries: Tuple[WorkingMemoryEntry, ...] = ()


class WorkingMemoryStore:
    """Thread-safe working memory with deterministic oldest-entry eviction.

    The store has no persistence, identity mapping, authorization, provider,
    tool, policy, executor, or audit behavior.  Callers must explicitly clear
    a session when its working context is no longer needed.
    """

    def __init__(self, *, max_entries: int = 20):
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self._max_entries = max_entries
        self._entries: Dict[str, OrderedDict[str, str]] = {}
        self._revisions: Dict[str, int] = {}
        self._lock = RLock()

    def put(self, session_id: str, key: str, value: str) -> WorkingMemorySnapshot:
        """Store one text fact, replacing the key and evicting oldest entries."""
        normalized_session_id = _normalize_session_id(session_id)
        normalized_key = _normalize_key(key)
        _validate_value(value)

        with self._lock:
            entries = self._entries.setdefault(normalized_session_id, OrderedDict())
            entries.pop(normalized_key, None)
            entries[normalized_key] = value
            while len(entries) > self._max_entries:
                entries.popitem(last=False)
            self._revisions[normalized_session_id] = self._revisions.get(normalized_session_id, 0) + 1
            return self._snapshot(normalized_session_id)

    def snapshot(self, session_id: str) -> WorkingMemorySnapshot:
        """Return an immutable snapshot without changing the session state."""
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            return self._snapshot(normalized_session_id)

    def clear(self, session_id: str) -> None:
        """Discard all working memory for exactly one session."""
        normalized_session_id = _normalize_session_id(session_id)
        with self._lock:
            self._entries.pop(normalized_session_id, None)
            self._revisions.pop(normalized_session_id, None)

    def _snapshot(self, session_id: str) -> WorkingMemorySnapshot:
        entries = self._entries.get(session_id, OrderedDict())
        return WorkingMemorySnapshot(
            session_id=session_id,
            revision=self._revisions.get(session_id, 0),
            entries=tuple(
                WorkingMemoryEntry(key=key, value=value)
                for key, value in entries.items()
            ),
        )


def _normalize_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise WorkingMemoryError(WORKING_MEMORY_SESSION_REQUIRED_MESSAGE)
    return session_id.strip()


def _normalize_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise WorkingMemoryError(WORKING_MEMORY_KEY_REQUIRED_MESSAGE)
    return "_".join(key.split()).casefold()


def _validate_value(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WorkingMemoryError(WORKING_MEMORY_VALUE_REQUIRED_MESSAGE)
