"""
modules/market_data/upstox/_ohlcv_backfill_runner.py

Shared bulk-OHLCV-backfill orchestration for ALL domains (indices, universe, and
future ones). Extracted from the proven fetch_index_ohlcv.py logic so the index and
universe callers don't duplicate ~90% identical code — same DRY principle as the
shared _ohlcv_engine (fetch core) and the config-driven instrument_store.

A domain differs only in TWO things: which catalogue table lists its instruments, and
its domain string ('indices' | 'universe'). Everything else — seed ledger, get pending,
loop (mark_attempt → backfill → mark done/failed), throttle, per-instrument isolation,
summary — is identical. So this module holds all of it, parameterised by a small
DomainConfig, and the callers are thin.

Standards applied: single responsibility (orchestration only — delegates fetch/store/
track), resumable + idempotent (leans on ohlcv_fetch_progress ledger), defensive
(per-instrument try/except so one bad instrument can't abort the run), proactive
throttle + the engine's existing 429/5xx retry as backstop, structured logging.

CONCURRENCY (added 2026-09-06): this work is I/O-bound (waiting on the Upstox API
and R2, not computing) — a full-history backfill run was found to spend ~2s/instrument
on R2 read-merge-write alone, dwarfing the ~0.27s API fetch, with the whole run
executed sequentially. Fixed with a ThreadPoolExecutor: each instrument's work
(mark_attempt -> backfill -> mark_done/failed) runs as an independent unit on a
worker thread and returns a result; RunSummary is aggregated ONLY on the main thread
as futures complete, never mutated from inside a worker (avoids needing to make the
dataclass itself thread-safe). Verified safe to share across threads: boto3 `client`
objects (R2) are documented thread-safe; supabase-py sits on httpx, whose `Client` is
documented thread-safe; `requests.Session` (Upstox) is not OFFICIALLY documented
thread-safe but is safe in the pattern used here — headers set once at construction,
never mutated after, concurrent .get() calls only. THROTTLE_SECONDS now paces each
WORKER individually (not a single global sleep serializing the whole run) — a simple
safety margin against Upstox's 25/sec cap, since backfill's paginated per-instrument
fetches can burst many calls in quick succession.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox import ohlcv_fetch_progress as progress
from modules.market_data.upstox._ohlcv_engine import TIER1_TIMEFRAMES
from modules.market_data.upstox.ohlcv_store import backfill_instrument

logger = logging.getLogger(__name__)

# Proactive pace per WORKER (seconds) — not a global serializing sleep. Keeps each
# thread's own call rate modest; MAX_WORKERS threads pacing independently spreads
# calls out without a hard rate-limiter. Tune down if Upstox 429s spike, tune
# MAX_WORKERS down first if so (fewer threads in flight is the primary lever).
THROTTLE_SECONDS = 0.25

# Concurrent instruments in flight. I/O-bound work (network + R2), not CPU-bound —
# threads, not processes. CONFIRMED 2026-09-06: 10 and 6 both triggered Cloudflare's
# edge rate limiting heavily (HTTP 429 "Error 1015" — 6 alone produced 680
# occurrences before finishing). 5 also showed rate-limit activity (53 occurrences),
# recoverable via retry but not clean. 4 is the only count that ran with ZERO 429s
# against a real workload (2,641 instruments, 1,423 genuine writes, 18m10s vs ~77m
# sequential — 4.2x). Back to 4 as the settled choice.
MAX_WORKERS = 4


@dataclass(frozen=True)
class DomainConfig:
    """The only things that differ between domains."""
    domain: str                 # 'indices' | 'universe' | 'universe_intraday'
    catalogue_table: str        # supabase table listing this domain's instruments
    timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES
    # Optional catalogue subset filter (e.g. is_fno_eligible=True for the
    # options-intraday domain, which only covers F&O-eligible stocks, not the
    # full universe). None = no extra filter (existing universe/indices behavior).
    extra_filter_column: Optional[str] = None
    extra_filter_value: Optional[bool] = None
    # Optional bounded backfill start (e.g. 1 year back for intraday, instead of
    # each unit's full history-start default in _ohlcv_engine). None = engine default.
    backfill_from_date: Optional[date] = None


@dataclass
class RunSummary:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    total_bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (instrument_key, error)


def _load_catalogue(cfg: DomainConfig) -> list[tuple[str, str]]:
    """All active instruments from the domain's catalogue as (instrument_key, domain)
    tuples for seeding the ledger. Paginated + is_active=true only, plus an optional
    extra column filter (e.g. is_fno_eligible=True for options-intraday, which only
    covers the F&O-eligible subset of the universe, not every stock)."""
    supabase = get_supabase()
    rows: list[tuple[str, str]] = []
    PAGE = 1000
    start = 0
    while True:
        q = (supabase.table(cfg.catalogue_table)
             .select("instrument_key")
             .eq("is_active", True))
        if cfg.extra_filter_column is not None:
            q = q.eq(cfg.extra_filter_column, cfg.extra_filter_value)
        resp = q.range(start, start + PAGE - 1).execute()
        batch = resp.data or []
        rows.extend((r["instrument_key"], cfg.domain) for r in batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("Loaded %d active instrument(s) from %s%s.", len(rows), cfg.catalogue_table,
                f" (filtered {cfg.extra_filter_column}={cfg.extra_filter_value})"
                if cfg.extra_filter_column else "")
    return rows


@dataclass
class _WorkerResult:
    """What a worker thread reports back — the main thread aggregates from this,
    never from shared state touched inside the thread."""
    instrument_key: str
    ok: bool
    bytes_written: int = 0
    error: Optional[str] = None


def _backfill_one(cfg: DomainConfig, ik: str) -> _WorkerResult:
    """Runs on a worker thread: one instrument's full backfill + ledger update,
    isolated try/except so one bad instrument can't take down the run. Returns a
    result for the main thread to fold into RunSummary — does not touch summary
    itself."""
    try:
        progress.mark_attempt(ik, cfg.domain)
        result = backfill_instrument(ik, cfg.domain, timeframes=cfg.timeframes,
                                     from_date=cfg.backfill_from_date)
        if result.ok:
            progress.mark_done(ik, cfg.domain)
            time.sleep(THROTTLE_SECONDS)
            return _WorkerResult(ik, ok=True, bytes_written=result.bytes_written)
        progress.mark_failed(ik, cfg.domain, result.error or "unknown")
        time.sleep(THROTTLE_SECONDS)
        return _WorkerResult(ik, ok=False, error=result.error or "unknown")
    except Exception as exc:  # noqa: BLE001 — isolate one bad instrument from the run
        msg = f"unexpected: {exc}"
        try:
            progress.mark_failed(ik, cfg.domain, msg)
        except Exception:  # noqa: BLE001
            logger.error("Could not mark_failed for %s: %s", ik, exc)
        time.sleep(THROTTLE_SECONDS)
        return _WorkerResult(ik, ok=False, error=msg)


def run_backfill(cfg: DomainConfig, limit: Optional[int] = None) -> RunSummary:
    """
    Backfill OHLCV for all pending instruments in a domain.
      1. Seed the ledger from the catalogue (idempotent; existing rows untouched).
      2. Get the pending work list (status != done) for this domain.
      3. Run each instrument's backfill on a worker thread pool (MAX_WORKERS at
         once); the main thread aggregates results as they complete. One
         instrument failing does NOT abort the run.
    Returns a RunSummary. Safe to re-run: done instruments are skipped by step 2 —
    unaffected by the concurrency change, since selection happens before the pool
    is ever created.

    Completion order is NOT submission order (threads finish whenever they finish)
    — the [i/N] progress numbers in logs count completions, not a fixed sequence.
    """
    summary = RunSummary()

    catalogue = _load_catalogue(cfg)
    progress.seed_instruments(catalogue)

    pending = progress.get_pending(domain=cfg.domain)
    if limit is not None:
        pending = pending[:limit]
    logger.info("Backfilling %d pending %s instrument(s)%s across %d worker(s).",
                len(pending), cfg.domain, f" (limited to {limit})" if limit else "",
                MAX_WORKERS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_backfill_one, cfg, item.instrument_key): item.instrument_key
                   for item in pending}
        for i, future in enumerate(as_completed(futures), start=1):
            ik = futures[future]
            try:
                res = future.result()
            except Exception as exc:  # noqa: BLE001 — defensive backstop; _backfill_one
                                       # already catches internally, so this shouldn't fire
                logger.error("[%d/%d] %s FAILED (worker crashed): %s", i, len(pending), ik, exc)
                summary.attempted += 1
                summary.failed += 1
                summary.failures.append((ik, f"worker crashed: {exc}"))
                continue

            summary.attempted += 1
            if res.ok:
                summary.succeeded += 1
                summary.total_bytes += res.bytes_written
                logger.info("[%d/%d] %s done.", i, len(pending), ik)
            else:
                summary.failed += 1
                summary.failures.append((ik, res.error or "unknown"))
                logger.warning("[%d/%d] %s failed: %s", i, len(pending), ik, res.error)

    return summary


def print_summary(cfg: DomainConfig, summary: RunSummary) -> None:
    logger.info("=" * 60)
    logger.info("%s OHLCV BACKFILL — SUMMARY", cfg.domain.upper())
    logger.info("=" * 60)
    logger.info("  attempted : %d", summary.attempted)
    logger.info("  succeeded : %d", summary.succeeded)
    logger.info("  failed    : %d", summary.failed)
    logger.info("  data written: %.2f MB", summary.total_bytes / 1024 / 1024)
    if summary.failures:
        logger.info("  failures:")
        for ik, err in summary.failures[:20]:
            logger.info("    %-30s %s", ik, err[:70])
        if len(summary.failures) > 20:
            logger.info("    ... and %d more", len(summary.failures) - 20)
    logger.info("  ledger counts: %s", progress.get_counts(domain=cfg.domain))
    logger.info("=" * 60)


def cli_main(cfg: DomainConfig) -> None:
    """Shared CLI entry: --limit N (verify-first) + --quiet. Callers pass their cfg."""
    import argparse
    import os
    from dotenv import load_dotenv

    load_dotenv()
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),                                          # terminal, as before
            logging.FileHandler(f"logs/ohlcv_backfill_{cfg.domain}.log", mode="w"),  # overwritten each run
        ],
    )

    parser = argparse.ArgumentParser(description=f"Bulk {cfg.domain} OHLCV backfill.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N pending instruments (verify-first).")
    parser.add_argument("--quiet", action="store_true",
                        help="Less log noise: per-instrument progress + problems only.")
    args = parser.parse_args()

    if args.quiet:
        for name in ("httpx",
                     "modules.market_data.upstox._ohlcv_engine",
                     "modules.market_data.upstox.ohlcv_store",
                     "modules.market_data.upstox.ohlcv_fetch_progress"):
            logging.getLogger(name).setLevel(logging.WARNING)

    summary = run_backfill(cfg, limit=args.limit)
    print_summary(cfg, summary)
