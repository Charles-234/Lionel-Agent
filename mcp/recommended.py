"""Opt-in definitions for useful MCP servers.

They are disabled until the operator reviews the server, tool allowlist, and
credential policy. ``build_recommended_registry`` only registers metadata.
"""

from mcp.registry import MCPRegistry
from lionel_platform.definitions import MCPServerSpec


RECOMMENDED_SERVERS = (
    MCPServerSpec(
        name="parallel-search",
        command="",
        transport="http",
        endpoint="https://search.parallel.ai/mcp",
        enabled=False,
        allowed_tools=("search",),
    ),
    MCPServerSpec(
        name="playwright",
        command="npx",
        args=("@playwright/mcp@latest",),
        transport="stdio",
        enabled=False,
        allowed_tools=(),
    ),
    MCPServerSpec(
        name="context7",
        command="npx",
        args=("-y", "@upstash/context7-mcp"),
        transport="stdio",
        enabled=False,
        allowed_tools=(),
    ),
    MCPServerSpec(
        name="21st",
        command="",
        transport="http",
        endpoint="https://21st.dev/api/mcp",
        enabled=False,
        allowed_tools=(),
    ),
    MCPServerSpec(
        name="agentql",
        command="npx",
        args=("-y", "agentql-mcp"),
        transport="stdio",
        enabled=False,
        allowed_tools=("extract-web-data",),
    ),
    MCPServerSpec(
        name="clicksend",
        command="npx",
        args=("-y", "@clicksend/clicksend-mcp-server@latest"),
        transport="stdio",
        enabled=False,
        allowed_tools=(),
    ),
)


def build_recommended_registry() -> MCPRegistry:
    registry = MCPRegistry()
    for server in RECOMMENDED_SERVERS:
        registry.register(server)
    return registry
