import unittest
from unittest.mock import patch

from agent.request_normalizer import RequestNormalizationError
from agent.runtime import AgentRuntime
from agent.session_state import SessionStateStore


class AgentBrainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.runtime = AgentRuntime()
        self.sessions = SessionStateStore()

    def test_normalized_request_reaches_non_executable_plan_and_session_state(self):
        decision = self.runtime.decide(
            "  Implement\n the requested feature  ",
            task_type="CODING",
            step_descriptions=["Inspect the codebase", "Implement the feature"],
        )
        state = self.sessions.record("integration-session", decision)

        self.assertEqual(decision.status, "PLAN_READY")
        self.assertEqual(decision.request.objective, "Implement the requested feature")
        self.assertEqual(decision.role_selection.role_id, "software_ai_architecture")
        self.assertEqual(
            [step.capability for step in decision.plan.steps],
            ["coding", "coding"],
        )
        self.assertFalse(decision.plan.execution_allowed)
        self.assertEqual(state.revision, 1)
        self.assertEqual(state.latest_decision, decision)

    def test_ambiguous_role_stops_before_plan_or_governance(self):
        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            decision = self.runtime.decide(
                "Assess the target",
                task_type="reconnaissance",
                step_descriptions=["Identify exposed services"],
            )
            state = self.sessions.record("integration-session", decision)

        self.assertEqual(decision.status, "ROLE_AMBIGUOUS")
        self.assertEqual(
            decision.role_selection.candidate_role_ids,
            ("offensive_security", "threat_intelligence"),
        )
        self.assertIsNone(decision.plan)
        self.assertEqual(state.latest_decision, decision)
        authorize.assert_not_called()
        execute.assert_not_called()

    def test_invalid_request_does_not_create_or_change_session_state(self):
        with self.assertRaises(RequestNormalizationError):
            self.runtime.decide(" \t", task_type="coding")

        state = self.sessions.get("integration-session")
        self.assertEqual(state.revision, 0)
        self.assertIsNone(state.latest_decision)

    def test_sessions_keep_independent_agent_decisions(self):
        ready = self.runtime.decide(
            "Implement the feature",
            task_type="coding",
            step_descriptions=["Inspect the codebase"],
        )
        needs_task_type = self.runtime.decide("Help me review this")

        self.sessions.record("session-ready", ready)
        self.sessions.record("session-pending", needs_task_type)

        self.assertEqual(
            self.sessions.get("session-ready").latest_decision.status,
            "PLAN_READY",
        )
        self.assertEqual(
            self.sessions.get("session-pending").latest_decision.status,
            "NEEDS_TASK_TYPE",
        )


if __name__ == "__main__":
    unittest.main()
