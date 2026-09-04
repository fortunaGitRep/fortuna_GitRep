"""
read_ohlcv.py — single shared accessor for reading OHLCV from R2.

LIVES IN: backend/modules/market_data/  (shared foundation layer, NOT under any
one feature — the funnel and backtest both read OHLCV through this one door.)

DESIGN (settled 2026-08-29):
  - R2 is the SINGLE source of truth. This reads it directly on every call.
    No disk cache: on Render the filesystem is ephemeral (wiped on deploy /
    spin-down) and a daily local copy would (a) not survive idle spin-down and
    (b) introduce a staleness rule we'd have to enforce forever — trading on a
    stale bar is exactly the silent-wrong-call the system forbids. R2 egress is
    already free, so caching buys nothing and risks correctness.
  - Optional in-memory memo (`memo` dict) lives for the LIFE OF ONE SCAN RUN
    only — passed in by the caller, dies when the caller drops it. It just avoids
    re-reading the same parquet twice inside a single "best buy today" pass. It
    is NOT a persistent cache and has no staleness surface.

The write side of R2 is owned by ohlcv_store.py; this is the read counterpart.

NOTE: `get_r2_settings().bucket` — confirm the bucket attribute name matches the
r2_client settings object (doc names bucket `fortuna-ohlcv` but not the field).
"""

from __future__ import annotations

import io
from typing import MutableMapping

import pandas as pd

from db.r2_client import get_r2, get_r2_settings  # documented shared client


VALID_TIMEFRAMES = {"1d", "1w", "1mo"}
_OHLCV_COLS = ["date", "open", "high", "low", "close"]


def _r2_key(instrument_key: str, domain: str) -> str:
    """Build the R2 object key for a stock (ISIN) or index (slug).

    domain='universe' -> upstox/universe/<ISIN>.parquet
    domain='indices'  -> upstox/indices/<slug>.parquet
    """
    if domain == "universe":
        return f"upstox/universe/{instrument_key}.parquet"
    if domain == "indices":
        return f"upstox/indices/{instrument_key}.parquet"
    raise ValueError(f"unknown domain {domain!r} (expected 'universe' or 'indices')")


def read_ohlcv(
    instrument_key: str,
    timeframe: str = "1d",
    domain: str = "universe",
    memo: MutableMapping[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Read one instrument's OHLCV for a single timeframe from R2.

    Args:
        instrument_key: ISIN (stocks) or slug (indices) — the parquet filename stem.
        timeframe: '1d' | '1w' | '1mo' (default '1d').
        domain: 'universe' (stocks) | 'indices'.
        memo: optional caller-owned dict for per-run in-memory reuse. Keyed by the
              R2 object key so the SAME file is fetched from R2 at most once per run.
              Pass the same dict across calls within one scan; drop it when done.

    Returns:
        DataFrame with columns [date, open, high, low, close], date as datetime,
        sorted ascending, filtered to the requested timeframe.

    Raises:
        ValueError on bad timeframe/domain.
        Underlying boto3/pandas errors propagate (missing/illiquid parquet) — the
        CALLER decides whether to skip or abort, so we don't swallow them here.
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"timeframe {timeframe!r} not in {sorted(VALID_TIMEFRAMES)}")

    key = _r2_key(instrument_key, domain)

    # Per-run memo: the full parquet (all timeframes) is cached under `key`,
    # so a second call for a different timeframe of the same instrument still
    # hits R2 only once.
    if memo is not None and key in memo:
        full = memo[key]
    else:
        settings = get_r2_settings()
        r2 = get_r2()
        obj = r2.get_object(Bucket=settings.bucket, Key=key)
        full = pd.read_parquet(io.BytesIO(obj["Body"].read()))
        if memo is not None:
            memo[key] = full

    df = full[full["timeframe"] == timeframe].copy()

    # Real schema (verified against parquet): the datetime is `ts`
    # (datetime64, tz-aware IST) and `trade_date` (date-only). There is no
    # `date` column. Use `ts`, rename to the canonical `date` the callers expect.
    df = df.rename(columns={"ts": "date"})
    df = df.sort_values("date").reset_index(drop=True)

    # Return only the canonical OHLCV columns that are present.
    present = [c for c in _OHLCV_COLS if c in df.columns]
    return df[present]
