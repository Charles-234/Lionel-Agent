"""Bounded deep-codebase context collection for planning and code tasks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules", "backups", ".pytest_cache"}
DEFAULT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".md", ".json", ".yaml", ".yml", ".toml"}


@dataclass(frozen=True)
class CodebaseContext:
    root: str
    files: tuple[str, ...]
    content: str
    truncated: bool = False


def collect_codebase_context(
    root: str | os.PathLike[str],
    query: str = "",
    *,
    max_files: int = 80,
    max_file_chars: int = 12_000,
    max_total_chars: int = 80_000,
) -> CodebaseContext:
    """Collect relevant source context without reading secrets or archives."""
    base = Path(root).resolve()
    candidates = []
    query_terms = {term.lower() for term in query.split() if len(term) > 2}
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.name.lower() in {".env", "credentials.json", "secrets.json"}:
            continue
        score = 0 if not query_terms else sum(term in path.name.lower() for term in query_terms)
        candidates.append((score, str(path)))
    candidates.sort(key=lambda item: (-item[0], item[1]))

    chunks = []
    files = []
    total = 0
    truncated = False
    for _, raw_path in candidates[:max_files]:
        path = Path(raw_path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:max_file_chars]
        except OSError:
            continue
        block = f"\n--- {path.relative_to(base).as_posix()} ---\n{text}"
        if total + len(block) > max_total_chars:
            truncated = True
            break
        chunks.append(block)
        files.append(path.relative_to(base).as_posix())
        total += len(block)
    return CodebaseContext(str(base), tuple(files), "".join(chunks), truncated)
