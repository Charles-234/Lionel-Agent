"""
Lionel Agent - TTP (Tactics, Techniques, and Procedures) Skill Ingestion.

Turns governed-fetched public text into normalized skill records that the
retriever understands, deduplicated by ID, and appended atomically to the
master skills index.

Governance:
- Uses the existing web_fetch tool via tools.executor.execute().
- PolicyGateway enforces capability 'research', role 'virtual_assistant',
  and network authorization scope.
- Ingestion layer never bypasses or duplicates the policy boundary.
- Refuses nothing silently: failures return concise, safe feedback.
"""
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from skills.loader import _make_id, _normalize, find_duplicates, parse_frontmatter
from tools.executor import execute
from tools.policy import AuthorizationScope

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    success: bool
    message: str
    skills_added: int = 0
    skills_skipped: int = 0
    skills: List[Dict[str, Any]] = field(default_factory=list)


def _clean_title(raw: str) -> str:
    """Strip markdown formatting and punctuation from titles."""
    text = re.sub(r"[#*_`~\[\]]", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120]


def _extract_first_paragraph(body: str, max_chars: int = 500) -> str:
    """Extract first non-heading, non-empty descriptive paragraph."""
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if stripped.startswith(("#", "```", "---", "- ", "* ", ">")):
            if lines:
                break
            continue
        lines.append(stripped)
    desc = " ".join(lines).strip()
    return desc[:max_chars]


def parse_ttp_text(text: str, source_url: str = "") -> List[Dict[str, Any]]:
    """Parse public text into candidate skill records.

    Handles:
    1. Markdown frontmatter with YAML metadata.
    2. Multi-section Markdown documents (e.g. Day 1, Day 2 study plans or multiple techniques).
    3. Plain text / single document fallback.
    """
    if not isinstance(text, str):
        return []
    cleaned = text.strip()
    if not cleaned or len(re.findall(r"[a-zA-Z0-9]", cleaned)) < 10:
        return []

    # 1. Frontmatter parsing
    fm, body = parse_frontmatter(cleaned)
    if fm and (fm.get("name") or fm.get("title")):
        name = _clean_title(str(fm.get("name") or fm.get("title")))
        description = str(fm.get("description") or "").strip()
        if not description:
            description = _extract_first_paragraph(body)
        category = str(fm.get("category") or fm.get("domain") or "ttp").strip()
        fm_copy = dict(fm)
        if source_url:
            fm_copy.setdefault("source_url", source_url)
        return [{
            "name": name,
            "description": description,
            "category": category,
            "body": body,
            "frontmatter": fm_copy,
        }]

    # 2. Multi-section document (e.g., ## Day 1: ..., ## Day 2: ... or ## Technique ...)
    section_pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    matches = list(section_pattern.finditer(cleaned))
    if len(matches) >= 2:
        records: List[Dict[str, Any]] = []
        for i, match in enumerate(matches):
            raw_title = match.group(2).strip()
            title = _clean_title(raw_title)
            if not title or len(re.findall(r"[a-zA-Z0-9]", title)) < 3:
                continue

            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
            section_body = cleaned[start_pos:end_pos].strip()

            desc = _extract_first_paragraph(section_body)
            if not desc:
                # Fallback to first non-empty lines of section
                first_lines = [l.strip() for l in section_body.splitlines() if l.strip() and not l.strip().startswith("#")]
                desc = (" ".join(first_lines))[:300] if first_lines else title

            records.append({
                "name": title,
                "description": desc,
                "category": "ttp",
                "body": f"## {title}\n\n{section_body}",
                "frontmatter": {
                    "source_url": source_url,
                    "section": title,
                },
            })
        if records:
            return records

    # 3. Single document fallback
    first_heading_match = re.search(r"^#\s+(.+)$", cleaned, re.MULTILINE)
    if first_heading_match:
        title = _clean_title(first_heading_match.group(1))
        body = cleaned[first_heading_match.end():].strip()
        desc = _extract_first_paragraph(body)
    else:
        # First non-empty line as title
        lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
        if not lines:
            return []
        first_line = lines[0]
        if len(lines) == 1 and (". " in first_line or len(first_line) > 80):
            if ". " in first_line:
                part1, part2 = first_line.split(". ", 1)
                title = _clean_title(part1)
                body = part2.strip()
                desc = _clean_title(part2)[:500]
            elif " - " in first_line:
                part1, part2 = first_line.split(" - ", 1)
                title = _clean_title(part1)
                body = part2.strip()
                desc = _clean_title(part2)[:500]
            elif ": " in first_line:
                part1, part2 = first_line.split(": ", 1)
                title = _clean_title(part1)
                body = part2.strip()
                desc = _clean_title(part2)[:500]
            else:
                title = _clean_title(first_line[:80])
                body = cleaned
                desc = _clean_title(first_line)[:500]
        else:
            title = _clean_title(first_line)
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else cleaned
            desc = _extract_first_paragraph(body)

    if not title or len(re.findall(r"[a-zA-Z0-9]", title)) < 3:
        return []

    if not desc:
        desc = title

    return [{
        "name": title,
        "description": desc,
        "category": "ttp",
        "body": cleaned,
        "frontmatter": {"source_url": source_url} if source_url else {},
    }]


