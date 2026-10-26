"""
Horizontal S&R ZONES from Zig Zag swings (Ash, 2026-10-26: "HSR zones are what the books
and studies say, I follow the same"). A new layer on top of horizontal_sr.py: the lines in
horizontal_sr.py are not changed (they stay checked against Ash's drawings).

Rules (SUPPORT_RESISTANCE.md section 4.13):
  1. Every Zig Zag swing is one ZONE (one turning point), not a line:
       swing high: from the candle HIGH (the wick) down to the top of the candle body
                   (max of open / close);
       swing low:  from the candle LOW (the wick) up to the bottom of the body
                   (min of open / close).
     Books: the outer edge runs through the extreme wick, the inner edge at the bodies.
  2. Depth limits, measured from the timeframe's own candles up to the swing candle (no
     future data), so it works the same on Nifty, stocks and option premiums:
       at least GAMMA = mean |close - previous close| of the last GAMMA_WINDOW candles
                        (studies: Garzarelli et al. 2014, Chung & Bellotti 2021);
       at most  ATR / 2, ATR = mean true range of the last ATR_WINDOW candles
                        (common indicator practice: swing +- ATR/2).
  3. Recency as for lines: horizontal_sr.RECENT_TRADING_DAYS (1M / 1W / 1D all history,
     60m / 15m 25 trading days, 5m 3).
  4. The same turning point seen on several timeframes (same kind, same price, pivots
     within one candle of the bigger timeframe) is ONE swing: it keeps the zone of its
     smallest timeframe (the finest candle) and lists every timeframe it is on.
  5. Zones that overlap merge into one zone. Each separate swing inside is one TOUCH.
  6. Facts per zone, no strength score (Ash 2026-10-18, section 4.4): touches, highs and
     lows inside (a mix = role reversal seen), timeframes, highest timeframe, first and
     last touch. Side from the reference close: R (zone above), S (below), AT (contains it);
     numbered R1 / S1 nearest first.
  7. Break (Ash 2026-10-26: "wick can say break"): price's side is the zone's side from the
     reference close (S / R / AT); a later wick past the far edge breaks it (from
     above: a low below the zone; from below: a high above it). The zone is kept (it can
     flip side), with the time and direction of the first break.

Pure functions: no file, R2 or database access.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr import (
    RECENT_TRADING_DAYS, TF_ORDER, _naive_ist, keep_recent, recent_since)

GAMMA_WINDOW = 20
ATR_WINDOW = 14
BAR_SPAN = {"1mo": pd.Timedelta(days=31), "1w": pd.Timedelta(days=7), "1d": pd.Timedelta(days=1),
            "60m": pd.Timedelta(hours=1), "15m": pd.Timedelta(minutes=15), "5m": pd.Timedelta(minutes=5)}
CANDLE_COLUMNS = ("time", "open", "high", "low", "close")
ZONE_COLUMNS = ["lo", "hi", "touches", "highs", "lows", "timeframes", "top_tf", "first_touch",
                "last_touch", "swings"]


def _check_candles(candles: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in CANDLE_COLUMNS if c not in candles.columns]
    if missing:
        raise ValueError(f"candles is missing column(s): {missing}")
    c = candles.loc[:, list(CANDLE_COLUMNS)].copy()
    c["time"] = _naive_ist(c["time"])
    return c.sort_values("time", kind="stable").reset_index(drop=True)


def depth_limits(candles: pd.DataFrame) -> pd.DataFrame:
    """Per candle: gamma (mean |close change|, last GAMMA_WINDOW) and half ATR (mean true
    range of the last ATR_WINDOW, halved). Uses only that candle and earlier ones."""
    c = _check_candles(candles)
    prev_close = c["close"].shift(1)
    tr = pd.concat([c["high"] - c["low"], (c["high"] - prev_close).abs(),
                    (c["low"] - prev_close).abs()], axis=1).max(axis=1)
    c["gamma"] = c["close"].diff().abs().rolling(GAMMA_WINDOW, min_periods=1).mean()
    c["atr_half"] = tr.rolling(ATR_WINDOW, min_periods=1).mean() / 2.0
    return c


def swing_zones(swings: pd.DataFrame, candles: pd.DataFrame, timeframe: str,
                since: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Rules 1-3 for one timeframe: one zone per swing. `since` (optional) keeps swings on
    or after it; default = the timeframe's recency from RECENT_TRADING_DAYS."""
    if timeframe not in BAR_SPAN:
        raise ValueError(f"unknown timeframe {timeframe!r}")
    cols = ["timeframe", "kind", "price", "lo", "hi", "pivot_time", "is_locked"]
    if swings is None or swings.empty:
        return pd.DataFrame(columns=cols)
    c = depth_limits(candles)
    sw = swings.loc[:, ["kind", "price", "pivot_time", "is_locked"]].copy()
    sw["pivot_time"] = _naive_ist(sw["pivot_time"])
    if since is None:
        since = recent_since(c["time"], RECENT_TRADING_DAYS.get(timeframe))
    sw = keep_recent(sw, since)
    at = sw.merge(c, left_on="pivot_time", right_on="time", how="left")
    if at["time"].isna().any():
        bad = at.loc[at["time"].isna(), "pivot_time"].iloc[0]
        raise ValueError(f"{timeframe}: no candle at swing time {bad}")
    rows = []
    for r in at.itertuples():
        if r.kind == "high":
            depth = r.high - max(r.open, r.close)
        else:
            depth = min(r.open, r.close) - r.low
        depth = min(max(depth, r.gamma), r.atr_half) if r.atr_half > 0 else max(depth, r.gamma)
        price = float(r.price)
        lo, hi = (price - depth, price) if r.kind == "high" else (price, price + depth)
        rows.append({"timeframe": timeframe, "kind": r.kind, "price": price, "lo": float(lo),
                     "hi": float(hi), "pivot_time": r.pivot_time, "is_locked": bool(r.is_locked)})
    return pd.DataFrame(rows, columns=cols)


