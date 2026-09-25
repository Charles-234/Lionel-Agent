from datetime import datetime, timedelta, timezone

import pytest

from lionel_platform.codebase import collect_codebase_context
from lionel_platform.definitions import MCPServerSpec, SandboxProfile, default_catalog
from lionel_platform.scheduler import ScheduledTask, TaskScheduler
from mcp.registry import MCPRegistry
from providers import direct
from providers.types import Message


def test_catalog_exposes_connectors_and_sandbox_profiles_without_enabling_them():
    catalog = default_catalog()
    assert catalog.connectors["telegram"].enabled is True
    assert catalog.connectors["discord"].enabled is False
    assert catalog.sandboxes["docker"].enabled is False


def test_mcp_requires_explicit_approved_role_grant():
    registry = MCPRegistry()
    registry.register(MCPServerSpec("docs", "npx", enabled=True, allowed_tools=("read",)))
    registry.grant_tool("docs", "read", "engineer")
    assert registry.can_use("docs", "read", "engineer") is False
    registry.grant_tool("docs", "read", "engineer", approved=True)
    assert registry.can_use("docs", "read", "engineer") is True
    with pytest.raises(ValueError):
        registry.grant_tool("docs", "write", "engineer", approved=True)


def test_scheduler_only_reports_due_and_reschedules_recurring_tasks():
    scheduler = TaskScheduler()
    now = datetime.now(timezone.utc)
    scheduler.add(ScheduledTask("daily", "run report", now - timedelta(seconds=1), 60))
    assert [task.task_id for task in scheduler.due(now)] == ["daily"]
    scheduler.acknowledge("daily", now)
    assert scheduler.due(now) == []


def test_codebase_context_skips_env_and_generated_directories():
    context = collect_codebase_context(".", query="chat", max_files=10)
    assert ".env" not in context.files
    assert not any(path.startswith(".venv/") for path in context.files)


def test_local_openai_compatible_provider_uses_standard_chat_payload(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"model": "local-test", "choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(direct, "_post_with_retries", lambda *args: Response())
    result = direct.call_openai_compatible(
        "local-test",
        [Message(role="user", content="hello")],
        "http://localhost:11434",
    )
    assert result.text == "ok"
    assert result.provider == "local"
