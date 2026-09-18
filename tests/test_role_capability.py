import unittest

from agent_registry.roles import ROLES
from agent_registry.capabilities import CAPABILITIES


class RoleCapabilityTests(unittest.TestCase):
    def test_all_19_roles_are_present(self):
        self.assertEqual(len(ROLES), 19)

    def test_roles_have_required_metadata(self):
        for role in ROLES.values():
            self.assertTrue(role.id)
            self.assertTrue(role.name)
            self.assertTrue(role.description)
            self.assertTrue(role.skill_categories)
            self.assertTrue(role.capability_categories)

    def test_capabilities_have_required_metadata(self):
        for capability in CAPABILITIES.values():
            self.assertTrue(capability.id)
            self.assertTrue(capability.name)
            self.assertTrue(capability.category)
            self.assertTrue(capability.modality)

    def test_core_capabilities_exist(self):
        for capability_id in (
            "chat", "reasoning", "coding", "web_design",
            "reconnaissance", "malware_analysis", "document_processing",
        ):
            self.assertIn(capability_id, CAPABILITIES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
