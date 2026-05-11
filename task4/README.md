# Task 4 — Shopify reviews app + theme extension + AI summary

Shopify embedded app + storefront theme extension App Block + Groq-powered
one-sentence AI summary of product reviews. Reviews persist in the same
Supabase Postgres that backs Tasks 1–3 — one schema, four consumers.

## Live demo evidence

End-to-end test on a Shopify Partner dev store
(`team-beauty-c84pe2wx.myshopify.com`), product `TB-WHITE-30`
(Whitening cream), Horizon theme:

```
Customer reviews
─────────────────────────────────────────────────────────────────
AI summary (2 reviews): Customers like the product, but some
find the quantity insufficient.

★★★★☆  Fatima        11/05/2026
Good product but less quantity

★★★★★  Shazam Khan   11/05/2026
Great product!
```

Two real reviews submitted via the App Block form, persisted to Supabase
`reviews` table, and the AI summary (Groq Llama 3.3 70B) correctly
synthesised the *contrast* between the 5★ "Great product!" and the 4★
"less quantity" review into a single sentence.

## Layout

```
task4/
├── schema.sql                              # reviews table (Postgres migration)
├── README.md                               # this file
└── teambeauty-reviews/                     # Shopify CLI scaffold
    ├── shopify.app.toml                    # CLI-managed app config
    ├── package.json
    ├── app/                                # Remix server source
    │   ├── shopify.server.ts               # Shopify session middleware
    │   ├── db.server.ts                    # Prisma client (SQLite, sessions only)
    │   ├── reviews.server.ts               # NEW: pg pool + review CRUD
    │   ├── summary.server.ts               # NEW: Groq AI summary
    │   ├── cors.server.ts                  # NEW: CORS helper for storefront calls
    │   └── routes/
    │       ├── app._index.tsx              # admin landing (scaffolded)
    │       ├── app.reviews.tsx             # NEW: admin reviews table
    │       ├── api.reviews.$sku.tsx        # NEW: GET list + POST create
    │       └── api.summary.$sku.tsx        # NEW: GET AI summary
    └── extensions/
        └── product-reviews/                # Theme app extension
            ├── shopify.extension.toml
            ├── blocks/
            │   └── product-reviews.liquid  # App Block: form + list + summary
            └── assets/
                └── reviews.js              # Storefront client: fetch + submit
```

## Architecture

```
Storefront product page (Horizon theme)
  ┌───────────────────────────────────────────────┐
  │ <App Block: Product reviews>                  │
  │   Liquid renders empty container w/ SKU       │
  │   reviews.js fetches list + summary           │
  │   Form POSTs new review                       │
  └───────────────────┬───────────────────────────┘
                      │ HTTPS (CORS-permissive)
                      ▼
Remix app on Shopify CLI Cloudflare tunnel
  GET  /api/reviews/:sku?shop=…    → list reviews
  POST /api/reviews/:sku           → insert review
  GET  /api/summary/:sku?shop=…    → Groq one-sentence summary
                      │
                      │ pg.Pool over SSL
                      ▼
  Supabase Postgres  (reviews table — shared schema with Tasks 1-3)
```

## Why some choices are not "the textbook Shopify way"

### Two databases, deliberately

| Data | DB | Why |
|---|---|---|
| Shopify session tokens | SQLite via Prisma | Scaffolded default. Well-tested, isolated, file-based. No need to invent. |
| Review records | Supabase Postgres via `pg` | The whole point of cross-task consistency — same DB as Tasks 1, 2, 3. |

Could we have replaced the Prisma session storage with
`@shopify/shopify-app-session-storage-postgresql` and used one DB? Yes —
but it would pollute the shared schema with a `shopify_sessions` table
that has nothing to do with the cosmetics business, and it adds a
package + risk vector for ~5 lines of "saved code." The pragmatic call
was to keep the well-tested SQLite session adapter and put only
business data in Supabase.

### Deviation from the brief — LLM provider (again)

Brief says **Claude API**. We don't have funded Claude credits, so the
AI summary uses **Groq's Llama 3.3 70B** through the OpenAI-compatible
API — same approach as Task 2. One non-tool call per summary, very
fast. The summary you see in the demo screenshot is real Groq output.

Switching back to Claude is a single-file edit (`app/summary.server.ts`,
change `baseURL` and SDK init).

### Deviation from the brief — embedded admin auth strategy

The scaffold ships with `unstable_newEmbeddedAuthStrategy: true` (token
exchange). It was flaky during our local install on Shopify CLI 3.94 +
Cloudflare tunnel + dev-store-with-password-protection — repeatedly
401-ing the embedded `/app` route. We flipped it to `false` in
`app/shopify.server.ts`, which uses the older OAuth-redirect flow.

