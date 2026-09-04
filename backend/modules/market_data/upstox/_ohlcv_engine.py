"""
modules/market_data/upstox/_ohlcv_engine.py

Shared OHLCV fetch core for all three domains (universe stocks, indices, Nifty 50).
Given an instrument_key + unit/interval + date range, it calls Upstox's V3
Historical Candle API, parses the response, and returns normalised candles. It
knows NOTHING about storage, tables, or which domain is calling — callers
(fetch_index_ohlcv / fetch_universe_ohlcv) layer those concerns on top.

>>> INCREMENT 2.2 (this version): PAGINATION + MULTI-TIMEFRAME, still print-only. <<<
Adds fetch_full_history() which loops fetch_candles() across the per-call date-range
limits to pull a full date range for one unit, and fetch_all_timeframes() which pulls
1D/1W/1Mo for one instrument. Still NO Parquet write (2.3), NO status tracking (2.4).
The __main__ block now pulls FULL history (2000->today) for one instrument across all
three timeframes and prints a per-timeframe summary — proving the pagination math
against the real API limits.

Design notes / ADR:
  - API: Upstox V3 Historical Candle.
      GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
    Response: data.candles = array of arrays, each:
      [timestamp_iso, open, high, low, close, volume, open_interest]
    Timestamp is ISO-8601 WITH IST offset ('2025-01-01T00:00:00+05:30') — so unlike
    the Dhan side (epoch seconds needing manual IST conversion), we parse the offset
    directly and take .date() / keep the datetime. No timezone guesswork.
  - Per-call retrieval limits (from V3 docs, drive pagination in 2.2, NOT this file):
      days=1   -> 1 decade/call,  history from 2000
      weeks=1  -> no limit,       history from 2000
      months=1 -> no limit,       history from 2000
      minutes 1-15 -> 1 month/call; minutes >15 & hours -> 1 quarter/call; from 2022
    Exceeding a limit returns an error (UDAPI1148 invalid date range), so 2.2's
    chunking must respect these. 2.1 just uses a short window that's safely inside them.
  - Auth: uses request_get() from upstox_auth_client (shared authed session + retry/
    backoff). The historical endpoint DOES require the Bearer token (unlike the public
    instrument file).
  - This module is a pure fetch/parse function returning typed candles + an ok flag —
    same FetchResult(ok=...) shape as the Dhan indices.py, so callers degrade
    gracefully rather than catching exceptions.

Standards applied: single responsibility (fetch+parse only), defensive parsing
(tolerate short/malformed candle arrays), graceful errors (ok flag, no raise for
expected failures), structured logging (no secrets), typed results.
Deferred: pagination (2.2), Parquet write (2.3), status tracking (2.4), the
per-domain callers (2.5+).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from modules.market_data.upstox.upstox_auth_client import request_get

logger = logging.getLogger(__name__)

# --- Config ----------------------------------------------------------------

# V3 historical candle path template (values are path segments, not query params).
_HIST_PATH = "/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}"

# Valid units per the V3 docs. interval is '1' for days/weeks/months; 1-300 for
# minutes; 1-5 for hours. 2.1 only exercises days=1.
VALID_UNITS = {"minutes", "hours", "days", "weeks", "months"}


@dataclass
class Candle:
    """One OHLCV(+OI) bar. `ts` is the candle start time as a timezone-aware
    datetime (IST offset from the API). trade_date is its calendar date."""
    ts: datetime
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    open_interest: Optional[float] = None


@dataclass
class OhlcvFetchResult:
    """Normalised fetch result. `ok` is the single flag callers check. Candles
    are returned in whatever order the API gave them (we sort at storage time)."""
    instrument_key: str
    unit: str
    interval: str
    ok: bool
    candles: list[Candle] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def count(self) -> int:
        return len(self.candles)


def _parse_candles(raw: dict) -> list[Candle]:
    """
    Defensively turn the V3 response into Candle objects. Each candle is an array:
      [0] timestamp ISO str, [1] open, [2] high, [3] low, [4] close,
      [5] volume, [6] open_interest
    A single malformed row is skipped + logged, never kills the whole parse.
    """
    data = raw.get("data") or {}
    rows = data.get("candles") or []
    candles: list[Candle] = []
    for i, row in enumerate(rows):
        try:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                raise ValueError(f"row too short: {row!r}")
            ts = datetime.fromisoformat(row[0])          # handles the +05:30 offset
            candles.append(Candle(
                ts=ts,
                trade_date=ts.date(),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]) if len(row) > 5 and row[5] is not None else None,
                open_interest=float(row[6]) if len(row) > 6 and row[6] is not None else None,
            ))
        except (TypeError, ValueError, IndexError) as exc:
            logger.warning("Skipping malformed candle at index %d: %s", i, exc)
            continue
    return candles


def fetch_candles(
    instrument_key: str,
    unit: str,
    interval: str,
    from_date: date,
    to_date: date,
) -> OhlcvFetchResult:
    """
    Single V3 historical-candle call for one instrument + unit/interval + date
    window. Returns OhlcvFetchResult(ok=...). Never raises for expected failure
    modes (network, API error, empty) — returns ok=False with a message instead.

    2.1 SCOPE: one call only. The caller must keep [from_date, to_date] inside the
    unit's per-call retrieval limit (2.2 adds the chunking that guarantees this).

    Programmer error (bad unit) DOES raise — that's a bug to fix.
    """
    if unit not in VALID_UNITS:
        raise ValueError(f"Invalid unit '{unit}'. Valid: {sorted(VALID_UNITS)}")
    if to_date < from_date:
        return OhlcvFetchResult(
            instrument_key, unit, interval, ok=False,
            error=f"to_date {to_date} < from_date {from_date}",
        )

    # Path parameters, in the order the V3 route expects: .../unit/interval/to/from
    path = _HIST_PATH.format(
        instrument_key=instrument_key,
        unit=unit,
        interval=interval,
        to_date=to_date.isoformat(),
        from_date=from_date.isoformat(),
    )

    try:
        resp = request_get(path)
    except Exception as exc:  # noqa: BLE001 — request_get already retried transient errors
        logger.error("OHLCV fetch failed for %s %s/%s: %s",
                     instrument_key, unit, interval, exc)
        return OhlcvFetchResult(instrument_key, unit, interval, ok=False,
                                error=f"request failed: {exc}")

    if resp.status_code != 200:
        return OhlcvFetchResult(
            instrument_key, unit, interval, ok=False,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    try:
        body = resp.json()
    except ValueError:
        return OhlcvFetchResult(instrument_key, unit, interval, ok=False,
                                error="200 but body was not JSON")

    if body.get("status") != "success":
        return OhlcvFetchResult(instrument_key, unit, interval, ok=False,
                                error=f"status != success: {str(body)[:200]}")

    candles = _parse_candles(body)
    if not candles:
        # Not necessarily an error (e.g. a holiday-only window), but flag it.
        return OhlcvFetchResult(instrument_key, unit, interval, ok=False,
                                error="no candles in response (empty window?)")

    logger.info("Fetched %d %s/%s candles for %s (%s..%s).",
                len(candles), unit, interval, instrument_key,
                from_date.isoformat(), to_date.isoformat())
    return OhlcvFetchResult(instrument_key, unit, interval, ok=True, candles=candles)


# --- Pagination (2.2) ------------------------------------------------------
# Per-call retrieval limits from the V3 docs. We express each as an approximate
# max span in DAYS per call and walk the window backwards from to_date in chunks
# no larger than that. days=1 is the important paginated case (1 decade/call over
# ~26 years of history); weeks/months have no limit (one call), and intraday
# units chunk tightest. History-start floors prevent asking before data exists.

# Earliest date data exists, by unit (V3 docs).
_HISTORY_START = {
    "days": date(2000, 1, 1),
    "weeks": date(2000, 1, 1),
    "months": date(2000, 1, 1),
    "minutes": date(2022, 1, 1),
    "hours": date(2022, 1, 1),
}

# Max span per single call, in days (approximate, deliberately UNDER the real
# limit to stay safely inside it). None = no limit (one call fetches everything).
def _max_span_days(unit: str, interval: str) -> Optional[int]:
    if unit in ("weeks", "months"):
        return None                      # no limit
    if unit == "days":
        return 3650                      # ~1 decade
    if unit == "hours":
        return 85                        # ~1 quarter (safety under 90)
    if unit == "minutes":
        iv = int(interval)
        return 28 if iv <= 15 else 85    # 1 month (<=15m) else ~1 quarter
    return 28                            # conservative fallback


def fetch_full_history(
    instrument_key: str,
    unit: str,
    interval: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> OhlcvFetchResult:
    """
    Fetch a full date range for one unit/interval by paginating in chunks that
    respect the per-call retrieval limit. Walks BACKWARD from to_date to from_date.
    from_date defaults to the unit's history-start (2000 or 2022); to_date defaults
    to today. Aggregates all chunks into one OhlcvFetchResult, de-duplicated by
    timestamp and sorted oldest-first.

    ok=True if at least one chunk returned candles. Partial success (some chunks
    empty, e.g. pre-listing years) is still ok — empties are skipped, not fatal.
    """
    if unit not in VALID_UNITS:
        raise ValueError(f"Invalid unit '{unit}'. Valid: {sorted(VALID_UNITS)}")

    hist_start = _HISTORY_START.get(unit, date(2000, 1, 1))
    start = max(from_date or hist_start, hist_start)
    end = to_date or date.today()
    if end < start:
        return OhlcvFetchResult(instrument_key, unit, interval, ok=False,
                                error=f"end {end} < start {start}")

    span = _max_span_days(unit, interval)

    # Collect chunks. dict keyed by ISO timestamp for dedup across chunk edges.
    by_ts: dict[str, Candle] = {}
    any_ok = False
    errors: list[str] = []

    if span is None:
        # No limit — single call for the whole range.
        chunks = [(start, end)]
    else:
        chunks = []
        chunk_to = end
        while chunk_to >= start:
            chunk_from = max(start, chunk_to - timedelta(days=span))
            chunks.append((chunk_from, chunk_to))
            chunk_to = chunk_from - timedelta(days=1)

    for chunk_from, chunk_to in chunks:
        res = fetch_candles(instrument_key, unit, interval, chunk_from, chunk_to)
        if res.ok:
            any_ok = True
            for c in res.candles:
                by_ts[c.ts.isoformat()] = c
        else:
            # Empty windows (pre-listing) come back ok=False "no candles" — that's
            # expected as we page past the instrument's inception; record but
            # don't abort. A real error (auth/HTTP) is also captured here.
            errors.append(f"[{chunk_from}..{chunk_to}] {res.error}")

    if not any_ok:
        return OhlcvFetchResult(
            instrument_key, unit, interval, ok=False,
            error=f"no candles across {len(chunks)} chunk(s); "
                  f"first error: {errors[0] if errors else 'unknown'}",
        )

    candles = sorted(by_ts.values(), key=lambda c: c.ts)
    logger.info("Full history %s %s/%s: %d candles across %d chunk(s), %s..%s.",
                instrument_key, unit, interval, len(candles), len(chunks),
                candles[0].trade_date.isoformat(), candles[-1].trade_date.isoformat())
    return OhlcvFetchResult(instrument_key, unit, interval, ok=True, candles=candles)


# Tier-1 timeframes: (unit, interval) pairs. These are what every instrument gets.
TIER1_TIMEFRAMES: tuple[tuple[str, str], ...] = (
    ("days", "1"),
    ("weeks", "1"),
    ("months", "1"),
)

# Intraday timeframes — options-eligible stocks only (see build-log 2026-09-04).
# 5m/15m/60m: enough resolution for intraday indicator screening without the row
# volume 1-minute would add for comparatively little screening value.
INTRADAY_TIMEFRAMES: tuple[tuple[str, str], ...] = (
    ("minutes", "5"),
    ("minutes", "15"),
    ("minutes", "60"),
)


def fetch_all_timeframes(
    instrument_key: str,
    timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict[str, OhlcvFetchResult]:
    """
    Fetch full history for one instrument across several timeframes. Returns a dict
    keyed by a short label ('1d'/'1w'/'1mo'/...) -> OhlcvFetchResult. Each timeframe
    is independent: one failing doesn't stop the others.
    """
    label_map = {("days", "1"): "1d", ("weeks", "1"): "1w", ("months", "1"): "1mo",
                ("minutes", "5"): "5m", ("minutes", "15"): "15m", ("minutes", "60"): "60m"}
    out: dict[str, OhlcvFetchResult] = {}
    for unit, interval in timeframes:
        label = label_map.get((unit, interval), f"{unit}{interval}")
        out[label] = fetch_full_history(instrument_key, unit, interval,
                                        from_date=from_date, to_date=to_date)
    return out


# --- Increment 2.2 manual spike: full history, all timeframes, one instrument -

if __name__ == "__main__":
    #   python -m modules.market_data.upstox._ohlcv_engine
    # Pulls FULL history (2000->today) for Nifty 50 across 1D/1W/1Mo and prints a
    # per-timeframe summary. Verifies the pagination math against the real API
    # per-call limits (daily pages in ~decade chunks; weekly/monthly single call).
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    test_key = "NSE_INDEX|Nifty 50"

    print("\n" + "=" * 64)
    print("OHLCV ENGINE — INCREMENT 2.2 (full history, all timeframes, print only)")
    print("=" * 64)
    print(f"Instrument : {test_key}")
    print("Pulling full history (since 2000) for 1D / 1W / 1Mo ...\n")

    results = fetch_all_timeframes(test_key)

    for label, res in results.items():
        print("-" * 64)
        if not res.ok:
            print(f"  {label:<4} FAIL -- {res.error}")
            continue
        first, last = res.candles[0], res.candles[-1]
        print(f"  {label:<4} OK  {res.count:>6,} candles  "
              f"{first.trade_date.isoformat()} .. {last.trade_date.isoformat()}")
        # show the 3 oldest + 3 newest so we can eyeball both ends
        print(f"       oldest: {first.trade_date} O={first.open:.2f} C={first.close:.2f}")
        print(f"       newest: {last.trade_date} O={last.open:.2f} C={last.close:.2f}")
    print("=" * 64 + "\n")
