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

CONCURRENCY (added 2026-09-06): same fix and same reasoning as
_ohlcv_backfill_runner.py — this is I/O-bound work dominated by R2 read-merge-write
(~2s/instrument observed) far more than the API fetch itself (~0.27s), run
sequentially before this change. Now a ThreadPoolExecutor per run; RunSummary is
aggregated on the main thread only, from each worker's returned result — never
mutated inside a worker thread. Same thread-safety basis as the backfill runner:
boto3 client (R2), httpx Client under supabase-py, and requests.Session (Upstox,
headers set once at construction, only concurrent .get() after) are all safe for
this usage pattern.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from modules.market_data.upstox import ohlcv_fetch_progress as progress
from modules.market_data.upstox._ohlcv_engine import TIER1_TIMEFRAMES
from modules.market_data.upstox.ohlcv_store import update_instrument

logger = logging.getLogger(__name__)

THROTTLE_SECONDS = 0.25  # per-worker pacing now, not a global serializing sleep — see module docstring
MAX_WORKERS = 4           # CONFIRMED 2026-09-06: 10 and 6 both triggered Cloudflare edge
                          # rate limiting heavily (6 alone: 680 occurrences before
                          # finishing). 5 also showed activity (53 occurrences),
                          # recoverable but not clean. 4 is the only count that ran with
                          # ZERO 429s against a real workload (2,641 instruments, 1,423
                          # genuine writes, 18m10s vs ~77m sequential — 4.2x).


@dataclass
class RunSummary:
    attempted: int = 0
    succeeded: int = 0      # ok=True AND a write actually happened
    unchanged: int = 0      # fetched, ok=True, but no change vs stored data — write skipped
    skipped: int = 0        # cooldown skip — NO fetch attempted at all (see ohlcv_store.COOLDOWN_MINUTES)
    failed: int = 0
    total_bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _WorkerResult:
    """What a worker thread reports back — the main thread aggregates from this,
    never from shared state touched inside the thread."""
    instrument_key: str
    ok: bool
    changed: bool = False
    skipped: bool = False
    bytes_written: int = 0
    error: Optional[str] = None


def _refresh_one(domain: str, item: "progress.PendingItem",
                 timeframes: tuple[tuple[str, str], ...]) -> _WorkerResult:
    """Runs on a worker thread: one instrument's windowed refresh. Same failure
    semantics as before this change — a miss does NOT call mark_failed() (see
    module docstring); only success touches the ledger. Returns a result for the
    main thread to fold into RunSummary. A cooldown skip makes NO API call, so it
    skips the throttle sleep too — there's no request pressure to pace against."""
    ik = item.instrument_key
    try:
        result = update_instrument(ik, domain, last_success_at=item.last_success_at,
                                   timeframes=timeframes)
        if result.skipped:
            return _WorkerResult(ik, ok=True, skipped=True)
        if result.ok:
            progress.mark_done(ik, domain)  # status already 'done'; confirms check succeeded
            time.sleep(THROTTLE_SECONDS)
            return _WorkerResult(ik, ok=True, changed=result.changed,
                                 bytes_written=result.bytes_written)
        time.sleep(THROTTLE_SECONDS)
        return _WorkerResult(ik, ok=False, error=result.error or "unknown")
    except Exception as exc:  # noqa: BLE001 — isolate one bad instrument from the run
        time.sleep(THROTTLE_SECONDS)
        return _WorkerResult(ik, ok=False, error=f"unexpected: {exc}")


def run_refresh(domain: str, limit: Optional[int] = None,
                timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES) -> RunSummary:
    """
    Refresh OHLCV for all 'done' instruments in a domain.
      1. Get the refresh work list (status == 'done') for this domain.
      2. Run each instrument's refresh on a worker thread pool (MAX_WORKERS at
         once); the main thread aggregates results as they complete. One
         instrument failing does NOT abort the run and does NOT touch the ledger
         (see module docstring).
    `timeframes` defaults to Tier-1 D/W/M; pass INTRADAY_TIMEFRAMES for the
    options-intraday domain. Safe to re-run any time — update_instrument is itself
    idempotent (merge-dedup); unaffected by the concurrency change since selection
    (get_done) happens before the pool is created.

    Completion order is NOT submission order — the [i/N] progress numbers in logs
    count completions, not a fixed sequence.
    """
    summary = RunSummary()

    todo = progress.get_done(domain=domain)
    if limit is not None:
        todo = todo[:limit]
    logger.info("Refreshing %d done %s instrument(s)%s across %d worker(s).",
                len(todo), domain, f" (limited to {limit})" if limit else "", MAX_WORKERS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_refresh_one, domain, item, timeframes): item.instrument_key
                   for item in todo}
        for i, future in enumerate(as_completed(futures), start=1):
            ik = futures[future]
            try:
                res = future.result()
            except Exception as exc:  # noqa: BLE001 — defensive backstop; _refresh_one
                                       # already catches internally, so this shouldn't fire
                logger.error("[%d/%d] %s FAILED (worker crashed): %s", i, len(todo), ik, exc)
                summary.attempted += 1
                summary.failed += 1
                summary.failures.append((ik, f"worker crashed: {exc}"))
                continue

            summary.attempted += 1
            if res.skipped:
                summary.skipped += 1
                logger.info("[%d/%d] %s skipped (cooldown).", i, len(todo), ik)
            elif res.ok:
                if res.changed:
                    summary.succeeded += 1
                    summary.total_bytes += res.bytes_written
                else:
                    summary.unchanged += 1
                logger.info("[%d/%d] %s ok (changed=%s).", i, len(todo), ik, res.changed)
            else:
                summary.failed += 1
                summary.failures.append((ik, res.error or "unknown"))
                logger.warning("[%d/%d] %s refresh miss: %s", i, len(todo), ik, res.error)

    return summary


def print_summary(domain: str, summary: RunSummary) -> None:
    logger.info("=" * 60)
    logger.info("%s OHLCV REFRESH — SUMMARY", domain.upper())
    logger.info("=" * 60)
    logger.info("  attempted : %d", summary.attempted)
    logger.info("  succeeded : %d  (data changed, wrote to R2)", summary.succeeded)
    logger.info("  unchanged : %d  (checked, nothing new — write skipped)", summary.unchanged)
    logger.info("  skipped   : %d  (cooldown — no API call made, checked too recently)", summary.skipped)
    logger.info("  failed    : %d  (self-heals via next run's lookback window)", summary.failed)
    logger.info("  data written: %.2f MB", summary.total_bytes / 1024 / 1024)
    if summary.failures:
        logger.info("  misses:")
        for ik, err in summary.failures[:20]:
            logger.info("    %-30s %s", ik, err[:70])
        if len(summary.failures) > 20:
            logger.info("    ... and %d more", len(summary.failures) - 20)
    logger.info("  ledger counts: %s", progress.get_counts(domain=domain))
    logger.info("=" * 60)


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
