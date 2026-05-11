"""Shared Supabase / Postgres connection helpers.

Reused by Task 1B, Task 2 (agent), Task 3 (scraper), Task 4 (Shopify app).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv(Path(__file__).parent.parent / ".env")


def _conn_str() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Copy .env.example to .env and fill in your Supabase URL."
        )
    return url


@contextmanager
def connect():
    """Yield a psycopg connection with pgvector adapter registered.

    `prepare_threshold = None` disables server-side prepared statements
    on this connection. Supabase's transaction-mode pooler routes
    subsequent transactions to different upstream Postgres connections,
    which can't see prepared statements registered by an earlier
    transaction — so reusing one client connection across many
    transactions trips `DuplicatePreparedStatement` errors otherwise.
    """
    with psycopg.connect(_conn_str()) as conn:
        conn.prepare_threshold = None
        register_vector(conn)
        yield conn
