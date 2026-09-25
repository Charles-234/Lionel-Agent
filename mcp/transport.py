"""Minimal MCP JSON-RPC transports and governed tool adapters.

The transport knows protocol mechanics only. Permission remains in
``tools.policy.PolicyGateway`` through the normal governed executor.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import requests

from audit.ledger import AuditEvent, AuditLedger
from lionel_platform.definitions import MCPServerSpec
from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
MCP_PROTOCOL_VERSION = "2025-06-18"


class MCPTransportError(RuntimeError):
    """Safe protocol/transport failure."""


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None


class JsonRpcClient:
    def request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        raise NotImplementedError

    def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return None


class StreamableHTTPClient(JsonRpcClient):
    """MCP Streamable HTTP client for a single server session."""

    def __init__(self, endpoint: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS, headers: Optional[dict[str, str]] = None):
        self.endpoint = endpoint
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        self.session = requests.Session()
        self.session_id: Optional[str] = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _decode(self, response: requests.Response) -> dict[str, Any]:
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self.session_id = session_id
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type:
            data_lines = []
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            if not data_lines:
                raise MCPTransportError("MCP returned an empty event stream.")
            payload = data_lines[-1]
        else:
            payload = response.text
        try:
            message = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise MCPTransportError("MCP returned invalid JSON.") from exc
        if "error" in message:
            error = message.get("error") or {}
            raise MCPTransportError(f"MCP request failed: {error.get('code', 'unknown')}")
        return message

    def _post(self, body: dict[str, Any]) -> requests.Response:
        try:
            response = self.session.post(
                self.endpoint,
                headers=self._headers(),
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.warning("MCP HTTP request failed: %s", type(exc).__name__)
            raise MCPTransportError("MCP server request failed.") from exc

    def request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        body = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            body["params"] = params
        return self._decode(self._post(body))

    def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        try:
            self._post(body)
        except MCPTransportError:
            logger.warning("MCP notification failed for %s", method)

    def close(self) -> None:
        self.session.close()


class StdioClient(JsonRpcClient):
    """Line-delimited JSON-RPC client for local MCP command servers."""

    def __init__(self, command: str, args: tuple[str, ...] = (), *, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.timeout = timeout
        self.process = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._request_id = 0
        self._lock = threading.Lock()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, body: dict[str, Any], expect_response: bool) -> Optional[dict[str, Any]]:
        if self.process.poll() is not None or self.process.stdin is None or self.process.stdout is None:
            raise MCPTransportError("MCP stdio server is not running.")
        with self._lock:
            self.process.stdin.write(json.dumps(body) + "\n")
            self.process.stdin.flush()
            if not expect_response:
                return None
            result: dict[str, Any] = {}
            ready = queue.Queue(maxsize=1)

            def read_one() -> None:
                try:
                    line = self.process.stdout.readline()
                    ready.put(json.loads(line) if line else {})
                except Exception:
                    ready.put({})

            thread = threading.Thread(target=read_one, daemon=True)
            thread.start()
            try:
                result = ready.get(timeout=self.timeout)
            except queue.Empty as exc:
                raise MCPTransportError("MCP stdio request timed out.") from exc
        if not result:
            raise MCPTransportError("MCP stdio server returned no response.")
        if "error" in result:
            raise MCPTransportError("MCP server returned a JSON-RPC error.")
        return result

    def request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        body = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            body["params"] = params
        return self._send(body, True) or {}

    def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        self._send(body, False)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


class MCPClient:
    """Handshake, discovery, and invocation for one registered MCP server."""

    def __init__(self, server: MCPServerSpec, *, timeout: int = DEFAULT_TIMEOUT_SECONDS, headers: Optional[dict[str, str]] = None):
        self.server = server
        self.timeout = timeout
        self.headers = headers or {}
        self.transport: Optional[JsonRpcClient] = None

    def connect(self) -> dict[str, Any]:
        if not self.server.enabled:
            raise MCPTransportError("MCP server is disabled.")
        if self.server.transport == "http":
            if not self.server.endpoint:
                raise MCPTransportError("MCP HTTP endpoint is not configured.")
            self.transport = StreamableHTTPClient(self.server.endpoint, timeout=self.timeout, headers=self.headers)
        elif self.server.transport == "stdio":
            self.transport = StdioClient(self.server.command, self.server.args, timeout=self.timeout)
        else:
            raise MCPTransportError("Unsupported MCP transport.")
        result = self.transport.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "Lionel", "version": "0.1.0"},
            },
        )
        self.transport.notify("notifications/initialized", {})
        return result.get("result", {})

    def list_tools(self) -> list[MCPTool]:
        if self.transport is None:
            self.connect()
        response = self.transport.request("tools/list", {})
        tools = (response.get("result") or {}).get("tools", [])
        return [
            MCPTool(
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                input_schema=item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {},
            )
            for item in tools
            if item.get("name")
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.transport is None:
            self.connect()
        response = self.transport.request("tools/call", {"name": name, "arguments": arguments})
        return (response.get("result") or {})

    def close(self) -> None:
        if self.transport:
            self.transport.close()
            self.transport = None


class MCPToolAdapter(Tool):
    """A normal governed Tool that delegates its run to one MCP tool."""

    def __init__(self, client: MCPClient, tool: MCPTool, *, tool_name: str, risk_level: str = "medium", audit_ledger: Optional[AuditLedger] = None):
        self.client = client
        self.mcp_tool = tool
        self.name = tool_name
        self.description = tool.description or f"MCP tool {tool.name}"
        self.category = "mcp"
        self.risk_level = risk_level
        self.network_access = True
        self.confirmation_required = True
        self.supports_simulation = False
        self.provenance = f"mcp:{client.server.name}"
        self.audit_ledger = audit_ledger

    def schema(self) -> dict[str, Any]:
        return self.mcp_tool.input_schema or {"type": "object", "properties": {}}

    def run(self, **kwargs: Any) -> ToolResult:
        started = time.perf_counter()
        ledger = self.audit_ledger or AuditLedger()
        try:
            result = self.client.call_tool(self.mcp_tool.name, kwargs)
            ledger.record(AuditEvent(
                event_type="MCP_TOOL_CALL",
                tool=self.name,
                execution_mode="real",
                success=True,
                verification_status="VERIFIED",
                duration_ms=int((time.perf_counter() - started) * 1000),
                details={"server": self.client.server.name, "mcp_tool": self.mcp_tool.name},
            ))
            return ToolResult(
                success=True,
                data=result,
                tool_name=self.name,
                execution_mode="real",
                verified=True,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except MCPTransportError:
            ledger.record(AuditEvent(
                event_type="MCP_TOOL_CALL",
                tool=self.name,
                execution_mode="real",
                success=False,
                verification_status="UNVERIFIED",
                error_code="MCP_TRANSPORT_ERROR",
                duration_ms=int((time.perf_counter() - started) * 1000),
                details={"server": self.client.server.name, "mcp_tool": self.mcp_tool.name},
            ))
            return ToolResult(
                success=False,
                error="MCP tool call failed safely.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


def make_client(server: MCPServerSpec, *, timeout: int = DEFAULT_TIMEOUT_SECONDS, headers: Optional[dict[str, str]] = None) -> MCPClient:
    return MCPClient(server, timeout=timeout, headers=headers)


def register_governed_adapter(
    adapter: MCPToolAdapter,
    *,
    capability_id: str,
    risk_level: str = "medium",
) -> None:
    """Expose an MCP tool through the existing registries.

    This registers declarations only. Authorization still happens later in
    PolicyGateway through tools.executor.execute().
    """
    from tools.registry import get_registry
    from tools_registry.base import ToolSpec, TOOLS, register_tool

    if adapter.name not in TOOLS:
        register_tool(ToolSpec(
            id=adapter.name,
            name=adapter.name,
            category="mcp",
            description=adapter.description,
            capabilities=[capability_id],
            risk_level=risk_level,
            network_access=True,
            confirmation_required=True,
            execution_modes=["real"],
            provenance=adapter.provenance,
        ))
    registry = get_registry()
    try:
        registry.get(adapter.name)
    except KeyError:
        registry.register(adapter, source=adapter.provenance)
