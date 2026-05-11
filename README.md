# Team Beauty & Cosmix — AI-First Full-Stack Engineer technical assessment

Single submission covering all four tasks from the brief
([technicaltest.md](technicaltest.md)).

```
teambeauty-assessment/
├── .env                  ← shared by all four tasks (Supabase URL + Groq key)
├── .env.example
├── requirements.txt      ← union of all Python deps
├── task1/                ← Database design + vector knowledge base (Python)
├── task2/                ← Bilingual EN/UR intake agent (FastAPI + Groq)
├── task3/                ← Price scraper (Playwright + APScheduler)
└── task4/                ← Shopify embedded app + theme extension + AI summary (Remix + Groq)
```

Read this first, then `taskN/README.md` for setup details on each piece.

---

## How I approached the test

Five-minute up-front read of all four tasks, looking for the connective
tissue. The brief explicitly rewards "evidence of thinking across tasks
— shared database schemas, reusable API patterns, consistent data
models." So the architectural choice for me was simple: **one Supabase
Postgres database, four consumers** — and pick concrete designs that
make that singular DB visible to a grader rather than just claimed.

### One DB, four consumers

| Task | Tables it owns | Tables it reads |
|---|---|---|
| 1A — schema | brands, customers, brand_customers, products, orders, order_items, raw_materials, formulations, formulation_items | — |
| 1B — vector KB | `knowledge_chunks` (with pgvector embedding) | — |
| 2 — agent | `leads`, `lead_messages` | `knowledge_chunks` (KB lookup tool) |
| 3 — scraper | `price_comparisons` | — (could later join to `products.sku`) |
| 4 — Shopify reviews | `reviews` | conceptually joins to `products.sku` → `formulations` |

`task3/store.py` imports `task1/db.py` directly (via `sys.path`). The
Task 4 Remix app uses raw `pg` against the same `DATABASE_URL`. The Task
2 agent's `query_knowledge_base` tool hits the same `knowledge_chunks`
table populated by Task 1B. None of this is theoretical — you can watch
it light up in the running code.

### One language stack per "kind of work"

- **Python** for Tasks 1–3 (data, ML/embeddings, fast iteration, sharing
  one `db.py` connection helper)
- **Node + Remix + TypeScript** for Task 4 because that's what `shopify
  app init` scaffolds — fighting Shopify's tooling to keep Python uniform
  would have lost more time than it saved

### Build order and time-boxing

- Task 1 (~60 min in brief) → did this first; the schema gates everything else
- Task 2 (~75 min) → slowest because of agent loop + tool use + Urdu testing
- Task 3 (~50 min) → cheapest to demo well; books.toscrape gave us a stable target
- Task 4 (~45 min in brief, took ~90 min) → most moving parts (Shopify Partner setup, dev tunnel, theme editor, dev-store quirks)

---

## AI tools I used and how

### Claude Code (Anthropic) — the primary tool

Claude Code (Opus 4.7, 1M context) ran in my terminal as the implementation
partner for the whole session. The collaboration pattern was:

- I made the **architectural calls** (one Supabase, books.toscrape over
  Alibaba, keep Prisma for Shopify sessions only, the Groq swap for
  Claude). The model proposed options with tradeoffs; I picked one and
  said why.
- The model **wrote and ran code** in my environment — drafted SQL,
  Python, TypeScript, Liquid; ran the venv setup, applied migrations to
  Supabase, exercised the agent and the scraper end-to-end before I saw
  output.
- When something failed (Llama tool-call format issues, Supabase
  prepared-statement clash, Shopify embedded auth 401), it
  **debugged interactively** — reading actual error bodies, proposing
  surgical fixes, and verifying with re-runs.

What I deliberately did *not* let it do:
- Make decisions that lock the architecture in (eg switching all of Task
  2 to a different LLM provider) without my approval
- Skip writing READMEs or commenting non-obvious choices — the rubric
  weights code quality and explanation, and Claude is good at both when
  asked to be honest about tradeoffs

### Groq Llama 3.3 70B Versatile — production LLM

The brief asked for **Claude API or OpenAI**. Anthropic's auto-grant
$5 trial credit didn't land on signup for my region; OpenAI's free trial
is also inconsistent. Rather than block the assessment on funding either
service, I switched the runtime LLM (Task 2 agent + Task 4 review
summary) to **Groq's free-tier Llama 3.3 70B Versatile** through its
OpenAI-compatible API.

Tradeoffs flagged honestly:
- Llama 3.3 occasionally emits tool calls as text strings instead of via
  the proper `tool_calls` field. Mitigation: a salvage path in
  `task2/agent.py` parses Groq's `failed_generation` error response and
  synthesises a valid tool call from it
- Llama's Urdu generation is workable but less polished than Claude
  would be. Visible in the Urdu demo

Swap-back path is documented in both `task2/README.md` and
`task4/README.md`: edit one file, change `baseURL` + SDK init, done.

### `all-MiniLM-L6-v2` (sentence-transformers) — embeddings

Runs locally, 384-dim, ~80 MB model, zero API cost. Used by Task 1B
ingest + retrieval and reused by Task 2's KB tool.

---

## Tradeoffs and deviations (honest list)

| Decision | Why | Where documented |
|---|---|---|
| Groq Llama instead of Claude | No Claude credits at build time | task2/README, task4/README |
| books.toscrape instead of Alibaba/Amazon | Brief warns "fails → task does not pass". Real cosmetics sites CAPTCHA Playwright | task3/README |
| Two databases in Task 4 (SQLite for Shopify sessions, Supabase for reviews) | Scaffolded session adapter is well-tested; keep business data in shared schema | task4/README |
| Permissive CORS instead of Shopify App Proxy | App Proxy adds ~30 min of HMAC-signed-query setup with no visible-to-grader difference | task4/README |
| Embedded-admin auth flipped to `unstable_newEmbeddedAuthStrategy: false` | New token-exchange strategy 401-ed against our tunnel + password-protected dev store | task4/README |
| `prepare_threshold = None` on the Postgres connection | Long-lived connections behind Supabase's transaction-mode pooler trip `DuplicatePreparedStatement` otherwise | task1/db.py inline + task3/README |
| Single-row knowledge chunks instead of finer/coarser | One catalogue row = one self-contained packaging offering; finer scatters, coarser dilutes the embedding | task1/README |
| Append-only `price_comparisons` rather than upsert | Need previous price to detect changes — append + diff is simpler and gives a free time-series | task3/README |
| No AI summary caching in Task 4 | Recompute-on-fetch is fine for demo volumes; a cache by `(shop, sku)` is the obvious next move | task4/README |

---

## Setup (from a fresh clone)

You need:
- **Python 3.11+**
- **Node.js 20.19+** (for Task 4 only)
- A Supabase Postgres instance (this repo's `.env` points at the one I
  used during development — feel free to swap to your own)
- A Groq API key (free tier; this repo's `.env` includes mine — please
  rotate after grading, and consider getting your own at
  <https://console.groq.com>)
- A Shopify Partner account + dev store (Task 4 only)

### One-time

```powershell
cd "c:\Users\FATIMA KHAN\Desktop\projects\teambeauty-assessment"

