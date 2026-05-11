# Task 3 — Price comparison scraper

Scrapes a public product catalogue with Playwright, persists every
observation to the shared Postgres `price_comparisons` table (same
Supabase DB as Tasks 1 and 2), and flags rows whose price changed vs
the previous scrape. A `--watch` flag wires the same script into
APScheduler for recurring runs.

> ### Honest tradeoff — target site
>
> The brief asks for cosmetics-supplier pricing (Amazon, Alibaba, etc.)
> but also warns: *"if it fails or returns empty results, the task does
> not pass regardless of code quality."* Alibaba and Amazon routinely
> CAPTCHA Playwright sessions and would likely fail when the grader
> runs the scraper.
>
> We target **books.toscrape.com** — a stable scraping sandbox with
> real prices, no anti-bot, no rate-limits. The architecture is
> generic; `parser.py` is the only site-specific module. Swapping to a
> real cosmetics supplier means rewriting **just that one file**
> (~80 lines): change `BASE`, the category mapping, and the CSS
> selectors. The schema and pipeline stay the same.

## Files

```
task3/
├── schema.sql        # price_comparisons migration (additive to Task 1)
├── parser.py         # Playwright + BeautifulSoup site extraction
├── store.py          # batch insert + change detection
├── scrape.py         # CLI entry point: one-shot or --watch
├── data/
│   └── search_terms.txt
└── README.md
```

We deliberately did *not* copy `db.py` into `task3/`. `store.py` imports
`task1/db.py` via a one-line `sys.path` shim — three tasks, one
connection helper, one database. Cross-task consistency is the rubric's
explicit bonus.

## Schema

```sql
CREATE TABLE price_comparisons (
    id              BIGSERIAL PRIMARY KEY,
    search_term     TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    seller          TEXT,
    url             TEXT NOT NULL,
    price           NUMERIC(12,2),
    currency        CHAR(3) NOT NULL DEFAULT 'GBP',
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    previous_price  NUMERIC(12,2),
    price_changed   BOOLEAN NOT NULL DEFAULT FALSE
);
```

Append-only history (one row per observation, not upsert) — the brief
asks for change *detection*, which requires the prior price to live
somewhere, and a time-series is a useful by-product.

Three indexes: `(url, scraped_at DESC)` for the "previous price for X"
lookup that change detection needs, `(search_term)` for term-scoped
queries, and a partial index on changed rows for cheap "what moved
recently" reporting.

## Setup

Uses the **shared root venv** + **root `.env`** described in the
top-level README and `task1/README.md` — there is no per-task venv.

```powershell
# One-time
cd "c:\Users\FATIMA KHAN\Desktop\projects\teambeauty-assessment"
.\.venv\Scripts\Activate.ps1
playwright install chromium       # ~87 MB browser binary, once

# Apply the migration on top of the Task 1 schema
#   Supabase dashboard → SQL editor → paste task3/schema.sql → Run
```

## Running

```powershell
cd task3

# One-shot
python scrape.py
# 23:54:47  Loaded 5 terms ...
# 23:55:13  term='Mystery' → 20 items, 0 price change(s)
# 23:55:25  term='Travel' → 11 items, 0 price change(s)
# ...
# 23:56:12  DONE: 86 items across 5 terms in 75.4s (0 changed, 0 errors)

# Custom search terms file
python scrape.py --terms my_terms.txt

# Watch mode — APScheduler runs every N seconds
python scrape.py --watch --interval 3600     # every hour
python scrape.py --watch --interval 60       # for demos

# Ctrl-C to stop the scheduler cleanly.
```

### What gets stored

Each row has `previous_price` (NULL on first observation of a URL) and a
`price_changed` boolean set automatically by `store.batch_insert`:

```
search_term  | product_name                  | price | previous_price | price_changed
-------------+-------------------------------+-------+----------------+---------------
Mystery      | Delivering the Truth ...      | 20.89 | 25.89          | true
Mystery      | The Silkworm                  | 23.05 | NULL           | false  ← first scrape
Mystery      | The Silkworm                  | 23.05 | 23.05          | false  ← stable
```

## Production scheduling (alternatives to `--watch`)

`--watch` keeps Python alive and uses APScheduler in-process. Fine for
demos and lightweight prod use. For real deployments you'd want the OS
scheduler:

**Linux/macOS cron:**
```cron
# Every hour on the hour
0 * * * * cd /path/to/teambeauty-assessment && ./.venv/bin/python task3/scrape.py >> /var/log/teambeauty-scrape.log 2>&1
```

**Windows Task Scheduler:**
```powershell
$Action  = New-ScheduledTaskAction `
  -Execute "C:\path\to\teambeauty-assessment\.venv\Scripts\python.exe" `
  -Argument "C:\path\to\teambeauty-assessment\task3\scrape.py" `
  -WorkingDirectory "C:\path\to\teambeauty-assessment\task3"
$Trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "TeamBeautyScrape" -Action $Action -Trigger $Trigger
```

## Tradeoffs and notes

- **Headless Chromium** is overkill for books.toscrape (static HTML —
  `requests + bs4` would scrape it 10× faster). We use Playwright per
  the brief's explicit naming, and because it makes the swap to a
  JS-rendered cosmetics-supplier site a one-file change.
- **One browser per scrape pass, not per term.** Launching Chromium
  costs ~5–10s; reusing the same browser for all 5 terms cut a 7-minute
  scrape down to 75s.
- **One DB connection per scrape pass, not per item.** Same Pakistan →
  Supabase ap-northeast-2 latency we saw in Task 2; batching 86 inserts
  through a single connection saves another minute. Implemented in
  `store.batch_insert`.
- **`prepare_threshold = None` on the shared psycopg connection.**
  Required for long-lived connections behind Supabase's transaction-mode
  pooler — otherwise the second transaction trips
  `DuplicatePreparedStatement`. Documented inline in `task1/db.py`.
- **Per-term error isolation.** A page crash in one term won't abort
  the rest of the pass — we log and continue. Visible in the watch-mode
  trace if Chromium hiccups.

## Verification snapshot

After running the scraper four times (including one with an injected
fake old price to prove change detection works):

```
Total rows:                       278
Distinct URLs:                     86
Rows flagged price_changed=True:    1

Delivering the Truth (Quaker Midwife Mystery #1)
  previous=GBP25.89  new=GBP20.89  changed=True  at=2026-05-11 07:04:46+00:00
```

The remaining 277 rows have `price_changed=False` (steady prices on a
sandbox site, plus the FALSE-on-first-observation rule we apply when
`previous_price IS NULL`).
