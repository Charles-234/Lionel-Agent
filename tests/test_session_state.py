import unittest
from unittest.mock import patch

from agent.runtime import AgentRuntime
from agent.session_state import (
    SESSION_ID_REQUIRED_MESSAGE,
    SessionStateError,
    SessionStateStore,
)


class SessionStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStateStore()
        self.decision = AgentRuntime().decide(
            "Implement the requested feature",
            task_type="coding",
            step_descriptions=["Inspect the codebase"],
        )

    def test_get_creates_empty_session_state(self):
        state = self.store.get(" session-1 ")

        self.assertEqual(state.session_id, "session-1")
        self.assertEqual(state.revision, 0)
        self.assertIsNone(state.latest_decision)

    def test_record_creates_incrementing_immutable_revisions(self):
        first = self.store.record("session-1", self.decision)
        second = self.store.record("session-1", self.decision)

        self.assertEqual(first.revision, 1)
        self.assertEqual(second.revision, 2)
        self.assertEqual(second.latest_decision, self.decision)
        self.assertEqual(self.store.get("session-1"), second)

    def test_sessions_are_isolated(self):
        self.store.record("session-a", self.decision)

        self.assertEqual(self.store.get("session-a").revision, 1)
        self.assertEqual(self.store.get("session-b").revision, 0)
        self.assertIsNone(self.store.get("session-b").latest_decision)

    def test_clear_discards_only_target_session_state(self):
        self.store.record("session-a", self.decision)
        self.store.record("session-b", self.decision)

        self.store.clear("session-a")

        self.assertEqual(self.store.get("session-a").revision, 0)
        self.assertEqual(self.store.get("session-b").revision, 1)

    def test_blank_session_id_is_rejected_deterministically(self):
        with self.assertRaisesRegex(SessionStateError, SESSION_ID_REQUIRED_MESSAGE):
            self.store.get(" \t")

    def test_store_does_not_authorize_or_execute(self):
        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            state = self.store.record("session-1", self.decision)

        self.assertEqual(state.revision, 1)
        authorize.assert_not_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
