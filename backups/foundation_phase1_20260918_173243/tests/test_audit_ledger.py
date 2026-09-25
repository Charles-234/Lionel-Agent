import tempfile
import unittest
from pathlib import Path

from audit.ledger import AuditEvent, AuditLedger


class AuditLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "audit.sqlite3"
        self.ledger = AuditLedger(str(self.db))

    def tearDown(self):
        self.tmp.cleanup()

    def test_database_and_event_are_created(self):
        event_id = self.ledger.record(AuditEvent(
            event_type="TOOL_EXECUTION",
            session_id="test-session",
            role="offensive_security",
            capability="reconnaissance",
            tool="nmap",
            policy_decision="ALLOW",
            execution_mode="simulation",
            success=True,
            verification_status="UNVERIFIED",
            duration_ms=12,
            target="192.0.2.10",
        ))
        self.assertTrue(event_id)
        rows = self.ledger.recent(10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tool"], "nmap")
        self.assertEqual(rows[0]["target_hash"], "6d99cbd08fc6c99c")

    def test_raw_target_is_not_stored(self):
        self.ledger.record(AuditEvent(
            event_type="POLICY_DECISION",
            target="https://example-authorized.invalid/secret",
        ))
        raw = self.db.read_bytes()
        self.assertNotIn(b"example-authorized.invalid", raw)
        self.assertNotIn(b"/secret", raw)

    def test_secrets_are_redacted(self):
        self.ledger.record(AuditEvent(
            event_type="ERROR",
            details={
                "message": "api_key=SUPER_SECRET_VALUE",
                "authorization": "Bearer TOP_SECRET_TOKEN",
            },
        ))
        rows = self.ledger.recent(10)
        text = str(rows[0])
        self.assertNotIn("SUPER_SECRET_VALUE", text)
        self.assertNotIn("TOP_SECRET_TOKEN", text)
        self.assertIn("[REDACTED]", text)

    def test_verification_status_is_stored(self):
        self.ledger.record(AuditEvent(
            event_type="VERIFICATION",
            verification_status="VERIFIED",
            success=True,
        ))
        rows = self.ledger.recent(10)
        self.assertEqual(rows[0]["verification_status"], "VERIFIED")

    def test_multiple_operations_release_database_handle(self):
        for _ in range(5):
            self.ledger.record(AuditEvent(event_type="HANDLE_TEST"))
            self.ledger.recent(10)
        # tearDown removes the SQLite file on Windows. If a connection
        # leaked, this test module would fail during cleanup.


if __name__ == "__main__":
    unittest.main(verbosity=2)
