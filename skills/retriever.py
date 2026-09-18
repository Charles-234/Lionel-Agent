"""
Lionel Agent - Skill retriever (hybrid: embeddings + BM25).

Priority:
1. If embeddings are available (loaded + query embedded successfully),
   use cosine similarity. Falls back to BM25 if the query embed fails.
2. Otherwise use BM25 with name/category/description weighting.
3. Results below MIN_SCORE are dropped.
"""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from rank_bm25 import BM25Okapi

import config
from skills import embeddings as embed_mod

logger = logging.getLogger(__name__)

NAME_WEIGHT = 3.0
DESC_WEIGHT = 1.0
CATEGORY_WEIGHT = 2.0
CATEGORY_MATCH_BOOST = 1.30
MIN_SCORE = 1.0
MIN_COSINE_SCORE = 0.30


@dataclass
class SkillMatch:
    id: str
    name: str
    description: str
    category: str
    source: str
    path: str
    score: float
    method: str = "bm25"
    category_boosted: bool = False


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _resolve_skill_file(path_str: str) -> Optional[Path]:
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_file():
        return p
    if p.is_dir():
        candidate = p / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


class SkillRetriever:
    def __init__(self, index_path: Optional[str] = None):
        self.index_path = Path(index_path or config.SKILLS_INDEX_PATH)
        self.skills: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self._corpus_tokens: List[List[str]] = []
        self._category_tokens: List[set] = []
        self._by_name: Dict[str, Dict[str, Any]] = {}
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self.embeddings: Optional[np.ndarray] = None
        self.embeddings_ready = False

    def load(self) -> None:
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"Skill index not found at {self.index_path}. "
                f"Run: python -m skills.loader"
            )
        with open(self.index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.skills = data.get("skills", [])
        logger.info(f"Loaded {len(self.skills)} skills from index")

        self._by_name = {s.get("name_lower", ""): s for s in self.skills if s.get("name_lower")}
        self._by_id = {s.get("id", ""): s for s in self.skills if s.get("id")}

        # Build BM25 fallback
        self._corpus_tokens = []
        self._category_tokens = []
        for skill in self.skills:
            name_tokens = _tokenize(skill.get("name", ""))
            desc_tokens = _tokenize(skill.get("description", ""))
            cat_tokens = _tokenize(skill.get("category", ""))
            weighted = (
                name_tokens * int(NAME_WEIGHT)
                + cat_tokens * int(CATEGORY_WEIGHT)
                + desc_tokens * int(DESC_WEIGHT)
            )
            if not weighted:
                weighted = ["__empty__"]
            self._corpus_tokens.append(weighted)
            self._category_tokens.append(set(cat_tokens))
        self.bm25 = BM25Okapi(self._corpus_tokens)
        logger.info("BM25 index built")

        # Try to load embeddings
        if config.EMBEDDINGS_ENABLED:
            arr = embed_mod.load_embeddings()
            if arr is not None and arr.shape[0] == len(self.skills):
                self.embeddings = arr
                self.embeddings_ready = True
                logger.info(f"Embeddings loaded: {arr.shape}")
            elif arr is not None:
                logger.warning(
                    f"Embedding count mismatch: {arr.shape[0]} vectors "
                    f"vs {len(self.skills)} skills. "
                    f"Rebuild with: python -m skills.embeddings --rebuild"
                )
        else:
            logger.info("Embeddings disabled in config")

    def _search_embeddings(
        self, query: str, top_k: int, source_filter: Optional[str], min_score: float
    ) -> Optional[List[SkillMatch]]:
        """Try embedding-based search. Returns None if unavailable."""
        if not self.embeddings_ready or self.embeddings is None:
            return None
        qv = embed_mod.embed_query(query)
        if qv is None:
            logger.warning("Query embedding failed - falling back to BM25")
            return None

        qn = qv / (np.linalg.norm(qv) + 1e-9)
        sims = self.embeddings @ qn
        scores = sims * 20.0

        candidates = []
        for idx, score in enumerate(scores):
            if score < min_score:
                continue
            skill = self.skills[idx]
            if source_filter and skill.get("source") != source_filter:
                continue
            if sims[idx] < MIN_COSINE_SCORE:
                continue
            candidates.append((idx, float(score)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        candidates = candidates[:top_k]

        results = []
        for idx, score in candidates:
            s = self.skills[idx]
            results.append(SkillMatch(
                id=s.get("id", ""),
                name=s.get("name", ""),
                description=s.get("description", ""),
                category=s.get("category", ""),
                source=s.get("source", ""),
                path=s.get("path", ""),
                score=score,
                method="embed",
            ))
        return results

    def _search_bm25(
        self, query: str, top_k: int, source_filter: Optional[str], min_score: float
    ) -> List[SkillMatch]:
        if self.bm25 is None:
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        query_set = set(query_tokens)

        candidates = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            skill = self.skills[idx]
            if source_filter and skill.get("source") != source_filter:
                continue
            cat_boosted = False
            cat_set = self._category_tokens[idx]
            if cat_set and (cat_set & query_set):
                score = float(score) * CATEGORY_MATCH_BOOST
                cat_boosted = True
            if score < min_score:
                continue
            candidates.append((idx, float(score), cat_boosted))

        candidates.sort(key=lambda x: x[1], reverse=True)
        candidates = candidates[:top_k]

        results = []
        for idx, score, cat_boosted in candidates:
            s = self.skills[idx]
            results.append(SkillMatch(
                id=s.get("id", ""),
                name=s.get("name", ""),
                description=s.get("description", ""),
                category=s.get("category", ""),
                source=s.get("source", ""),
                path=s.get("path", ""),
                score=score,
                method="bm25",
                category_boosted=cat_boosted,
            ))
        return results

    def search(
        self,
        query: str,
        top_k: int = 5,
        source_filter: Optional[str] = None,
        min_score: float = MIN_SCORE,
    ) -> List[SkillMatch]:
        if self.embeddings_ready:
            results = self._search_embeddings(query, top_k, source_filter, min_score)
            if results is not None:
                return results
        return self._search_bm25(query, top_k, source_filter, min_score)

    def load_skill(self, skill_id: str) -> Optional[str]:
        s = self._by_id.get(skill_id)
        if not s:
            return None
        resolved = _resolve_skill_file(s.get("path", ""))
        if not resolved:
            return None
        try:
            return resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read {resolved}: {e}")
            return None

    def load_skill_by_name(self, name: str) -> Optional[str]:
        s = self._by_name.get(name.lower())
        if not s:
            return None
        resolved = _resolve_skill_file(s.get("path", ""))
        if not resolved:
            return None
        try:
            return resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read {resolved}: {e}")
            return None

    def list_categories(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for s in self.skills:
            cat = s.get("category") or "(uncategorized)"
            out[cat] = out.get(cat, 0) + 1
        return out

    def list_sources(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for s in self.skills:
            src = s.get("source", "unknown")
            out[src] = out.get(src, 0) + 1
        return out


_default: Optional[SkillRetriever] = None


def get_retriever() -> SkillRetriever:
    global _default
    if _default is None:
        _default = SkillRetriever()
        _default.load()
    return _default


def search(query: str, top_k: int = 5, source_filter: Optional[str] = None) -> List[SkillMatch]:
    return get_retriever().search(query, top_k=top_k, source_filter=source_filter)


def load_skill(skill_id: str) -> Optional[str]:
    return get_retriever().load_skill(skill_id)


def list_categories() -> Dict[str, int]:
    return get_retriever().list_categories()


def list_sources() -> Dict[str, int]:
    return get_retriever().list_sources()