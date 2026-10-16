"""
Structure events: BOS / CHoCH and trend state (plan step 5, decided 16 Oct 2026).

Sources: Dow Theory (trend = higher highs + higher lows, presumed to continue
until a CLOSE beyond the prior swing; Murphy), Sperandeo 1-2-3 (close beyond
point 2), TradingView market-structure scripts (Xcelerate, LuxAlgo): close
beyond the LATEST swing, trend starts neutral, first break = CHoCH, a broken
level is used up. BOS/CHoCH are the modern names for the Dow events.

Meaning (Ash's wording, shown on every report):
  BOS  : Break of Structure  - indicates a trend continuation
  CHoCH: Change of Character - indicates a potential trend reversal
Trend values are 'uptrend' / 'downtrend' / 'neutral' (not bull / bear).

Rules (agreed with Ash, 16 Oct 2026: "label as we see it today; tomorrow
informs same or different"):
  Targets : at any moment, the latest swing high (above) and latest swing low
            (below) KNOWN TODAY, i.e. from the swing's detected time. No
            waiting for the swing to lock. A newer swing of the same kind
            replaces the target. (Matches TradingView pivot-based scripts.)
  Event   : first candle CLOSE beyond a target (step 4's confirmed break).
              up   + uptrend              -> BOS   (trend continuation)
              up   + downtrend / neutral  -> CHoCH (potential reversal, trend flips to uptrend)
              down mirrors it.
            Example: 3 May 2024 high 22794.70 -> BOS Thu 23 May 2024; failed
            Tue 4 Jun (close back below); re-broken Thu 6 Jun (label).
  Start   : neutral on the first candle of the history; the whole history is
            scanned, so today's state is built from real events.
  Final   : the event (type, time, level) and any trend flip are final at the
            close of the breaking candle; we only use what is known that day.
            The swing itself may still move later; the report then simply
            says what it sees on that day.
  Labels  : gap / cleared / retest / held / failed / re-breaks come from
            level_breaks (step 4) and keep updating. They never undo an event
            or flip the trend. Every label is kept, low weight today, may be
            high weight later.
  One event per level: re-breaks of an already-broken level are labels only.

Provisional (Ash's method): pass HIGHER-timeframe levels (provisional swings,
active from known_at) with LOWER-timeframe candles.

Pure functions, no I/O.
"""

from __future__ import annotations

import pandas as pd

try:
    from .level_breaks import find_level_breaks
except ImportError:  # run from the tests with the folder on sys.path
    from level_breaks import find_level_breaks

EVENT_COLUMNS = ["time", "direction", "event", "level_kind", "level_price", "level_pivot_time",
                 "active_from", "trend_before", "trend_after"]
LABEL_COLUMNS = ["gap", "cleared_time", "retest_time", "held_time", "outcome", "outcome_time",
                 "rebreaks"]


def _scan(candles: pd.DataFrame, levels: pd.DataFrame):
    """Walk the candles once. Returns (event rows, final state)."""
    need_c = {"time", "close"}
    need_l = {"kind", "price", "active_from"}
    if need_c - set(candles.columns):
        raise ValueError(f"candles is missing columns: {sorted(need_c - set(candles.columns))}")
    if need_l - set(levels.columns):
        raise ValueError(f"levels is missing columns: {sorted(need_l - set(levels.columns))}")

    times = pd.DatetimeIndex(pd.to_datetime(candles["time"]))
    closes = candles["close"].to_numpy(float)
    lv = levels.sort_values("active_from", kind="stable").reset_index(drop=True)
    act = pd.DatetimeIndex(pd.to_datetime(lv["active_from"]))
    # a level is live from the first candle AFTER its active_from time
    start_at = times.searchsorted(act, side="right")

    has_pivot = "pivot_time" in lv
    trend = "neutral"
    target = {"high": None, "low": None}      # row index into lv, or None
    rows = []
    j = 0
    for i in range(len(times)):
        while j < len(lv) and start_at[j] <= i:
            target[lv.at[j, "kind"]] = j      # newer known swing replaces the target
            j += 1
        for kind, up in (("high", True), ("low", False)):
            t = target[kind]
            if t is None:
                continue
            p = float(lv.at[t, "price"])
            if (closes[i] > p) if up else (closes[i] < p):
                side = "uptrend" if up else "downtrend"
                rows.append({
                    "time": times[i], "direction": "up" if up else "down",
                    "event": "BOS" if trend == side else "CHoCH",
                    "level_kind": kind, "level_price": p,
                    "level_pivot_time": lv.at[t, "pivot_time"] if has_pivot else pd.NaT,
                    "active_from": lv.at[t, "active_from"],
                    "trend_before": trend, "trend_after": side,
                })
                trend = side
                target[kind] = None           # a broken level is used up
    state = {
        "trend": trend,
        "up_target": None if target["high"] is None else float(lv.at[target["high"], "price"]),
        "down_target": None if target["low"] is None else float(lv.at[target["low"], "price"]),
    }
    return rows, state


def find_structure_events(candles: pd.DataFrame, levels: pd.DataFrame,
                          tol_pct: float) -> pd.DataFrame:
    """
    candles : time, open, high, low, close (sorted by time).
    levels  : kind ('high'/'low'), price, active_from (the swing's detected
              time; known_at for provisional swings), optional pivot_time.
    tol_pct : the levels' timeframe equal tolerance (for the step-4 labels).
    Returns one row per BOS/CHoCH with EVENT_COLUMNS + LABEL_COLUMNS.
    """
    rows, _ = _scan(candles, levels)
    ev = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    if ev.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS + LABEL_COLUMNS)

    # step-4 labels for each event's level, scanned from when it became a target
    lv = pd.DataFrame({"kind": ev["level_kind"], "price": ev["level_price"],
                       "known_at": ev["active_from"], "event_id": range(len(ev))})
    br = find_level_breaks(candles, lv, tol_pct)
    first = br[br["cycle"] == 1].set_index("event_id")
    last = br.groupby("event_id").tail(1).set_index("event_id")
    ev["gap"] = first["gap"].reindex(ev.index).fillna(False).astype(bool).to_numpy()
    for col in ("cleared_time", "retest_time", "held_time"):
        ev[col] = first[col].reindex(ev.index).to_numpy()
    # outcome = the LATEST state of the level (held is never final)
    ev["outcome"] = last["outcome"].reindex(ev.index).to_numpy()
    ev["outcome"] = ev["outcome"].astype(object).where(ev["outcome"].notna(), None)
    ev["outcome_time"] = last["outcome_time"].reindex(ev.index).to_numpy()
    ev["rebreaks"] = (br.groupby("event_id")["cycle"].max().reindex(ev.index) - 1).astype(int).to_numpy()
    return ev


def current_structure(candles: pd.DataFrame, levels: pd.DataFrame) -> dict:
    """
    Trend now and what would change it:
      trend       : 'uptrend' / 'downtrend' / 'neutral'
      up_target   : close above this = BOS if uptrend, CHoCH (to uptrend) otherwise
      down_target : close below this = BOS if downtrend, CHoCH (to downtrend) otherwise
    A target is None when the latest known swing of that kind is already
    broken (wait for a new swing).
    """
    _, state = _scan(candles, levels)
    return state
