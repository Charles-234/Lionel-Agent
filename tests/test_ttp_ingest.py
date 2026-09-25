"""
Tests for TTP ingestion layer (skills/ingest.py) and /ingest command.

Everything runs completely offline:
- HTTP requests are faked (requests patched).
- Index writes are isolated to temporary directories (tempfile).
- Real skills/master_index.json and network resources are never touched.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commands.registry import parse_and_dispatch
from skills.ingest import (
    append_to_index,
    ingest_text,
    ingest_url,
    parse_ttp_text,
)
from skills.retriever import SkillRetriever
from tools.policy import AuthorizationScope


class _FakeResponse:
    def __init__(self, status_code: int = 200, body: bytes = b""):
        self.status_code = status_code
        self._body = body

    def iter_content(self, chunk_size: int = 65536):
        yield self._body

    def close(self):
        pass


class _FakeSessionModule:
    class exceptions:
        class RequestException(Exception):
            pass


def _raise_exc(_exc):
    raise _FakeSessionModule.exceptions.RequestException("connection dropped")


class TTPTextParsingTests(unittest.TestCase):
    def test_parse_frontmatter_text(self):
        text = (
            "---\n"
            "name: bypass-uac-fodhelper\n"
            "description: Abuse fodhelper registry keys to bypass UAC on Windows.\n"
            "category: privilege_escalation\n"
            "---\n"
            "# Bypass UAC via Fodhelper\n\n"
            "Steps:\n1. Write registry key HKCU:\\Software\\Classes\\ms-settings\\shell\\open\\command\n"
        )
        records = parse_ttp_text(text, source_url="https://example.com/uac")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["name"], "bypass-uac-fodhelper")
        self.assertIn("fodhelper", rec["description"])
        self.assertEqual(rec["category"], "privilege_escalation")
        self.assertEqual(rec["frontmatter"].get("source_url"), "https://example.com/uac")

    def test_parse_multisection_study_plan(self):
        text = (
            "# 30-Day Cybersecurity Curriculum\n\n"
            "Introductory plan for learning security fundamentals.\n\n"
            "## Day 1: Network Reconnaissance\n"
            "Learn TCP three-way handshakes, host discovery, and port enumeration.\n\n"
            "Practical exercises with tcpdump.\n\n"
            "## Day 2: Vulnerability Analysis\n"
            "Learn how to interpret CVEs and configure vulnerability scanners.\n\n"
            "Practical exercises with scan engines.\n"
        )
        records = parse_ttp_text(text, source_url="https://example.com/study-plan")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "Day 1: Network Reconnaissance")
        self.assertIn("three-way handshakes", records[0]["description"])
        self.assertEqual(records[1]["name"], "Day 2: Vulnerability Analysis")
        self.assertIn("CVEs", records[1]["description"])
        for r in records:
            self.assertEqual(r["category"], "ttp")
            self.assertEqual(r["frontmatter"].get("source_url"), "https://example.com/study-plan")

    def test_parse_single_doc_fallback(self):
        text = (
            "# Credential Dumping with Procdump\n\n"
            "Procdump is a Sysinternals utility that can be used to dump LSASS memory.\n\n"
            "Usage: procdump.exe -ma lsass.exe lsass.dmp\n"
        )
        records = parse_ttp_text(text, source_url="https://example.com/procdump")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["name"], "Credential Dumping with Procdump")
        self.assertIn("Sysinternals utility", rec["description"])
        self.assertEqual(rec["category"], "ttp")

    def test_parse_empty_and_garbage_returns_empty(self):
        self.assertEqual(parse_ttp_text(""), [])
        self.assertEqual(parse_ttp_text("   \n\n\t  "), [])
        self.assertEqual(parse_ttp_text("--- *** ### !!!"), [])
        self.assertEqual(parse_ttp_text(None), [])


class TTPIndexPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.index_path = Path(self.temp_dir.name) / "test_index.json"
        self.storage_dir = Path(self.temp_dir.name) / "ttp"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_append_creates_normalized_records_and_atomic_index(self):
        records = [
            {
                "name": "Kerberoasting Technique",
                "description": "Request TGS service tickets for accounts with SPNs.",
                "category": "credential_access",
                "source": "ttp",
                "body": "Detailed kerberoasting tutorial and methodology.",
                "frontmatter": {"mitre_id": "T1558.003"},
            }
        ]
        added, skipped = append_to_index(
            records,
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertEqual(len(added), 1)
        self.assertEqual(skipped, 0)

        # Check normalization shape
        rec = added[0]
        expected_keys = {
            "id", "name", "name_lower", "description",
            "category", "source", "path", "frontmatter"
        }
        self.assertEqual(set(rec.keys()), expected_keys)
        self.assertTrue(rec["id"].startswith("ttp-"))
        self.assertEqual(rec["name_lower"], "kerberoasting technique")
        self.assertTrue(Path(rec["path"]).is_file())

        # Check file content on disk
        saved_file = Path(rec["path"])
        content = saved_file.read_text(encoding="utf-8")
        self.assertIn("Kerberoasting Technique", content)
        self.assertIn("TGS service tickets", content)

        # Check JSON index structure
        with open(self.index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["by_source"].get("ttp"), 1)
        self.assertEqual(len(data["skills"]), 1)

    def test_deduplication_by_id(self):
        records = [
            {
                "name": "Pass-the-Hash",
                "description": "Authenticate using NTLM hash without plaintext password.",
                "category": "lateral_movement",
                "source": "ttp",
                "body": "PTH procedure.",
            }
        ]
        added1, skipped1 = append_to_index(
            records,
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertEqual(len(added1), 1)
        self.assertEqual(skipped1, 0)

        # Ingest identical skill again
        added2, skipped2 = append_to_index(
            records,
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertEqual(len(added2), 0)
        self.assertEqual(skipped2, 1)

        # Index total should remain 1
        with open(self.index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["total"], 1)

    def test_retriever_discovers_and_loads_ingested_skill(self):
        text = (
            "# Attack Graph Exploration\n\n"
            "## BloodHound Cypher Querying\n"
            "Query Active Directory attack graphs using Cypher syntax.\n\n"
            "MATCH (u:User)-[r:AdminTo]->(c:Computer) RETURN u,c\n\n"
            "## SharpHound Data Collection\n"
            "Collect session data and ACLs from domain joined systems.\n\n"
            "## AzureHound Entra Mapping\n"
            "Enumerate cloud identity attack paths in Microsoft Entra ID.\n"
        )
        res = ingest_text(
            text,
            source_url="https://example.com/bloodhound",
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.skills_added, 3)

        # Initialize retriever on temporary index
        retriever = SkillRetriever(index_path=str(self.index_path))
        retriever.load()

        # Search for skill
        matches = retriever.search("BloodHound Cypher", top_k=5, min_score=0.1)
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0].name, "BloodHound Cypher Querying")

        # Load skill content by name
        loaded = retriever.load_skill_by_name("BloodHound Cypher Querying")
        self.assertIsNotNone(loaded)
        self.assertIn("Active Directory attack graphs", loaded)


class GovernedIngestUrlTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.index_path = Path(self.temp_dir.name) / "test_index.json"
        self.storage_dir = Path(self.temp_dir.name) / "ttp"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _patch_requests(self, response=None, exc=None):
        import tools.web_fetcher as wf

        fake = _FakeSessionModule()
        fake.get = lambda *args, **kwargs: (
            _raise_exc(exc) if exc is not None else response
        )
        self._real_requests = wf.requests
        wf.requests = fake
        self.addCleanup(setattr, wf, "requests", self._real_requests)

    def test_ingest_url_success_offline(self):
        html_body = (
            b"<html><body>\n"
            b"<h1>Golden Ticket Creation</h1>\n"
            b"<p>Forge Kerberos TGT using the KRBTGT NTLM hash to gain domain persistence.</p>\n"
            b"</body></html>\n"
        )
        self._patch_requests(_FakeResponse(status_code=200, body=html_body))

        res = ingest_url(
            "https://example.com/golden-ticket",
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.skills_added, 1)
        self.assertIn("Golden Ticket", res.message)

        # Verify saved in index
        with open(self.index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["skills"][0]["name"], "Golden Ticket Creation")

    def test_ingest_url_refuses_invalid_url_safely(self):
        for bad_url in ("file:///etc/passwd", "ftp://example.com", "not-a-url", ""):
            res = ingest_url(
                bad_url,
                index_path=str(self.index_path),
                storage_dir=self.storage_dir,
            )
            self.assertFalse(res.success)
            self.assertNotIn("Traceback", res.message)

    def test_ingest_url_safe_refusal_on_network_failure(self):
        self._patch_requests(exc=True)
        res = ingest_url(
            "https://example.com/fails",
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertFalse(res.success)
        self.assertIn("Fetch failed safely", res.message)
        self.assertNotIn("Traceback", res.message)

    def test_ingest_url_safe_refusal_on_empty_text(self):
        html_body = b"<html><body><script>alert('only script')</script></body></html>"
        self._patch_requests(_FakeResponse(status_code=200, body=html_body))
        res = ingest_url(
            "https://example.com/empty",
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
        )
        self.assertFalse(res.success)
        self.assertIn("No usable text", res.message)

    def test_policy_enforcement_blocks_without_network_scope(self):
        # Scope without network permission must be denied by PolicyGateway
        restricted_scope = AuthorizationScope(
            principal="restricted",
            allow_network=False,
            max_risk="medium",
        )
        res = ingest_url(
            "https://example.com/test",
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
            scope=restricted_scope,
        )
        self.assertFalse(res.success)
        self.assertIn("network access is not allowed", res.message.lower())

    def test_policy_enforcement_blocks_insufficient_risk_scope(self):
        # Scope with lower risk than medium must be denied
        low_risk_scope = AuthorizationScope(
            principal="restricted",
            allow_network=True,
            max_risk="low",
        )
        res = ingest_url(
            "https://example.com/test",
            index_path=str(self.index_path),
            storage_dir=self.storage_dir,
            scope=low_risk_scope,
        )
        self.assertFalse(res.success)
        self.assertIn("risk exceeds", res.message.lower())


class CommandRegistryIngestTests(unittest.TestCase):
    def test_cmd_help_includes_ingest(self):
        res = parse_and_dispatch("/help")
        self.assertIsNotNone(res)
        self.assertIn("/ingest <url>", res.text)

    def test_cmd_ingest_without_args_shows_usage(self):
        res = parse_and_dispatch("/ingest")
        self.assertIsNotNone(res)
        self.assertTrue(res.is_error)
        self.assertIn("Usage: /ingest <url>", res.text)

    @patch("skills.ingest.ingest_url")
    def test_cmd_ingest_dispatches_cleanly(self, mock_ingest_url):
        from skills.ingest import IngestResult
        mock_ingest_url.return_value = IngestResult(
            success=True,
            message="Successfully ingested 1 skill(s) from https://example.com/ttp (IDs: ttp-123456).",
            skills_added=1,
        )
        res = parse_and_dispatch("/ingest https://example.com/ttp")
        self.assertIsNotNone(res)
        self.assertFalse(res.is_error)
        self.assertIn("Successfully ingested 1 skill(s)", res.text)
        mock_ingest_url.assert_called_once_with("https://example.com/ttp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
