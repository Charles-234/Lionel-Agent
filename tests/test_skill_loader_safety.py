"""Focused safety tests for skill-index path handling.

A bad path in an outside skill list must never let the loader point at
files outside the skill folder.  Configured scan folders must also stay
inside the project.
"""

import json
import unittest
from pathlib import Path

from skills.loader import load_by_scan, load_prebuilt_index


def _write_index(tmp_dir: Path, skills: list) -> Path:
    index_path = tmp_dir / "index.json"
    index_path.write_text(json.dumps({"skills": skills}), encoding="utf-8")
    return index_path


class SkillLoaderSafetyTests(unittest.TestCase):
    def test_escape_path_is_dropped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            index_path = _write_index(tmp_dir, [
                {"name": "bad", "path": "../../secret.txt"},
                {"name": "ok", "path": "my-skill"},
            ])
            out = load_prebuilt_index("t", {"index_path": str(index_path)})
            by_name = {s["name"]: s for s in out}
            self.assertEqual(by_name["bad"]["path"], "")
            self.assertTrue(by_name["ok"]["path"].endswith("SKILL.md"))

    def test_absolute_outside_path_is_dropped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            index_path = _write_index(tmp_dir, [
                {"name": "evil", "path": "C:/Windows/System32/drivers/etc/hosts"},
            ])
            out = load_prebuilt_index("t", {"index_path": str(index_path)})
            self.assertEqual(out[0]["path"], "")

    def test_scan_root_outside_project_is_refused(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = load_by_scan("t", {"root": tmp, "filename": "SKILL.md"})
            self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
