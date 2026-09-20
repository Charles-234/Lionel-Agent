import unittest
from unittest.mock import patch

from memory.working import (
    WORKING_MEMORY_KEY_REQUIRED_MESSAGE,
    WORKING_MEMORY_SESSION_REQUIRED_MESSAGE,
    WorkingMemoryError,
    WorkingMemoryStore,
)


class WorkingMemoryStoreTests(unittest.TestCase):
    def test_put_returns_immutable_session_snapshot(self):
        store = WorkingMemoryStore()

        snapshot = store.put(" session-1 ", " Authorized Target ", "example.com")

        self.assertEqual(snapshot.session_id, "session-1")
        self.assertEqual(snapshot.revision, 1)
        self.assertEqual(snapshot.entries[0].key, "authorized_target")
        self.assertEqual(snapshot.entries[0].value, "example.com")

    def test_replacing_key_increments_revision_without_duplicate_entry(self):
        store = WorkingMemoryStore()
        store.put("session-1", "target", "first.example")

        snapshot = store.put("session-1", "TARGET", "second.example")

        self.assertEqual(snapshot.revision, 2)
        self.assertEqual(len(snapshot.entries), 1)
        self.assertEqual(snapshot.entries[0].value, "second.example")

    def test_oldest_entry_is_evicted_deterministically_at_capacity(self):
        store = WorkingMemoryStore(max_entries=2)
        store.put("session-1", "first", "1")
        store.put("session-1", "second", "2")

        snapshot = store.put("session-1", "third", "3")

        self.assertEqual(
            [(entry.key, entry.value) for entry in snapshot.entries],
            [("second", "2"), ("third", "3")],
        )

    def test_sessions_are_isolated_and_clear_is_exact(self):
        store = WorkingMemoryStore()
        store.put("session-a", "target", "a.example")
        store.put("session-b", "target", "b.example")

        store.clear("session-a")

        self.assertEqual(store.snapshot("session-a").entries, ())
        self.assertEqual(store.snapshot("session-a").revision, 0)
        self.assertEqual(store.snapshot("session-b").entries[0].value, "b.example")

    def test_invalid_session_and_key_are_rejected_deterministically(self):
        store = WorkingMemoryStore()

        with self.assertRaisesRegex(WorkingMemoryError, WORKING_MEMORY_SESSION_REQUIRED_MESSAGE):
            store.snapshot(" ")
        with self.assertRaisesRegex(WorkingMemoryError, WORKING_MEMORY_KEY_REQUIRED_MESSAGE):
            store.put("session-1", " ", "value")

    def test_working_memory_does_not_authorize_or_execute(self):
        store = WorkingMemoryStore()

        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            snapshot = store.put("session-1", "target", "example.com")

        self.assertEqual(snapshot.revision, 1)
        authorize.assert_not_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
