# Task 2 — Bilingual AI intake agent

A FastAPI app that simulates the inbound qualification agent. It detects
English vs Urdu, holds a multi-turn conversation, queries the Task 1
knowledge base when the customer asks factual questions, and returns a
structured lead summary once all six fields are collected.

> ### Deviation from the brief — LLM provider
>
> The test brief specifies **Claude API or OpenAI**. We are using
> **Groq's Llama 3.3 70B Versatile** instead, because funded credits on
> Claude / OpenAI were not available at build time and Groq offers a
> genuinely free tier sufficient for this assessment.
>
> Groq exposes an OpenAI-compatible API, so the swap is small: same
> tool-use architecture, same system prompt, same conversation flow —
> only the SDK and the wire format change. With a Claude or OpenAI key,
> swapping back is a ~15-minute edit to `agent.py` (`OpenAI(...)` →
> `Anthropic()`, and the tool-call shape converts back to Anthropic's).
>
> Known tradeoff: Llama 3.3's Urdu output is workable but less polished
> than Claude's would be on the same prompt.

## Architecture

```
HTTP request
   │
   ▼
detect_language()          ← Python (Unicode block check), deterministic
   │
   ▼
agent.chat()               ← Groq Llama 3.3 70B (OpenAI-compatible) with tool use
   │  ├── tool: query_knowledge_base  → hits the same `knowledge_chunks` table from Task 1
   │  └── tool: record_lead_fields    → writes to `leads` table
   ▼
store.* persist everything to Postgres
   │
   ▼
ChatOut (reply, language_detected, fields_collected, complete)
```

### Files

```
task2/
├── schema.sql        # leads + lead_messages migration
├── db.py             # Postgres connection
├── language.py       # Urdu/English Unicode-block detector
├── kb.py             # vector search over Task 1's knowledge_chunks
├── store.py          # lead + message persistence
├── agent.py          # Groq Llama tool-use loop
├── app.py            # FastAPI surface
├── chat_cli.py       # interactive CLI client (hits the FastAPI server)
├── requirements.txt
├── .env.example
└── README.md
```

### Why these design choices

- **Language detection in Python, not the model.** Cheap, fast,
  deterministic, and lets us return `language_detected` to the caller
  before/after the LLM call. The detected language is then injected into
  the system prompt so Claude *commits* to replying in that language.
- **Two tools, not one giant prompt.** `query_knowledge_base` for catalog
  facts and `record_lead_fields` for structured state updates. This lets
  the model decide when to look something up vs when it has enough info,
  and surfaces every state change as a discrete tool call we can audit.
- **DB as the source of truth for state and history.** No in-memory
  session dict — the FastAPI process is stateless. Restarting the server
  doesn't lose conversations.
- **Same DB, same `knowledge_chunks` table as Task 1.** The agent does
  not call Task 1's code; it just queries the same pgvector table
  directly. One schema, two consumers.
- **Urdu handling.** The system prompt switches to Urdu when
  `language == 'ur'` (test brief permits hardcoded Urdu prompts). For KB
  lookups the agent is instructed to translate Urdu questions to a short
  English query before calling `query_knowledge_base` (since the catalog
  is English).

## Setup

A single `.venv` and `.env` at the **repo root** are shared across all four
tasks (see the top-level README and `task1/README.md` for the one-time setup).

```powershell
# From the repo root, assuming you've already run the shared setup:
.\.venv\Scripts\Activate.ps1

# 1) Apply the task 2 migration on top of Task 1's schema:
#    Supabase dashboard → SQL editor → paste task2/schema.sql → Run.

# 2) Run the API
cd task2
python -m uvicorn app:app --reload --port 8000
```

Docs are auto-generated at <http://localhost:8000/docs>.

## Talking to the agent

Three ways, in order of convenience:

### 1. Interactive CLI (recommended for demo)

Open a **second** terminal while the server is running and start the CLI:

```powershell
cd task2
.\.venv\Scripts\python.exe chat_cli.py
```

You get a chat-style prompt. Slash commands: `/lead` (see the structured
lead so far), `/reset` (new session), `/quit`. Urdu input works directly
— just type or paste Urdu text.

```
────────────────────────────────────────────────────────────
 Team Beauty intake agent — interactive CLI
 Session : cli-3f2a91b8
 ...
────────────────────────────────────────────────────────────

You › Hi, I want to launch a skincare brand.
Agent [en] › Welcome! What's the name of your brand?
  [█░░░░░] 1/6  complete=False
```

### 2. Swagger UI

Open <http://localhost:8000/docs>, click **POST /chat → Try it out**,
paste a JSON body, hit Execute. Same `session_id` across calls keeps
the conversation going.

### 3. Curl examples

#### English conversation

```powershell
# Turn 1
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-en","channel":"whatsapp","message":"Hi, I want to launch a skincare brand."}'

# Turn 2 — answer the agent's question
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-en","channel":"whatsapp","message":"My company is Lumen Botanicals, I am Sara."}'

# Turn 3 — ask a catalog question
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-en","channel":"whatsapp","message":"What is the MOQ for a 30ml airless pump?"}'

# Turn 4 — finish qualifying
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-en","channel":"whatsapp","message":"Target 5000 units, launch in 3 months, clean-beauty positioning."}'

# Get the final structured lead
curl.exe http://localhost:8000/lead/demo-en
```

#### Urdu conversation

```powershell
# Turn 1 (Urdu)
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-ur","channel":"whatsapp","message":"السلام علیکم، میں اپنا اسکن کیئر برانڈ شروع کرنا چاہتی ہوں۔"}'

# Turn 2 (Urdu) — provide company / contact
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-ur","channel":"whatsapp","message":"کمپنی کا نام نور بیوٹی ہے، میرا نام عائشہ ہے۔"}'

# Turn 3 (Urdu) — catalog question
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id":"demo-ur","channel":"whatsapp","message":"30ml ایئرلیس پمپ بوتل کے لیے MOQ کیا ہے؟"}'

# Final lead
curl.exe http://localhost:8000/lead/demo-ur
```

## Response shape

`POST /chat`:
```json
{
  "reply": "Welcome! What is the name of your brand?",
  "language_detected": "en",
  "fields_collected": {
    "company_name": null,
    "contact_name": null,
    "product_category": "skincare",
    "target_quantity": null,
    "timeline": null,
    "brand_goals": null
  },
  "complete": false
}
```

`GET /lead/{session_id}` once `complete = true`:
```json
{
  "session_id": "demo-en",
  "channel": "whatsapp",
  "language": "en",
  "fields_collected": {
    "company_name": "Lumen Botanicals",
    "contact_name": "Sara",
    "product_category": "skincare",
    "target_quantity": "5000 units",
    "timeline": "3 months",
    "brand_goals": "clean-beauty positioning"
  },
  "complete": true
}
```

## The system prompt

The full prompt is built dynamically in `agent.py::_system_prompt` so it
includes the currently-collected fields and the missing ones every turn.
The static skeleton — role, language directive, conversation rules, tool
usage — is reproduced below for reference:

> You are the inbound qualification agent for Team Beauty & Cosmix — a
> private-label and contract-manufacturing operation for cosmetics. The
> customer is reaching you on the {channel} channel.
>
> {language directive — Urdu or English}
>
> Your job is to (a) answer the customer's questions warmly and (b)
> collect six qualification fields, one or two at a time, through natural
> conversation: company_name, contact_name, product_category,
> target_quantity, timeline, brand_goals.
>
> ALREADY COLLECTED: {…}
> STILL MISSING: {…}
>
> Conversation rules: greet once; ask for ONE missing field at a time;
> when the customer asks about packaging/MOQ/lead time/pricing call
> query_knowledge_base first; whenever you learn a field value call
> record_lead_fields; keep replies under 4 short sentences; no bullet
> lists in user-facing text; when all six fields are collected propose a
> 20-minute discovery call.
