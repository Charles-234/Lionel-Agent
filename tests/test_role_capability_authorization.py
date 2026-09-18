import unittest

from agent_registry.authorization import (
    authorize_role_capability,
    validate_role_capability_contract,
)


class RoleCapabilityAuthorizationTests(unittest.TestCase):
    def test_contract_has_no_undefined_capabilities(self):
        self.assertEqual(validate_role_capability_contract(), [])

    def test_offensive_security_can_use_reconnaissance(self):
        self.assertTrue(authorize_role_capability("offensive_security", "reconnaissance").allowed)

    def test_offensive_security_can_use_security_testing(self):
        self.assertTrue(authorize_role_capability("offensive_security", "security_testing").allowed)

    def test_virtual_assistant_cannot_use_reconnaissance(self):
        decision = authorize_role_capability("virtual_assistant", "reconnaissance")
        self.assertFalse(decision.allowed)
        self.assertIn("not authorized", decision.reason.lower())

    def test_unknown_role_is_denied(self):
        self.assertFalse(authorize_role_capability("does_not_exist", "research").allowed)

    def test_unknown_capability_is_denied(self):
        self.assertFalse(authorize_role_capability("offensive_security", "does_not_exist").allowed)

    def test_missing_role_is_denied(self):
        self.assertFalse(authorize_role_capability(None, "research").allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
