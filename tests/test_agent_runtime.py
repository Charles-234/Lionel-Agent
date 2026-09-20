import unittest
from unittest.mock import patch

from agent.runtime import AgentRuntime


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = AgentRuntime()

    def test_prepares_plan_after_unique_role_selection(self):
        decision = self.runtime.decide(
            "Implement the requested feature",
            task_type="coding",
            step_descriptions=["Inspect the codebase", "Implement the feature"],
        )

        self.assertEqual(decision.status, "PLAN_READY")
        self.assertEqual(decision.role_selection.role_id, "software_ai_architecture")
        self.assertIsNotNone(decision.plan)
        self.assertEqual(len(decision.plan.steps), 2)
        self.assertFalse(decision.plan.execution_allowed)

    def test_stops_when_task_type_is_unspecified(self):
        decision = self.runtime.decide("Help me review this")

        self.assertEqual(decision.status, "NEEDS_TASK_TYPE")
        self.assertIsNone(decision.plan)

    def test_stops_when_role_selection_is_ambiguous(self):
        decision = self.runtime.decide(
            "Assess the target",
            task_type="reconnaissance",
            step_descriptions=["Identify exposed services"],
        )

        self.assertEqual(decision.status, "ROLE_AMBIGUOUS")
        self.assertIsNone(decision.plan)

    def test_stops_when_no_role_matches_task_type(self):
        decision = self.runtime.decide("Hello", task_type="chat")

        self.assertEqual(decision.status, "ROLE_UNAVAILABLE")
        self.assertIsNone(decision.plan)

    def test_requires_explicit_steps_before_planning(self):
        decision = self.runtime.decide(
            "Implement the requested feature",
            task_type="coding",
        )

        self.assertEqual(decision.status, "PLAN_REQUIRED")
        self.assertIsNone(decision.plan)

    def test_decision_is_deterministic(self):
        kwargs = {
            "task_type": "coding",
            "step_descriptions": ["Inspect the codebase"],
        }

        self.assertEqual(
            self.runtime.decide("Implement the requested feature", **kwargs),
            self.runtime.decide("Implement the requested feature", **kwargs),
        )

    def test_runtime_does_not_authorize_or_execute(self):
        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            decision = self.runtime.decide(
                "Implement the requested feature",
                task_type="coding",
                step_descriptions=["Inspect the codebase"],
            )

        self.assertEqual(decision.status, "PLAN_READY")
        authorize.assert_not_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
