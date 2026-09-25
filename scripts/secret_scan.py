"""Repository secret scan for Lionel.

This is intentionally narrow and conservative: it looks for likely credential
material in source and configuration files without exposing the actual secret
value in the result payload.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Dict, Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|authorization|bearer)\b\s*[:=]\s*[^\s\r\n]+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(?:ghp|gho|ghu|ghs|github_pat|xox[baprs]-)[A-Za-z0-9_\-]{10,}\b"),
]

_IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "logs",
    ".idea",
    ".vscode",
    "node_modules",
}

_IGNORED_FILES = {".env.example", "README.md"}


def _is_ignored(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in _IGNORED_DIRS for part in rel.parts):
        return True
    if path.name in _IGNORED_FILES:
        return True
    return False


def scan_repo(root: str | Path) -> List[Dict[str, Any]]:
    """Return secret-like findings without leaking the actual matched secret."""
    base = Path(root).resolve()
    findings: List[Dict[str, Any]] = []

    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if _is_ignored(path, base):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for pattern in _SECRET_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            snippet = match.group(0)
            redacted = re.sub(r"(?i)(sk-[A-Za-z0-9_-]{8,}|(?:ghp|gho|ghu|ghs|github_pat|xox[baprs]-)[A-Za-z0-9_\-]{10,}|\b(?:api[_-]?key|token|secret|password|passwd|authorization|bearer)\b\s*[:=]\s*)[^\s\r\n]+",
                              lambda m: m.group(1) + "[REDACTED]" if m.group(1) else "[REDACTED]",
                              snippet)
            findings.append({
                "path": str(path),
                "match": redacted,
                "kind": pattern.pattern,
            })
            break

    return findings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scan a repo for likely secret material.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    results = scan_repo(args.root)
    if not results:
        print("No likely secret material found.")
    else:
        print(f"Found {len(results)} candidate secret-like matches.")
        for item in results:
            print(f"- {item['path']}: {item['match']}")
