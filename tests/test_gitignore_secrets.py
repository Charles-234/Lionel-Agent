import unittest
from pathlib import Path


class GitignoreSecretHygieneTests(unittest.TestCase):
    def test_gitignore_excludes_local_secret_artifacts(self):
        root = Path(__file__).resolve().parents[1]
        content = (root / ".gitignore").read_text(encoding="utf-8")

        for pattern in (
            ".env",
            ".env.*",
            "*.key",
            "*.pem",
            "*.crt",
            "*.p12",
            "*.pfx",
            "credentials*",
            "secrets*",
            "Armando.txt",
            "*.sqlite3",
            "*.sqlite",
            "*.db",
            "logs/",
        ):
            self.assertIn(pattern, content, f"Missing ignore pattern: {pattern}")


if __name__ == "__main__":
    unittest.main()
