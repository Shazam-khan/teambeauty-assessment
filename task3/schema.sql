-- Task 3 — price comparison scraper
--
-- Append-only history of scrape observations.
--
-- Why one row per observation (vs. upsert one row per URL):
--   The brief requires detecting price *changes between scrapes*, which
--   needs the previous price to live somewhere. The simplest design is
--   to keep every observation and let `previous_price` + `price_changed`
--   summarise the diff against the most recent prior row for that URL.
--   This also gives us a free time-series for later charting / analytics.

CREATE TABLE IF NOT EXISTS price_comparisons (
    id              BIGSERIAL PRIMARY KEY,
    search_term     TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    seller          TEXT,
    url             TEXT NOT NULL,
    price           NUMERIC(12,2),
    currency        CHAR(3) NOT NULL DEFAULT 'GBP',
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    previous_price  NUMERIC(12,2),                -- NULL on first observation
    price_changed   BOOLEAN NOT NULL DEFAULT FALSE
);

-- Fast lookup "most recent price for URL X" — used by change detection.
CREATE INDEX IF NOT EXISTS idx_price_comparisons_url_time
    ON price_comparisons (url, scraped_at DESC);

-- Find all observations for a given search term.
CREATE INDEX IF NOT EXISTS idx_price_comparisons_term
    ON price_comparisons (search_term);

-- Partial index: cheap "what changed recently?" queries.
CREATE INDEX IF NOT EXISTS idx_price_comparisons_changed
    ON price_comparisons (scraped_at DESC) WHERE price_changed;
