"""
modules/market_data/upstox/_ohlcv_refresh_runner.py

Shared daily-OHLCV-refresh orchestration for all domains (indices, universe — Nifty
50 included, it already lives in the 'indices' domain per ohlcv_store's own spike
test). Mirrors _ohlcv_backfill_runner.py's shape (same throttle, same per-instrument
isolation, same RunSummary), but works the OPPOSITE end of the ledger: instruments
already status='done' (backfilled), not pending ones. Backfill and refresh are
separate runners, not one runner with a mode flag — different ledger lifecycles
(one-time-complete vs recurring), see build-log discussion.

CADENCE: all three Tier-1 timeframes (1d/1w/1mo) every run. update_instrument's
lookback windows are small (10/21/95 days), so the API cost of refreshing W/M daily
is negligible — no calendar-conditional branching needed.

FAILURE HANDLING: a failed update_instrument() call is logged + counted in the run
summary, but does NOT call mark_failed() on the ledger — that would flip status to
'failed' and pull the instrument into the BACKFILL runner's queue (a full-history
re-fetch), the wrong response to a transient daily miss. update_instrument's
overlapping windows self-heal a missed day on tomorrow's run.

Standards applied: single responsibility (orchestration only), resumable in the
"self-heals via overlap" sense rather than a ledger-tracked resume (daily refresh has
no partial-run resume need — it's a full domain sweep every day), defensive
(per-instrument try/except), proactive throttle, structured logging.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from modules.market_data.upstox import ohlcv_fetch_progress as progress
from modules.market_data.upstox._ohlcv_engine import TIER1_TIMEFRAMES
from modules.market_data.upstox.ohlcv_store import update_instrument

logger = logging.getLogger(__name__)

THROTTLE_SECONDS = 0.25  # same pacing proven on the backfill runs


@dataclass
class RunSummary:
    attempted: int = 0
    succeeded: int = 0      # ok=True AND a write actually happened
    unchanged: int = 0      # ok=True but no change vs stored data — write skipped
    failed: int = 0
    total_bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def run_refresh(domain: str, limit: Optional[int] = None,
                timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES) -> RunSummary:
    """
    Refresh OHLCV for all 'done' instruments in a domain.
      1. Get the refresh work list (status == 'done') for this domain.
      2. For each (optionally capped by `limit`): update_instrument -> mark_done on
         success. One instrument failing does NOT abort the run and does NOT touch
         the ledger (see module docstring).
    `timeframes` defaults to Tier-1 D/W/M; pass INTRADAY_TIMEFRAMES for the
    options-intraday domain. Safe to re-run any time — update_instrument is itself
    idempotent (merge-dedup).
    """
    summary = RunSummary()

    todo = progress.get_done(domain=domain)
    if limit is not None:
        todo = todo[:limit]
    logger.info("Refreshing %d done %s instrument(s)%s.",
                len(todo), domain, f" (limited to {limit})" if limit else "")

    for i, item in enumerate(todo, start=1):
        ik = item.instrument_key
        summary.attempted += 1
        logger.info("[%d/%d] %s ...", i, len(todo), ik)
        try:
            result = update_instrument(ik, domain, last_success_at=item.last_success_at,
                                       timeframes=timeframes)
            if result.ok:
                progress.mark_done(ik, domain)  # status already 'done'; confirms check succeeded
                if result.changed:
                    summary.succeeded += 1
                    summary.total_bytes += result.bytes_written
                else:
                    summary.unchanged += 1
            else:
                summary.failed += 1
                summary.failures.append((ik, result.error or "unknown"))
                logger.warning("[%d/%d] %s refresh miss: %s", i, len(todo), ik, result.error)
        except Exception as exc:  # noqa: BLE001 — isolate one bad instrument from the run
            summary.failed += 1
            summary.failures.append((ik, f"unexpected: {exc}"))
            logger.error("[%d/%d] %s FAILED: %s", i, len(todo), ik, exc)

        time.sleep(THROTTLE_SECONDS)

    return summary


def print_summary(domain: str, summary: RunSummary) -> None:
    print("\n" + "=" * 60)
    print(f"{domain.upper()} OHLCV REFRESH — SUMMARY")
    print("=" * 60)
    print(f"  attempted : {summary.attempted}")
    print(f"  succeeded : {summary.succeeded}  (data changed, wrote to R2)")
    print(f"  unchanged : {summary.unchanged}  (checked, nothing new — write skipped)")
    print(f"  failed    : {summary.failed}  (self-heals via next run's lookback window)")
    print(f"  data written: {summary.total_bytes/1024/1024:.2f} MB")
    if summary.failures:
        print("\n  misses:")
        for ik, err in summary.failures[:20]:
            print(f"    {ik:<30} {err[:70]}")
        if len(summary.failures) > 20:
            print(f"    ... and {len(summary.failures) - 20} more")
    print("\n  ledger counts:", progress.get_counts(domain=domain))
    print("=" * 60 + "\n")


def cli_main(domain: str, timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES) -> None:
    """Shared CLI entry: --limit N (verify-first) + --quiet."""
    import argparse
    from dotenv import load_dotenv

    load_dotenv()
    import os
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),                                         # terminal, as before
            logging.FileHandler(f"logs/ohlcv_refresh_{domain}.log", mode="w"),  # overwritten each run
        ],
    )

    parser = argparse.ArgumentParser(description=f"Daily {domain} OHLCV refresh.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N done instruments (verify-first).")
    parser.add_argument("--quiet", action="store_true",
                        help="Less log noise: per-instrument progress + problems only.")
    args = parser.parse_args()

    if args.quiet:
        for name in ("httpx",
                     "modules.market_data.upstox._ohlcv_engine",
                     "modules.market_data.upstox.ohlcv_store",
                     "modules.market_data.upstox.ohlcv_fetch_progress"):
            logging.getLogger(name).setLevel(logging.WARNING)

    summary = run_refresh(domain, limit=args.limit, timeframes=timeframes)
    print_summary(domain, summary)