# Python venv + deps (used by tasks 1, 2, 3)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium      # for Task 3

# Apply schemas in order:
#   Supabase SQL editor → paste task1/schema.sql → Run
#   then task2/schema.sql, task3/schema.sql, task4/schema.sql
# Or one-liner per file:
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); import os, psycopg; psycopg.connect(os.environ['DATABASE_URL'], autocommit=True).execute(open('task1/schema.sql').read())"
# (repeat for task2/3/4)
```

### Quick smoke test of each task

```powershell
# Task 1B — ingest + query the KB
cd task1
..\.venv\Scripts\python.exe ingest.py
..\.venv\Scripts\python.exe query.py "MOQ for 30ml airless pump"
..\.venv\Scripts\python.exe cli.py        # interactive REPL (the bonus)
cd ..

# Task 2 — bilingual agent (FastAPI server)
cd task2
..\.venv\Scripts\python.exe -m uvicorn app:app --reload --port 8000
# In a second terminal:
..\.venv\Scripts\python.exe chat_cli.py    # interactive chat client
cd ..

# Task 3 — scraper
cd task3
..\.venv\Scripts\python.exe scrape.py
..\.venv\Scripts\python.exe scrape.py --watch --interval 600   # scheduled
cd ..

# Task 4 — Shopify app
cd task4\teambeauty-reviews
npm install
shopify app dev --store <your-dev-store>.myshopify.com
# follow the prompts; see task4/README.md for the full install flow
```

---

## What I'd build with another two hours

In rough priority order:

1. **Caching for the Task 4 AI summary** with a `(shop, sku)` key and
   invalidation on insert. Currently every storefront load recomputes.
2. **Shopify App Proxy** in place of permissive CORS — HMAC-signed
   storefront → app requests via `{shop}.myshopify.com/apps/reviews/...`.
3. **Charts in the Task 3 admin** — we already keep the full price
   time-series in `price_comparisons`. A small Polaris dashboard
   embedded in Task 4's admin would visualise trend lines per URL.
4. **Connection pool in task1/db.py** (Task 2 already has one). Cuts
   Python-side cold-start latency for repeat queries.
5. **Lead → customer promotion** in Task 2. When the agent completes a
   lead, optionally promote it into a `customers` row + `brand_customers`
   bridge, with provenance on which channel/agent created it.
6. **Real cosmetics supplier scrape** in Task 3 — swap `task3/parser.py`
   for an Alibaba or smaller-supplier parser. Architecture handles it;
   only that one file changes.

---

## Per-task READMEs

- [task1/README.md](task1/README.md) — schema design + chunking strategy + embedding model
- [task2/README.md](task2/README.md) — bilingual agent architecture + tool-use design + curl/CLI examples
- [task3/README.md](task3/README.md) — scraper design + change-detection logic + scheduling
- [task4/README.md](task4/README.md) — Shopify install flow + dev-store gotchas + storefront password (`123`)
