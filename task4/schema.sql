-- Task 4 — Shopify reviews app
--
-- One row per customer review, scoped by shop_domain so the same
-- Supabase can back multiple Shopify stores without cross-contamination.
--
-- Why product_sku is TEXT and not a foreign key to products.sku:
--   * products.sku is unique per brand (not globally), so a real FK
--     would need (brand_id, sku) — and brand_id isn't visible at the
--     Shopify storefront.
--   * The brief says the SKU "could match a formulation" — meaning
--     matching is conceptual, not enforced. A reviews row may exist
--     for SKUs that don't appear in our internal products table at
--     all (e.g. brand-new Shopify products).
--
-- The conceptual join is:
--     reviews JOIN products ON products.sku = reviews.product_sku
--     JOIN formulations ON formulations.product_id = products.id

CREATE TABLE IF NOT EXISTS reviews (
    id              BIGSERIAL PRIMARY KEY,
    shop_domain     TEXT NOT NULL,
    product_sku     TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reviews_shop_sku
    ON reviews (shop_domain, product_sku);
CREATE INDEX IF NOT EXISTS idx_reviews_created
    ON reviews (created_at DESC);
