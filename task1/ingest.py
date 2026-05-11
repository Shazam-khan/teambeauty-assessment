"""Ingest a CSV catalogue into the knowledge_chunks pgvector table.

Chunking strategy:
  One row = one chunk.

  Why row-level? The catalogue is already structured: each row is a
  self-contained packaging or service offering with its own MOQ, lead time,
  and price. Customer questions ("What's the MOQ on a 30ml airless?",
  "Lead time for dropper bottles?") map almost 1:1 onto rows. Splitting
  finer (e.g. by sentence) would scatter the answer; merging coarser (e.g.
  by category) would dilute the embedding signal.

  Each row is rendered into a short natural-language paragraph before
  embedding. Embeddings work much better on prose than on CSV-style
  "k1=v1,k2=v2" strings — the model was trained on the former.

Run:
    python ingest.py                                 # uses data/packaging_catalog.csv
    python ingest.py --csv path/to/other.csv         # custom path
    python ingest.py --reset                         # wipe previous rows for this source
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

from db import connect

HERE = Path(__file__).parent
DEFAULT_CSV = HERE / "data" / "packaging_catalog.csv"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def row_to_text(row: dict[str, str]) -> str:
    """Render a CSV row into a paragraph suitable for embedding."""
    parts = [f"{row['item_name']} ({row['category']})."]
    if row.get("material") and row["material"] != "N/A":
        parts.append(f"Material: {row['material']}.")
    if row.get("size") and row["size"] != "N/A":
        parts.append(f"Size: {row['size']}.")
    if row.get("moq") and row["moq"] != "N/A":
        parts.append(f"Minimum order quantity (MOQ): {row['moq']} units.")
    if row.get("lead_time_days") and row["lead_time_days"] != "N/A":
        parts.append(f"Lead time: {row['lead_time_days']} days.")
    if row.get("price_per_unit_usd") and row["price_per_unit_usd"] != "N/A":
        parts.append(f"Price: ${row['price_per_unit_usd']} per unit.")
    if row.get("customization"):
        parts.append(f"Customization options: {row['customization']}.")
    if row.get("notes"):
        parts.append(f"Notes: {row['notes']}")
    return " ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing chunks for this source before inserting.",
    )
    args = ap.parse_args()

    csv_path: Path = args.csv
    source = csv_path.name

    print(f"Loading model: {args.model}")
    model = SentenceTransformer(args.model)

    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Read {len(rows)} rows from {csv_path}")

    texts = [row_to_text(r) for r in rows]
    print("Computing embeddings...")
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    with connect() as conn, conn.cursor() as cur:
        if args.reset:
            cur.execute("DELETE FROM knowledge_chunks WHERE source = %s", (source,))
            print(f"Deleted {cur.rowcount} existing chunks for source={source}")

        inserted = 0
        for i, (row, text, emb) in enumerate(zip(rows, texts, embeddings)):
            metadata = {k: v for k, v in row.items() if v}
            cur.execute(
                """
                INSERT INTO knowledge_chunks (source, source_row_id, content, metadata, embedding)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (source, source_row_id) DO UPDATE
                  SET content = EXCLUDED.content,
                      metadata = EXCLUDED.metadata,
                      embedding = EXCLUDED.embedding
                """,
                (source, str(i), text, json.dumps(metadata), emb.tolist()),
            )
            inserted += 1
        conn.commit()
        print(f"Inserted/updated {inserted} chunks into knowledge_chunks.")


if __name__ == "__main__":
    main()
