# Task 1 — Database design & AI knowledge base

## 1A — Schema (`schema.sql`)

PostgreSQL schema for the Team Beauty / Cosmix stack.

### What's in it

| Table | Purpose |
|---|---|
| `brands` | Team Beauty, Cosmix, future brands |
| `customers` | One shared identity per person across brands |
| `brand_customers` | Bridge: which brands has each customer interacted with |
| `products` | Per-brand catalogue (name, SKU, category, price) |
| `orders` / `order_items` | Orders belong to a brand, link to shared customer |
| `raw_materials` | Inventory: stock qty, reorder level, cost per unit |
| `formulations` / `formulation_items` | Versioned product recipes (BOM) |
| `knowledge_chunks` | pgvector store for the AI agent's knowledge base |

### Non-obvious design decisions

- **SKU unique per brand**, not globally — different brands routinely share SKU codes.
- **Customer email is nullable but unique** — WhatsApp/IG leads often have no email; phone is captured separately and indexed.
- **Money is `NUMERIC(12,2)`** to avoid float drift.
- **Formulations are versioned** (`UNIQUE(product_id, version)`) — recipes change in manufacturing and we need history.
- **`knowledge_chunks.embedding VECTOR(384)`** matches `all-MiniLM-L6-v2`. HNSW index on cosine.

## 1B — Vector knowledge base

### Files

```
task1/
├── schema.sql              # 1A schema + knowledge_chunks
├── data/packaging_catalog.csv  # 14 rows of realistic packaging/MOQ/lead-time data
├── db.py                   # shared psycopg connection helper
├── ingest.py               # CSV → embeddings → pgvector
├── query.py                # query(question, top_k=3) → list[Chunk]
├── cli.py                  # interactive REPL (bonus)
├── requirements.txt
└── .env.example
```

### Chunking strategy

**One row = one chunk.** Each row in the catalogue is a self-contained
packaging or service offering. Customer questions (MOQ, lead time, price)
map 1:1 onto rows; finer chunking scatters the answer, coarser dilutes the
signal. Before embedding, each row is rendered into a short prose paragraph
— embedding models perform much better on prose than on CSV key=value
strings.

### Embedding model

`sentence-transformers/all-MiniLM-L6-v2` — 384 dims, ~80MB, fast and runs
locally with zero API cost. English-only.

### Setup

A single `.venv` and `.env` at the **repo root** are shared across all four
tasks — there is no per-task venv.

```powershell
# From the repo root (one-time):
cd "c:\Users\FATIMA KHAN\Desktop\projects\teambeauty-assessment"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Configure DB connection
Copy-Item .env.example .env
# edit .env, paste your Supabase DATABASE_URL (use the pooler URL, port 6543)

# Create the schema in Supabase
#   Supabase dashboard → SQL editor → paste contents of task1/schema.sql → Run

# Ingest the sample catalogue
cd task1
python ingest.py

# Query
python query.py "What is the MOQ for a 30ml airless pump?"
python cli.py                  # interactive REPL
```

### Sample output

```
$ python query.py "lead time for glass droppers"
[0.812] Glass Dropper Bottle (Bottle). Material: Amber Glass. Size: 30ml. MOQ: 1000 units. Lead time: 21 days. ...
[0.794] Glass Dropper Bottle (Bottle). Material: Clear Glass. Size: 50ml. MOQ: 1000 units. Lead time: 21 days. ...
[0.612] Frosted Glass Jar (Jar). Material: Frosted Glass. Size: 50ml. MOQ: 500 units. Lead time: 28 days. ...
```

### Public API

```python
from query import query
chunks = query("What is the MOQ for a 30ml airless pump?", top_k=3)
for c in chunks:
    print(c.similarity, c.content)
```
