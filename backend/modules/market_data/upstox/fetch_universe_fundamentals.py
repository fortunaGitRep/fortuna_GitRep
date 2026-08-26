"""
modules/market_data/upstox/fetch_universe_fundamentals.py

Bulk fundamentals fetch for all EQ stocks. Reads f_universe_instruments -> seeds the
f_fundamentals_fetch_progress ledger -> loops pending (mark_attempt -> store_fundamentals
-> mark done/failed). Same resumable/throttled orchestration as the OHLCV backfill; the
per-stock work is store_fundamentals (fetch 8 endpoints, parse, upsert 3 tables).

Scope: all active EQ instruments in f_universe_instruments (~2,643). ETFs are NOT
separately flagged in the catalogue, so they're included and FAIL GRACEFULLY (no
fundamentals -> store returns ok=False -> marked failed). The failed-list therefore
doubles as the ETF/no-fundamentals signal.

SCALE: 8 API calls/stock * ~2,643 = ~21,000 calls — longer than the OHLCV run, spans
several rate-limit windows. Proactive throttle + the auth client's 429/5xx retry handle
it; resumability makes interruptions safe.

Standards: orchestration only (delegates to fundamentals_store), resumable + idempotent,
per-instrument try/except isolation, throttle + retry backstop, --limit (verify-first) +
--quiet. Progress-ledger access is inline here (small, fundamentals-specific) rather than
a separate module.

Run:
  verify-first:  python -m modules.market_data.upstox.fetch_universe_fundamentals --limit 3
  full run:      python -m modules.market_data.upstox.fetch_universe_fundamentals --quiet
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox.fundamentals_store import store_fundamentals

logger = logging.getLogger(__name__)

_CATALOGUE = "f_universe_instruments"
_PROGRESS = "f_fundamentals_fetch_progress"

# Adaptive throttle: a moderate base pace between stocks, and — when we detect the rate
# window is exhausted (a stock came back rate-limited) — a longer cooldown to let it
# reset, instead of hammering 429s. Base ~1.0s keeps us reasonable; the auth client's
# own 429 retry/backoff sits underneath. On true exhaustion we sleep RATE_COOLDOWN.
BASE_THROTTLE_SECONDS = 1.0
RATE_COOLDOWN_SECONDS = 60.0


def _now_ist_iso() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).replace(tzinfo=None).isoformat(timespec="seconds")


@dataclass
class RunSummary:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    rate_limited: int = 0    # stayed retryable (429), NOT counted as no-data failures
    failures: list[tuple[str, str]] = field(default_factory=list)


# --- Catalogue + ledger ----------------------------------------------------

def _load_eq_stocks() -> list[tuple[str, str]]:
    """Active EQ instruments as (isin, instrument_key). Paginated. Skips rows with no
    ISIN (shouldn't happen for EQ, but defensive)."""
    supabase = get_supabase()
    rows: list[tuple[str, str]] = []
    PAGE = 1000
    start = 0
    while True:
        resp = (supabase.table(_CATALOGUE)
                .select("isin, instrument_key")
                .eq("is_active", True)
                .eq("instrument_type", "EQ")
                .range(start, start + PAGE - 1)
                .execute())
        batch = resp.data or []
        for r in batch:
            if r.get("isin") and r.get("instrument_key"):
                rows.append((r["isin"], r["instrument_key"]))
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("Loaded %d active EQ instruments from %s.", len(rows), _CATALOGUE)
    return rows


def _seed(rows: list[tuple[str, str]]) -> None:
    """Ensure a progress row per stock (idempotent; existing rows untouched)."""
    if not rows:
        return
    supabase = get_supabase()
    payloads = [{"isin": isin, "instrument_key": ik, "status": "pending"}
                for isin, ik in rows]
    CHUNK = 500
    for i in range(0, len(payloads), CHUNK):
        supabase.table(_PROGRESS).upsert(
            payloads[i:i + CHUNK], on_conflict="isin", ignore_duplicates=True
        ).execute()
    logger.info("Seeded/ensured %d fundamentals progress rows.", len(payloads))


def _get_pending() -> list[tuple[str, str]]:
    """(isin, instrument_key) for status != done. Paginated."""
    supabase = get_supabase()
    out: list[tuple[str, str]] = []
    PAGE = 1000
    start = 0
    while True:
        resp = (supabase.table(_PROGRESS)
                .select("isin, instrument_key, status")
                .in_("status", ["pending", "failed"])
                .range(start, start + PAGE - 1)
                .execute())
        batch = resp.data or []
        out.extend((r["isin"], r["instrument_key"]) for r in batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return out


def _mark_attempt(isin: str) -> None:
    supabase = get_supabase()
    resp = (supabase.table(_PROGRESS).select("attempt_count")
            .eq("isin", isin).limit(1).execute())
    current = resp.data[0]["attempt_count"] if resp.data else 0
    supabase.table(_PROGRESS).update(
        {"attempt_count": current + 1, "last_attempt_at": _now_ist_iso()}
    ).eq("isin", isin).execute()


def _mark_done(isin: str) -> None:
    supabase = get_supabase()
    supabase.table(_PROGRESS).update(
        {"status": "done", "last_success_at": _now_ist_iso(), "last_error": None}
    ).eq("isin", isin).execute()


def _mark_failed(isin: str, error: str) -> None:
    supabase = get_supabase()
    supabase.table(_PROGRESS).update(
        {"status": "failed", "last_error": (error or "")[:1000]}
    ).eq("isin", isin).execute()


def _counts() -> dict:
    supabase = get_supabase()
    out = {"pending": 0, "done": 0, "failed": 0}
    for s in ("pending", "done", "failed"):
        r = supabase.table(_PROGRESS).select("isin", count="exact").eq("status", s).execute()
        out[s] = r.count or 0
    out["total"] = sum(out.values())
    return out


# --- Orchestration ---------------------------------------------------------

def run(limit: Optional[int] = None, screening_only: bool = True) -> RunSummary:
    summary = RunSummary()

    _seed(_load_eq_stocks())
    pending = _get_pending()
    if limit is not None:
        pending = pending[:limit]
    logger.info("Fetching fundamentals for %d pending stock(s)%s [%s].",
                len(pending), f" (limited to {limit})" if limit else "",
                "screening-only (4 endpoints)" if screening_only else "all 8 endpoints")

    for i, (isin, ik) in enumerate(pending, start=1):
        summary.attempted += 1
        logger.info("[%d/%d] %s ...", i, len(pending), isin)
        cooldown = False
        try:
            _mark_attempt(isin)
            result = store_fundamentals(isin, ik, write=True, screening_only=screening_only)
            if result.ok:
                _mark_done(isin)
                summary.succeeded += 1
            elif result.rate_limited:
                # Rate-limited: DO NOT mark failed (that would pollute the ETF signal).
                # Leave it pending (reset any attempt bump is unnecessary) so it retries.
                # Trigger a cooldown to let the rate window recover before continuing.
                summary.rate_limited += 1
                cooldown = True
                logger.warning("[%d/%d] %s rate-limited; left pending for retry.",
                               i, len(pending), isin)
            else:
                _mark_failed(isin, result.error or "unknown")
                summary.failed += 1
                summary.failures.append((isin, result.error or "unknown"))
        except Exception as exc:  # noqa: BLE001 — isolate one bad stock from the run
            msg = f"unexpected: {exc}"
            try:
                _mark_failed(isin, msg)
            except Exception:  # noqa: BLE001
                logger.error("Could not mark_failed for %s: %s", isin, exc)
            summary.failed += 1
            summary.failures.append((isin, msg))
            logger.error("[%d/%d] %s FAILED: %s", i, len(pending), isin, exc)

        # Adaptive pacing: normal gap, or a longer cooldown after rate exhaustion.
        if cooldown:
            logger.warning("Rate cooldown %.0fs to let the window recover ...",
                           RATE_COOLDOWN_SECONDS)
            time.sleep(RATE_COOLDOWN_SECONDS)
        else:
            time.sleep(BASE_THROTTLE_SECONDS)

    return summary


def _print_summary(summary: RunSummary) -> None:
    print("\n" + "=" * 60)
    print("UNIVERSE FUNDAMENTALS FETCH — SUMMARY")
    print("=" * 60)
    print(f"  attempted    : {summary.attempted}")
    print(f"  succeeded    : {summary.succeeded}")
    print(f"  failed       : {summary.failed}  (genuine no-data / ETFs)")
    print(f"  rate-limited : {summary.rate_limited}  (left pending — re-run to retry)")
    if summary.failures:
        print("\n  first no-data failures (isin -> reason):")
        for isin, err in summary.failures[:15]:
            print(f"    {isin:<16} {err[:60]}")
        if len(summary.failures) > 15:
            print(f"    ... and {len(summary.failures) - 15} more")
    print("\n  ledger counts:", _counts())
    if summary.rate_limited:
        print("\n  NOTE: rate-limited stocks stayed 'pending' — re-run the same command")
        print("        to fetch them once the rate window has recovered.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Bulk fundamentals fetch (EQ stocks).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N pending stocks (verify-first).")
    parser.add_argument("--quiet", action="store_true",
                        help="Less log noise: per-stock progress + problems only.")
    parser.add_argument("--all-endpoints", action="store_true",
                        help="Fetch all 8 endpoints incl Tier-2 statements archive "
                             "(default: screening-only, 4 endpoints — faster).")
    args = parser.parse_args()

    if args.quiet:
        for name in ("httpx",
                     "modules.market_data.upstox.fundamentals_store",
                     "modules.market_data.upstox.upstox_auth_client"):
            logging.getLogger(name).setLevel(logging.WARNING)

    _print_summary(run(limit=args.limit, screening_only=not args.all_endpoints))
