-- Task 2 — bilingual AI agent
--
-- Adds two tables on top of the Task 1 core schema:
--   * leads          — one row per session_id; the structured lead summary.
--   * lead_messages  — full conversation history for that session.
--
-- Why a dedicated `leads` table (not just reuse `customers`)?
--   At intake time we usually don't have an email yet, the contact may
--   eventually become a customer of more than one brand, and the lead
--   carries lots of qualification-specific fields (target quantity,
--   timeline, brand goals) that don't belong in `customers`. When a lead
--   converts, the app layer can promote it into a `customers` row.

CREATE TABLE IF NOT EXISTS leads (
    session_id        TEXT PRIMARY KEY,
    channel           TEXT NOT NULL,            -- 'whatsapp', 'instagram', 'email', etc.
    language          TEXT,                     -- 'en' or 'ur' — first detected language
    company_name      TEXT,
    contact_name      TEXT,
    product_category  TEXT,
    target_quantity   TEXT,                     -- free text: "5000 units", "MOQ-level for trial"
    timeline          TEXT,
    brand_goals       TEXT,
    complete          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES leads(session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lead_messages_session
    ON lead_messages (session_id, created_at);