The storefront-facing App Block doesn't go through this strategy at all,
which is why the actual review submission + AI summary demo (the
brief's pass criteria) works regardless.

### Permissive CORS instead of App Proxy

The storefront-facing `/api/*` routes use `Access-Control-Allow-Origin: *`
so the App Block JavaScript can `fetch()` them directly from
`{shop}.myshopify.com`. The "correct" Shopify way is App Proxy
(`{shop}.myshopify.com/apps/reviews/...` with HMAC-signed query params),
but that adds ~30 min of setup and doesn't change what the user sees.
Documented as a known upgrade path.

In production you'd either move behind App Proxy or restrict the CORS
Allow-Origin to a known list of shop domains.

## Reviews schema

```sql
CREATE TABLE reviews (
    id              BIGSERIAL PRIMARY KEY,
    shop_domain     TEXT NOT NULL,   -- 'team-beauty-c84pe2wx.myshopify.com'
    product_sku     TEXT NOT NULL,   -- matches products.sku conceptually
    customer_name   TEXT NOT NULL,
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_reviews_shop_sku ON reviews (shop_domain, product_sku);
CREATE INDEX idx_reviews_created  ON reviews (created_at DESC);
```

`product_sku` is **not** an FK to `products.sku` because in our schema
SKU is unique per brand (not globally), and Shopify product SKUs may
not match internal SKUs 1:1. The conceptual join is:

```sql
reviews
  JOIN products ON products.sku = reviews.product_sku
  JOIN formulations ON formulations.product_id = products.id
```

i.e. you can pivot from a review to the formulation it came from —
the "could match a formulation" line in the brief.

## Setup (from scratch)

You need:
- The shared repo-root `.venv` and `.env` (see top-level README)
- Node.js 20.19+ (we used Node 24)
- A free Shopify Partner account at <https://partners.shopify.com>
- A development store under your Partner account
- The Shopify CLI installed globally:
  ```powershell
  npm install -g @shopify/cli@latest
  ```

### One-time

```powershell
# 1) Apply the reviews migration to Supabase
cd "c:\Users\FATIMA KHAN\Desktop\projects\teambeauty-assessment"
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); import os, psycopg; psycopg.connect(os.environ['DATABASE_URL'], autocommit=True).execute(open('task4/schema.sql').read())"

# 2) Configure the Shopify app's env (one .env per Shopify app — the CLI
#    expects it inside the app folder). The DATABASE_URL + GROQ_API_KEY
#    values are duplicated from the repo-root .env.
cd task4\teambeauty-reviews
# .env should already exist with the right values; if not:
Copy-Item ..\..\.env .env

# 3) Install npm deps (already done if you scaffolded)
npm install
```

### Each dev session

```powershell
cd task4\teambeauty-reviews
shopify app dev --store <your-dev-store>.myshopify.com
```

On first run the CLI will:
1. Ask you to log into your Shopify Partner account (browser auth flow)
2. Ask for the storefront password. Dev stores are password-protected
   by default and you can't disable it for development stores.
   **For this assessment's dev store the password is `123`.** (You can
   verify or change it in admin → Online Store → Preferences →
   Password protection.)
3. Open a Cloudflare tunnel and print a Preview URL like
   `https://<random>-trycloudflare.com`.

Copy the trycloudflare.com URL — you'll need it for the App Block
settings on first install.

### First-time install on the dev store

1. In the dev-server terminal output find the install URL labeled
   `[1] https://admin.shopify.com/?organization_id=...` and click it.
2. Click **Install app** to install on your dev store.
3. (Optional, hits the embedded auth quirk) Open the app's icon in the
   dev-store admin sidebar to see the embedded UI. If you get
   `oauth_error=same_site_cookies`, allow third-party cookies for
   shopify.com or use Firefox/Edge.

### Add the App Block to a product page

1. Dev-store admin → **Online Store → Themes** → Customize on the
   active theme.
2. Top dropdown: switch from "Home page" to **Products → your-product**.
   (If your store has no products, create one first; the SKU goes in
   **Inventory → SKU**, not the Variants section.)
3. **Add block → Apps → Product reviews**.
4. Click the new Product reviews block → paste your tunnel URL into
   **App URL** (no trailing slash).
5. **Save**.

### Demo

1. Open the storefront product page; enter the storefront password (`123`).
2. Scroll to the **Customer reviews** block.
3. Click **Write a review** → fill in name, rating, text → **Submit**.
4. The review appears in the list and the AI summary line at the top
   regenerates within a couple of seconds.
5. Open the dev-server terminal — you'll see logs for the `POST
   /api/reviews/...` and `GET /api/summary/...` requests.
6. Confirm in Postgres:
   ```sql
   SELECT * FROM reviews ORDER BY id DESC LIMIT 5;
   ```

## API surface

### Storefront-facing (CORS, no auth)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/reviews/:sku?shop=<domain>` | `GET` | List reviews for shop+SKU |
| `/api/reviews/:sku` | `POST` | Create one review. Body: `{shop_domain, customer_name, rating, review_text}` |
| `/api/summary/:sku?shop=<domain>` | `GET` | Groq-generated one-sentence summary + review count |

All three handle CORS preflight (OPTIONS) automatically.

### Admin-facing (Shopify session auth)

| Route | Purpose |
|---|---|
| `/app` | Default scaffolded landing page |
| `/app/reviews` | Admin reviews table for the current shop (Polaris IndexTable) |

## Known issues / what we'd do next

- **Same-site cookie 401 on embedded admin in Chrome.** Standard
  Shopify dev pain. Documented above. Affects only the admin
  `/app/reviews` view, not the actual review functionality.
- **No caching of AI summaries.** Recomputed on every fetch. Fine for
  demo volumes; a real install would cache by (shop, sku) with a
  short TTL or invalidate-on-insert.
- **No moderation.** Submitted reviews appear immediately. Easy add:
  `moderated boolean` column + WHERE clause in the GET endpoint.
- **Cloudflare tunnel URL changes on every `shopify app dev` restart.**
  You'd need to update the App Block's "App URL" setting each time.
  Production deployment to a stable URL (Fly.io / Render / Heroku /
  Vercel etc) removes that.
- **App Proxy not implemented.** Would replace the CORS approach with
  HMAC-signed requests via `{shop}.myshopify.com/apps/reviews/...`.
  Cleaner architecturally; ~30 min of setup we cut for time.
