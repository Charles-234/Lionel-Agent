import unittest

from chains.recon import ReconChain
from tools.policy import AuthorizationScope
from tools.registry import ToolRegistry
from tools.recon.subfinder import Subfinder


class GovernedToolsTests(unittest.TestCase):
    def test_real_network_tool_denied_without_scope(self):
        registry = ToolRegistry()
        registry.register(Subfinder())
        result = registry.authorize_and_run("subfinder", {"domain": "example.com"}, capability_id="reconnaissance", role_id="offensive_security")
        self.assertFalse(result.success)
        self.assertIn("authorization scope", result.error.lower())

    def test_simulation_is_explicit_and_unverified(self):
        registry = ToolRegistry()
        registry.register(Subfinder())
        result = registry.authorize_and_run(
            "subfinder", {"domain": "example.com"}, capability_id="reconnaissance", role_id="offensive_security", execution_mode="simulation"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.execution_mode, "simulation")
        self.assertFalse(result.verified)

    def test_scope_does_not_authorize_other_domain(self):
        registry = ToolRegistry()
        registry.register(Subfinder())
        scope = AuthorizationScope.for_targets(
            "developer", ["example.com"], allow_network=True, max_risk="medium"
        )
        result = registry.authorize_and_run(
            "subfinder", {"domain": "example.net"}, capability_id="reconnaissance", role_id="offensive_security", scope=scope
        )
        self.assertFalse(result.success)
        self.assertIn("outside", result.error.lower())

    def test_scope_allows_in_scope_target(self):
        registry = ToolRegistry()
        registry.register(Subfinder())
        scope = AuthorizationScope.for_targets(
            "developer", ["example.com"], allow_network=True, max_risk="medium"
        )
        result = registry.authorize_and_run(
            "subfinder", {"domain": "example.com"}, scope=scope
        )
        # This test reaches the adapter; it may return success/failure depending
        # on whether the local subfinder binary exists, but policy must not deny it.
        self.assertNotEqual(result.error, "Requested target is outside the supplied authorization scope.")

    def test_chain_requires_scope_in_real_mode(self):
        result = ReconChain().run("example.com", execution_mode="real")
        self.assertFalse(result.success)
        self.assertIn("authorization", (result.error or "").lower())

    def test_chain_simulation_is_marked_unverified(self):
        result = ReconChain().run("example.com", execution_mode="simulation")
        self.assertEqual(result.execution_mode, "simulation")
        self.assertFalse(result.verified)


if __name__ == "__main__":
    unittest.main()
