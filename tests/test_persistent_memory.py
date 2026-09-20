import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory.persistent import (
    MEMORY_KEY_REQUIRED_MESSAGE,
    OWNER_ID_REQUIRED_MESSAGE,
    PersistentMemoryError,
    PersistentMemoryStore,
)


class PersistentMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "lionel_memory.sqlite3"
        self.store = PersistentMemoryStore(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_fact_persists_across_store_instances(self):
        stored = self.store.put("owner-1", "Preferred Language", "Python")
        reloaded = PersistentMemoryStore(self.db_path).get("owner-1", "preferred language")

        self.assertEqual(stored, reloaded)
        self.assertEqual(stored.key, "preferred_language")

    def test_owner_records_are_isolated(self):
        self.store.put("owner-a", "project", "Lionel")
        self.store.put("owner-b", "project", "Other")

        self.assertEqual(self.store.get("owner-a", "project").value, "Lionel")
        self.assertEqual(self.store.get("owner-b", "project").value, "Other")

    def test_replaces_key_and_lists_in_deterministic_order(self):
        self.store.put("owner-1", "zeta", "first")
        self.store.put("owner-1", "alpha", "second")
        self.store.put("owner-1", "ZETA", "updated")

        entries = self.store.list("owner-1")

        self.assertEqual([(entry.key, entry.value) for entry in entries], [
            ("alpha", "second"),
            ("zeta", "updated"),
        ])

    def test_forget_and_clear_owner_are_exact(self):
        self.store.put("owner-a", "one", "1")
        self.store.put("owner-a", "two", "2")
        self.store.put("owner-b", "one", "other")

        self.assertTrue(self.store.forget("owner-a", "one"))
        self.assertFalse(self.store.forget("owner-a", "one"))
        self.assertEqual(self.store.clear_owner("owner-a"), 1)
        self.assertEqual(self.store.list("owner-a"), ())
        self.assertEqual(self.store.get("owner-b", "one").value, "other")

    def test_invalid_owner_and_key_are_rejected_deterministically(self):
        with self.assertRaisesRegex(PersistentMemoryError, OWNER_ID_REQUIRED_MESSAGE):
            self.store.list(" ")
        with self.assertRaisesRegex(PersistentMemoryError, MEMORY_KEY_REQUIRED_MESSAGE):
            self.store.put("owner-1", " ", "value")

    def test_persistent_memory_does_not_authorize_or_execute(self):
        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            entry = self.store.put("owner-1", "project", "Lionel")

        self.assertEqual(entry.value, "Lionel")
        authorize.assert_not_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
