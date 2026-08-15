"""
modules/market_data/indices.py

Dhan historical-data fetches for the three indices Module_F_Global_Gate_Funnel
needs: NIFTY 50, India VIX, and (unverified) GIFT Nifty.

Design notes / ADR:
  - This is a read-only data-access layer. It has one responsibility: fetch
    daily index candles from Dhan and hand back a normalised, typed result.
    It deliberately knows NOTHING about the funnel's Pydantic schemas -- the
    dependency points the other way (the funnel converts FROM this).
  - Security IDs were confirmed from Dhan's scrip master CSV
    (https://images.dhan.co/api-data/api-scrip-master.csv) on 2026-08-14,
    NOT guessed.
  - GIFT Nifty (security_id 5024) is UNVERIFIED. It's listed in Dhan's
    scrip master under the NSE index segment, which contradicts our earlier
    assumption that GIFT Nifty (NSE IFSC) wouldn't be reachable via a normal
    NSE feed. Being *listed* doesn't guarantee a populated feed. Callers get
    a FetchResult.ok flag and must fall back to the AI+web_search GIFT path
    in Module_F_Global_Gate_Funnel/ai_gateway.py if this returns not-ok.

Standards applied: single responsibility, DRY, defensive programming,
graceful error handling, bounded retry w/ backoff, structured logging
(no secrets), input validation, stdlib-only (no new deps).
Deferred (not applicable to a read-only fetcher): auth/authz (lives in
dhan_client), DB/migrations/pagination, caching (measure first),
idempotency/concurrency (no writes), app-side rate limiting (Dhan enforces
server-side; we respect it via backoff).
KNOWN GAP -- no true per-call timeout: MAX_RETRIES bounds the number of
attempts, not the duration of any single call. If the dhanhq SDK hangs on
one call, that call blocks. A real timeout needs the SDK to expose one (to
be verified) or the call run under a timeout wrapper; deferred until we
confirm SDK support rather than fake it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from dhan_client import dhan

logger = logging.getLogger(__name__)

# Dhan stamps each daily candle at midnight IST of that trading day, delivered
# as epoch SECONDS. We must convert in IST explicitly and take the calendar
# date -- NOT rely on the server's local timezone. On a UTC server (e.g.
# Render) a naive conversion would land on the PREVIOUS day (midnight IST is
# 18:30 UTC the day before), silently shifting every trading date back by one.
# That off-by-one would corrupt CPR (wrong prior-day H/L/C), the gap calc, and
# the VIX percentile. Pinning IST here is a correctness guarantee for live
# trading, not a cosmetic choice.
IST = timezone(timedelta(hours=5, minutes=30))


def epoch_to_ist_date(epoch_seconds: float) -> date:
    """Convert a Dhan candle epoch (seconds) to its IST calendar date."""
    return datetime.fromtimestamp(epoch_seconds, tz=IST).date()

# --- Config (kept out of function bodies so it's easy to tune) -------------

# Confirmed via Dhan scrip master CSV, 2026-08-14. GIFT_NIFTY unverified.
SECURITY_IDS: dict[str, dict[str, str]] = {
    "NIFTY_50":   {"security_id": "13",   "exchange_segment": "IDX_I", "instrument_type": "INDEX"},
    "INDIA_VIX":  {"security_id": "21",   "exchange_segment": "IDX_I", "instrument_type": "INDEX"},
    "GIFT_NIFTY": {"security_id": "5024", "exchange_segment": "IDX_I", "instrument_type": "INDEX"},
}

DEFAULT_LOOKBACK_DAYS = 10        # generous, so weekend/holiday gaps still yield candles
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0        # 1s, 2s, 4s


@dataclass
class Candle:
    """One daily OHLC bar. trade_date is the IST calendar date of the bar.
    Volume optional (indices often report 0/None)."""
    trade_date: Optional[date]
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


@dataclass
class FetchResult:
    """
    Normalised result of a fetch. `ok` is the single flag callers check --
    never assume success. `error` explains a failure without leaking
    secrets. Candles are oldest-first.
    """
    instrument: str
    ok: bool
    candles: list[Candle] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def latest(self) -> Optional[Candle]:
        return self.candles[-1] if self.candles else None


def _validate_instrument_key(instrument_key: str) -> None:
    if instrument_key not in SECURITY_IDS:
        raise KeyError(
            f"Unknown instrument '{instrument_key}'. Known: {sorted(SECURITY_IDS)}"
        )


def _parse_candles(raw: dict) -> list[Candle]:
    """
    Defensively turn Dhan's columnar response into Candle objects.
    Dhan returns parallel arrays: {open:[...], high:[...], ...}. We only
    build candles up to the length of the SHORTEST required array, so a
    short/malformed array can't cause an IndexError.
    """
    data = raw.get("data") or {}
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    volumes = data.get("volume") or []
    timestamps = data.get("timestamp") or []

    n = min(len(opens), len(highs), len(lows), len(closes))
    candles: list[Candle] = []
    for i in range(n):
        try:
            # trade_date is REQUIRED for storage/compare -- a bar we can't
            # date is useless, so a missing/bad timestamp skips the row
            # rather than storing it undated.
            if i >= len(timestamps) or timestamps[i] is None:
                raise ValueError("missing timestamp")
            trade_date = epoch_to_ist_date(float(timestamps[i]))

            candles.append(Candle(
                trade_date=trade_date,
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(lows[i]),
                close=float(closes[i]),
                volume=float(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
            ))
        except (TypeError, ValueError, OSError, OverflowError) as exc:
            # A single malformed row shouldn't kill the whole fetch. Log it,
            # skip that bar, keep the rest.
            logger.warning("Skipping malformed candle at index %d: %s", i, exc)
            continue
    return candles


def _call_dhan_with_retry(spec: dict[str, str], from_date: str, to_date: str) -> dict:
    """
    Single Dhan call wrapped in bounded retry with exponential backoff.
    Retries only on exceptions -- a Dhan-level 'failure' status is returned
    as-is (not retried blindly). Raises the last exception if all network
    attempts fail (caller catches it).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = dhan.historical_daily_data(
                security_id=spec["security_id"],
                exchange_segment=spec["exchange_segment"],
                instrument_type=spec["instrument_type"],
                expiry_code=0,
                from_date=from_date,
                to_date=to_date,
            )
            if isinstance(response, dict) and response.get("status") == "failure":
                logger.warning(
                    "Dhan returned failure for security_id=%s: %s",
                    spec["security_id"], response.get("remarks", "no remarks"),
                )
            return response
        except Exception as exc:  # noqa: BLE001 -- catch anything the SDK throws
            last_exc = exc
            wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Dhan call failed (attempt %d/%d) for security_id=%s: %s. Retrying in %.1fs",
                attempt, MAX_RETRIES, spec["security_id"], exc, wait,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def fetch_daily(instrument_key: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> FetchResult:
    """
    Fetch daily candles for one known index. Never raises for EXPECTED
    failure modes (network, auth, empty data) -- returns FetchResult(ok=False)
    with an error message instead, so callers can degrade gracefully.

    Programmer error (unknown instrument key) DOES raise -- that's a bug to
    fix, not a runtime condition to handle.
    """
    _validate_instrument_key(instrument_key)
    spec = SECURITY_IDS[instrument_key]

    to_date = date.today()
    from_date = to_date - timedelta(days=lookback_days)

    try:
        raw = _call_dhan_with_retry(spec, from_date.isoformat(), to_date.isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.error("All retries exhausted for %s: %s", instrument_key, exc)
        return FetchResult(instrument=instrument_key, ok=False, error=f"fetch failed: {exc}")

    if not isinstance(raw, dict) or raw.get("status") == "failure":
        remarks = raw.get("remarks") if isinstance(raw, dict) else "non-dict response"
        return FetchResult(instrument=instrument_key, ok=False, error=f"dhan failure: {remarks}")

    candles = _parse_candles(raw)
    if not candles:
        return FetchResult(instrument=instrument_key, ok=False, error="no candles in response")

    logger.info("Fetched %d daily candles for %s", len(candles), instrument_key)
    return FetchResult(instrument=instrument_key, ok=True, candles=candles)


# --- Thin named wrappers (readability at call sites) -----------------------

def get_nifty_daily(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> FetchResult:
    return fetch_daily("NIFTY_50", lookback_days)


def get_india_vix_daily(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> FetchResult:
    return fetch_daily("INDIA_VIX", lookback_days)


def get_gift_nifty_daily(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> FetchResult:
    """UNVERIFIED -- check .ok and fall back to the AI/web_search GIFT path if False."""
    return fetch_daily("GIFT_NIFTY", lookback_days)
