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

    def test_creates_multi_step_plan_from_explicit_descriptions(self):
        plan = self.request_planner.create_multi_step_plan(
            task_type="RECONNAISSANCE",
            objective="Assess an authorized target",
            descriptions=[
                "Identify exposed services",
                "Document observed endpoints",
            ],
            requires_tool=True,
        )

        self.assertEqual(plan.task_type, "reconnaissance")
        self.assertEqual(
            [step.description for step in plan.steps],
            ["Identify exposed services", "Document observed endpoints"],
        )
        self.assertEqual(
            [step.capability for step in plan.steps],
            ["reconnaissance", "reconnaissance"],
        )
        self.assertTrue(all(step.requires_tool for step in plan.steps))
        self.assertFalse(plan.execution_allowed)

    def test_multi_step_plan_rejects_missing_descriptions(self):
        with self.assertRaisesRegex(ValueError, "at least one plan step description"):
            self.request_planner.create_multi_step_plan(
                task_type="research",
                objective="Review the sources",
                descriptions=[],
            )

    def test_multi_step_plan_rejects_empty_description(self):
        with self.assertRaisesRegex(ValueError, "plan step descriptions"):
            self.request_planner.create_multi_step_plan(
                task_type="research",
                objective="Review the sources",
                descriptions=["Gather sources", "  "],
            )

    def test_multi_step_plan_rejects_single_string_as_descriptions(self):
        with self.assertRaisesRegex(ValueError, "at least one plan step description"):
            self.request_planner.create_multi_step_plan(
                task_type="research",
                objective="Review the sources",
                descriptions="Gather sources",
            )


if __name__ == "__main__":
    unittest.main()
