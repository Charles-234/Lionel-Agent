"""Lionel live dashboard backend — FastAPI server for the web dashboard.

Serves real data from the audit ledger, provider router state, token budget,
and skill index. The dashboard.html/app.js fetch from these endpoints instead
of mock_data.json.

Run: uvicorn dashboard_backend:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from audit.metrics import tool_execution_summary, recent_activity, tool_usage_ranking
from providers import router, token_budget
from skills import retriever

app = FastAPI(title="Lionel Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user_name: str = ""
    error: str = ""


class SessionRow(BaseModel):
    id: str
    model: str
    turns: int
    tokens: int
    status: str


class ProviderRow(BaseModel):
    name: str
    status: str
    latency_ms: Optional[int] = None


class TokenSummary(BaseModel):
    total_tokens: int
    total_requests: int
    by_hour: Dict[str, int]


class SkillsSummary(BaseModel):
    total: int
    by_source: Dict[str, int]
    by_category: Dict[str, int]


# ---------------------------------------------------------------------------
# Auth (simple check against config — owner-only for now)
# ---------------------------------------------------------------------------

OWNER_EMAIL = "+254712633234@lionel.local"


def _check_owner(email: str, password: str) -> Optional[str]:
    """Return user name if credentials match, else None."""
    if email.strip().lower() == OWNER_EMAIL and password.strip():
        return "Owner"
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "agent": config.AGENT_NAME,
        "version": config.AGENT_VERSION,
        "roles": len(config.ROLES),
        "skills_indexed": _skill_total(),
        "router_models": len(config.ROUTING),
        "utc_now": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    name = _check_owner(req.email, req.password)
    if name:
        return LoginResponse(ok=True, user_name=name)
    return LoginResponse(ok=False, error="Invalid credentials")


@app.get("/api/sessions", response_model=List[SessionRow])
def get_sessions() -> List[SessionRow]:
    """Return recent audit sessions as session rows."""
    from audit.ledger import AuditLedger
    ledger = AuditLedger()
    events = ledger.recent(limit=200)
    sessions: Dict[str, Dict[str, Any]] = {}
    for e in events:
        sid = e.get("session_id")
        if not sid:
            continue
        if sid not in sessions:
            sessions[sid] = {
                "id": sid,
                "model": e.get("tool", "unknown") or "unknown",
                "turns": 1,
                "tokens": 0,
                "status": "ok",
            }
        if e["event_type"] == "TOOL_RESULT":
            sessions[sid]["turns"] = sessions[sid].get("turns", 0) + 1
            if e.get("success"):
                sessions[sid]["status"] = "ok"
            else:
                sessions[sid]["status"] = "error"
    rows = sorted(sessions.values(), key=lambda s: s["id"], reverse=True)[:50]
    return [
        SessionRow(
            id=r["id"],
            model=r["model"],
            turns=r["turns"],
            tokens=r["tokens"],
            status=r["status"],
        )
        for r in rows
    ]


@app.get("/api/providers", response_model=List[ProviderRow])
def get_providers() -> List[ProviderRow]:
    """Return provider health from router state + config."""
    state = router.router_state()
    rows: List[ProviderRow] = []

    for task_type, entries in config.ROUTING.items():
        for entry in entries:
            source = entry.get("source", "")
            provider = entry.get("provider", "-")
            model = entry.get("model", "")
            label = f"{provider}/{model}" if source == "direct" else f"{source}/{model}"

            if label in state:
                status = "degraded"
                latency = None
            else:
                status = "ok"
                latency = None

            rows.append(ProviderRow(name=label, status=status, latency_ms=latency))

    # Deduplicate by name
    seen: Dict[str, ProviderRow] = {}
    for r in rows:
        if r.name not in seen:
            seen[r.name] = r
    return list(seen.values())


@app.get("/api/tokens/summary", response_model=TokenSummary)
def get_tokens_summary() -> TokenSummary:
    """Return token usage summary from the token budget."""
    total_used = 0
    for user_id in (0, config.ADMIN_TELEGRAM_ID):
        try:
            stats = token_budget.stats(user_id)
            total_used += stats["used"]
        except Exception:
            pass

    return TokenSummary(
        total_tokens=total_used,
        total_requests=0,
        by_hour={},
    )


@app.get("/api/skills/summary", response_model=SkillsSummary)
def get_skills_summary() -> SkillsSummary:
    """Return skill index summary."""
    try:
        r = retriever.get_retriever()
        categories = r.list_categories()
        sources = r.list_sources()
        return SkillsSummary(
            total=len(r.skills),
            by_source=sources,
            by_category=categories,
        )
    except Exception:
        return SkillsSummary(total=0, by_source={}, by_category={})


@app.get("/api/audit/summary")
def get_audit_summary() -> Dict[str, Any]:
    """Return tool execution summary from audit ledger."""
    try:
        return tool_execution_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit/activities")
def get_audit_activities(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent audit activities."""
    try:
        return recent_activity(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _skill_total() -> int:
    try:
        return len(retriever.get_retriever().skills)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Static files — dashboard UI
# ---------------------------------------------------------------------------

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

# Serve static assets (CSS, JS, images) at /assets
app.mount(
    "/assets",
    StaticFiles(directory="web_dashboard"),
    name="assets",
)

@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    """Serve dashboard at root."""
    return FileResponse("web_dashboard/dashboard.html")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
