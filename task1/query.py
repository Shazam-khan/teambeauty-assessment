"""Query the knowledge base for the top-N most relevant chunks.

Public API used by Task 2 (agent):
    from task1.query import query
    results = query("What is the MOQ for a 30ml airless pump?", top_k=3)
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer

from db import connect

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class Chunk:
    id: int
    source: str
    content: str
    metadata: dict[str, Any]
    similarity: float          # 1.0 = identical, 0.0 = orthogonal (cosine)

    def __str__(self) -> str:  # for nice CLI output
        return f"[{self.similarity:.3f}] {self.content}"


@lru_cache(maxsize=1)
def _model(name: str = DEFAULT_MODEL) -> SentenceTransformer:
    return SentenceTransformer(name)


def query(question: str, top_k: int = 3, model_name: str = DEFAULT_MODEL) -> list[Chunk]:
    """Return the top_k most relevant knowledge chunks for `question`."""
    embedding = _model(model_name).encode([question], normalize_embeddings=True)[0]

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source, content, metadata, 1 - (embedding <=> %s) AS similarity
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (embedding, embedding, top_k),
        )
        rows = cur.fetchall()

    return [
        Chunk(id=r[0], source=r[1], content=r[2], metadata=r[3] or {}, similarity=float(r[4]))
        for r in rows
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args()
    for c in query(args.question, top_k=args.top_k):
        print(c)


if __name__ == "__main__":
    main()
