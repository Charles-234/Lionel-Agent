"""
Lionel Agent - Skill loader.

Scans configured skill sources, normalizes them into a single index,
detects duplicates by skill name, and writes master_index.json.

Run: python -m skills.loader
"""
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)


# Frontmatter parsing
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML-ish frontmatter from the top of a markdown file."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw = match.group(1)
    body = text[match.end():]

    fm: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_value_lines: List[str] = []

    def flush():
        nonlocal current_key, current_value_lines
        if current_key is not None:
            joined = "\n".join(current_value_lines).strip()
            if len(joined) >= 2 and joined[0] == joined[-1] and joined[0] in ('"', "'"):
                joined = joined[1:-1]
            fm[current_key] = joined
        current_key = None
        current_value_lines = []

    for line in raw.split("\n"):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_\-]*):\s*(.*)$", line)
        if m:
            flush()
            current_key = m.group(1)
            current_value_lines = [m.group(2)] if m.group(2) else []
        else:
            if current_key is not None:
                current_value_lines.append(line)

    flush()
    return fm, body


def load_prebuilt_index(source_name: str, source_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Load an existing index.json. Converts relative paths to absolute.
    Handles both folder paths (repo convention) and file paths.
    """
    index_path = Path(source_cfg["index_path"])
    if not index_path.exists():
        logger.warning(f"{source_name}: index not found at {index_path}")
        return []

    # Repo root = parent of the index.json file
    repo_root = index_path.parent.resolve()

    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    skills = []
    for skill in data.get("skills", []):
        rel_path = (skill.get("path") or "").strip()

        if not rel_path:
            abs_path = ""
        else:
            # Join with repo root
            joined = (repo_root / rel_path).resolve()
            # Keep the joined path inside the repo folder.  A path that points
            # outside (for example "../../secret") is dropped to an empty
            # value so it can never be used to reach other files.
            try:
                inside = joined.is_relative_to(repo_root)
            except ValueError:
                inside = False
            if not inside:
                logger.warning(f"{source_name}: ignoring path outside repo: {rel_path!r}")
                abs_path = ""
            elif joined.is_dir():
                candidate = joined / "SKILL.md"
                abs_path = str(candidate)
            elif joined.suffix == "" and not joined.exists():
                # Path has no extension and doesn't exist; likely a folder path
                # Assume it's a directory that should contain SKILL.md
                abs_path = str(joined / "SKILL.md")
            else:
                # Already a file path
                abs_path = str(joined)

        skills.append(_normalize({
            "name": skill.get("name", ""),
            "description": skill.get("description", ""),
            "category": skill.get("subdomain") or skill.get("category") or "",
            "source": source_name,
            "path": abs_path,
            "frontmatter": skill,
        }))
    return skills


def load_by_scan(source_name: str, source_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Walk a root folder, find every SKILL.md, parse frontmatter."""
    root = Path(source_cfg["root"])
    filename = source_cfg.get("filename", "SKILL.md")

    # Keep scan roots inside the project folder.  An outside root would let
    # the scan read files it should never touch, so refuse it loudly.
    try:
        _root_resolved = root.resolve()
        _project_root = Path(__file__).resolve().parent.parent
        _inside = _root_resolved.is_relative_to(_project_root)
    except ValueError:
        _inside = False
    if not _inside:
        logger.warning(f"{source_name}: ignoring scan root outside project: {str(root)!r}")
        return []
    if not root.exists():
        logger.warning(f"{source_name}: root not found at {root}")
        return []

    skills = []
    scanned = 0
    failed = 0

    for skill_file in root.rglob(filename):
        scanned += 1
        try:
            text = skill_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"{source_name}: cannot read {skill_file}: {e}")
            failed += 1
            continue

        fm, body = parse_frontmatter(text)
        name = fm.get("name") or skill_file.parent.name

        description = fm.get("description") or ""
        if not description:
            for line in body.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped[:500]
                    break

        category = fm.get("category") or ""
        if not category:
            try:
                rel = skill_file.parent.relative_to(root)
                parts = list(rel.parts)
                if len(parts) >= 2:
                    category = "/".join(parts[:-1])
            except ValueError:
                pass

        skills.append(_normalize({
            "name": str(name),
            "description": str(description),
            "category": str(category),
            "source": source_name,
            "path": str(skill_file.resolve()),
            "frontmatter": fm,
        }))

    logger.info(f"{source_name}: scanned={scanned}, loaded={len(skills)}, failed={failed}")
    return skills


def _normalize(record: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure every record has the same shape."""
    name = record.get("name", "").strip()
    description = record.get("description", "").strip()

    return {
        "id": _make_id(record.get("source", ""), name),
        "name": name,
        "name_lower": name.lower(),
        "description": description,
        "category": record.get("category", "").strip(),
        "source": record.get("source", ""),
        "path": record.get("path", ""),
        "frontmatter": record.get("frontmatter", {}),
    }


def _make_id(source: str, name: str) -> str:
    h = hashlib.sha1(f"{source}:{name}".encode()).hexdigest()[:12]
    return f"{source}-{h}"


def find_duplicates(skills: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Find skills with the same name (case-insensitive) across sources."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for s in skills:
        buckets.setdefault(s["name_lower"], []).append(s)
    return {k: v for k, v in buckets.items() if len(v) > 1}


def load_all() -> Dict[str, Any]:
    """Load from all sources, detect duplicates, return the master index dict."""
    all_skills: List[Dict[str, Any]] = []

    for source_name, source_cfg in config.SKILL_SOURCES.items():
        stype = source_cfg.get("type")
        logger.info(f"Loading source: {source_name} ({stype})")

        if stype == "prebuilt_index":
            skills = load_prebuilt_index(source_name, source_cfg)
        elif stype == "scan":
            skills = load_by_scan(source_name, source_cfg)
        else:
            logger.warning(f"{source_name}: unknown type '{stype}'")
            skills = []

        logger.info(f"{source_name}: {len(skills)} skills loaded")
        all_skills.extend(skills)

    dupes = find_duplicates(all_skills)
    duplicate_names = sorted(dupes.keys())
    logger.info(f"Duplicate names found: {len(duplicate_names)}")

    by_source: Dict[str, int] = {}
    for s in all_skills:
        by_source[s["source"]] = by_source.get(s["source"], 0) + 1

    return {
        "version": "1.0",
        "total": len(all_skills),
        "by_source": by_source,
        "duplicate_count": len(duplicate_names),
        "duplicate_names": duplicate_names[:100],
        "skills": all_skills,
        "duplicates": {k: [{"source": r["source"], "path": r["path"]} for r in v]
                       for k, v in dupes.items()},
    }


def save_index(index: Dict[str, Any], path: Optional[str] = None) -> None:
    """Write the master index to disk."""
    out_path = Path(path or config.SKILLS_INDEX_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    logger.info(f"Wrote {index['total']} skills to {out_path}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    index = load_all()
    save_index(index)

    print()
    print("=" * 60)
    print(f"TOTAL SKILLS:  {index['total']}")
    print("=" * 60)
    print()
    print("By source:")
    for source, count in sorted(index["by_source"].items()):
        print(f"  {source:12s} {count}")
    print()
    print(f"Duplicate names: {index['duplicate_count']}")
    if index["duplicate_count"] > 0:
        print("First 20 duplicate names:")
        for name in index["duplicate_names"][:20]:
            print(f"  - {name}")
    print()
    print(f"Master index written to: {config.SKILLS_INDEX_PATH}")


if __name__ == "__main__":
    main()