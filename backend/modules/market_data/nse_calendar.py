"""
modules/market_data/nse_calendar.py

Builds and maintains fortuna_nse_calendar. Two data sources, one module:
  1. NSE holiday-master API -> trading_holiday + clearing_holiday rows
  2. Generated Sat/Sun     -> weekend rows

Entry point: ensure_calendar(year). Each step (holidays / weekends) checks
whether it's already done for that year and SKIPS if so -- so routine
re-runs do no pointless work. (Duplicates are impossible regardless:
trade_date is the PK and we upsert on it. The skip is an efficiency guard,
not a correctness one.)

  type=trading  -> 'trading_holiday'  (market closed, don't trade)
  type=clearing -> 'clearing_holiday' (market open, CAN trade)
  Sat/Sun       -> 'weekend'          (don't trade)

Mid-year NSE circular (a holiday added after our annual run): call with
force=True to re-fetch holidays even if the year already has them.

"See what's available, store what's available": the holiday fetch doesn't
hardcode a year -- it stores whatever years NSE returns. Weekend generation
DOES need an explicit year (you can't derive "which year" from nothing).

NSE blocks plain requests, but browser-like HEADERS alone are sufficient
(confirmed by live test 2026-08-14 -- 200 with no cookies). No cookie-priming.

Fail-loud: fetch failure returns ok=False, leaving existing data untouched
rather than wiping it.

Standards applied: single responsibility, idempotent upsert, cheap skip
guards, defensive parsing, timeouts, structured logging, typed results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta

import requests

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

TABLE_NAME = "fortuna_nse_calendar"

NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master"

# Browser-like headers -- required, and sufficient (no cookies needed).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/resources/exchange-communication-holidays",
    "Connection": "keep-alive",
}

REQUEST_TIMEOUT_SECONDS = 10

# NSE returns holidays keyed by segment; CM = Capital Market (equity), which
# is what Fortuna trades. FO mirrors CM in India, so CM alone suffices.
CM_SEGMENT = "CM"

# NSE date format e.g. "26-Jan-2026"
NSE_DATE_FORMAT = "%d-%b-%Y"


@dataclass
class CalendarSyncResult:
    ok: bool
    trading_holidays_stored: int = 0
    clearing_holidays_stored: int = 0
    weekends_stored: int = 0
    holidays_skipped: bool = False   # true if holidays already present and not forced
    weekends_skipped: bool = False   # true if weekends already present
    years_seen: list[int] = field(default_factory=list)
    error: str | None = None


def _year_has_day_type(year: int, day_types: tuple[str, ...]) -> bool:
    """
    Cheap check: does this year already have rows of the given day_type(s)?
    One bounded query (limit 1). Used to skip redundant work on re-runs.
    """
    supabase = get_supabase()
    resp = (
        supabase.table(TABLE_NAME)
        .select("trade_date")
        .eq("year", year)
        .in_("day_type", list(day_types))
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def _fetch_nse_holidays(holiday_type: str) -> list[dict]:
    """
    Fetch one NSE holiday list ('trading' or 'clearing'). Returns the CM
    segment rows. Raises on network/HTTP failure (caller converts to a
    fail-loud result).
    """
    resp = requests.get(
        NSE_HOLIDAY_URL,
        params={"type": holiday_type},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    rows = data.get(CM_SEGMENT, [])
    logger.info("NSE %s: %d CM rows returned.", holiday_type, len(rows))
    return rows


def _parse_rows(rows: list[dict], day_type: str) -> list[dict]:
    """
    Turn raw NSE rows into calendar table payloads. Skips any row whose date
    can't be parsed rather than aborting the whole batch.
    """
    payloads: list[dict] = []
    for row in rows:
        raw_date = row.get("tradingDate")
        if not raw_date:
            logger.warning("Skipping %s row with no tradingDate: %r", day_type, row)
            continue
        try:
            d = datetime.strptime(raw_date, NSE_DATE_FORMAT).date()
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping unparseable %s date %r: %s", day_type, raw_date, exc)
            continue
        payloads.append({
            "trade_date": d.isoformat(),
            "day_type": day_type,
            "description": row.get("description"),
            "year": d.year,
        })
    return payloads


def _sync_holidays(force: bool = False) -> tuple[int, int, list[int], bool]:
    """
    Fetch + upsert NSE trading/clearing holidays. Skips the network call if
    the CURRENT year already has holiday rows, unless force=True (mid-year
    circular update). Returns (trading_count, clearing_count, years, skipped).
    Raises on fetch/upsert failure (caller converts to fail-loud result).
    """
    current_year = date.today().year
    if not force and _year_has_day_type(current_year, ("trading_holiday", "clearing_holiday")):
        logger.info("Holidays already present for %d, skipping fetch (use force=True to refresh).", current_year)
        return 0, 0, [], True

    clearing_rows = _fetch_nse_holidays("clearing")
    trading_rows = _fetch_nse_holidays("trading")

    clearing_payloads = _parse_rows(clearing_rows, "clearing_holiday")
    trading_payloads = _parse_rows(trading_rows, "trading_holiday")

    supabase = get_supabase()
    # clearing first, then trading (trading wins on any same-date overlap)
    if clearing_payloads:
        supabase.table(TABLE_NAME).upsert(clearing_payloads, on_conflict="trade_date").execute()
    if trading_payloads:
        supabase.table(TABLE_NAME).upsert(trading_payloads, on_conflict="trade_date").execute()

    years = sorted({p["year"] for p in (clearing_payloads + trading_payloads)})
    logger.info("Holidays synced: %d trading, %d clearing, years=%s",
                len(trading_payloads), len(clearing_payloads), years)
    return len(trading_payloads), len(clearing_payloads), years, False


def _generate_weekends(year: int) -> tuple[int, bool]:
    """
    Upsert every Saturday/Sunday of `year` as a 'weekend' row. Skips if the
    year already has weekend rows. Returns (weekends_stored, skipped).
    """
    if _year_has_day_type(year, ("weekend",)):
        logger.info("Weekends already present for %d, skipping generation.", year)
        return 0, True

    payloads: list[dict] = []
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        if d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            payloads.append({
                "trade_date": d.isoformat(),
                "day_type": "weekend",
                "description": None,
                "year": year,
            })
        d += timedelta(days=1)

    if payloads:
        supabase = get_supabase()
        supabase.table(TABLE_NAME).upsert(payloads, on_conflict="trade_date").execute()
    logger.info("Weekends generated for %d: %d rows.", year, len(payloads))
    return len(payloads), False


def ensure_calendar(year: int | None = None, force_holidays: bool = False) -> CalendarSyncResult:
    """
    One entry point: ensure the calendar is populated for `year` (defaults to
    current year). Runs holiday fetch and weekend generation, each skipping
    independently if already done. Fail-loud on any error.

    force_holidays=True re-fetches NSE holidays even if present (mid-year
    circular update).
    """
    year = year or date.today().year
    try:
        t_count, c_count, years, holidays_skipped = _sync_holidays(force=force_holidays)
        w_count, weekends_skipped = _generate_weekends(year)
    except Exception as exc:  # noqa: BLE001
        logger.error("ensure_calendar(%s) failed: %s", year, exc)
        return CalendarSyncResult(ok=False, error=str(exc))

    seen = sorted(set(years) | {year})
    return CalendarSyncResult(
        ok=True,
        trading_holidays_stored=t_count,
        clearing_holidays_stored=c_count,
        weekends_stored=w_count,
        holidays_skipped=holidays_skipped,
        weekends_skipped=weekends_skipped,
        years_seen=seen,
    )
