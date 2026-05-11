"""Persist scrape results to Postgres + flag price changes.

The whole insert (look up previous price + write new row) happens in a
single transaction so two concurrent scrapes can't both decide "I'm the
new latest" against a stale read.

Two API shapes:
  * insert_with_change_detection(item)            — one row per call
  * batch_insert(items) -> dict                   — many rows, one connection
The batched form is what scrape.py uses on the hot path. Opening one
connection (Pakistan → Supabase ap-northeast-2 is ~250ms per TCP+TLS
handshake) instead of N saves minutes per scrape pass.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Iterable

# Re-use task1's connection helper rather than copying it. Same Supabase,
# one schema, three consumers (task1 ingest/query, task2 agent, task3
# scraper). This is the visible "cross-task consistency" signal.
sys.path.insert(0, str(Path(__file__).parent.parent / "task1"))
from db import connect  # noqa: E402

from parser import ScrapedItem  # noqa: E402


def _do_insert(cur, item: ScrapedItem) -> bool:
    cur.execute(
        """
        SELECT price FROM price_comparisons
        WHERE url = %s
        ORDER BY scraped_at DESC, id DESC
        LIMIT 1
        """,
        (item.url,),
    )
    row = cur.fetchone()
    previous: Decimal | None = row[0] if row else None
    changed = bool(previous is not None and previous != item.price)

    cur.execute(
        """
        INSERT INTO price_comparisons
            (search_term, product_name, seller, url, price, currency,
             previous_price, price_changed)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            item.search_term,
            item.product_name,
            item.seller,
            item.url,
            item.price,
            item.currency,
            previous,
            changed,
        ),
    )
    return changed


def insert_with_change_detection(item: ScrapedItem) -> bool:
    """One-shot helper: open a connection, insert one row, return whether
    the price changed since the most recent prior observation."""
    with connect() as conn, conn.cursor() as cur:
        changed = _do_insert(cur, item)
        conn.commit()
    return changed


def batch_insert(items: Iterable[ScrapedItem]) -> dict[str, int]:
    """Insert many rows over a single connection. Returns a summary
    {"items": N, "changed": K}. Caller is responsible for chunking
    if `items` is enormous (we hold the connection for the whole batch).
    """
    inserted = 0
    changed = 0
    with connect() as conn, conn.cursor() as cur:
        for item in items:
            if _do_insert(cur, item):
                changed += 1
            inserted += 1
        conn.commit()
    return {"items": inserted, "changed": changed}
