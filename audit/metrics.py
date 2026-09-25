"""Audit metrics export for Lionel.

Exposes aggregate metrics from the audit ledger for dashboards and
operational monitoring. All values are derived from recorded audit events.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from audit.ledger import AuditLedger, AuditEvent

logger = logging.getLogger(__name__)


def get_ledger() -> AuditLedger:
    from audit.integration import get_audit_ledger
    return get_audit_ledger()


def tool_execution_summary(
    ledger: Optional[AuditLedger] = None,
    *,
    limit: int = 1000,
) -> Dict[str, Any]:
    """Aggregate tool execution stats from the audit ledger.

    Returns counts and rates by tool, capability, and outcome.
    """
    if ledger is None:
        ledger = get_ledger()

    events = ledger.recent(limit=limit)
    if not events:
        return _empty_summary()

    # Filter to tool events
    tool_events = [e for e in events if e["event_type"] in ("TOOL_REQUEST", "TOOL_RESULT")]

    total_requests = 0
    total_results = 0
    succeeded = 0
    failed = 0
    verified = 0
    unverified = 0
    by_tool: Dict[str, Dict[str, int]] = {}
    by_capability: Dict[str, Dict[str, int]] = {}
    by_execution_mode: Dict[str, int] = {}
    errors: Dict[str, int] = {}

    for e in tool_events:
        if e["event_type"] == "TOOL_REQUEST":
            total_requests += 1
            tool = e.get("tool") or "unknown"
            cap = e.get("capability") or "unknown"
            mode = e.get("execution_mode") or "unknown"
            by_tool.setdefault(tool, {"requests": 0, "results": 0, "succeeded": 0, "failed": 0})
            by_tool[tool]["requests"] += 1
            by_capability.setdefault(cap, {"requests": 0, "results": 0})
            by_capability[cap]["requests"] += 1
            by_execution_mode[mode] = by_execution_mode.get(mode, 0) + 1

        elif e["event_type"] == "TOOL_RESULT":
            total_results += 1
            tool = e.get("tool") or "unknown"
            cap = e.get("capability") or "unknown"
            success = e.get("success")
            verified_status = e.get("verification_status")
            err = e.get("error_code")

            if tool in by_tool:
                by_tool[tool]["results"] += 1
            if cap in by_capability:
                by_capability[cap]["results"] += 1

            if success:
                succeeded += 1
                if tool in by_tool:
                    by_tool[tool]["succeeded"] += 1
            else:
                failed += 1
                if tool in by_tool:
                    by_tool[tool]["failed"] += 1
                if err:
                    errors[err] = errors.get(err, 0) + 1

            if verified_status == "VERIFIED":
                verified += 1
            else:
                unverified += 1

    return {
        "total_requests": total_requests,
        "total_results": total_results,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": round(succeeded / max(total_results, 1) * 100, 1),
        "verified": verified,
        "unverified": unverified,
        "verification_rate": round(verified / max(total_results, 1) * 100, 1),
        "by_tool": by_tool,
        "by_capability": by_capability,
        "by_execution_mode": by_execution_mode,
        "errors": errors,
        "period": {
            "from": _iso(events[-1]["timestamp_utc"]) if events else None,
            "to": _iso(events[0]["timestamp_utc"]) if events else None,
        },
    }


def recent_activity(
    ledger: Optional[AuditLedger] = None,
    *,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return recent audit events as a plain list for display."""
    if ledger is None:
        ledger = get_ledger()
    events = ledger.recent(limit=limit)
    return [
        {
            "event_id": e["event_id"],
            "event_type": e["event_type"],
            "timestamp": e["timestamp_utc"],
            "session_id": e["session_id"],
            "role": e["role"],
            "capability": e["capability"],
            "tool": e["tool"],
            "execution_mode": e["execution_mode"],
            "success": e["success"],
            "verification_status": e["verification_status"],
            "error_code": e["error_code"],
            "duration_ms": e["duration_ms"],
            "target_hash": e["target_hash"],
        }
        for e in events
    ]


def tool_usage_ranking(
    ledger: Optional[AuditLedger] = None,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Rank tools by usage frequency."""
    summary = tool_execution_summary(ledger)
    by_tool = summary.get("by_tool", {})
    ranked = sorted(
        by_tool.items(),
        key=lambda item: item[1].get("requests", 0) + item[1].get("results", 0),
        reverse=True,
    )
    return [
        {
            "tool": tool,
            "requests": stats.get("requests", 0),
            "results": stats.get("results", 0),
            "succeeded": stats.get("succeeded", 0),
            "failed": stats.get("failed", 0),
            "success_rate": round(
                stats.get("succeeded", 0) / max(stats.get("results", 1), 1) * 100, 1
            ),
        }
        for tool, stats in ranked[:limit]
    ]


def _empty_summary() -> Dict[str, Any]:
    return {
        "total_requests": 0,
        "total_results": 0,
        "succeeded": 0,
        "failed": 0,
        "success_rate": 0.0,
        "verified": 0,
        "unverified": 0,
        "verification_rate": 0.0,
        "by_tool": {},
        "by_capability": {},
        "by_execution_mode": {},
        "errors": {},
        "period": {"from": None, "to": None},
    }


def _iso(ts: Optional[str]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts
