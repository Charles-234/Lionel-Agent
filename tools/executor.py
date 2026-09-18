"""Single governed execution facade with compact audit integration."""

from __future__ import annotations

from typing import Any, Optional
import time

from audit.integration import record_request, record_result
from audit.ledger import AuditLedger
from tools.registry import get_registry


_LEDGER: Optional[AuditLedger] = None


def get_audit_ledger() -> AuditLedger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = AuditLedger()
    return _LEDGER


def _target_from_args(args: Any) -> Optional[str]:
    if not isinstance(args, dict):
        return None
    for key in ("target", "url", "host", "domain"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def execute(
    tool: Any,
    args: Optional[dict] = None,
    *,
    capability: Optional[str] = None,
    capability_id: Optional[str] = None,
    scope: Any = None,
    execution_mode: str = "real",
    confirmed: bool = False,
    session_id: Optional[str] = None,
    role: Optional[str] = None,
) -> Any:
    """Authorize and execute one tool, recording only compact audit events.

    The policy/registry remain the enforcement boundary. Audit failures must
    not silently authorize a tool, so a ledger write failure aborts before
    execution.
    """
    if capability is not None and capability_id is not None and capability != capability_id:
        raise ValueError("capability and capability_id disagree")
    capability_id = capability_id if capability_id is not None else capability

    tool_name = getattr(tool, "name", tool if isinstance(tool, str) else tool.__class__.__name__)
    started = time.time()

    ledger = get_audit_ledger()
    target = _target_from_args(args)
    record_request(
        ledger,
        session_id=session_id,
        role=role,
        capability=capability_id,
        tool=tool_name,
        execution_mode=execution_mode,
        target=target,
    )

    registry = get_registry()
    result = registry.authorize_and_run(
        tool_name,
        args or {},
        capability_id=capability_id,
        role_id=role,
        scope=scope,
        execution_mode=execution_mode,
        confirmed=confirmed,
    )

    record_result(
        ledger,
        started=started,
        session_id=session_id,
        role=role,
        capability=capability_id,
        tool=tool_name,
        execution_mode=getattr(result, "execution_mode", execution_mode),
        target=target,
        result=result,
    )
    return result
