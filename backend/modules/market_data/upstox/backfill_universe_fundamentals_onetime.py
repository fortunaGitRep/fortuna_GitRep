"""
modules/market_data/upstox/backfill_universe_fundamentals_onetime.py

ONE-TIME archival backfill of the 4 TIER-2 fundamentals endpoints (balance-sheet,
cash-flow, corporate-actions, competitors) for the full stock universe -> the
f_fundamentals_statements JSONB table. The screening 4 endpoints (profile/ratios/
income/holdings -> metrics) are ALREADY done by fetch_universe_fundamentals.py and are
NOT touched here.

WHY one-time + archival: Upstox only serves a rolling ~4 years of history. A company
that's uninteresting today may matter later, and by then its early years will have
rolled off. So we capture every stock's currently-available deep statements NOW, once,
to preserve them. Going forward, a SEPARATE recurring job
(update_universe_fundamentals_qtrly.py, future) will APPEND new periods without
overwriting this archive.

HANDS-OFF (auto-cooldown-and-continue): the fundamentals API rate limit (1000/30min)
means a full run repeatedly exhausts the window. Instead of failing or needing manual
restarts, this job DETECTS sustained rate-limiting (RATE_STREAK stocks in a row all
rate-limited) and AUTO-SLEEPS for RATE_SLEEP (~30 min) to let the window fully reset,
then resumes. Start it once and walk away — it self-navigates every rate wall. Combined
with the resumable ledger, it's fire-and-forget.

Own progress ledger: f_fundamentals_tier2_progress (separate from the screening
ledger, so Tier-2 completion is tracked independently). Keyed by isin.

Standards: orchestration only (delegates to fundamentals_store.store_tier2_statements),
resumable + idempotent, rate-limited stays retryable (never false-failed), structured
logging. Reuses the store's proven fetch/parse; does NOT duplicate or overwrite the
screening backfill code.

Run:
  verify-first:  python -m modules.market_data.upstox.backfill_universe_fundamentals_onetime --limit 3
  full run:      python -m modules.market_data.upstox.backfill_universe_fundamentals_onetime --quiet
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox.fundamentals_store import store_tier2_statements

logger = logging.getLogger(__name__)

_CATALOGUE = "f_universe_instruments"
_PROGRESS = "f_fundamentals_tier2_progress"

BASE_THROTTLE_SECONDS = 1.0        # base pace between stocks
# Per-stock rate handling: try a stock up to 2 times (RATE_RETRY_PAUSE apart). If BOTH
# attempts are rate-limited, the window is exhausted -> sleep RATE_SLEEP (30 min), then
# resume the SAME stock. We do not move on to other stocks while rate-limited.
RATE_RETRY_PAUSE_SECONDS = 10      # wait between a stock's 1st and 2nd attempt
RATE_SLEEP_SECONDS = 30 * 60       # 30 minutes — a full rate-window reset


def _now_ist_iso() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).replace(tzinfo=None).isoformat(timespec="seconds")


@dataclass
class RunSummary:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    rate_limited: int = 0
    auto_sleeps: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


# --- Catalogue + ledger ----------------------------------------------------

def _load_stocks() -> list[tuple[str, str]]:
    """Active EQ stocks as (isin, instrument_key). ETFs already split out of this table."""
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
    logger.info("Loaded %d active stocks from %s.", len(rows), _CATALOGUE)
    return rows


def _seed(rows: list[tuple[str, str]]) -> None:
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
    logger.info("Seeded/ensured %d tier-2 progress rows.", len(payloads))


def _get_pending() -> list[tuple[str, str]]:
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
    get_supabase().table(_PROGRESS).update(
        {"status": "done", "last_success_at": _now_ist_iso(), "last_error": None}
    ).eq("isin", isin).execute()


def _mark_failed(isin: str, error: str) -> None:
    get_supabase().table(_PROGRESS).update(
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


# --- Orchestration with auto-cooldown --------------------------------------

def run(limit: Optional[int] = None) -> RunSummary:
    summary = RunSummary()

    _seed(_load_stocks())
    pending = _get_pending()
    if limit is not None:
        pending = pending[:limit]
    logger.info("Tier-2 archival backfill for %d pending stock(s)%s.",
                len(pending), f" (limited to {limit})" if limit else "")

    i = 0
    while i < len(pending):
        isin, ik = pending[i]
        logger.info("[%d/%d] %s ...", i + 1, len(pending), isin)

        # Per-stock: attempt up to 2 times (10s apart). If BOTH are rate-limited, the
        # window is exhausted -> go straight to the 30-min sleep (do NOT move on to other
        # stocks), then resume THIS same stock. Nothing is skipped.
        stock_done = False
        for attempt in (1, 2):
            summary.attempted += 1
            try:
                _mark_attempt(isin)
                result = store_tier2_statements(isin, ik)
            except Exception as exc:  # noqa: BLE001
                msg = f"unexpected: {exc}"
                try:
                    _mark_failed(isin, msg)
                except Exception:  # noqa: BLE001
                    logger.error("Could not mark_failed for %s: %s", isin, exc)
                summary.failed += 1
                summary.failures.append((isin, msg))
                logger.error("[%d/%d] %s FAILED: %s", i + 1, len(pending), isin, exc)
                stock_done = True   # a genuine error (not rate-limit) -> move on
                break

            if result.ok:
                _mark_done(isin)
                summary.succeeded += 1
                stock_done = True
                break
            if not result.rate_limited:
                # genuine no-data (ETF/dataless) -> mark failed, move on
                _mark_failed(isin, result.error or "unknown")
                summary.failed += 1
                summary.failures.append((isin, result.error or "unknown"))
                stock_done = True
                break

            # rate-limited this attempt
            summary.rate_limited += 1
            if attempt == 1:
                logger.warning("[%d/%d] %s rate-limited (attempt 1/2); pausing %ds then retry.",
                               i + 1, len(pending), isin, RATE_RETRY_PAUSE_SECONDS)
                time.sleep(RATE_RETRY_PAUSE_SECONDS)
                # loop to attempt 2
            else:
                # 2nd rate-limited attempt on THIS stock -> window is spent. Sleep 30 min,
                # then resume this same stock (stays pending, i not advanced).
                summary.auto_sleeps += 1
                logger.warning("[%d/%d] %s rate-limited twice. Auto-sleeping %d min, then "
                               "resuming this stock ... [auto-sleep #%d]",
                               i + 1, len(pending), isin,
                               RATE_SLEEP_SECONDS // 60, summary.auto_sleeps)
                time.sleep(RATE_SLEEP_SECONDS)
                # stock_done stays False -> outer loop retries same i

        if stock_done:
            i += 1
            time.sleep(BASE_THROTTLE_SECONDS)
        # else: rate-limited twice + slept -> retry same i (no advance)

    return summary


def _print_summary(summary: RunSummary) -> None:
    print("\n" + "=" * 60)
    print("TIER-2 FUNDAMENTALS ARCHIVAL BACKFILL — SUMMARY")
    print("=" * 60)
    print(f"  attempted    : {summary.attempted}")
    print(f"  succeeded    : {summary.succeeded}")
    print(f"  failed       : {summary.failed}  (genuine no-data / ETFs)")
    print(f"  rate-limited : {summary.rate_limited}  (retried; left pending if any remain)")
    print(f"  auto-sleeps  : {summary.auto_sleeps}  (30-min waits to clear the rate window)")
    if summary.failures:
        print("\n  first no-data failures:")
        for isin, err in summary.failures[:15]:
            print(f"    {isin:<16} {err[:60]}")
        if len(summary.failures) > 15:
            print(f"    ... and {len(summary.failures) - 15} more")
    print("\n  ledger counts:", _counts())
    print("=" * 60 + "\n")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="One-time Tier-2 fundamentals archival backfill.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N pending stocks (verify-first).")
    parser.add_argument("--quiet", action="store_true",
                        help="Less log noise: per-stock progress + problems only.")
    args = parser.parse_args()

    if args.quiet:
        for name in ("httpx",
                     "modules.market_data.upstox.fundamentals_store",
                     "modules.market_data.upstox.upstox_auth_client"):
            logging.getLogger(name).setLevel(logging.WARNING)

    _print_summary(run(limit=args.limit))
