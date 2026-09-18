"""
Lionel Agent - Embedding backend for semantic skill search.

Three-tier fallback:
1. Cloudflare Workers AI embeddings (fast, semantic, free tier)
2. Local sentence-transformers (offline, ~90MB model)
3. None (caller falls back to BM25)

Embeddings are cached to disk in a .npz file. Rebuild with:
    python -m skills.embeddings --rebuild
"""
import logging
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import requests

import config

logger = logging.getLogger(__name__)

# Lazy-loaded local model
_local_model = None


def _cloudflare_embed(texts: List[str]) -> Optional[np.ndarray]:
    """Embed via Cloudflare Workers AI. Returns None on any failure."""
    if not config.CLOUDFLARE_API_TOKEN or not config.CLOUDFLARE_ACCOUNT_ID:
        return None

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/{config.CLOUDFLARE_EMBED_MODEL}"
    )
    headers = {
        "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    vectors = []
    batch_size = config.EMBED_BATCH_SIZE
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            r = requests.post(url, headers=headers, json={"text": batch}, timeout=60)
        except Exception as e:
            logger.warning(f"Cloudflare embed network error: {e}")
            return None
        if r.status_code != 200:
            logger.warning(f"Cloudflare embed HTTP {r.status_code}: {r.text[:120]}")
            return None
        try:
            body = r.json()
        except Exception as e:
            logger.warning(f"Cloudflare embed bad JSON: {e}")
            return None
        if not body.get("success"):
            logger.warning(f"Cloudflare embed failed: {body.get('errors')}")
            return None
        result = body.get("result", {}).get("data") or []
        if len(result) != len(batch):
            logger.warning(f"Cloudflare embed count mismatch: {len(result)} vs {len(batch)}")
            return None
        vectors.extend(result)

    arr = np.asarray(vectors, dtype=np.float32)
    if arr.size == 0:
        return None
    # Normalize for cosine similarity via dot product
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _local_embed(texts: List[str]) -> Optional[np.ndarray]:
    """Embed using a local sentence-transformers model. Returns None on failure."""
    global _local_model
    try:
        if _local_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local embedding model: {config.LOCAL_EMBED_MODEL}")
            _local_model = SentenceTransformer(config.LOCAL_EMBED_MODEL)
        vectors = _local_model.encode(
            texts,
            batch_size=config.EMBED_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(vectors, dtype=np.float32)
    except ImportError:
        logger.warning("sentence-transformers not installed")
        return None
    except Exception as e:
        logger.warning(f"Local embed failed: {e}")
        return None


def embed_texts(texts: List[str]) -> Optional[np.ndarray]:
    """Try Cloudflare, then local. Returns None if both fail."""
    if not texts:
        return None

    logger.info(f"Embedding {len(texts)} texts via Cloudflare...")
    t0 = time.time()
    arr = _cloudflare_embed(texts)
    if arr is not None:
        logger.info(f"Cloudflare embeddings OK ({time.time() - t0:.1f}s)")
        return arr

    logger.info("Cloudflare embeddings failed, trying local model...")
    t0 = time.time()
    arr = _local_embed(texts)
    if arr is not None:
        logger.info(f"Local embeddings OK ({time.time() - t0:.1f}s)")
        return arr

    logger.warning("All embedding backends failed")
    return None


def embed_query(text: str) -> Optional[np.ndarray]:
    """Embed a single query string."""
    arr = embed_texts([text])
    if arr is None:
        return None
    return arr[0]


def save_embeddings(arr: np.ndarray, path: Optional[str] = None) -> None:
    """Save embedding matrix to a .npz file."""
    out_path = Path(path or config.EMBEDDINGS_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, vectors=arr)
    logger.info(f"Saved embeddings to {out_path} ({arr.shape})")


def load_embeddings(path: Optional[str] = None) -> Optional[np.ndarray]:
    """Load embedding matrix from .npz file. Returns None if missing."""
    in_path = Path(path or config.EMBEDDINGS_PATH)
    if not in_path.exists():
        return None
    try:
        data = np.load(in_path)
        arr = data["vectors"]
        logger.info(f"Loaded embeddings from {in_path} ({arr.shape})")
        return arr
    except Exception as e:
        logger.warning(f"Failed to load embeddings: {e}")
        return None


def build_embeddings_for_skills(skills: List[dict]) -> Optional[np.ndarray]:
    """
    Build embeddings for a list of skill dicts.
    Uses name + category + description as the source text.
    """
    texts = []
    for s in skills:
        name = s.get("name", "")
        desc = s.get("description", "")
        cat = s.get("category", "")
        text = f"{name}. {cat}. {desc}".strip()
        texts.append(text[:2000])

    return embed_texts(texts)


# CLI: python -m skills.embeddings --rebuild
if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild embeddings from master index")
    parser.add_argument("--test", action="store_true",
                        help="Test embedding a sample query")
    args = parser.parse_args()

    if args.rebuild:
        logger.info(f"Loading master index: {config.SKILLS_INDEX_PATH}")
        with open(config.SKILLS_INDEX_PATH, "r", encoding="utf-8") as f:
            idx = json.load(f)
        skills = idx.get("skills", [])
        logger.info(f"Building embeddings for {len(skills)} skills...")
        arr = build_embeddings_for_skills(skills)
        if arr is None:
            print("FAILED: no embedding backend available")
            raise SystemExit(1)
        save_embeddings(arr)
        print(f"OK: saved {arr.shape[0]} vectors, dim {arr.shape[1]}")

    if args.test:
        q = "how do I scan for open ports"
        v = embed_query(q)
        if v is None:
            print("FAILED: no embedding backend available")
        else:
            print(f"OK: query vector shape {v.shape}")