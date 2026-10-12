"""
modules/Module_F_Tech_Indicators_Funnel/indicator_common/smoothing.py

TradingView's two moving averages, shared by every indicator.

  ema_tradingview(prices, n)   Pine ta.ema: alpha = 2/(n+1), seeded with the simple
                               average of the first n values, blank before.
                               Used by EMA, MACD (proven to the paisa, EMA.md §3.5).
  rma_tradingview(series, n)   Pine ta.rma (Wilder's average): alpha = 1/n, seeded
                               with the simple average of the first n NON-BLANK
                               values, blank before. Used by ADX (exact to 4 decimals,
                               ADX.md §3.2); RSI uses the same average.

Moved unchanged 2026-10-12: ema_tradingview from trend_indicators/ema/ema.py,
rma_tradingview from trend_indicators/adx/adx.py (both still re-exported there).

Pure functions: no I/O, input never modified, output aligned to the input index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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


def rma_tradingview(series: pd.Series, period: int) -> pd.Series:
    """
    Pine ta.rma (Wilder's average) over a series that may start with blanks:
    alpha = 1/period, seeded with the simple average of the first `period`
    non-blank values, blank before that.
    """
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    valid = series.dropna()
    if len(valid) < period:
        return out
    start = series.index.get_loc(valid.index[0])
    values = series.iloc[start:].to_numpy(dtype="float64")
    tail = values[period - 1:].copy()
    tail[0] = values[:period].mean()
    rma = pd.Series(tail).ewm(alpha=1.0 / period, adjust=False).mean().to_numpy()
    out.iloc[start + period - 1:] = rma
    return out
