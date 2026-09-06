"""
modules/market_data/upstox/fetch_daily_news.py

Daily news fetch across EVERY active instrument in all three catalogues (universe
stocks, ETFs, indices -- ~2,782 instrument_keys total). No ledger, no resumability
infra: unlike OHLCV backfill (thousands of instruments, hours-long runs, genuine
interrupt risk), this is ~93 batched calls that finish in well under a minute, and
Upstox's News API only returns the last 7 days anyway -- a failed batch today just
gets picked up again on tomorrow's run for anything still inside that window. The
7-day window is what makes daily, gap-free running matter (this data is
perishable), not what makes a ledger necessary (a single run is too short-lived
to need mid-run resume).

Standards applied: single responsibility (orchestration only -- delegates fetch/
store), per-batch isolation (one bad batch doesn't abort the run), proactive
throttle + the engine's existing retry as backstop, structured logging to both
console and an overwritten-per-run file (same pattern as the OHLCV refresh
runner).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox._news_engine import MAX_KEYS_PER_CALL, fetch_news_batch_resilient
from modules.market_data.upstox.news_store import store_articles

logger = logging.getLogger(__name__)

THROTTLE_SECONDS = 0.25  # same proactive pace as the OHLCV runners

# The three catalogue tables that between them define "every instrument."
_CATALOGUE_TABLES = ("f_universe_instruments", "f_etf_instruments",
                     "f_all_nse_index_instruments")


@dataclass
class RunSummary:
    total_instruments: int = 0
    batches_attempted: int = 0
    batches_clean: int = 0       # no errors at all
    batches_partial: int = 0     # bisection isolated a bad key; rest of batch still stored
    batches_failed: int = 0      # non-isolatable error (network/429/5xx); whole batch lost, retries tomorrow
    articles_fetched: int = 0
    bad_keys: list[str] = field(default_factory=list)              # confirmed-bad, individually isolated
    failures: list[tuple[str, str]] = field(default_factory=list)  # (label, error) — not isolated, not confirmed bad


def _load_all_instrument_keys() -> list[str]:
    """All active instrument_keys across universe + ETF + index catalogues,
    deduplicated (a key should only ever live in one catalogue, but dedup is
    cheap insurance against that assumption breaking silently)."""
    supabase = get_supabase()
    keys: set[str] = set()
    for table in _CATALOGUE_TABLES:
        PAGE = 1000
        start = 0
        table_count = 0
        while True:
            resp = (supabase.table(table)
                    .select("instrument_key")
                    .eq("is_active", True)
                    .range(start, start + PAGE - 1)
                    .execute())
            batch = resp.data or []
            keys.update(r["instrument_key"] for r in batch)
            table_count += len(batch)
            if len(batch) < PAGE:
                break
            start += PAGE
        logger.info("Loaded %d active instrument(s) from %s.", table_count, table)
    return sorted(keys)


def _batched(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_daily_news_fetch(limit: Optional[int] = None) -> RunSummary:
    """
    Fetch + store news for every active instrument across all catalogues.
      1. Load all instrument_keys (universe + ETF + index).
      2. Batch into groups of <=30 (the API's per-call limit).
      3. For each batch (optionally capped by `limit` batches, for verify-first):
         fetch_news_batch -> store_articles. One batch failing does NOT abort
         the run.
    Safe to re-run any time same-day -- store_articles is itself idempotent
    (dedup upsert).
    """
    summary = RunSummary()

    all_keys = _load_all_instrument_keys()
    summary.total_instruments = len(all_keys)
    batches = list(_batched(all_keys, MAX_KEYS_PER_CALL))
    if limit is not None:
        batches = batches[:limit]
    logger.info("Fetching news for %d instrument(s) across %d batch(es)%s.",
                len(all_keys), len(batches), f" (limited to {limit})" if limit else "")

    for i, batch in enumerate(batches, start=1):
        summary.batches_attempted += 1
        logger.info("[%d/%d] batch of %d instrument(s) ...", i, len(batches), len(batch))
        try:
            resilient = fetch_news_batch_resilient(batch)
            store_result = store_articles(resilient.articles)
            if not store_result.ok:
                summary.batches_failed += 1
                summary.failures.append((f"batch {i} store", store_result.error or "unknown"))
                logger.warning("[%d/%d] store failed: %s", i, len(batches), store_result.error)
                continue

            summary.articles_fetched += len(resilient.articles)
            if resilient.bad_keys:
                summary.bad_keys.extend(resilient.bad_keys)
                summary.batches_partial += 1
                logger.warning("[%d/%d] %d bad key(s) isolated, rest of batch stored (%d article(s)).",
                               i, len(batches), len(resilient.bad_keys), len(resilient.articles))
            if resilient.other_errors:
                summary.batches_failed += 1
                summary.failures.extend(resilient.other_errors)
                logger.warning("[%d/%d] non-isolatable error: %s",
                               i, len(batches), resilient.other_errors[0][1])
            elif not resilient.bad_keys:
                summary.batches_clean += 1
        except Exception as exc:  # noqa: BLE001 -- isolate one bad batch from the run
            summary.batches_failed += 1
            summary.failures.append((f"batch {i}", f"unexpected: {exc}"))
            logger.error("[%d/%d] FAILED: %s", i, len(batches), exc)

        time.sleep(THROTTLE_SECONDS)

    return summary


def print_summary(summary: RunSummary) -> None:
    logger.info("=" * 60)
    logger.info("DAILY NEWS FETCH — SUMMARY")
    logger.info("=" * 60)
    logger.info("  total instruments : %d", summary.total_instruments)
    logger.info("  batches attempted : %d", summary.batches_attempted)
    logger.info("  batches clean     : %d", summary.batches_clean)
    logger.info("  batches partial   : %d  (bad key isolated, rest stored)", summary.batches_partial)
    logger.info("  batches failed    : %d  (non-isolatable; self-heals within the 7-day window)",
                summary.batches_failed)
    logger.info("  articles fetched  : %d  (upserted; duplicates silently skipped)",
                summary.articles_fetched)
    if summary.bad_keys:
        logger.info("  bad keys isolated (%d):", len(summary.bad_keys))
        for key in summary.bad_keys:
            logger.info("    %s", key)
    if summary.failures:
        logger.info("  failures (not isolated, likely transient):")
        for label, err in summary.failures[:20]:
            logger.info("    %-40s %s", label, err[:70])
        if len(summary.failures) > 20:
            logger.info("    ... and %d more", len(summary.failures) - 20)
    logger.info("=" * 60)


def cli_main() -> None:
    """CLI entry: --limit N (batches, verify-first) + --quiet."""
    import argparse
    import os
    from dotenv import load_dotenv

    load_dotenv()
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/news_fetch.log", mode="w"),
        ],
    )

    parser = argparse.ArgumentParser(description="Daily news fetch (all catalogues).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N batches of 30 (verify-first).")
    parser.add_argument("--quiet", action="store_true",
                        help="Less log noise: per-batch progress + problems only.")
    args = parser.parse_args()

    if args.quiet:
        for name in ("httpx",
                     "modules.market_data.upstox._news_engine",
                     "modules.market_data.upstox.news_store"):
            logging.getLogger(name).setLevel(logging.WARNING)

    summary = run_daily_news_fetch(limit=args.limit)
    print_summary(summary)


if __name__ == "__main__":
    cli_main()