def same_turns(per_timeframe: list[pd.DataFrame]) -> pd.DataFrame:
    """Rule 4: one row per turning point. Same kind, same price (2 decimals) and pivots
    within one candle of the bigger timeframe = the same swing; it keeps the zone of its
    smallest timeframe and lists all its timeframes (column `timeframes`)."""
    frames = [f for f in per_timeframe if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=["timeframe", "kind", "price", "lo", "hi", "pivot_time",
                                     "is_locked", "timeframes"])
    allz = pd.concat(frames, ignore_index=True)
    allz["_rank"] = allz["timeframe"].map(TF_ORDER.index)          # 0 = 1mo ... 5 = 5m
    allz = allz.sort_values(["_rank", "pivot_time"], ascending=[False, True], kind="stable")
    kept: list[dict] = []
    for r in allz.to_dict("records"):
        for k in kept:
            span = max(BAR_SPAN[k["timeframe"]], BAR_SPAN[r["timeframe"]])
            if (k["kind"] == r["kind"] and round(k["price"], 2) == round(r["price"], 2)
                    and abs(k["pivot_time"] - r["pivot_time"]) < span):
                k["_tfs"].add(r["timeframe"])
                break
        else:
            r["_tfs"] = {r["timeframe"]}
            kept.append(r)
    out = pd.DataFrame(kept)
    out["timeframes"] = out["_tfs"].map(lambda s: " ".join(t for t in TF_ORDER if t in s))
    return out.drop(columns=["_tfs", "_rank"]).sort_values("lo", kind="stable").reset_index(drop=True)


