"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema.py

EMA calculator, part 1: EMA VALUES ONLY. Crosses, the stack ladder (stage -5..+5),
the 50/200 golden/death cross and the plain-English texts are later steps.

TradingView parity (decided 2026-10-11): same method as Pine's ta.ema, so values
match what Ash sees on his TradingView charts.
  - alpha = 2 / (n + 1)
  - bars 1 .. n-1  -> blank (NaN): fewer than n closes exist, so no EMA yet
  - bar n          -> simple average of the first n closes (the seed)
  - every later bar -> alpha * close + (1 - alpha) * previous EMA
Because the seed's influence fades bar by bar, long histories (Nifty: 6,657 daily
bars since 2000) give the same values as TradingView even if TradingView's own
history starts on a different date.

Reusable by design: a pure function with no I/O and nothing instrument-specific.
The same compute_emas() runs on Nifty 50 today and on every watchlist / options
stock later, on any timeframe (periods are counted in bars of whatever timeframe
the input holds). Reading the bars is the caller's job (indicator_ohlcv_reader).

Input contract (programming errors raise ValueError -- the caller passes data it
already validated through the reader, so a bad input here is a code bug, not a
data condition to report):
  - DataFrame with a numeric price column (default 'close')
  - rows in ascending time order ('ts' checked when present)
  - periods: positive, unique integers
The input DataFrame is never modified; a copy with ema_<n> columns is returned.

Standards applied: single responsibility (EMA math only), pure function (no I/O,
no global state), input validation, readable/consistent naming, vectorised
pandas (milliseconds for 6 EMAs on ~6,600 bars), unit tests (test_ema.py).
Deferred (with reasons):
  - Logging: none inside the pure function (nothing can fail silently here; bad
    input raises). The manual check below and future callers log their runs.
  - Crosses / stage / texts: separate later steps, by agreement (baby steps).
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

DEFAULT_PERIODS: tuple[int, ...] = (5, 13, 26, 50, 100, 200)


def ema_tradingview(prices: pd.Series, period: int) -> pd.Series:
    """
    One EMA series, TradingView method (SMA seed at bar `period`, blank before).

    Returns a float Series aligned to `prices` (same index), NaN for the first
    period-1 bars, or all-NaN if there are fewer than `period` bars.
    """
    out = pd.Series(np.nan, index=prices.index, dtype="float64")
    if len(prices) < period:
        return out

    values = prices.to_numpy(dtype="float64")
    seed = values[:period].mean()
    # From the seed bar onward: start at the SMA seed, then the recursive EMA.
    tail = values[period - 1:].copy()
    tail[0] = seed
    alpha = 2.0 / (period + 1)
    ema_tail = (pd.Series(tail)
                .ewm(alpha=alpha, adjust=False)
                .mean()
                .to_numpy())
    out.iloc[period - 1:] = ema_tail
    return out


def _validate(df: pd.DataFrame, periods: tuple[int, ...], price_col: str) -> None:
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame "
                         f"(columns: {list(df.columns)})")
    if not periods:
        raise ValueError("periods is empty")
    for p in periods:
        if isinstance(p, bool) or not isinstance(p, (int, np.integer)) or p < 1:
            raise ValueError(f"period {p!r} is not a positive integer")
    if len(set(periods)) != len(periods):
        raise ValueError(f"periods contain duplicates: {periods}")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before computing EMAs")


def compute_emas(
    df: pd.DataFrame,
    periods: Iterable[int] = DEFAULT_PERIODS,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Return a copy of `df` with one column per period: ema_5, ema_13, ... ema_200.

    Args:
        df: bars in ascending time order (e.g. indicator_ohlcv_reader output).
        periods: EMA lengths in bars. Default (5, 13, 26, 50, 100, 200).
        price_col: column to average. Default 'close' (TradingView default source).

    Raises:
        ValueError on a missing price column, bad periods or unsorted bars.
    """
    periods = tuple(periods)
    _validate(df, periods, price_col)

    out = df.copy()
    prices = out[price_col]
    for p in periods:
        out[f"ema_{p}"] = ema_tradingview(prices, p)
    return out


# --- Manual check: Nifty 50 EMAs on the latest bars, to compare with TradingView ---

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema
    import argparse
    import logging

    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Print EMAs for the latest bars (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--domain", default="indices")
    parser.add_argument("--bars", type=int, default=3, help="how many latest bars to print")
    parser.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD",
                        help="print these trade dates instead of the latest bars")
    args = parser.parse_args()

    res = read_for_indicators(args.key, args.domain, "1d")
    print("\n" + "=" * 78)
    print(f"EMA CHECK — {args.key} (daily, TradingView method)")
    print("=" * 78)
    if not res.ok:
        print(f"NOT OK -- {res.error}")
    else:
        emas = compute_emas(res.df)
        cols = [f"ema_{p}" for p in DEFAULT_PERIODS]
        header = f"{'date':<12}{'close':>11}" + "".join(f"{c:>11}" for c in cols)
        print(header)
        if args.dates:
            wanted = set(args.dates)
            rows = emas[emas["trade_date"].astype(str).isin(wanted)]
            found = set(rows["trade_date"].astype(str))
            for d in sorted(wanted - found):
                print(f"{d:<12}  no bar on this date (not a trading day in our data)")
        else:
            rows = emas.tail(args.bars)
        for _, r in rows.iterrows():
            row = f"{str(r['trade_date']):<12}{r['close']:>11.2f}"
            row += "".join(f"{r[c]:>11.2f}" for c in cols)
            print(row)
        print(f"\nbars used: {len(emas):,}  (data as of {res.last_trade_date} close)")
    print("=" * 78 + "\n")
