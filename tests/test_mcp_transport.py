import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lionel_platform.definitions import MCPServerSpec
from mcp.transport import (
    MCPClient,
    MCPTool,
    MCPTransportError,
    StreamableHTTPClient,
    register_governed_adapter,
    MCPToolAdapter,
)
from tools.policy import AuthorizationScope
from tools.executor import execute
from audit.ledger import AuditLedger


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {"content-type": "application/json"}
        self.text = json.dumps(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_streamable_http_handshake_discovery_and_invocation(monkeypatch):
    responses = iter([
        FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "fake"}}}, {"Mcp-Session-Id": "session-1"}),
        FakeResponse({"jsonrpc": "2.0"}),
        FakeResponse({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "search", "description": "Search", "inputSchema": {"type": "object"}}]}}),
        FakeResponse({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "ok"}]}}),
    ])
    post = MagicMock(side_effect=lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("mcp.transport.requests.Session.post", post)

    client = MCPClient(MCPServerSpec("fake", "", transport="http", endpoint="https://fake.test/mcp", enabled=True))
    result = client.connect()
    tools = client.list_tools()
    called = client.call_tool("search", {"query": "lionel"})

    assert result["serverInfo"]["name"] == "fake"
    assert tools[0].name == "search"
    assert called["content"][0]["text"] == "ok"
    assert post.call_args_list[2].kwargs["headers"]["Mcp-Session-Id"] == "session-1"


def test_streamable_http_timeout_is_sanitized(monkeypatch):
    def fail(*args, **kwargs):
        raise __import__("requests").Timeout()

    monkeypatch.setattr("mcp.transport.requests.Session.post", fail)
    client = MCPClient(MCPServerSpec("fake", "", transport="http", endpoint="https://fake.test/mcp", enabled=True))
    with pytest.raises(MCPTransportError, match="request failed"):
        client.connect()


def test_mcp_adapter_requires_normal_policy_before_invocation(monkeypatch, tmp_path):
    called = []

    class FakeClient:
        server = MCPServerSpec("fake", "", transport="http", endpoint="https://fake.test", enabled=True)

        def call_tool(self, name, arguments):
            called.append((name, arguments))
            return {"ok": True}

    adapter = MCPToolAdapter(
        FakeClient(),
        MCPTool("search"),
        tool_name="mcp_fake_search",
        audit_ledger=AuditLedger(str(tmp_path / "audit.sqlite3")),
    )
    register_governed_adapter(adapter, capability_id="research")

    denied = execute(
        "mcp_fake_search",
        {"query": "x"},
        capability_id="research",
        role="virtual_assistant",
        scope=AuthorizationScope(principal="owner", allow_network=False, max_risk="medium"),
        confirmed=True,
        session_id="mcp-test-denied",
    )
    assert denied.success is False
    assert called == []

    allowed = execute(
        "mcp_fake_search",
        {"query": "x"},
        capability_id="research",
        role="virtual_assistant",
        scope=AuthorizationScope(principal="owner", allow_network=True, max_risk="medium"),
        confirmed=True,
        session_id="mcp-test-allowed",
    )
    assert allowed.success is True
    assert called == [("search", {"query": "x"})]
    assert any(event["event_type"] == "MCP_TOOL_CALL" for event in adapter.audit_ledger.recent())