def merge_zones(turns: pd.DataFrame) -> pd.DataFrame:
    """Rule 5-6: overlapping zones merge; facts per zone."""
    if turns is None or turns.empty:
        return pd.DataFrame(columns=ZONE_COLUMNS)
    t = turns.sort_values(["lo", "hi"], kind="stable").reset_index(drop=True)
    groups, cur, cur_hi = [], [], None
    for i, r in t.iterrows():
        if cur and r["lo"] > cur_hi:
            groups.append(cur)
            cur, cur_hi = [], None
        cur.append(i)
        cur_hi = r["hi"] if cur_hi is None else max(cur_hi, r["hi"])
    groups.append(cur)
    rows = []
    for g in groups:
        z = t.loc[g]
        tfs = set(" ".join(z["timeframes"]).split())
        rows.append({
            "lo": float(z["lo"].min()), "hi": float(z["hi"].max()), "touches": len(z),
            "highs": int((z["kind"] == "high").sum()), "lows": int((z["kind"] == "low").sum()),
            "timeframes": " ".join(x for x in TF_ORDER if x in tfs),
            "top_tf": next(x for x in TF_ORDER if x in tfs),
            "first_touch": z["pivot_time"].min(), "last_touch": z["pivot_time"].max(),
            "swings": "; ".join(f"{r.price:,.2f} {r.kind} {r.pivot_time:%d %b %Y %H:%M} [{r.timeframes}]"
                                for r in z.sort_values("pivot_time").itertuples()),
        })
    return pd.DataFrame(rows, columns=ZONE_COLUMNS)


def zone_breaks(zones: pd.DataFrame, candles: pd.DataFrame) -> pd.DataFrame:
    """Rule 7: add `broken_at` (time) and `broken_dir` ('down' / 'up' / '').
    The side price is on: the zone's `side` when given (S = price above the zone, R = price
    below it, AT = inside; set by number_zones from the reference close), otherwise the first
    candle after the zone's last touch (its close above / below / inside the zone). From
    above, the first later low below the zone breaks it down; from below, the first later
    high above it breaks it up; from inside, whichever comes first."""
    out = zones.copy()
    out["broken_at"] = pd.NaT
    out["broken_dir"] = ""
    if out.empty:
        return out
    c = _check_candles(candles)
    t = c["time"].to_numpy()
    hi, lo, cl = c["high"].to_numpy(float), c["low"].to_numpy(float), c["close"].to_numpy(float)
    for i, z in out.iterrows():
        idx = np.flatnonzero(t > np.datetime64(z["last_touch"]))
        if idx.size == 0:
            continue
        side = z.get("side") if "side" in out.columns else None
        if side in ("S", "R", "AT"):
            from_above, from_below = side == "S", side == "R"
        else:
            first = idx[0]
            from_above, from_below = cl[first] > z["hi"], cl[first] < z["lo"]
        down = idx[lo[idx] < z["lo"]] if not from_below else idx[:0]
        up = idx[hi[idx] > z["hi"]] if not from_above else idx[:0]
        events = [(d[0], name) for d, name in ((down, "down"), (up, "up")) if d.size]
        if events:
            k, name = min(events)
            out.at[i, "broken_at"] = pd.Timestamp(t[k])
            out.at[i, "broken_dir"] = name
    return out


def number_zones(zones: pd.DataFrame, close: float) -> pd.DataFrame:
    """Side from `close`: R (zone above), S (below), AT (contains it); R1 / S1 nearest
    first. Returned top of the chart first."""
    if close is None or not math.isfinite(float(close)) or float(close) <= 0:
        raise ValueError(f"close must be a positive number, got {close!r}")
    c = float(close)
    out = zones.copy()
    out["side"] = np.where(out["lo"] > c, "R", np.where(out["hi"] < c, "S", "AT"))
    above = out[out["side"] == "R"].sort_values("lo")
    below = out[out["side"] == "S"].sort_values("hi", ascending=False)
    out["label"] = "AT"
    out.loc[above.index, "label"] = [f"R{k}" for k in range(1, len(above) + 1)]
    out.loc[below.index, "label"] = [f"S{k}" for k in range(1, len(below) + 1)]
    order = list(above.index[::-1]) + list(out.index[out["side"] == "AT"]) + list(below.index)
    return out.loc[order].reset_index(drop=True)


def hsr_zones(per_timeframe: dict, close: float, break_candles: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """All rules. per_timeframe: timeframe -> (swings, candles) known at the moment wanted.
    break_candles: candles to check breaks on (e.g. the 5m chart); None = no break check."""
    zs = [swing_zones(sw, cd, tf) for tf, (sw, cd) in per_timeframe.items()
          if sw is not None and cd is not None and not cd.empty]
    zones = number_zones(merge_zones(same_turns(zs)), close)
    if break_candles is not None:
        zones = zone_breaks(zones, break_candles)       # side from `close` (number_zones)
    return zones
