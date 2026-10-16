"""
Provisional higher-timeframe swings from lower-timeframe locked swings
(Ash's "temporary lock" idea, 14 Oct 2026).

Why: a 60m Zig Zag swing needs 5 hourly bars to confirm (5 hours); a daily one
needs 5 days. The same turn usually shows up much earlier as a LOCKED swing on
a lower timeframe. So we re-run the Zig Zag rule over the lower timeframe's
locked swings, using the HIGHER timeframe's deviation:
    5m locked swings  + 60m deviation (1.25%) -> provisional 60m swings
    60m locked swings + 1D deviation (5%)     -> provisional daily swings

The guard is the higher deviation: a 5m swing only counts for the hourly view
if the move from the last hourly swing is at least 1.25%, so the hourly
direction does not flip on every small 5m wiggle.

Rule (same as TradingView's newPivotPointFound, applied to swings not bars):
  - first swing           -> becomes the first provisional swing
  - same kind as the last -> replaces it only if more extreme
  - opposite kind         -> added only if >= deviation_pct away from the last

Times:
  known_at     : lower-timeframe lock time of the swing that set this level
                 (when we could first know it)
  confirmed_at : when the next opposite provisional swing was added; NaT for
                 the latest one (it can still extend)

Provisional swings are a fast view, not a copy of the chart: the real 60m/1D
Zig Zag stays the reference for chart parity. Pure function, no I/O.
"""

from __future__ import annotations

import pandas as pd

PROVISIONAL_COLUMNS = ["kind", "price", "pivot_time", "known_at", "confirmed_at", "is_confirmed"]


def provisional_swings(lower_swings: pd.DataFrame, deviation_pct: float) -> pd.DataFrame:
    """
    lower_swings  : output of find_zigzag_swings() for the lower timeframe.
    deviation_pct : the HIGHER timeframe's deviation, e.g. 1.25 for 60m.
    Only locked lower swings are used.
    """
    if not (isinstance(deviation_pct, (int, float)) and deviation_pct > 0):
        raise ValueError(f"deviation_pct must be > 0, got {deviation_pct!r}")
    needed = {"kind", "price", "pivot_time", "locked_time", "is_locked"}
    missing = needed - set(lower_swings.columns)
    if missing:
        raise ValueError(f"lower_swings is missing columns: {sorted(missing)}")

    locked = lower_swings[lower_swings["is_locked"]].sort_values("locked_time")
    out: list[dict] = []

    for row in locked.itertuples(index=False):
        if not out:
            out.append(_new(row))
            continue
        last = out[-1]
        if row.kind == last["kind"]:
            more = row.price > last["price"] if row.kind == "high" else row.price < last["price"]
            if more:
                last.update(price=float(row.price), pivot_time=row.pivot_time,
                            known_at=row.locked_time)
            continue
        dev = 100.0 * (row.price - last["price"]) / abs(last["price"])
        if (last["kind"] == "low" and dev >= deviation_pct) or (
            last["kind"] == "high" and dev <= -deviation_pct
        ):
            last["confirmed_at"] = row.locked_time
            last["is_confirmed"] = True
            out.append(_new(row))

    result = pd.DataFrame(out, columns=PROVISIONAL_COLUMNS)
    result["is_confirmed"] = result["is_confirmed"].astype(bool)
    return result


def current_direction(prov: pd.DataFrame, deviation_pct: float) -> dict:
    """Direction of the last confirmed leg: last swing high -> 'up', low -> 'down'.
    reverses_at: price that would confirm the opposite leg."""
    if prov.empty:
        return {"direction": "unknown", "from_price": None, "extreme": None,
                "reverses_at": None, "since": None}
    last = prov.iloc[-1]
    up = last["kind"] == "high"
    k = deviation_pct / 100.0
    return {
        "direction": "up" if up else "down",
        "from_price": float(prov.iloc[-2]["price"]) if len(prov) > 1 else None,
        "extreme": float(last["price"]),
        "reverses_at": float(last["price"]) * (1 - k if up else 1 + k),
        "since": last["known_at"],
    }


def _new(row) -> dict:
    return {
        "kind": row.kind,
        "price": float(row.price),
        "pivot_time": row.pivot_time,
        "known_at": row.locked_time,
        "confirmed_at": pd.NaT,
        "is_confirmed": False,
    }
