"""Postgres connection helper — same DB as Task 1, with a client-side pool.

The Supabase pooler (port 6543) is in transaction mode, but the network
hop from us → Supabase pooler still costs a TCP+TLS round trip every time
we open a connection. With ~7 small queries per chat turn from Pakistan to
ap-northeast-2 (Seoul) that adds up to a couple of seconds per request.
A client-side psycopg_pool keeps a handful of warm connections so each
`connect()` call is effectively free.

Two important configure-time settings on each pooled connection:
  * `register_vector(conn)` — needed for pgvector parameter binding.
  * `prepare_threshold = None` — disables server-side prepared statements.
    Long-lived connections behind Supabase's transaction-mode pooler can
    otherwise hit "prepared statement ... does not exist" errors when a
    later transaction lands on a different upstream Postgres connection.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

load_dotenv(Path(__file__).parent.parent / ".env")


def _conn_str() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Copy .env.example to .env and fill in your Supabase URL."
        )
    return url


def _configure_conn(conn) -> None:
    conn.prepare_threshold = None
    register_vector(conn)


_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_conn_str(),
            min_size=1,
            max_size=5,
            configure=_configure_conn,
            open=True,
        )
    return _pool


def open_pool() -> None:
    """Eagerly initialise the pool (so the first request after startup is fast)."""
    _get_pool()


@contextmanager
def connect():
    """Borrow a pooled connection. Cheap — no TCP/TLS handshake on the hot path."""
    with _get_pool().connection() as conn:
        yield conn
