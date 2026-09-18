import unittest

from agent.planner import Plan, PlanStep, Planner


class PlannerTests(unittest.TestCase):

    def setUp(self):
        self.planner = Planner()

    def test_creates_plan(self):
        plan = self.planner.plan(
            task_type="reconnaissance",
            objective="Assess an authorized target",
            steps=[
                PlanStep(
                    description="Identify exposed services",
                    capability="reconnaissance",
                    requires_tool=True,
                )
            ],
        )

        self.assertIsInstance(plan, Plan)
        self.assertEqual(plan.task_type, "reconnaissance")
        self.assertEqual(plan.objective, "Assess an authorized target")
        self.assertEqual(len(plan.steps), 1)

    def test_planner_never_authorizes_execution(self):
        plan = self.planner.plan(
            task_type="security_testing",
            objective="Assess an authorized target",
            steps=[
                PlanStep(
                    description="Perform assessment",
                    capability="security_testing",
                    requires_tool=True,
                )
            ],
        )

        self.assertFalse(plan.execution_allowed)

    def test_plan_step_records_capability(self):
        step = PlanStep(
            description="Enumerate services",
            capability="reconnaissance",
            requires_tool=True,
        )

        self.assertEqual(step.capability, "reconnaissance")
        self.assertTrue(step.requires_tool)

    def test_empty_task_type_rejected(self):
        with self.assertRaises(ValueError):
            self.planner.plan(
                task_type="",
                objective="Test",
                steps=[
                    PlanStep(
                        description="Step",
                        capability="reconnaissance",
                    )
                ],
            )

    def test_empty_objective_rejected(self):
        with self.assertRaises(ValueError):
            self.planner.plan(
                task_type="reconnaissance",
                objective="",
                steps=[
                    PlanStep(
                        description="Step",
                        capability="reconnaissance",
                    )
                ],
            )

    def test_empty_steps_rejected(self):
        with self.assertRaises(ValueError):
            self.planner.plan(
                task_type="reconnaissance",
                objective="Test",
                steps=[],
            )


if __name__ == "__main__":
    unittest.main()
