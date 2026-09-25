import unittest

from tools.policy import AuthorizationScope, PolicyGateway
from tools.registry import get_registry
from tools.executor import execute


class CapabilityGateTests(unittest.TestCase):
    def setUp(self):
        self.scope = AuthorizationScope.for_targets(
            "offline-test",
            ["example.com"],
            allow_network=True,
            max_risk="high",
            reason="offline governance test",
        )

    def test_correct_capability_allows_simulation(self):
        result = execute(
            "subfinder",
            {"domain": "example.com"},
            capability_id="reconnaissance",
            role="offensive_security",
            execution_mode="simulation",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.execution_mode, "simulation")
        self.assertFalse(result.verified)

    def test_wrong_capability_is_denied(self):
        result = execute(
            "subfinder",
            {"domain": "example.com"},
            capability_id="web_design",
            role="offensive_security",
            execution_mode="simulation",
        )
        self.assertFalse(result.success)
        self.assertIn("not authorized", result.error.lower())

    def test_missing_capability_is_denied_for_network_tool(self):
        result = execute(
            "subfinder",
            {"domain": "example.com"},
            role="offensive_security",
            execution_mode="simulation",
        )
        self.assertFalse(result.success)
        self.assertIn("capability", result.error.lower())

    def test_real_network_requires_scope_and_correct_capability(self):
        result = execute(
            "subfinder",
            {"domain": "example.com"},
            capability_id="reconnaissance",
            role="offensive_security",
            execution_mode="real",
        )
        self.assertFalse(result.success)
        self.assertIn("authorization scope", result.error.lower())

    def test_real_network_with_scope_reaches_tool_boundary(self):
        result = execute(
            "subfinder",
            {"domain": "example.com"},
            capability_id="reconnaissance",
            role="offensive_security",
            scope=self.scope,
            execution_mode="real",
        )
        # The test environment may not have the binary. Either a controlled
        # unavailable-binary result or a real adapter result is acceptable;
        # the policy must not deny the call.
        self.assertNotIn("capability context is required", (result.error or "").lower())
        self.assertNotIn("not authorized", (result.error or "").lower())

    def test_registry_contains_only_governed_current_adapters(self):
        names = {item["name"] for item in get_registry().list()}
        self.assertEqual(names, {"subfinder", "httpx", "nuclei"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
