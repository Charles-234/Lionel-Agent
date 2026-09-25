import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.secret_scan import scan_repo


class SecretScanTests(unittest.TestCase):
    def test_finds_secret_like_values_without_printing_the_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("OMNIROUTE_API_KEY=sk-real-secret-token\n", encoding="utf-8")
            (root / "notes.txt").write_text("Authorization: Bearer abcdef123456\n", encoding="utf-8")
            (root / ".env.example").write_text("OMNIROUTE_API_KEY=\n", encoding="utf-8")

            results = scan_repo(root)

            self.assertTrue(results)
            self.assertEqual(len(results), 2)
            for item in results:
                self.assertIn(str(root), item["path"])
                self.assertNotIn("sk-real-secret-token", item["match"])
                self.assertNotIn("abcdef123456", item["match"])

    def test_ignores_example_template_and_ignored_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".venv").mkdir()
            (root / ".venv" / "bad.txt").write_text("api_key = secret_here\n", encoding="utf-8")
            (root / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
            (root / "safe.txt").write_text("This is just documentation.\n", encoding="utf-8")

            results = scan_repo(root)
            self.assertFalse(results)


if __name__ == "__main__":
    unittest.main()
