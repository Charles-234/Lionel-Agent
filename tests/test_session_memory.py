import unittest
from unittest.mock import patch

from agent.runtime import AgentRuntime
from memory.session import (
    SESSION_MEMORY_ID_REQUIRED_MESSAGE,
    SessionMemoryError,
    SessionMemoryStore,
)


class SessionMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.runtime = AgentRuntime()

    def test_records_compact_decision_summary_without_raw_user_text(self):
        store = SessionMemoryStore()
        decision = self.runtime.decide(
            "Implement the requested sensitive feature",
            task_type="coding",
            step_descriptions=["Inspect the codebase", "Implement the feature"],
        )

        snapshot = store.record("session-1", decision)
        entry = snapshot.entries[0]

        self.assertEqual(snapshot.revision, 1)
        self.assertEqual(entry.status, "PLAN_READY")
        self.assertEqual(entry.task_type, "coding")
        self.assertEqual(entry.role_id, "software_ai_architecture")
        self.assertEqual(entry.plan_step_count, 2)
        self.assertNotIn("sensitive", repr(entry))

    def test_history_is_bounded_in_insertion_order(self):
        store = SessionMemoryStore(max_entries=2)
        ready = self.runtime.decide(
            "Implement the feature",
            task_type="coding",
            step_descriptions=["Inspect the codebase"],
        )
        pending = self.runtime.decide("Help me review this")

        store.record("session-1", ready)
        store.record("session-1", pending)
        snapshot = store.record("session-1", ready)

        self.assertEqual(snapshot.revision, 3)
        self.assertEqual(
            [entry.status for entry in snapshot.entries],
            ["NEEDS_TASK_TYPE", "PLAN_READY"],
        )

    def test_sessions_are_isolated_and_clear_is_exact(self):
        store = SessionMemoryStore()
        decision = self.runtime.decide("Help me review this")
        store.record("session-a", decision)
        store.record("session-b", decision)

        store.clear("session-a")

        self.assertEqual(store.snapshot("session-a").entries, ())
        self.assertEqual(store.snapshot("session-a").revision, 0)
        self.assertEqual(store.snapshot("session-b").revision, 1)

    def test_blank_session_id_is_rejected_deterministically(self):
        store = SessionMemoryStore()

        with self.assertRaisesRegex(SessionMemoryError, SESSION_MEMORY_ID_REQUIRED_MESSAGE):
            store.snapshot(" \n")

    def test_session_memory_does_not_authorize_or_execute(self):
        store = SessionMemoryStore()
        decision = self.runtime.decide("Help me review this")

        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            snapshot = store.record("session-1", decision)

        self.assertEqual(snapshot.revision, 1)
        authorize.assert_not_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