def _write_skill_markdown(
    record: Dict[str, Any],
    skill_id: str,
    storage_dir: Path,
) -> str:
    """Save skill body to a markdown file on disk so retriever can load it."""
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / f"{skill_id}.md"
        content = (
            f"---\n"
            f"name: \"{record.get('name', '')}\"\n"
            f"description: \"{record.get('description', '')}\"\n"
            f"category: \"{record.get('category', '')}\"\n"
            f"source: \"{record.get('source', 'ttp')}\"\n"
            f"id: \"{skill_id}\"\n"
            f"---\n\n"
            f"{record.get('body', record.get('description', ''))}\n"
        )
        file_path.write_text(content, encoding="utf-8")
        return str(file_path.resolve())
    except Exception as exc:
        logger.warning("Failed to write skill markdown file: %s", exc)
        return ""


def append_to_index(
    records: List[Dict[str, Any]],
    index_path: Optional[str] = None,
    storage_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Normalize, deduplicate by ID, and atomically append skills to index.

    Returns (added_records, skipped_count).
    """
    target_path = Path(index_path or config.SKILLS_INDEX_PATH)
    if storage_dir is None:
        storage_dir = target_path.parent / "ttp"

    # Load or initialize index
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception as exc:
            logger.error("Failed to read existing index at %s: %s", target_path, exc)
            index_data = {
                "version": "1.0",
                "total": 0,
                "by_source": {},
                "duplicate_count": 0,
                "duplicate_names": [],
                "skills": [],
                "duplicates": {},
            }
    else:
        index_data = {
            "version": "1.0",
            "total": 0,
            "by_source": {},
            "duplicate_count": 0,
            "duplicate_names": [],
            "skills": [],
            "duplicates": {},
        }

    existing_skills = index_data.get("skills", [])
    existing_ids = {s.get("id") for s in existing_skills if s.get("id")}

    added: List[Dict[str, Any]] = []
    skipped = 0

    for rec in records:
        source_name = rec.get("source") or "ttp"
        rec_name = rec.get("name", "").strip()
        skill_id = _make_id(source_name, rec_name)

        if skill_id in existing_ids:
            skipped += 1
            continue

        # Save markdown file so retriever.load_skill works
        saved_path = _write_skill_markdown(rec, skill_id, storage_dir)

        candidate = {
            "name": rec_name,
            "description": rec.get("description", ""),
            "category": rec.get("category", "ttp"),
            "source": source_name,
            "path": saved_path,
            "frontmatter": rec.get("frontmatter", {}),
        }
        normalized = _normalize(candidate)
        added.append(normalized)
        existing_ids.add(skill_id)

    if added:
        all_skills = existing_skills + added
        index_data["skills"] = all_skills
        index_data["total"] = len(all_skills)

        # Update by_source counts
        by_source: Dict[str, int] = {}
        for s in all_skills:
            src = s.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1
        index_data["by_source"] = by_source

        # Update duplicate statistics
        dupes = find_duplicates(all_skills)
        index_data["duplicate_count"] = len(dupes)
        index_data["duplicate_names"] = sorted(dupes.keys())[:100]
        index_data["duplicates"] = {
            k: [{"source": r.get("source", ""), "path": r.get("path", "")} for r in v]
            for k, v in dupes.items()
        }

        # Atomic file replacement
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = target_path.with_name(
            f"{target_path.name}.tmp.{os.getpid()}.{time.time_ns()}"
        )
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target_path)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

        # Reload in-memory retriever if it points to this index
        try:
            from skills import retriever
            if retriever._default is not None:
                if retriever._default.index_path.resolve() == target_path.resolve():
                    retriever._default.load()
        except Exception:
            logger.warning("Could not refresh active in-memory retriever", exc_info=True)

    return added, skipped


def ingest_text(
    text: str,
    source_url: str = "",
    *,
    index_path: Optional[str] = None,
    storage_dir: Optional[Path] = None,
    source: str = "ttp",
    category: str = "ttp",
) -> IngestResult:
    """Parse text, normalize, and atomically append to index."""
    raw_records = parse_ttp_text(text, source_url=source_url)
    if not raw_records:
        return IngestResult(
            success=False,
            message="Ingest failed: No usable skill or TTP content found in text.",
        )

    for r in raw_records:
        r.setdefault("source", source)
        r.setdefault("category", category)

    added, skipped = append_to_index(
        raw_records, index_path=index_path, storage_dir=storage_dir
    )

    if not added and skipped > 0:
        return IngestResult(
            success=True,
            message=f"Ingested 0 new skills ({skipped} duplicate(s) skipped).",
            skills_added=0,
            skills_skipped=skipped,
            skills=[],
        )

    names = [s["name"] for s in added]
    if len(added) == 1:
        details = f": '{names[0]}' (ID: {added[0]['id']})"
    else:
        name_preview = ", ".join(f"'{n}'" for n in names[:3]) + ("..." if len(names) > 3 else "")
        id_preview = ", ".join(s["id"] for s in added[:3]) + ("..." if len(added) > 3 else "")
        details = f": {name_preview} (IDs: {id_preview})"
    src_str = f" from {source_url}" if source_url else ""
    return IngestResult(
        success=True,
        message=f"Successfully ingested {len(added)} skill(s){src_str}{details}.",
        skills_added=len(added),
        skills_skipped=skipped,
        skills=added,
    )


def ingest_url(
    url: str,
    *,
    index_path: Optional[str] = None,
    storage_dir: Optional[Path] = None,
    scope: Optional[AuthorizationScope] = None,
    execution_mode: str = "real",
    session_id: Optional[str] = None,
) -> IngestResult:
    """Governed ingestion of public web text into skill records.

    Executes web_fetch strictly through tools.executor.execute with
    capability_id='research' and role='virtual_assistant'.
    """
    if not isinstance(url, str) or not url.strip():
        return IngestResult(success=False, message="Usage: /ingest <url>")

    clean_url = url.strip()

    if scope is None:
        scope = AuthorizationScope(
            principal="system:ttp_ingest",
            allow_network=True,
            max_risk="medium",
            reason=f"TTP skill ingestion from {clean_url}",
        )

    tool_result = execute(
        "web_fetch",
        {"url": clean_url},
        capability_id="research",
        role="virtual_assistant",
        scope=scope,
        execution_mode=execution_mode,
        session_id=session_id,
    )

    if not tool_result.success:
        err = tool_result.error or "Fetch refused safely."
        return IngestResult(success=False, message=f"Ingest failed: {err}")

    data = tool_result.data or {}
    text = data.get("text", "")
    if not text or not text.strip():
        return IngestResult(
            success=False,
            message="Ingest failed: No usable text extracted from the URL.",
        )

    return ingest_text(
        text,
        source_url=clean_url,
        index_path=index_path,
        storage_dir=storage_dir,
    )
