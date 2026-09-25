"""Temporary live probe for the newly registered MCP servers.

Uses the repository transport only. No tool is called, so no audit event is
written; the probe answers one question: does a real MCP server complete the
handshake and list tools through ``mcp.transport``?
"""

from __future__ import annotations

import json
import time

from lionel_platform.definitions import MCPServerSpec
from mcp.transport import MCPClient


def probe(command: str, args: tuple[str, ...], *, timeout: int = 150) -> None:
    server = MCPServerSpec(name="probe", command=command, args=args, transport="stdio", enabled=True)
    client = MCPClient(server, timeout=timeout)
    started = time.perf_counter()
    try:
        info = client.connect()
    except Exception as exc:
        print(f"  connect: FAILED after {time.perf_counter() - started:.1f}s -> {type(exc).__name__}: {exc}", flush=True)
        client.close()
        return
    print(f"  connect: ok after {time.perf_counter() - started:.1f}s -> {json.dumps(info)[:200]}", flush=True)
    try:
        names = [item.name for item in client.list_tools()]
        print(f"  tools/list: {len(names)} -> {names}", flush=True)
    except Exception as exc:
        print(f"  tools/list: FAILED -> {type(exc).__name__}: {exc}", flush=True)
    client.close()


CASES = (
    ("agentql via npx", "npx", ("-y", "agentql-mcp")),
    ("agentql via npx.cmd", "npx.cmd", ("-y", "agentql-mcp")),
    ("clicksend via npx", "npx", ("-y", "@clicksend/clicksend-mcp-server@latest")),
    ("clicksend via npx.cmd", "npx.cmd", ("-y", "@clicksend/clicksend-mcp-server@latest")),
)

for label, command, arguments in CASES:
    print(f"{label} (command={command})", flush=True)
    probe(command, arguments)
print("probe finished", flush=True)
