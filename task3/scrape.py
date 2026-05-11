"""Price scraper entry point.

Usage:
    python scrape.py                              # one-shot
    python scrape.py --terms data/search_terms.txt
    python scrape.py --watch --interval 3600      # APScheduler, every hour
    python scrape.py --watch --interval 60        # for demo: every minute
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

import parser
import store

HERE = Path(__file__).parent
DEFAULT_TERMS = HERE / "data" / "search_terms.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scrape")


def load_terms(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def scrape_once(terms: list[str]) -> dict:
    """Run a full scrape pass for all terms. Returns a summary dict.

    One Playwright browser is shared across all terms — launching a fresh
    Chromium per term would dominate wall-clock time.
    """
    started = datetime.now()
    totals = {"items": 0, "changed": 0, "errors": 0, "by_term": {}}

    with parser.browser_session() as browser:
        for term in terms:
            try:
                items = parser.scrape_search(browser, term)
            except Exception:
                log.exception("scrape failed for term=%r", term)
                totals["errors"] += 1
                totals["by_term"][term] = {"items": 0, "changed": 0, "error": True}
                continue

            if not items:
                log.warning("term=%r returned 0 items (unmapped or empty page?)", term)
                totals["by_term"][term] = {"items": 0, "changed": 0, "error": False}
                continue

            try:
                summary = store.batch_insert(items)
            except Exception:
                log.exception("batch insert failed for term=%r", term)
                totals["errors"] += 1
                totals["by_term"][term] = {"items": 0, "changed": 0, "error": True}
                continue

            totals["items"] += summary["items"]
            totals["changed"] += summary["changed"]
            totals["by_term"][term] = {**summary, "error": False}
            log.info("term=%r → %d items, %d price change(s)", term, summary["items"], summary["changed"])

    elapsed = (datetime.now() - started).total_seconds()
    log.info(
        "DONE: %d items across %d terms in %.1fs (%d changed, %d errors)",
        totals["items"], len(terms), elapsed, totals["changed"], totals["errors"],
    )
    return totals


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", type=Path, default=DEFAULT_TERMS,
                    help="Path to a file with one search term per line.")
    ap.add_argument("--watch", action="store_true",
                    help="Run on a schedule via APScheduler (instead of one-shot).")
    ap.add_argument("--interval", type=int, default=3600,
                    help="Watch-mode interval in seconds (default: 3600).")
    args = ap.parse_args()

    terms = load_terms(args.terms)
    if not terms:
        log.error("No search terms found in %s", args.terms)
        sys.exit(1)
    log.info("Loaded %d terms from %s", len(terms), args.terms)

    if not args.watch:
        scrape_once(terms)
        return

    sched = BlockingScheduler()
    sched.add_job(
        scrape_once,
        trigger=IntervalTrigger(seconds=args.interval),
        args=[terms],
        next_run_time=datetime.now(),       # run immediately on start
        id="scrape",
        max_instances=1,
        coalesce=True,
    )

    def _stop(_sig, _frm):
        log.info("Shutting down scheduler...")
        sched.shutdown(wait=False)

    signal.signal(signal.SIGINT, _stop)
    log.info("Scheduler started — interval=%ds. Ctrl-C to stop.", args.interval)
    sched.start()


if __name__ == "__main__":
    main()
