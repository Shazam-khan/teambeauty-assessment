"""Knowledge base retrieval — hits the same `knowledge_chunks` table Task 1
populated. Embedding model is loaded once at import time and cached.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer

from db import connect

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class Chunk:
    content: str
    metadata: dict[str, Any]
    similarity: float


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def warmup() -> None:
    """Load the model into memory eagerly (used at FastAPI startup)."""
    _model()


def query(question: str, top_k: int = 3) -> list[Chunk]:
    emb = _model().encode([question], normalize_embeddings=True)[0]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT content, metadata, 1 - (embedding <=> %s) AS similarity
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (emb, emb, top_k),
        )
        rows = cur.fetchall()
    return [Chunk(content=r[0], metadata=r[1] or {}, similarity=float(r[2])) for r in rows]
