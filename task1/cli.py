"""Interactive CLI for querying the knowledge base.

Run:
    python cli.py
    > MOQ for a 30ml airless?
    [0.842] Airless Pump Bottle (Bottle). Material: PP + AS. Size: 30ml. ...
    ...
"""
from __future__ import annotations

from query import query


def main() -> None:
    print("Team Beauty knowledge base — ask anything about packaging, MOQs, lead times.")
    print("Type 'quit' or Ctrl-C to exit.\n")
    try:
        while True:
            q = input("> ").strip()
            if not q:
                continue
            if q.lower() in {"quit", "exit", "q"}:
                break
            results = query(q, top_k=3)
            if not results:
                print("  (no results — has the knowledge base been ingested? run `python ingest.py`)")
                continue
            for i, chunk in enumerate(results, 1):
                print(f"  {i}. [{chunk.similarity:.3f}] {chunk.content}")
            print()
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
