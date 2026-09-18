import unittest

from agent.request_planner import RequestPlanner, TASK_CAPABILITIES


class RequestPlannerTests(unittest.TestCase):

    def setUp(self):
        self.request_planner = RequestPlanner()

    def test_known_task_maps_to_capability(self):
        plan = self.request_planner.create_plan(
            task_type="reconnaissance",
            objective="Assess an authorized target",
            description="Identify exposed services",
            requires_tool=True,
        )

        self.assertEqual(plan.task_type, "reconnaissance")
        self.assertEqual(plan.steps[0].capability, "reconnaissance")
        self.assertTrue(plan.steps[0].requires_tool)

    def test_task_type_is_case_insensitive(self):
        plan = self.request_planner.create_plan(
            task_type="RECONNAISSANCE",
            objective="Assess an authorized target",
            description="Identify exposed services",
        )

        self.assertEqual(plan.task_type, "reconnaissance")

    def test_unknown_task_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.request_planner.create_plan(
                task_type="something_unknown",
                objective="Test",
                description="Test step",
            )

    def test_all_mappings_use_registered_capability_names(self):
        from agent_registry.capabilities import CAPABILITIES

        for capability in TASK_CAPABILITIES.values():
            self.assertIn(capability, CAPABILITIES)

    def test_adapter_does_not_authorize_execution(self):
        plan = self.request_planner.create_plan(
            task_type="security_testing",
            objective="Assess an authorized target",
            description="Perform assessment",
            requires_tool=True,
        )

        self.assertFalse(plan.execution_allowed)

    def test_adapter_does_not_execute_tools(self):
        plan = self.request_planner.create_plan(
            task_type="reconnaissance",
            objective="Assess an authorized target",
            description="Enumerate services",
            requires_tool=True,
        )

        self.assertIsNotNone(plan)
        self.assertFalse(plan.execution_allowed)


if __name__ == "__main__":
    unittest.main()
