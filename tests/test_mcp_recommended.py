import unittest

from lionel_platform.definitions import MCPServerSpec
from mcp.recommended import RECOMMENDED_SERVERS, build_recommended_registry


class MCPRecommendedRegistryTests(unittest.TestCase):
    def test_every_recommended_server_is_registered_but_disabled(self):
        registry = build_recommended_registry()
        servers = registry.list()
        self.assertEqual(
            {server.name for server in servers},
            {server.name for server in RECOMMENDED_SERVERS},
        )
        for server in servers:
            self.assertFalse(server.enabled)
            self.assertTrue(server.requires_approval)
            with self.assertRaises(KeyError):
                registry.get(server.name)

    def test_21st_ui_server_targets_the_vendor_http_endpoint_without_a_fixed_allowlist(self):
        server = next(item for item in RECOMMENDED_SERVERS if item.name == "21st")
        self.assertEqual(server.transport, "http")
        self.assertEqual(server.endpoint, "https://21st.dev/api/mcp")
        self.assertFalse(server.enabled)
        self.assertEqual(server.allowed_tools, ())

    def test_agentql_recommendation_is_a_governed_stdio_server_for_the_documented_tool(self):
        server = next(item for item in RECOMMENDED_SERVERS if item.name == "agentql")
        self.assertEqual(server.transport, "stdio")
        self.assertEqual(server.command, "npx")
        self.assertEqual(server.args, ("-y", "agentql-mcp"))
        self.assertEqual(server.allowed_tools, ("extract-web-data",))
        self.assertEqual(server.endpoint, "")
        self.assertFalse(server.enabled)

    def test_clicksend_recommendation_leaves_the_tool_allowlist_to_the_operator(self):
        server = next(item for item in RECOMMENDED_SERVERS if item.name == "clicksend")
        self.assertEqual(server.transport, "stdio")
        self.assertEqual(server.command, "npx")
        self.assertEqual(server.args, ("-y", "@clicksend/clicksend-mcp-server@latest"))
        self.assertEqual(server.allowed_tools, ())
        self.assertFalse(server.enabled)

    def test_recommended_specs_carry_no_inline_credentials(self):
        for server in RECOMMENDED_SERVERS:
            joined = " ".join((server.name, server.command, *server.args, server.endpoint)).lower()
            for marker in ("api_key", "apikey", "token", "password", "secret"):
                self.assertNotIn(marker, joined)

    def test_enabling_21st_still_requires_an_approved_role_grant(self):
        registry = build_recommended_registry()
        registry.register(MCPServerSpec(
            name="21st",
            command="",
            transport="http",
            endpoint="https://21st.dev/api/mcp",
            enabled=True,
            allowed_tools=("search",),
        ))
        registry.grant_tool("21st", "search", "engineer")
        self.assertFalse(registry.can_use("21st", "search", "engineer"))

        registry.grant_tool("21st", "search", "engineer", approved=True)
        self.assertTrue(registry.can_use("21st", "search", "engineer"))

        with self.assertRaises(ValueError):
            registry.grant_tool("21st", "generate", "engineer", approved=True)
