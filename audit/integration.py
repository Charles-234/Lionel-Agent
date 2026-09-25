"""Small audit helpers used at Lionel's tool execution boundary."""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from audit.ledger import AuditEvent, AuditLedger


_ERROR_CODE = re.compile(r"\b(POLICY_[A-Z0-9_]+|[A-Z][A-Z0-9_]{2,})\b")


def get_audit_ledger() -> AuditLedger:
    """Return a shared audit ledger instance for dashboard queries."""
    return AuditLedger()


def error_code(value: Any) -> Optional[str]:
    if not value:
        return None
    match = _ERROR_CODE.search(str(value))
    return match.group(1) if match else "TOOL_EXECUTION_ERROR"


def record_request(
    ledger: AuditLedger,
    *,
    session_id: Optional[str],
    role: Optional[str],
    capability: Optional[str],
    tool: Optional[str],
    execution_mode: str,
    target: Optional[str],
) -> None:
    ledger.record(AuditEvent(
        event_type="TOOL_REQUEST",
        session_id=session_id,
        role=role,
        capability=capability,
        tool=tool,
        execution_mode=execution_mode,
        target=target,
    ))


def record_result(
    ledger: AuditLedger,
    *,
    started: float,
    session_id: Optional[str],
    role: Optional[str],
    capability: Optional[str],
    tool: Optional[str],
    execution_mode: str,
    target: Optional[str],
    result: Any,
) -> None:
    success = getattr(result, "success", None)
    verified = getattr(result, "verified", False)
    status = "VERIFIED" if verified else "UNVERIFIED"
    err = getattr(result, "error", None)
    ledger.record(AuditEvent(
        event_type="TOOL_RESULT",
        session_id=session_id,
        role=role,
        capability=capability,
        tool=tool,
        execution_mode=execution_mode,
        success=success,
        verification_status=status,
        error_code=error_code(err) if not success else None,
        duration_ms=int((time.perf_counter() - started) * 1000),
        target=target,
    ))
