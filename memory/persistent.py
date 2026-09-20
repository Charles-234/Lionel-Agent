"""Explicit, owner-scoped SQLite storage for selected persistent memory.

A fact is stored only when a caller explicitly calls ``put``.  Each fact may
carry an optional lifetime: once that lifetime passes, the fact is treated as
absent and ``purge_expired`` removes it from disk.  Expiry is never a
permission, an authorization, or a substitute for auditing, and this module
does not encrypt data or authenticate identities.
"""

from __future__ import annotations

import math
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterator, Optional, Tuple


OWNER_ID_REQUIRED_MESSAGE = "Memory owner identifier is required."
MEMORY_KEY_REQUIRED_MESSAGE = "Persistent-memory key is required."
MEMORY_VALUE_REQUIRED_MESSAGE = "Persistent-memory value is required."
MEMORY_LIFETIME_INVALID_MESSAGE = "Memory lifetime must be a positive number of seconds."
MAX_OWNER_ID_LENGTH = 128
MAX_MEMORY_KEY_LENGTH = 128
MAX_MEMORY_VALUE_LENGTH = 10_000


class PersistentMemoryError(ValueError):
    """A deterministic validation error suitable for an external adapter."""


@dataclass(frozen=True)
class PersistentMemoryEntry:
    owner_id: str
    key: str
    value: str


@dataclass(frozen=True)
class PersistentMemoryRecord:
    """One stored fact paired with its lifecycle metadata."""

    entry: PersistentMemoryEntry
    created_at: float
    expires_at: Optional[float]
    expired: bool


class PersistentMemoryStore:
    """Local storage for facts explicitly chosen for persistence.

    The caller must provide the database path and call ``put`` explicitly.
    This store never ingests chat messages, requests, plans, or tool output
    automatically. It is owner-scoped and supports deletion, but it does not
    provide encryption, identity authentication, authorization, or auditing;
    those remain deployment-layer responsibilities.

    Lifetimes are opt-in per fact.  Reads hide expired facts, and expired rows
    are removed from disk only when a caller invokes ``purge_expired``.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.db_path), timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA busy_timeout=5000")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS persistent_memory (
                    owner_id TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT 0,
                    expires_at REAL,
                    PRIMARY KEY (owner_id, memory_key)
                )
            """)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(persistent_memory)")
            }
            if "created_at" not in columns:
                connection.execute(
                    "ALTER TABLE persistent_memory ADD COLUMN created_at REAL NOT NULL DEFAULT 0"
                )
            if "expires_at" not in columns:
                connection.execute(
                    "ALTER TABLE persistent_memory ADD COLUMN expires_at REAL"
                )
            connection.commit()

    def put(
        self,
        owner_id: str,
        key: str,
        value: str,
        *,
        ttl_seconds: Optional[float] = None,
    ) -> PersistentMemoryEntry:
        """Explicitly create or replace one owner-scoped persistent fact.

        ``ttl_seconds`` is optional.  When supplied, the fact is treated as
        absent once that many seconds have passed.  Replacing a fact without a
        lifetime restores it to permanent storage, because the caller is
        stating that intent explicitly.
        """
        normalized_owner_id = _normalize_owner_id(owner_id)
        normalized_key = _normalize_key(key)
        _validate_value(value)
        lifetime = _validate_lifetime(ttl_seconds)

        now = _now()
        expires_at = None if lifetime is None else now + lifetime

        with self._lock:
            with self._connection() as connection:
                connection.execute("""
                    INSERT INTO persistent_memory (
                        owner_id, memory_key, memory_value, created_at, expires_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(owner_id, memory_key) DO UPDATE SET
                        memory_value = excluded.memory_value,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at
                """, (normalized_owner_id, normalized_key, value, now, expires_at))
                connection.commit()
        return PersistentMemoryEntry(normalized_owner_id, normalized_key, value)

    def get(self, owner_id: str, key: str) -> Optional[PersistentMemoryEntry]:
        normalized_owner_id = _normalize_owner_id(owner_id)
        normalized_key = _normalize_key(key)
        with self._connection() as connection:
            row = connection.execute("""
                SELECT owner_id, memory_key, memory_value
                FROM persistent_memory
                WHERE owner_id = ? AND memory_key = ?
                  AND (expires_at IS NULL OR expires_at > ?)
            """, (normalized_owner_id, normalized_key, _now())).fetchone()
        return _entry_from_row(row) if row else None

    def list(self, owner_id: str) -> Tuple[PersistentMemoryEntry, ...]:
        """Return one owner's live facts in deterministic key order."""
        normalized_owner_id = _normalize_owner_id(owner_id)
        with self._connection() as connection:
            rows = connection.execute("""
                SELECT owner_id, memory_key, memory_value
                FROM persistent_memory
                WHERE owner_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY memory_key ASC
            """, (normalized_owner_id, _now())).fetchall()
        return tuple(_entry_from_row(row) for row in rows)

    def count(self, owner_id: str) -> int:
        """Return how many live facts one owner currently holds."""
        normalized_owner_id = _normalize_owner_id(owner_id)
        with self._connection() as connection:
            row = connection.execute("""
                SELECT COUNT(*) AS total
                FROM persistent_memory
                WHERE owner_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
            """, (normalized_owner_id, _now())).fetchone()
        return int(row["total"])

    def list_records(self, owner_id: str) -> Tuple[PersistentMemoryRecord, ...]:
        """Return every stored row, expired ones included, in key order.

        This is a lifecycle inspection view.  It exists so an owner can see
        what is still on disk, including facts that reads already hide.
        """
        normalized_owner_id = _normalize_owner_id(owner_id)
        now = _now()
        with self._connection() as connection:
            rows = connection.execute("""
                SELECT owner_id, memory_key, memory_value, created_at, expires_at
                FROM persistent_memory
                WHERE owner_id = ?
                ORDER BY memory_key ASC
            """, (normalized_owner_id,)).fetchall()
        return tuple(_record_from_row(row, now) for row in rows)

    def purge_expired(self, owner_id: Optional[str] = None) -> int:
        """Delete expired facts from disk and report how many rows went away.

        Passing ``owner_id`` limits the deletion to that owner.  Expiry alone
        never deletes data; removal always happens here, explicitly.
        """
        now = _now()
        with self._lock:
            with self._connection() as connection:
                if owner_id is None:
                    cursor = connection.execute("""
                        DELETE FROM persistent_memory
                        WHERE expires_at IS NOT NULL AND expires_at <= ?
                    """, (now,))
                else:
                    normalized_owner_id = _normalize_owner_id(owner_id)
                    cursor = connection.execute("""
                        DELETE FROM persistent_memory
                        WHERE expires_at IS NOT NULL AND expires_at <= ?
                          AND owner_id = ?
                    """, (now, normalized_owner_id))
                connection.commit()
        return cursor.rowcount

    def forget(self, owner_id: str, key: str) -> bool:
        """Remove one owner-scoped fact and report whether it existed."""
        normalized_owner_id = _normalize_owner_id(owner_id)
        normalized_key = _normalize_key(key)
        with self._lock:
            with self._connection() as connection:
                cursor = connection.execute("""
                    DELETE FROM persistent_memory
                    WHERE owner_id = ? AND memory_key = ?
                """, (normalized_owner_id, normalized_key))
                connection.commit()
        return cursor.rowcount > 0

    def clear_owner(self, owner_id: str) -> int:
        """Remove all facts for exactly one owner and return the removed count."""
        normalized_owner_id = _normalize_owner_id(owner_id)
        with self._lock:
            with self._connection() as connection:
                cursor = connection.execute(
                    "DELETE FROM persistent_memory WHERE owner_id = ?",
                    (normalized_owner_id,),
                )
                connection.commit()
        return cursor.rowcount


