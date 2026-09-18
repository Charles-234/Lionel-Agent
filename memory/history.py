"""
Lionel Agent - Per-user conversation history.

Keeps recent exchanges verbatim; older ones get summarized.
In-memory only for now; can persist to SQLite later.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """A single exchange."""
    role: str          # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class UserHistory:
    """History for a single user."""
    turns: List[Turn] = field(default_factory=list)

    def add(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))
        # Cap: keep last N verbatim, summarize the rest
        if len(self.turns) > config.HISTORY_VERBATIM_TURNS * 2:
            self._compress()

    def _compress(self) -> None:
        """Fold old turns into a summary turn."""
        keep = config.HISTORY_VERBATIM_TURNS * 2
        if len(self.turns) <= keep:
            return
        old = self.turns[:-keep]
        recent = self.turns[-keep:]

        # Crude summary: concatenate old turns, truncate
        parts = []
        for t in old:
            parts.append(f"{t.role}: {t.content[:120]}")
        summary = " | ".join(parts)[:config.HISTORY_SUMMARY_MAX_CHARS]

        self.turns = [Turn(role="system", content=f"[Earlier: {summary}]")] + recent

    def recent(self, limit: Optional[int] = None) -> List[Turn]:
        if limit is None:
            limit = config.HISTORY_VERBATIM_TURNS * 2
        return self.turns[-limit:]

    def clear(self) -> None:
        self.turns = []


class HistoryStore:
    """Manages per-user histories."""

    def __init__(self):
        self._by_user: Dict[int, UserHistory] = {}

    def get(self, user_id: int) -> UserHistory:
        if user_id not in self._by_user:
            self._by_user[user_id] = UserHistory()
        return self._by_user[user_id]

    def clear(self, user_id: int) -> None:
        if user_id in self._by_user:
            self._by_user[user_id].clear()


# Singleton
_store = HistoryStore()


def get(user_id: int) -> UserHistory:
    return _store.get(user_id)


def clear(user_id: int) -> None:
    _store.clear(user_id)