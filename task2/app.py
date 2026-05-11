"""FastAPI surface for the bilingual intake agent.

Endpoints:
    POST /chat              — accept a message, return reply + state
    GET  /lead/{session_id} — return the structured lead summary
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import agent
import db
import kb
import store
from language import detect_language


class ChatIn(BaseModel):
    session_id: str = Field(..., min_length=1)
    channel: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatOut(BaseModel):
    reply: str
    language_detected: str
    fields_collected: dict
    complete: bool


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Open the DB connection pool and preload the embedding model so the
    # first /chat request doesn't pay TCP/TLS + model-load latency.
    db.open_pool()
    kb.warmup()
    yield


app = FastAPI(title="Team Beauty intake agent", lifespan=lifespan)


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    language = detect_language(body.message)
    lead = agent.chat(
        session_id=body.session_id,
        channel=body.channel,
        message=body.message,
        language=language,
    )
    # Read the agent's reply: the latest assistant row in lead_messages.
    history = store.load_history(body.session_id)
    reply = next(
        (m["content"] for m in reversed(history) if m["role"] == "assistant"),
        "",
    )
    return ChatOut(
        reply=reply,
        language_detected=language,
        fields_collected=lead.as_dict(),
        complete=lead.complete,
    )


@app.get("/lead/{session_id}")
def get_lead(session_id: str):
    lead = store.get_lead(session_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {
        "session_id": lead.session_id,
        "channel": lead.channel,
        "language": lead.language,
        "fields_collected": lead.as_dict(),
        "complete": lead.complete,
    }
