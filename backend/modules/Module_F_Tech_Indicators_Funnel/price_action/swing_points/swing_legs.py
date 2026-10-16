"""
Leg measurements for a swing list (plan step 2).

A leg is the move that ENDED at a swing (from the previous swing to this one).
Works on any alternating swing list: real Zig Zag swings
(find_zigzag_swings) or provisional ones (provisional_swings).

Added columns:
  leg_points  : this swing's price minus the previous swing's price (signed)
  leg_pct     : leg_points as % of the previous swing's price (signed)
  leg_bars    : candles from the previous swing's pivot to this one
  retrace_pct : this leg's size as % of the previous leg's size
                (a pullback of 50 = it gave back half the previous move)
The first swing has no leg (NaN); the second has no retrace (NaN).

Pure function, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LEG_COLUMNS = ["leg_points", "leg_pct", "leg_bars", "retrace_pct"]


def add_leg_data(swings: pd.DataFrame, candle_times: pd.Series) -> pd.DataFrame:
    """
    swings       : DataFrame with at least 'price' and 'pivot_time', oldest first.
    candle_times : the candle times the swings were found on (for bar counts).
    Returns a copy of swings with LEG_COLUMNS added.
    """
    missing = {"price", "pivot_time"} - set(swings.columns)
    if missing:
        raise ValueError(f"swings is missing columns: {sorted(missing)}")

    out = swings.copy().reset_index(drop=True)
    if out.empty:
        for col in LEG_COLUMNS:
            out[col] = pd.Series(dtype=float)
        return out

    price = out["price"].astype(float)
    prev = price.shift(1)
    out["leg_points"] = price - prev
    out["leg_pct"] = 100.0 * out["leg_points"] / prev.abs()

    times = pd.to_datetime(pd.Series(candle_times)).to_numpy()
    idx = np.searchsorted(times, pd.to_datetime(out["pivot_time"]).to_numpy())
    out["leg_bars"] = pd.Series(idx, dtype=float).diff()

    size = out["leg_points"].abs()
    out["retrace_pct"] = 100.0 * size / size.shift(1)
    return out
