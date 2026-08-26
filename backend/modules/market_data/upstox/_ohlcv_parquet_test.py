"""
modules/market_data/upstox/_ohlcv_parquet_test.py

>>> INCREMENT 2.3a: LOCAL Parquet write/read test (throwaway spike). <<<

Purpose: prove the Parquet storage format + measure REAL file size before touching
Supabase. Fetches one instrument's full history across all Tier-1 timeframes, writes
ONE local Parquet file (all timeframes in it, distinguished by a `timeframe` column),
prints the actual on-disk size, then reads it back and verifies the round-trip matches
what we wrote.

This is a temporary spike file to de-risk 2.3 — the real writer/reader modules
(fetch_universe_ohlcv.py + read_ohlcv.py, writing to Supabase Storage) come after this
confirms the format + size. Delete this file once 2.3 proper is built.

Schema written (one row per candle, all timeframes stacked):
    timeframe (str: '1d'/'1w'/'1mo'), ts (datetime, IST), trade_date (date),
    open, high, low, close (float), volume, open_interest (float, nullable)

Run:  python -m modules.market_data.upstox._ohlcv_parquet_test
"""

from __future__ import annotations

import logging
import os
from datetime import date

import pandas as pd

from modules.market_data.upstox._ohlcv_engine import fetch_all_timeframes

logger = logging.getLogger(__name__)

# Local scratch output (NOT Supabase). Written next to where you run from.
_LOCAL_DIR = "ohlcv_local_test"


def _results_to_dataframe(results: dict) -> pd.DataFrame:
    """Flatten the {label: OhlcvFetchResult} dict into one tidy DataFrame with a
    `timeframe` column — the shape we'll store as a single per-instrument Parquet."""
    frames = []
    for label, res in results.items():
        if not res.ok:
            logger.warning("Timeframe %s not ok: %s", label, res.error)
            continue
        rows = [{
            "timeframe": label,
            "ts": c.ts,
            "trade_date": c.trade_date,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "open_interest": c.open_interest,
        } for c in res.candles]
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # Deterministic order: by timeframe then time.
    df = df.sort_values(["timeframe", "ts"]).reset_index(drop=True)
    return df


def _human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Nifty 50: a full-26-year instrument = a near-WORST-CASE Tier-1 file size, so
    # the measured size is a safe upper bound for estimating the universe total.
    test_key = "NSE_INDEX|Nifty 50"
    # filename = the part after '|', space-slugified (the naming rule).
    fname = test_key.split("|", 1)[1].strip().replace(" ", "_") + ".parquet"

    print("\n" + "=" * 64)
    print("OHLCV PARQUET — INCREMENT 2.3a (LOCAL write/read, size measure)")
    print("=" * 64)
    print(f"Instrument : {test_key}")
    print("Fetching full history (1D/1W/1Mo) ...")

    results = fetch_all_timeframes(test_key)
    df = _results_to_dataframe(results)
    if df.empty:
        print("FAIL -- no data to write.")
        raise SystemExit(1)

    os.makedirs(_LOCAL_DIR, exist_ok=True)
    path = os.path.join(_LOCAL_DIR, fname)

    # Write Parquet with snappy compression (good speed/size default).
    df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)

    size = os.path.getsize(path)
    print(f"\nWrote {len(df):,} rows -> {path}")
    print(f"FILE SIZE  : {_human_size(size)}  ({size:,} bytes)")
    print(f"  rows by timeframe: {df['timeframe'].value_counts().to_dict()}")

    # --- Round-trip verify: read back, confirm it matches what we wrote ---
    df_back = pd.read_parquet(path, engine="pyarrow")
    same_rows = len(df_back) == len(df)
    same_cols = list(df_back.columns) == list(df.columns)
    # spot-check: last close per timeframe matches
    checks_ok = True
    for tf in df["timeframe"].unique():
        a = df[df.timeframe == tf].iloc[-1]["close"]
        b = df_back[df_back.timeframe == tf].iloc[-1]["close"]
        if a != b:
            checks_ok = False
            print(f"  MISMATCH in {tf}: wrote {a}, read {b}")

    print("\nRound-trip verify:")
    print(f"  row count match : {same_rows} ({len(df_back):,} read)")
    print(f"  columns match   : {same_cols}")
    print(f"  close values    : {'OK' if checks_ok else 'MISMATCH'}")

    # --- Extrapolation to the whole plan, using THIS measured size ---
    print("\nSize extrapolation (using this file as the per-instrument estimate):")
    per = size
    print(f"  Tier 1, 2,643 stocks   ~ {_human_size(per * 2643)}")
    print(f"  Tier 1, 139 indices    ~ {_human_size(per * 139)}")
    print(f"  (Nifty 50 is a 26yr instrument = upper-bound per-file size;")
    print(f"   most stocks are younger, so real totals will be LOWER.)")
    print("=" * 64 + "\n")
