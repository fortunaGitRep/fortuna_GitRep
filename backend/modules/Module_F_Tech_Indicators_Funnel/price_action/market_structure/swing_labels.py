"""
Swing labels and equal-high / equal-low zones (plan step 3).

Each swing is compared with the previous swing of the same kind (two rows
back, since swings alternate high/low):
  high -> HH (higher), LH (lower), EQH (equal within tolerance)
  low  -> HL (higher), LL (lower), EQL (equal within tolerance)
The first high and first low have no earlier swing to compare: label "H"/"L".

Zones (double / triple tops and bottoms): consecutive equal swings of the same
kind form one zone.
  zone_id      : running number per zone (NaN when the swing is in no zone)
  zone_touches : 2 = double top/bottom, 3 = triple, ...
  zone_low/high: price range of the touches so far
  neckline     : lowest low between the tops (highest high between the
                 bottoms) -- the level that confirms the pattern if broken
Zone columns are filled on every touch of the zone (the latest row shows the
zone as it stands now).

label_can_change: True for the latest, not yet locked swing -- its price can
still extend, so EQH can become HH, etc.

Tolerance: percent of the previous same-kind swing's price. Fortuna uses 10%
of each timeframe's Zig Zag deviation (zigzag_settings.get_equal_tolerance).
Pure function, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LABEL_COLUMNS = ["label", "zone_id", "zone_touches", "zone_low", "zone_high",
                 "neckline", "label_can_change"]


def add_swing_labels(swings: pd.DataFrame, equal_tol_pct: float) -> pd.DataFrame:
    """
    swings        : alternating swing list with 'kind' and 'price', oldest first;
                    'is_locked' (real) or 'is_confirmed' (provisional) if present.
    equal_tol_pct : e.g. 0.02 for 5m.
    Returns a copy of swings with LABEL_COLUMNS added.
    """
    if not (isinstance(equal_tol_pct, (int, float)) and equal_tol_pct >= 0):
        raise ValueError(f"equal_tol_pct must be >= 0, got {equal_tol_pct!r}")
    missing = {"kind", "price"} - set(swings.columns)
    if missing:
        raise ValueError(f"swings is missing columns: {sorted(missing)}")

    out = swings.copy().reset_index(drop=True)
    n = len(out)
    kinds = out["kind"].to_numpy()
    prices = out["price"].to_numpy(dtype=float)
    if n and (kinds[1:] == kinds[:-1]).any():
        raise ValueError("swings must alternate high/low")

    label = np.empty(n, dtype=object)
    zone_id = np.full(n, np.nan)
    touches = np.full(n, np.nan)
    z_low = np.full(n, np.nan)
    z_high = np.full(n, np.nan)
    neck = np.full(n, np.nan)
    next_zone = 0

    for i in range(n):
        high = kinds[i] == "high"
        if i < 2:
            label[i] = "H" if high else "L"
            continue
        p, q = prices[i], prices[i - 2]
        if abs(p - q) / abs(q) * 100.0 <= equal_tol_pct:
            label[i] = "EQH" if high else "EQL"
            if np.isnan(zone_id[i - 2]):          # new zone: i-2 is the first touch
                next_zone += 1
                first, zid = i - 2, next_zone
            else:                                  # zone continues
                zid = zone_id[i - 2]
                first = i - 2 - 2 * (int(touches[i - 2]) - 1)
            members = list(range(first, i + 1, 2))
            between = prices[first + 1:i:2]        # the opposite swings inside
            for m in members:
                zone_id[m] = zid
                touches[m] = len(members)
                z_low[m] = prices[members].min()
                z_high[m] = prices[members].max()
                neck[m] = between.min() if high else between.max()
        elif high:
            label[i] = "HH" if p > q else "LH"
        else:
            label[i] = "HL" if p > q else "LL"

    out["label"] = label
    out["zone_id"] = zone_id
    out["zone_touches"] = touches
    out["zone_low"] = z_low
    out["zone_high"] = z_high
    out["neckline"] = neck

    lock_col = "is_locked" if "is_locked" in out.columns else (
        "is_confirmed" if "is_confirmed" in out.columns else None)
    if lock_col is None:
        out["label_can_change"] = False
        if n:
            out.loc[n - 1, "label_can_change"] = True
    else:
        out["label_can_change"] = ~out[lock_col].astype(bool)
    return out
