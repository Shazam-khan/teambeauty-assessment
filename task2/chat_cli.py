"""Interactive chat CLI for the Task 2 agent.

Talks to the FastAPI server over HTTP, so you can see both:
  * uvicorn logs in one terminal (showing every /chat request)
  * the conversation in this terminal

Run the server first:
    python -m uvicorn app:app --reload --port 8000

Then in a second terminal:
    python chat_cli.py
    python chat_cli.py --session my-id            # resume an existing session
    python chat_cli.py --channel instagram        # set channel (default whatsapp)
    python chat_cli.py --api http://host:8000     # point at a remote server

Slash commands:
    /lead     show the structured lead summary so far
    /reset    wipe this session in the DB and start over with a new session_id
    /quit     exit
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid

# UTF-8 console — needed for Urdu input/output on Windows.
sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")


def _post(url: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url: str, timeout: int = 30) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


def _progress_bar(collected: int, total: int = 6) -> str:
    filled = "█" * collected
    empty = "░" * (total - collected)
    return f"[{filled}{empty}] {collected}/{total}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=f"cli-{uuid.uuid4().hex[:8]}",
                    help="Session ID (default: random)")
    ap.add_argument("--channel", default="whatsapp",
                    help="Channel name (whatsapp, instagram, email, ...)")
    ap.add_argument("--api", default="http://localhost:8000",
                    help="FastAPI base URL")
    args = ap.parse_args()

    print("─" * 60)
    print(f" Team Beauty intake agent — interactive CLI")
    print(f" Session : {args.session}")
    print(f" Channel : {args.channel}")
    print(f" Server  : {args.api}")
    print(f" Type a message and hit Enter. Slash commands: /lead /reset /quit")
    print("─" * 60)

    try:
        while True:
            try:
                msg = input("\nYou › ").strip()
            except EOFError:
                break
            if not msg:
                continue

            if msg in ("/quit", "/exit", "/q"):
                break

            if msg == "/lead":
                code, data = _get(f"{args.api}/lead/{args.session}")
                if code == 404:
                    print("  (no lead yet — send a message first)")
                else:
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                continue

            if msg == "/reset":
                args.session = f"cli-{uuid.uuid4().hex[:8]}"
                print(f"  New session: {args.session}")
                continue

            try:
                data = _post(
                    f"{args.api}/chat",
                    {
                        "session_id": args.session,
                        "channel": args.channel,
                        "message": msg,
                    },
                )
            except urllib.error.URLError as e:
                print(f"  ✗ Couldn't reach server at {args.api} — is uvicorn running?")
                print(f"    {e}")
                continue

            lang = data.get("language_detected", "?")
            reply = data.get("reply", "")
            fields = data.get("fields_collected", {})
            complete = data.get("complete", False)
            collected = sum(1 for v in fields.values() if v)

            print(f"\nAgent [{lang}] › {reply}")
            print(f"  {_progress_bar(collected)}  complete={complete}")

            if complete:
                print("\n✓ All six fields collected. Final lead summary:")
                print(json.dumps(fields, ensure_ascii=False, indent=2))
                print("  (start a new conversation with /reset)")

    except KeyboardInterrupt:
        pass
    print("\nBye.")


if __name__ == "__main__":
    main()
