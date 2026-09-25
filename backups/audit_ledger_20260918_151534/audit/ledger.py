"""Compact SQLite audit ledger for Lionel.

Design goals:
- local SQLite, no external service
- compact structured events, not prompts or chain-of-thought
- secret-safe sanitization
- append-oriented records
- policy/tool/verification events
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}"),
]


def sanitize(value: Any) -> Any:
    """Remove likely credential material without storing full prompts/responses."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value[:20]]
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:1000]


def target_fingerprint(target: Optional[str]) -> Optional[str]:
    """Store a non-reversible target fingerprint instead of raw target text."""
    if not target:
        return None
    return hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    session_id: Optional[str] = None
    role: Optional[str] = None
    capability: Optional[str] = None
    tool: Optional[str] = None
    policy_decision: Optional[str] = None
    execution_mode: Optional[str] = None
    success: Optional[bool] = None
    verification_status: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: Optional[int] = None
    target: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def compact(self) -> Dict[str, Any]:
        data = asdict(self)
        target = data.pop("target")
        data["target_hash"] = target_fingerprint(target)
        data["details"] = sanitize(data.get("details"))
        return data


class AuditLedger:
    def __init__(self, db_path: str = "logs/lionel_audit.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    timestamp_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    session_id TEXT,
                    role TEXT,
                    capability TEXT,
                    tool TEXT,
                    policy_decision TEXT,
                    execution_mode TEXT,
                    success INTEGER,
                    verification_status TEXT,
                    error_code TEXT,
                    duration_ms INTEGER,
                    target_hash TEXT,
                    details_json TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp "
                "ON audit_events(timestamp_utc)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_event_type "
                "ON audit_events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_session "
                "ON audit_events(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_tool "
                "ON audit_events(tool)"
            )

    def record(self, event: AuditEvent) -> str:
        data = event.compact()
        event_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO audit_events (
                        event_id, timestamp_utc, event_type, session_id,
                        role, capability, tool, policy_decision,
                        execution_mode, success, verification_status,
                        error_code, duration_ms, target_hash, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id, timestamp, data["event_type"],
                    data["session_id"], data["role"], data["capability"],
                    data["tool"], data["policy_decision"],
                    data["execution_mode"],
                    None if data["success"] is None else int(data["success"]),
                    data["verification_status"], data["error_code"],
                    data["duration_ms"], data["target_hash"],
                    json.dumps(data["details"], separators=(",", ":"))
                    if data["details"] is not None else None,
                ))
        return event_id

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