def _entry_from_row(row: sqlite3.Row) -> PersistentMemoryEntry:
    return PersistentMemoryEntry(
        owner_id=row["owner_id"],
        key=row["memory_key"],
        value=row["memory_value"],
    )


def _record_from_row(row: sqlite3.Row, now: float) -> PersistentMemoryRecord:
    expires_at = row["expires_at"]
    expiration = None if expires_at is None else float(expires_at)
    return PersistentMemoryRecord(
        entry=_entry_from_row(row),
        created_at=float(row["created_at"]),
        expires_at=expiration,
        expired=expiration is not None and expiration <= now,
    )


def _normalize_owner_id(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise PersistentMemoryError(OWNER_ID_REQUIRED_MESSAGE)
    normalized = owner_id.strip()
    if len(normalized) > MAX_OWNER_ID_LENGTH:
        raise PersistentMemoryError("Memory owner identifier is too long.")
    return normalized


def _normalize_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise PersistentMemoryError(MEMORY_KEY_REQUIRED_MESSAGE)
    normalized = "_".join(key.split()).casefold()
    if len(normalized) > MAX_MEMORY_KEY_LENGTH:
        raise PersistentMemoryError("Persistent-memory key is too long.")
    return normalized


def _validate_value(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PersistentMemoryError(MEMORY_VALUE_REQUIRED_MESSAGE)
    if len(value) > MAX_MEMORY_VALUE_LENGTH:
        raise PersistentMemoryError("Persistent-memory value is too long.")


def _now() -> float:
    """Current POSIX time, isolated so lifecycle behavior stays testable."""
    return time.time()


def _validate_lifetime(ttl_seconds: Optional[float]) -> Optional[float]:
    """Accept a finite, strictly positive lifetime, or no lifetime at all."""
    if ttl_seconds is None:
        return None
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
        raise PersistentMemoryError(MEMORY_LIFETIME_INVALID_MESSAGE)
    lifetime = float(ttl_seconds)
    if not math.isfinite(lifetime) or lifetime <= 0:
        raise PersistentMemoryError(MEMORY_LIFETIME_INVALID_MESSAGE)
    return lifetime
