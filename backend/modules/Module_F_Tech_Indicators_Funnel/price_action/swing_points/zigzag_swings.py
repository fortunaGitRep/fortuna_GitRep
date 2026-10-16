"""
Zig Zag swing points: a Python port of TradingView's ZigZag library (v9,
2026-02-25), confirmed-pivot logic only.

Original Pine Script: (c) TradingView, Mozilla Public License 2.0
https://mozilla.org/MPL/2.0/  (library page: tradingview.com/script/bzIRuGXC-ZigZag/)

Ported rules (from TradingView's update(), findPivotPoint(), newPivotPointFound()):
  1. Bars checked each side = max(2, floor(depth / 2)). Depth 10 -> 5 bars.
  2. A bar is a pivot high when its high is strictly above the `d` bars before it
     and above-or-equal to the `d` bars after it (so the FIRST of equal highs
     wins). Pivot lows mirror this. A pivot is only known `d` bars later.
  3. Highs are checked before lows on every bar. One bar may give both.
  4. A new pivot of the same type as the last swing replaces it only if more
     extreme. A pivot of the opposite type is added only if it is at least
     `deviation_pct` percent away from the last swing's price.

Not ported (on purpose): TradingView's "projection pivots" (the dashed last
line drawn only on the latest bar). Fortuna instead marks the latest swing as
not locked; it can still be replaced by a more extreme pivot.

Times recorded per swing:
  pivot_time    : bar where the high/low happened
  detected_time : bar where the pivot was confirmed (d bars after pivot_time);
                  if the swing was replaced, the bar of the latest replacement
  locked_time   : bar where the next opposite swing was added; from then on the
                  swing can never change. NaT for the latest swing.

This function only computes. It does not read or write files or the database.
The caller passes candles already cleaned by the indicator reader rules.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

SWING_COLUMNS = [
    "kind",           # "high" or "low"
    "price",
    "pivot_time",
    "detected_time",
    "locked_time",
    "is_locked",
]


def bars_each_side(depth: int) -> int:
    """TradingView's internal depth: max(2, floor(depth / 2))."""
    return max(2, math.floor(depth / 2))


def _validate(candles: pd.DataFrame, deviation_pct: float, depth: int) -> None:
    missing = {"time", "high", "low"} - set(candles.columns)
    if missing:
        raise ValueError(f"candles is missing columns: {sorted(missing)}")
    if not isinstance(depth, (int, np.integer)) or depth < 1:
        raise ValueError(f"depth must be an integer >= 1, got {depth!r}")
    if not (isinstance(deviation_pct, (int, float)) and deviation_pct > 0):
        raise ValueError(f"deviation_pct must be > 0, got {deviation_pct!r}")
    if candles[["high", "low"]].isna().any().any():
        raise ValueError("candles has empty high/low values")
    if (candles[["high", "low"]] <= 0).any().any():
        raise ValueError("candles has non-positive prices; apply the reader rules first")
    if not candles["time"].is_monotonic_increasing or candles["time"].duplicated().any():
        raise ValueError("candles must be sorted by time with no duplicate times")


def _is_pivot(values: np.ndarray, bar: int, d: int, is_high: bool) -> bool:
    """findPivotPoint(): is the bar `d` bars before `bar` a pivot?"""
    p = bar - d
    price = values[p]
    # Later bars (p+1 .. bar): may equal the pivot, must not exceed it.
    later = values[p + 1: bar + 1]
    # Earlier bars (p-d .. p-1): must be strictly below (high) / above (low).
    earlier = values[p - d: p]
    if is_high:
        return not (later > price).any() and not (earlier >= price).any()
    return not (later < price).any() and not (earlier <= price).any()


def find_zigzag_swings(
    candles: pd.DataFrame, deviation_pct: float, depth: int
) -> pd.DataFrame:
    """
    Return Zig Zag swings for one instrument and one timeframe.

    candles       : DataFrame with columns time, high, low (sorted by time).
    deviation_pct : e.g. 5.0 for 5%.
    depth         : TradingView "Depth" input (halved internally).

    Returns a DataFrame with SWING_COLUMNS, one row per swing, oldest first.
    """
    _validate(candles, deviation_pct, depth)

    times = candles["time"].to_numpy()
    highs = candles["high"].to_numpy(dtype=float)
    lows = candles["low"].to_numpy(dtype=float)
    d = bars_each_side(depth)

    swings: list[dict] = []

    def register(is_high: bool, bar: int) -> None:
        """newPivotPointFound(): add, replace, or ignore a confirmed pivot."""
        p = bar - d
        price = highs[p] if is_high else lows[p]
        kind = "high" if is_high else "low"

        if not swings:
            swings.append(_new_swing(kind, price, times[p], times[bar]))
            return

        last = swings[-1]
        if last["kind"] == kind:
            more_extreme = price > last["price"] if is_high else price < last["price"]
            if more_extreme:
                last["price"] = price
                last["pivot_time"] = times[p]
                last["detected_time"] = times[bar]
            return

        dev = 100.0 * (price - last["price"]) / abs(last["price"])
        if (last["kind"] == "low" and dev >= deviation_pct) or (
            last["kind"] == "high" and dev <= -deviation_pct
        ):
            last["locked_time"] = times[bar]
            last["is_locked"] = True
            swings.append(_new_swing(kind, price, times[p], times[bar]))

    for bar in range(2 * d, len(candles)):
        if _is_pivot(highs, bar, d, is_high=True):
            register(True, bar)
        if _is_pivot(lows, bar, d, is_high=False):
            register(False, bar)

    result = pd.DataFrame(swings, columns=SWING_COLUMNS)
    for col in ("pivot_time", "detected_time", "locked_time"):
        result[col] = pd.to_datetime(result[col])
    result["is_locked"] = result["is_locked"].astype(bool)
    return result


def _new_swing(kind: str, price: float, pivot_time, detected_time) -> dict:
    return {
        "kind": kind,
        "price": float(price),
        "pivot_time": pivot_time,
        "detected_time": detected_time,
        "locked_time": pd.NaT,
        "is_locked": False,
    }
