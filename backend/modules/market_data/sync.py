"""
modules/market_data/sync.py

Keeps the three Fortuna index tables (VIX, Nifty, GIFT) current. Two distinct
entry points with different jobs and frequencies -- this separation is the
whole point (per Ash's design):

  backfill_and_verify(index_key)   -- run ONCE per index, at setup.
      Backfills ~1 year of history, then does a FULL integrity check:
      stored dates must equal the calendar's expected trading days for the
      range. Once this passes, the historical data is trusted and frozen --
      never re-verified. This is the expensive, thorough check.

  sync_daily(index_key)            -- run EVERY trading day.
      Cheap: reads max stored date, fetches only the missing days, upserts,
      then verifies ONLY the newly-added days landed. Never re-checks the
      backfilled history -- that was already verified once and is trusted.

Why two functions, not one with a flag: the daily path must stay cheap and
must NOT re-doubt old data every morning. Ash's explicit requirement: verify
the backfill thoroughly once, then only ever add new days cleanly.

Correctness foundations this builds on:
  - IST-correct dates from indices.py (epoch_to_ist_date)
  - idempotent upserts on trade_date PK (index_store)
  - calendar's expected-trading-days (nse_calendar) as the integrity oracle

Standards applied: single responsibility per function, DRY (one path for 3
indices), defensive verification (never trust the write landed), graceful
per-index isolation (one index failing doesn't abort the others), structured
logging, typed results. Fail-loud: integrity failures are surfaced in the
result, never swallowed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .indices import fetch_daily, FetchResult, Candle
from .index_store import (
    DailyBar, upsert_bars, get_max_trade_date, get_stored_dates, TABLE_CONFIG,
)
from .nse_calendar import get_expected_trading_days, get_calendar_coverage_start

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# ~1 trading year for the VIX percentile window (250 trading days ~= 365
# calendar days after weekends/holidays).
BACKFILL_DAYS = 365

# Extra days added to a gap fetch so a weekend/holiday boundary can't leave
# the most recent bar just out of range.
GAP_PADDING_DAYS = 5


@dataclass
class SyncResult:
    index_key: str
    action: str          # "backfilled" | "gap_filled" | "already_current" | "failed"
    ok: bool
    rows_written: int = 0
    max_date_before: date | None = None
    max_date_after: date | None = None
    integrity_ok: bool | None = None      # result of the date-set check (None if not run)
    missing_dates: list[date] = field(default_factory=list)
    error: str | None = None


def _candles_to_bars(candles: list[Candle]) -> list[DailyBar]:
    """Map fetch-layer Candles to store-layer DailyBars, dropping any dateless
    candle defensively (indices.py should already have skipped those)."""
    bars: list[DailyBar] = []
    for c in candles:
        if c.trade_date is None:
            continue
        bars.append(DailyBar(
            trade_date=c.trade_date, close=c.close,
            open=c.open, high=c.high, low=c.low,
        ))
    return bars


def _integrity_check(index_key: str, from_date: date, to_date: date) -> tuple[bool, list[date]]:
    """
    Compare what we STORED against what SHOULD exist (calendar's expected
    trading days) for the checkable range. Returns (ok, sorted_missing_dates).
    ok = True means every expected trading day is present in storage.

    Clamps the check to the calendar's coverage floor: the calendar only holds
    years NSE's API served (currently 2026), so dates before that can't be
    validated -- that data is still stored and used, just not calendar-checked.
    A check whose entire range is below the floor returns ok=True with no
    missing dates (nothing checkable, nothing to fail).
    """
    coverage_start = get_calendar_coverage_start()
    if coverage_start is not None and from_date < coverage_start:
        from_date = coverage_start
    if from_date > to_date:
        # Entire requested range predates calendar coverage -- nothing to check.
        return True, []

    expected = get_expected_trading_days(from_date, to_date)
    stored = get_stored_dates(index_key, from_date, to_date)
    missing = sorted(expected - stored)
    return (len(missing) == 0), missing


# ---------------------------------------------------------------------------
# Entry point 1 -- backfill_and_verify (run ONCE per index)
# ---------------------------------------------------------------------------

def backfill_and_verify(index_key: str) -> SyncResult:
    """
    One-time setup for an index: pull ~1 year of history, then fully verify it
    against the calendar's expected trading days. After this passes, the daily
    path trusts the history and never re-checks it.
    """
    if index_key not in TABLE_CONFIG:
        raise KeyError(f"Unknown index '{index_key}'. Known: {sorted(TABLE_CONFIG)}")

    max_before = get_max_trade_date(index_key)

    result: FetchResult = fetch_daily(index_key, lookback_days=BACKFILL_DAYS)
    if not result.ok:
        return SyncResult(index_key, action="failed", ok=False,
                          max_date_before=max_before,
                          error=f"backfill fetch failed: {result.error}")

    bars = _candles_to_bars(result.candles)
    if not bars:
        return SyncResult(index_key, action="failed", ok=False,
                          max_date_before=max_before,
                          error="backfill returned no usable candles")

    try:
        rows = upsert_bars(index_key, bars)
        max_after = get_max_trade_date(index_key)
    except Exception as exc:  # noqa: BLE001
        logger.error("backfill_and_verify(%s): write failed: %s", index_key, exc)
        return SyncResult(index_key, action="failed", ok=False,
                          max_date_before=max_before, error=f"write failed: {exc}")

    # Full integrity check across the backfilled range.
    from_date = min(b.trade_date for b in bars)
    to_date = max(b.trade_date for b in bars)
    integrity_ok, missing = _integrity_check(index_key, from_date, to_date)

    if not integrity_ok:
        logger.error("backfill_and_verify(%s): INTEGRITY FAIL, missing %d days: %s",
                     index_key, len(missing), missing[:10])

    return SyncResult(
        index_key, action="backfilled", ok=integrity_ok, rows_written=rows,
        max_date_before=max_before, max_date_after=max_after,
        integrity_ok=integrity_ok, missing_dates=missing,
        error=None if integrity_ok else f"integrity check failed: {len(missing)} missing trading days",
    )


# ---------------------------------------------------------------------------
# Entry point 2 -- sync_daily (run EVERY trading day)
# ---------------------------------------------------------------------------

def sync_daily(index_key: str) -> SyncResult:
    """
    Cheap daily incremental. Adds only the days missing since the last stored
    date, verifies ONLY those new days landed, and trusts all older history
    (already verified once by backfill_and_verify). Does NOT re-scan the whole
    table.
    """
    if index_key not in TABLE_CONFIG:
        raise KeyError(f"Unknown index '{index_key}'. Known: {sorted(TABLE_CONFIG)}")

    try:
        max_before = get_max_trade_date(index_key)
    except Exception as exc:  # noqa: BLE001
        return SyncResult(index_key, action="failed", ok=False,
                          error=f"max-date read failed: {exc}")

    # Guard: daily path assumes backfill already happened. If the table is
    # empty, refuse rather than silently doing a partial fetch -- fail loud.
    if max_before is None:
        return SyncResult(index_key, action="failed", ok=False,
                          error="table empty -- run backfill_and_verify first")

    today_ist = datetime.now(IST).date()

    # Already current? (stored max >= today means nothing newer exists to
    # fetch; weekends/holidays naturally produce no new bar.)
    if max_before >= today_ist:
        return SyncResult(index_key, action="already_current", ok=True,
                          max_date_before=max_before, max_date_after=max_before,
                          integrity_ok=True)

    # Fetch a window covering the gap (+ padding for weekend/holiday edges).
    gap_days = (today_ist - max_before).days + GAP_PADDING_DAYS
    result = fetch_daily(index_key, lookback_days=gap_days)
    if not result.ok:
        return SyncResult(index_key, action="failed", ok=False,
                          max_date_before=max_before,
                          error=f"gap fetch failed: {result.error}")

    # Only the bars strictly newer than what we already have.
    new_bars = [b for b in _candles_to_bars(result.candles) if b.trade_date > max_before]

    if not new_bars:
        # Fetch succeeded but nothing newer -- e.g. run on a holiday/weekend.
        # Normal, correct "nothing to do", not a failure.
        return SyncResult(index_key, action="already_current", ok=True,
                          max_date_before=max_before, max_date_after=max_before,
                          integrity_ok=True)

    try:
        rows = upsert_bars(index_key, new_bars)
        max_after = get_max_trade_date(index_key)
    except Exception as exc:  # noqa: BLE001
        logger.error("sync_daily(%s): write failed: %s", index_key, exc)
        return SyncResult(index_key, action="failed", ok=False,
                          max_date_before=max_before, error=f"write failed: {exc}")

    # Verify ONLY the newly-added range (cheap -- not the whole history).
    from_date = min(b.trade_date for b in new_bars)
    to_date = max(b.trade_date for b in new_bars)
    integrity_ok, missing = _integrity_check(index_key, from_date, to_date)

    if not integrity_ok:
        logger.error("sync_daily(%s): new-day integrity FAIL, missing: %s", index_key, missing)

    return SyncResult(
        index_key, action="gap_filled", ok=integrity_ok, rows_written=rows,
        max_date_before=max_before, max_date_after=max_after,
        integrity_ok=integrity_ok, missing_dates=missing,
        error=None if integrity_ok else f"new-day integrity failed: {missing}",
    )


# ---------------------------------------------------------------------------
# Convenience wrappers over all three indices (per-index isolation)
# ---------------------------------------------------------------------------

ALL_INDICES = ("INDIA_VIX", "NIFTY_50", "GIFT_NIFTY")


def backfill_and_verify_all() -> dict[str, SyncResult]:
    """Run the one-time backfill+verify for all three indices. One index
    failing does not abort the others."""
    return {k: backfill_and_verify(k) for k in ALL_INDICES}


def sync_daily_all() -> dict[str, SyncResult]:
    """Run the daily incremental for all three indices, isolated per index."""
    return {k: sync_daily(k) for k in ALL_INDICES}
