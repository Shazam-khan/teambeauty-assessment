"""Lead + conversation persistence layer for Task 2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from db import connect

REQUIRED_FIELDS = (
    "company_name",
    "contact_name",
    "product_category",
    "target_quantity",
    "timeline",
    "brand_goals",
)


@dataclass
class Lead:
    session_id: str
    channel: str
    language: Optional[str]
    company_name: Optional[str]
    contact_name: Optional[str]
    product_category: Optional[str]
    target_quantity: Optional[str]
    timeline: Optional[str]
    brand_goals: Optional[str]
    complete: bool

    def as_dict(self) -> dict:
        return {f: getattr(self, f) for f in REQUIRED_FIELDS}

    def missing_fields(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if not getattr(self, f)]


def get_or_create_lead(session_id: str, channel: str, language: str) -> Lead:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leads (session_id, channel, language)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET updated_at = NOW()
            RETURNING session_id, channel, language, company_name, contact_name,
                      product_category, target_quantity, timeline, brand_goals, complete
            """,
            (session_id, channel, language),
        )
        row = cur.fetchone()
        conn.commit()
    return Lead(*row)


def get_lead(session_id: str) -> Optional[Lead]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, channel, language, company_name, contact_name,
                   product_category, target_quantity, timeline, brand_goals, complete
            FROM leads WHERE session_id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()
    return Lead(*row) if row else None


def update_lead_fields(session_id: str, fields: dict) -> Lead:
    """Apply partial updates to a lead. Only known columns are touched.
    `complete` is set to TRUE iff all REQUIRED_FIELDS are non-null after update.
    """
    fields = {k: v for k, v in fields.items() if k in REQUIRED_FIELDS and v}
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    params = list(fields.values())

    with connect() as conn, conn.cursor() as cur:
        if set_clause:
            cur.execute(
                f"UPDATE leads SET {set_clause}, updated_at = NOW() WHERE session_id = %s",
                params + [session_id],
            )
        # recompute completeness
        cur.execute(
            f"""
            UPDATE leads SET complete = (
                {' AND '.join(f"{f} IS NOT NULL" for f in REQUIRED_FIELDS)}
            )
            WHERE session_id = %s
            RETURNING session_id, channel, language, company_name, contact_name,
                      product_category, target_quantity, timeline, brand_goals, complete
            """,
            (session_id,),
        )
        row = cur.fetchone()
        conn.commit()
    return Lead(*row)


def append_message(session_id: str, role: str, content: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO lead_messages (session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, role, content),
        )
        conn.commit()


def load_history(session_id: str) -> list[dict]:
    """Return conversation history in Anthropic messages format."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT role, content FROM lead_messages WHERE session_id = %s ORDER BY created_at, id",
            (session_id,),
        )
        rows = cur.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]
