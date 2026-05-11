-- Team Beauty & Cosmix — core schema (Task 1A) + knowledge base (Task 1B)
--
-- Design notes (the non-obvious):
--   * Customers are a single shared identity across brands. A bridge table
--     (brand_customers) records which brands a person has interacted with,
--     so we keep one canonical contact record even when the same person
--     orders from Team Beauty AND a Cosmix consumer brand.
--   * SKUs are UNIQUE PER BRAND, not globally. Different brands routinely
--     reuse the same SKU codes; enforcing global uniqueness causes pain.
--   * Money is stored as NUMERIC(12,2) — exact decimal, no float drift.
--   * Formulations are versioned (UNIQUE product_id+version). Recipes evolve
--     in manufacturing and you need history for QC and audit.
--   * Raw materials use NUMERIC(14,4) for quantity because cosmetics
--     formulations often use fractional grams / ml.
--   * The knowledge base lives in this same database (pgvector) so the
--     Task 2 agent, Task 3 scraper, and Task 4 review app all hit one DB.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- handy for fuzzy name lookups

-- ---------------------------------------------------------------------------
-- Brands
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brands (
    id           BIGSERIAL PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Customers (shared identity across all brands)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id           BIGSERIAL PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        TEXT UNIQUE,             -- nullable: WhatsApp/IG leads may not provide email
    phone        TEXT,                    -- E.164 ideally; not enforced
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone) WHERE phone IS NOT NULL;

-- Bridge: which brands has this customer interacted with?
CREATE TABLE IF NOT EXISTS brand_customers (
    brand_id       BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    customer_id    BIGINT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (brand_id, customer_id)
);

-- ---------------------------------------------------------------------------
-- Products (each brand has its own catalogue)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id           BIGSERIAL PRIMARY KEY,
    brand_id     BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    sku          TEXT NOT NULL,
    name         TEXT NOT NULL,
    category     TEXT,
    price        NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    currency     CHAR(3) NOT NULL DEFAULT 'USD',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (brand_id, sku)
);
CREATE INDEX IF NOT EXISTS idx_products_brand    ON products (brand_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);

-- ---------------------------------------------------------------------------
-- Orders
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id           BIGSERIAL PRIMARY KEY,
    brand_id     BIGINT NOT NULL REFERENCES brands(id),
    customer_id  BIGINT NOT NULL REFERENCES customers(id),
    placed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status       TEXT NOT NULL DEFAULT 'pending',
    total        NUMERIC(12,2) NOT NULL CHECK (total >= 0),
    currency     CHAR(3) NOT NULL DEFAULT 'USD'
);
CREATE INDEX IF NOT EXISTS idx_orders_brand    ON orders (brand_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_placed   ON orders (placed_at DESC);

CREATE TABLE IF NOT EXISTS order_items (
    id               BIGSERIAL PRIMARY KEY,
    order_id         BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id       BIGINT NOT NULL REFERENCES products(id),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price       NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0)
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);

-- ---------------------------------------------------------------------------
-- Raw materials
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_materials (
    id                BIGSERIAL PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    unit_of_measure   TEXT NOT NULL,         -- 'g', 'ml', 'kg', 'l', 'units'
    stock_quantity    NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    reorder_level     NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    cost_per_unit     NUMERIC(12,4) NOT NULL CHECK (cost_per_unit >= 0),
    currency          CHAR(3) NOT NULL DEFAULT 'USD',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Formulations (product recipes)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS formulations (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL DEFAULT 1,
    yield_quantity  NUMERIC(14,4),            -- e.g. 1000 (g) per batch
    yield_unit      TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, version)
);
CREATE INDEX IF NOT EXISTS idx_formulations_product ON formulations (product_id);

CREATE TABLE IF NOT EXISTS formulation_items (
    id                BIGSERIAL PRIMARY KEY,
    formulation_id    BIGINT NOT NULL REFERENCES formulations(id) ON DELETE CASCADE,
    raw_material_id   BIGINT NOT NULL REFERENCES raw_materials(id),
    quantity          NUMERIC(14,4) NOT NULL CHECK (quantity > 0),
    unit              TEXT NOT NULL             -- may differ from raw material's UOM
);
CREATE INDEX IF NOT EXISTS idx_formulation_items_formulation ON formulation_items (formulation_id);

-- ---------------------------------------------------------------------------
-- Knowledge base for the AI agent (Task 1B)
-- ---------------------------------------------------------------------------
--   * source / source_row_id let us re-ingest from the same CSV without dups
--   * embedding dims = 384 to match sentence-transformers/all-MiniLM-L6-v2
--   * HNSW index with cosine ops — works well at small/medium scale and does
--     not need an explicit `lists` parameter like ivfflat does.

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id             BIGSERIAL PRIMARY KEY,
    source         TEXT NOT NULL,
    source_row_id  TEXT,
    content        TEXT NOT NULL,
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding      VECTOR(384),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, source_row_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
