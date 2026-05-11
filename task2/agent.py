"""LLM-powered intake agent.

Note on model choice
--------------------
The test brief states the agent should be powered by Claude or OpenAI.
We are using **Groq's Llama 3.3 70B Versatile** instead, because I did 
not have funded Claude / OpenAI credits at build time.
Groq exposes an OpenAI-compatible API, so the only thing that changes
relative to the original Anthropic design is the SDK and the tool-call
wire format. The architecture is unchanged:
    * Two tools exposed to the model:
        - `query_knowledge_base(question)` — pgvector search over the
          Task 1 `knowledge_chunks` table.
        - `record_lead_fields(...)` — structured state updates persisted
          to the `leads` table.
    * Agent loop: call → execute tool calls → feed results back →
      repeat → exit when the model returns a final text response.
    * Language detection happens *outside* the model (language.py) and
      the detected language is forced via the system prompt.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

import kb
import store

load_dotenv(Path(__file__).parent.parent / ".env")

MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROQ_API_KEY", ""),
)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_knowledge_base",
            "description": (
                "Search Team Beauty & Cosmix's internal catalogue for packaging, "
                "MOQ, lead time, pricing, or formulation information. Use this "
                "whenever the customer asks a specific factual question about offerings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "A focused English-language question to look up.",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_lead_fields",
            "description": (
                "Record any of the six lead qualification fields you have just learned "
                "from the customer's message. Only include fields with concrete values."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name":     {"type": "string", "description": "Name of the customer's company / brand"},
                    "contact_name":     {"type": "string", "description": "The person we are speaking with"},
                    "product_category": {"type": "string", "description": "e.g. skincare, haircare, body care, makeup"},
                    "target_quantity":  {"type": "string", "description": "Order size or quantity context, free text"},
                    "timeline":         {"type": "string", "description": "When they want to launch / receive product"},
                    "brand_goals":      {"type": "string", "description": "Short summary of brand positioning or goal"},
                },
            },
        },
    },
]


def _system_prompt(lead: store.Lead) -> str:
    lang_directive = (
        "REPLY IN URDU (اردو) using natural, polite Pakistani business Urdu. "
        "Do not switch to English unless the customer does first."
        if lead.language == "ur"
        else "Reply in clear, friendly business English."
    )
    known = {f: getattr(lead, f) for f in store.REQUIRED_FIELDS if getattr(lead, f)}
    missing = lead.missing_fields()
    known_str = json.dumps(known, ensure_ascii=False) if known else "(none yet)"

    return f"""You are the inbound qualification agent for Team Beauty & Cosmix —
a private-label and contract-manufacturing operation for cosmetics. The
customer is reaching you on the {lead.channel} channel.

{lang_directive}

Your job is to (a) answer the customer's questions warmly and (b) collect
six qualification fields, one or two at a time, through natural conversation:

  - company_name        (their brand / business name)
  - contact_name        (who they are)
  - product_category    (skincare, haircare, makeup, body care, etc.)
  - target_quantity     (rough volume / MOQ they have in mind)
  - timeline            (when they want to launch / receive stock)
  - brand_goals         (positioning, audience, what they're trying to build)

ALREADY COLLECTED: {known_str}
STILL MISSING: {missing}

Conversation rules:
1. Greet on the very first turn, then ask for ONE missing field at a time —
   never interrogate. Acknowledge their previous answer first.
2. If the customer asks about packaging, MOQs, lead times, pricing, or
   formulation capabilities, call `query_knowledge_base` BEFORE replying.
   Translate Urdu questions to a short English query for the tool.
3. Whenever you learn a value for any of the six fields, call
   `record_lead_fields` with just the new values.
4. When all six fields are collected, confirm the summary back to the
   customer and propose booking a 20-minute discovery call.
5. Keep replies under 4 short sentences. No bullet lists in user-facing text.
"""


def _execute_tool(session_id: str, name: str, args: dict) -> str:
    if name == "query_knowledge_base":
        chunks = kb.query(args.get("question", ""), top_k=3)
        if not chunks:
            return "No matching catalogue entries found."
        return "\n\n".join(f"- {c.content}" for c in chunks)
    if name == "record_lead_fields":
        store.update_lead_fields(session_id, args)
        return "Recorded."
    return f"Unknown tool: {name}"


# Llama-on-Groq occasionally emits tool calls as text rather than via the
# proper `tool_calls` field, e.g. `<function=name {json}</function>`. When
# that happens Groq returns HTTP 400 with `code: 'tool_use_failed'` and the
# raw string in `failed_generation`. We salvage it.
# Matches any of: <function=name {json}</function>, <function=name({json})</function>,
# <function=name>{json}</function>. Leading `(` or `>` and trailing `)` are optional.
_FN_RE = re.compile(
    r"<function=(?P<name>\w+)\s*[(>]?\s*(?P<args>\{.*?\})\s*[)]?\s*</function>",
    re.DOTALL,
)


def _salvage_tool_call(failed_generation: str):
    m = _FN_RE.search(failed_generation or "")
    if not m:
        return None
    try:
        return m.group("name"), json.loads(m.group("args"))
    except json.JSONDecodeError:
        return None


def chat(session_id: str, channel: str, message: str, language: str) -> store.Lead:
    """Run one turn of the conversation. Returns the latest Lead row."""
    lead = store.get_or_create_lead(session_id, channel, language)
    store.append_message(session_id, "user", message)

    history = store.load_history(session_id)
    lead = store.get_lead(session_id) or lead
    system = _system_prompt(lead)

    # OpenAI-format messages: system first, then chat history.
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend({"role": m["role"], "content": m["content"]} for m in history)

    # Tool-use loop — hard cap as a safety belt.
    for _ in range(8):
        try:
            resp = _client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                max_tokens=1024,
            )
        except BadRequestError as e:
            # Salvage malformed Llama tool calls. If we can parse a call out
            # of `failed_generation`, synthesise a proper tool_calls turn and
            # let the loop continue. Note: OpenAI SDK's `e.body` is the inner
            # error dict (already unwrapped from `{"error": {...}}`).
            err = e.body if isinstance(e.body, dict) else {}
            if err.get("code") == "tool_use_failed":
                salvage = _salvage_tool_call(err.get("failed_generation", ""))
                if salvage:
                    name, args = salvage
                    call_id = f"salvaged_{uuid.uuid4().hex[:8]}"
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }],
                    })
                    result = _execute_tool(session_id, name, args)
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
                    continue
            raise

        choice = resp.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            # Final text response — persist and return.
            text = (msg.content or "").strip()
            store.append_message(session_id, "assistant", text)
            return store.get_lead(session_id) or lead

        # Append the assistant turn (must include tool_calls so the model can
        # match its tool_call_id when it sees the tool results).
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _execute_tool(session_id, tc.function.name, args)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

    fallback = "Sorry — I'm having trouble responding. A human will follow up shortly."
    store.append_message(session_id, "assistant", fallback)
    return store.get_lead(session_id) or lead
