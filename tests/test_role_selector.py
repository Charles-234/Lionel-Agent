import unittest
from unittest.mock import patch

from agent.request_normalizer import normalize_request
from agent.role_selector import RoleSelection, select_role


class RoleSelectorTests(unittest.TestCase):
    def test_selects_unique_role_for_known_task_type(self):
        selection = select_role(
            normalize_request("Implement the requested feature", task_type="coding")
        )

        self.assertEqual(
            selection,
            RoleSelection(
                status="SELECTED",
                task_type="coding",
                role_id="software_ai_architecture",
                candidate_role_ids=("software_ai_architecture",),
            ),
        )

    def test_ambiguous_roles_remain_explicit(self):
        selection = select_role(
            normalize_request("Assess the target", task_type="reconnaissance")
        )

        self.assertEqual(selection.status, "AMBIGUOUS")
        self.assertIsNone(selection.role_id)
        self.assertEqual(
            selection.candidate_role_ids,
            ("offensive_security", "threat_intelligence"),
        )

    def test_missing_task_type_remains_explicit(self):
        selection = select_role(normalize_request("Help me review this"))

        self.assertEqual(selection.status, "UNSPECIFIED")
        self.assertIsNone(selection.role_id)
        self.assertEqual(selection.candidate_role_ids, ())

    def test_task_type_without_declared_role_is_not_invented(self):
        selection = select_role(normalize_request("Hello", task_type="chat"))

        self.assertEqual(selection.status, "NO_MATCH")
        self.assertIsNone(selection.role_id)
        self.assertEqual(selection.candidate_role_ids, ())

    def test_selection_is_deterministic(self):
        request = normalize_request("Assess the target", task_type="reconnaissance")

        self.assertEqual(select_role(request), select_role(request))

    def test_selection_does_not_authorize_capabilities(self):
        request = normalize_request("Implement the feature", task_type="coding")

        with patch("agent_registry.authorization.authorize_role_capability") as authorize:
            select_role(request)

        authorize.assert_not_called()

    def test_selection_cannot_execute_tools(self):
        request = normalize_request("Implement the feature", task_type="coding")

        with patch("tools.executor.execute") as execute:
            select_role(request)

        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
