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
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox import ohlcv_fetch_progress as progress
from modules.market_data.upstox.ohlcv_store import backfill_instrument

logger = logging.getLogger(__name__)

# Proactive pace between instruments (seconds). Keeps us under Upstox limits
# (25/sec, 250/min, 1000/30min); the engine's retry/backoff handles any 429 that
# still slips through. Same value proven on the 139-index run.
THROTTLE_SECONDS = 0.25


@dataclass(frozen=True)
class DomainConfig:
    """The only things that differ between domains."""
    domain: str                 # 'indices' | 'universe'
    catalogue_table: str        # supabase table listing this domain's instruments


@dataclass
class RunSummary:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    total_bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (instrument_key, error)


def _load_catalogue(cfg: DomainConfig) -> list[tuple[str, str]]:
    """All active instruments from the domain's catalogue as (instrument_key, domain)
    tuples for seeding the ledger. Paginated + is_active=true only."""
    supabase = get_supabase()
    rows: list[tuple[str, str]] = []
    PAGE = 1000
    start = 0
    while True:
        resp = (supabase.table(cfg.catalogue_table)
                .select("instrument_key")
                .eq("is_active", True)
                .range(start, start + PAGE - 1)
                .execute())
        batch = resp.data or []
        rows.extend((r["instrument_key"], cfg.domain) for r in batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("Loaded %d active instrument(s) from %s.", len(rows), cfg.catalogue_table)
    return rows


def run_backfill(cfg: DomainConfig, limit: Optional[int] = None) -> RunSummary:
    """
    Backfill OHLCV for all pending instruments in a domain.
      1. Seed the ledger from the catalogue (idempotent; existing rows untouched).
      2. Get the pending work list (status != done) for this domain.
      3. For each (optionally capped by `limit`): mark_attempt → backfill → mark
         done/failed. One instrument failing does NOT abort the run.
    Returns a RunSummary. Safe to re-run: done instruments are skipped by step 2.
    """
    summary = RunSummary()

    catalogue = _load_catalogue(cfg)
    progress.seed_instruments(catalogue)

    pending = progress.get_pending(domain=cfg.domain)
    if limit is not None:
        pending = pending[:limit]
    logger.info("Backfilling %d pending %s instrument(s)%s.",
                len(pending), cfg.domain, f" (limited to {limit})" if limit else "")

    for i, item in enumerate(pending, start=1):
        ik = item.instrument_key
        summary.attempted += 1
        logger.info("[%d/%d] %s ...", i, len(pending), ik)
        try:
            progress.mark_attempt(ik)
            result = backfill_instrument(ik, cfg.domain)
            if result.ok:
                progress.mark_done(ik)
                summary.succeeded += 1
                summary.total_bytes += result.bytes_written
            else:
                progress.mark_failed(ik, result.error or "unknown")
                summary.failed += 1
                summary.failures.append((ik, result.error or "unknown"))
        except Exception as exc:  # noqa: BLE001 — isolate one bad instrument from the run
            msg = f"unexpected: {exc}"
            try:
                progress.mark_failed(ik, msg)
            except Exception:  # noqa: BLE001
                logger.error("Could not mark_failed for %s: %s", ik, exc)
            summary.failed += 1
            summary.failures.append((ik, msg))
            logger.error("[%d/%d] %s FAILED: %s", i, len(pending), ik, exc)

        time.sleep(THROTTLE_SECONDS)

    return summary


def print_summary(cfg: DomainConfig, summary: RunSummary) -> None:
    print("\n" + "=" * 60)
    print(f"{cfg.domain.upper()} OHLCV BACKFILL — SUMMARY")
    print("=" * 60)
    print(f"  attempted : {summary.attempted}")
    print(f"  succeeded : {summary.succeeded}")
    print(f"  failed    : {summary.failed}")
    print(f"  data written: {summary.total_bytes/1024/1024:.2f} MB")
    if summary.failures:
        print("\n  failures:")
        for ik, err in summary.failures[:20]:
            print(f"    {ik:<30} {err[:70]}")
        if len(summary.failures) > 20:
            print(f"    ... and {len(summary.failures) - 20} more")
    print("\n  ledger counts:", progress.get_counts())
    print("=" * 60 + "\n")


def cli_main(cfg: DomainConfig) -> None:
    """Shared CLI entry: --limit N (verify-first) + --quiet. Callers pass their cfg."""
    import argparse
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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
