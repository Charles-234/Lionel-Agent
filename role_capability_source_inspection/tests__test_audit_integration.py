import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit.ledger import AuditLedger
from audit.integration import record_request, record_result


class FakeResult:
    success = True
    verified = False
    execution_mode = "simulation"
    error = None


class AuditIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "audit.sqlite3"
        self.ledger = AuditLedger(str(self.db))

    def tearDown(self):
        self.tmp.cleanup()

    def test_request_and_result_are_recorded(self):
        record_request(
            self.ledger,
            session_id="s1",
            role="offensive_security",
            capability="reconnaissance",
            tool="nmap",
            execution_mode="simulation",
            target="192.0.2.10",
        )
        record_result(
            self.ledger,
            started=0.0,
            session_id="s1",
            role="offensive_security",
            capability="reconnaissance",
            tool="nmap",
            execution_mode="simulation",
            target="192.0.2.10",
            result=FakeResult(),
        )
        rows = self.ledger.recent(10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_type"], "TOOL_RESULT")
        self.assertEqual(rows[1]["event_type"], "TOOL_REQUEST")
        self.assertEqual(rows[0]["verification_status"], "UNVERIFIED")

    def test_raw_target_and_secret_do_not_enter_audit(self):
        record_request(
            self.ledger,
            session_id="s2",
            role="test",
            capability="test",
            tool="test",
            execution_mode="simulation",
            target="https://private.example.invalid/path",
        )
        self.ledger.record(__import__("audit.ledger", fromlist=["AuditEvent"]).AuditEvent(
            event_type="ERROR",
            details={"message": "token=DO_NOT_STORE_THIS"},
        ))
        raw = self.db.read_bytes()
        self.assertNotIn(b"private.example.invalid", raw)
        self.assertNotIn(b"DO_NOT_STORE_THIS", raw)

    def test_audit_failure_does_not_reach_tool(self):
        from tools.executor import execute

        class Tool:
            name = "fake"

        with patch("tools.executor.get_audit_ledger", side_effect=RuntimeError("ledger unavailable")):
            with self.assertRaises(RuntimeError):
                execute(Tool(), {}, capability="test", execution_mode="simulation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
