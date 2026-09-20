import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory.persistent import (
    MEMORY_LIFETIME_INVALID_MESSAGE,
    PersistentMemoryError,
    PersistentMemoryStore,
)


class _FrozenClock:
    """A controllable clock so expiry is tested without sleeping."""

    def __init__(self, start: float = 1_700_000_000.0):
        self._current = start

    def now(self) -> float:
        return self._current

    def advance(self, seconds: float) -> None:
        self._current += seconds


class PersistentMemoryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "lionel_memory.sqlite3"
        self.clock = _FrozenClock()
        self._clock_patch = patch("memory.persistent._now", self.clock.now)
        self._clock_patch.start()
        self.store = PersistentMemoryStore(self.db_path)

    def tearDown(self):
        self._clock_patch.stop()
        self.tmp.cleanup()

    def _raw_row_count(self) -> int:
        """Count rows straight from the file, bypassing the store's own reads."""
        connection = sqlite3.connect(str(self.db_path))
        try:
            return connection.execute(
                "SELECT COUNT(*) FROM persistent_memory"
            ).fetchone()[0]
        finally:
            connection.close()

    def test_fact_without_a_lifetime_never_expires(self):
        self.store.put("owner-1", "project", "Lionel")

        self.clock.advance(60 * 60 * 24 * 365 * 10)

        self.assertEqual(self.store.get("owner-1", "project").value, "Lionel")
        self.assertEqual(len(self.store.list("owner-1")), 1)
        self.assertEqual(self.store.count("owner-1"), 1)
        self.assertIsNone(self.store.list_records("owner-1")[0].expires_at)
        self.assertFalse(self.store.list_records("owner-1")[0].expired)

    def test_lifetime_hides_a_fact_from_reads_once_it_passes(self):
        self.store.put("owner-1", "session token", "temporary", ttl_seconds=60)
        self.assertEqual(self.store.get("owner-1", "session token").value, "temporary")

        self.clock.advance(61)

        self.assertIsNone(self.store.get("owner-1", "session token"))
        self.assertEqual(self.store.list("owner-1"), ())
        self.assertEqual(self.store.count("owner-1"), 0)

        records = self.store.list_records("owner-1")
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].expired)

    def test_expiry_alone_does_not_delete_from_disk_until_purge(self):
        self.store.put("owner-1", "old note", "stale", ttl_seconds=10)

        self.clock.advance(11)

        self.assertEqual(self._raw_row_count(), 1)
        self.assertEqual(self.store.purge_expired("owner-1"), 1)
        self.assertEqual(self._raw_row_count(), 0)

    def test_purge_expired_can_be_limited_to_one_owner(self):
        self.store.put("owner-a", "note", "a", ttl_seconds=10)
        self.store.put("owner-b", "note", "b", ttl_seconds=10)

        self.clock.advance(11)

        self.assertEqual(self.store.purge_expired("owner-a"), 1)
        self.assertEqual(self.store.list_records("owner-a"), ())
        self.assertEqual(len(self.store.list_records("owner-b")), 1)
        self.assertEqual(self.store.purge_expired(), 1)
        self.assertEqual(self._raw_row_count(), 0)

    def test_purge_leaves_permanent_and_live_facts_untouched(self):
        self.store.put("owner-1", "permanent", "keep")
        self.store.put("owner-1", "live", "keep", ttl_seconds=3600)
        self.store.put("owner-1", "stale", "drop", ttl_seconds=10)

        self.clock.advance(11)

        self.assertEqual(self.store.purge_expired("owner-1"), 1)
        self.assertEqual(
            [entry.key for entry in self.store.list("owner-1")],
            ["live", "permanent"],
        )

    def test_replacing_a_fact_without_a_lifetime_makes_it_permanent_again(self):
        self.store.put("owner-1", "note", "temporary", ttl_seconds=10)
        self.store.put("owner-1", "note", "durable")

        self.clock.advance(60)

        self.assertEqual(self.store.get("owner-1", "note").value, "durable")
        self.assertIsNone(self.store.list_records("owner-1")[0].expires_at)

    def test_replacing_a_fact_restarts_its_lifetime(self):
        self.store.put("owner-1", "note", "first", ttl_seconds=100)

        self.clock.advance(60)
        self.store.put("owner-1", "note", "second", ttl_seconds=100)
        self.clock.advance(60)

        self.assertEqual(self.store.get("owner-1", "note").value, "second")

        self.clock.advance(41)
        self.assertIsNone(self.store.get("owner-1", "note"))

    def test_invalid_lifetimes_are_rejected_deterministically(self):
        for invalid in (0, -1, True, "60", float("inf"), float("nan")):
            with self.subTest(lifetime=invalid):
                with self.assertRaisesRegex(
                    PersistentMemoryError, MEMORY_LIFETIME_INVALID_MESSAGE
                ):
                    self.store.put("owner-1", "note", "value", ttl_seconds=invalid)

        self.assertEqual(self.store.count("owner-1"), 0)

    def test_an_existing_database_is_migrated_without_losing_facts(self):
        legacy_path = Path(self.tmp.name) / "legacy_memory.sqlite3"
        connection = sqlite3.connect(str(legacy_path))
        try:
            connection.execute("""
                CREATE TABLE persistent_memory (
                    owner_id TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    PRIMARY KEY (owner_id, memory_key)
                )
            """)
            connection.execute(
                "INSERT INTO persistent_memory (owner_id, memory_key, memory_value)"
                " VALUES (?, ?, ?)",
                ("owner-legacy", "project", "Lionel"),
            )
            connection.commit()
        finally:
            connection.close()

        migrated = PersistentMemoryStore(legacy_path)

        self.assertEqual(migrated.get("owner-legacy", "project").value, "Lionel")
        record = migrated.list_records("owner-legacy")[0]
        self.assertEqual(record.created_at, 0.0)
        self.assertIsNone(record.expires_at)
        self.assertFalse(record.expired)
        self.assertEqual(migrated.purge_expired(), 0)

        migrated.put("owner-legacy", "scratch", "temporary", ttl_seconds=5)
        self.assertEqual(migrated.count("owner-legacy"), 2)

    def test_lifecycle_operations_do_not_authorize_or_execute(self):
        with patch("agent_registry.authorization.authorize_role_capability") as authorize, \
                patch("tools.executor.execute") as execute:
            self.store.put("owner-1", "note", "value", ttl_seconds=10)
            self.store.get("owner-1", "note")
            self.store.list("owner-1")
            self.store.count("owner-1")
            self.store.list_records("owner-1")
            self.store.purge_expired()

        authorize.assert_not_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()