"""
EMA break watch (Ash, 2026-10-19) — EMAs are NOT support / resistance on Nifty
(EMA S&R study, SUPPORT_RESISTANCE.md §5): about 3 in 4 touches end in a close
through the EMA. So Fortuna watches the EMA as a level that is likely to BREAK,
tells Ash when price is near one, labels the break when it happens with the
breaking candle's size, and shows the odds from the instrument's own history.

Built for live trading (Ash: no noise that does not help):
  - Live timeframes 60m / 15m / 5m; EMAs 50 / 100 / 200 only. Breaks of
    EMA 5 / 13 / 26 mostly reverse (5m: only 6-25% still broken after 10 candles).
  - NEAR: |close - EMA| <= X (X = average candle move over the last 20 candles,
    the study's X). Flagged NEW only on the candle price first comes near.
  - BREAK: the latest candle closes through the EMA (the touch-episode rule of
    the study: line_reaction_study.find_episodes, wick touch, close = break).
  - Breaking candle SIZE = its range / average range of the last 20 candles:
      tall   >= 2x   (Bulkowski's "tall candle": 2x the average height)
      normal 1-2x
      small  < 1x
    Body % and close position were tested and add little (1-5 pts); size is
    what separates lasting breaks (study 2026-10-19, 5m/15m/60m EMA 50/100/200,
    10,685 breaks; chosen on 2022-24, same on 2025-26):
      tall   : still broken after 10 candles 50.3%, back within 3 candles 30.7% (2,380)
      normal : 32.4% / 46.0% (5,446)
      small  : 24.9% / 56.8% (2,859)
  - ODDS: computed live from the same candles' history for this timeframe x EMA
    x size, so they stay current and work on any instrument. A break counts in
    the odds only once 10 candles after it exist (otherwise its outcome is not
    known yet).
  - "still broken after 10 candles" / "back within 3 candles" are facts
    reported from history, not settings.

Pure functions, no I/O. Reuses the tested episode definitions from
indicator_common/line_reaction_study.py (single source of truth for touch / break / X)
and the TradingView-matched EMAs from trend_indicators/ema/ema.py.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.line_reaction_study import (
    DEFAULT_X_WINDOW,
    average_move,
    find_episodes,
)

WATCH_PERIODS = (50, 100, 200)
LIVE_TIMEFRAMES = ("60m", "15m", "5m")
TALL_X = 2.0
SMALL_X = 1.0
HELD_AFTER = 10          # "still broken after 10 candles"
FAILED_WITHIN = 3        # "back within 3 candles"
TIERS = ("tall", "normal", "small")


def size_tier(range_vs_avg: float) -> Optional[str]:
    """tall >= 2x average range, normal 1-2x, small < 1x; None if unknown."""
    if range_vs_avg is None or (isinstance(range_vs_avg, float) and math.isnan(range_vs_avg)):
        return None
    if range_vs_avg >= TALL_X:
        return "tall"
    if range_vs_avg >= SMALL_X:
        return "normal"
    return "small"


def _odds(breaks: pd.DataFrame) -> dict:
    n = len(breaks)
    if not n:
        return {"n": 0, "held_pct": None, "failed_pct": None}
    held = breaks["reclaimed_after"].isna() | (breaks["reclaimed_after"] > HELD_AFTER)
    failed = breaks["reclaimed_after"] <= FAILED_WITHIN
    return {"n": int(n), "held_pct": round(100.0 * held.mean(), 1),
            "failed_pct": round(100.0 * failed.mean(), 1)}


def history_odds(episodes: pd.DataFrame, candle_times: pd.Series) -> dict:
    """Odds per breaking-candle size from past breaks, plus the touch break rate.

    Only breaks with at least HELD_AFTER candles after them count (their outcome
    is known). Returns {"tall": {...}, "normal": {...}, "small": {...},
    "all": {...}, "touch_break_pct": float|None, "touches": int}."""
    out = {t: {"n": 0, "held_pct": None, "failed_pct": None} for t in TIERS}
    out["all"] = {"n": 0, "held_pct": None, "failed_pct": None}
    done = episodes[episodes["outcome"].isin(["bounce", "break"])] if not episodes.empty else episodes
    out["touches"] = int(len(done))
    out["touch_break_pct"] = (round(100.0 * (done["outcome"] == "break").mean(), 1) if len(done) else None)
    if done.empty:
        return out
    times = pd.Index(pd.to_datetime(candle_times))
    br = done[done["outcome"] == "break"].copy()
    end_pos = times.get_indexer(pd.to_datetime(br["end_time"]))
    candles_after = len(times) - 1 - end_pos
    br = br[candles_after > HELD_AFTER]
    br["tier"] = br["range_vs_avg"].map(size_tier)
    out["all"] = _odds(br)
    for t in TIERS:
        out[t] = _odds(br[br["tier"] == t])
    return out


def analyze_line(candles: pd.DataFrame, ema: pd.Series, period: int, timeframe: str) -> Optional[dict]:
    """State of one EMA on the latest candle: near / break (+ size, odds).

    candles: time, open, high, low, close (sorted). ema: one value per candle.
    Returns None when the EMA or X has no value yet on the latest candle."""
    if len(candles) < 2:
        return None
    x = average_move(candles["close"], DEFAULT_X_WINDOW)
    close, e, xv = float(candles["close"].iloc[-1]), ema.iloc[-1], x.iloc[-1]
    if pd.isna(e) or pd.isna(xv):
        return None
    e, xv = float(e), float(xv)
    prev_close, prev_e, prev_x = candles["close"].iloc[-2], ema.iloc[-2], x.iloc[-2]
    near = abs(close - e) <= xv
    prev_near = (not (pd.isna(prev_e) or pd.isna(prev_x))) and abs(float(prev_close) - float(prev_e)) <= float(prev_x)

    episodes = find_episodes(candles, ema, "wick", x_window=DEFAULT_X_WINDOW)
    odds = history_odds(episodes, candles["time"])

    brk = None
    if not episodes.empty:
        last = episodes.iloc[-1]
        if last["outcome"] == "break" and pd.Timestamp(last["end_time"]) == pd.Timestamp(candles["time"].iloc[-1]):
            tier = size_tier(last["range_vs_avg"])
            brk = {
                "direction": "below" if last["side"] == "support" else "above",
                "range_vs_avg": None if pd.isna(last["range_vs_avg"]) else round(float(last["range_vs_avg"]), 2),
                "tier": tier,
                "touches": int(last["touches"]),
                "odds": odds.get(tier) if tier else None,
            }
    return {
        "timeframe": timeframe,
        "period": period,
        "ema": round(e, 2),
        "close": round(close, 2),
        "distance_pts": round(close - e, 2),
        "distance_pct": round(100.0 * (close - e) / e, 2),
        "avg_move": round(xv, 2),
        "side": "above" if close > e else ("below" if close < e else "at"),
        "near": bool(near),
        "near_new": bool(near and not prev_near),
        "break": brk,
        "history": odds,
    }


def _odds_text(o: Optional[dict], tier: str) -> str:
    if not o or not o.get("n"):
        return f"History: no past {tier}-candle breaks yet."
    return (f"History, {tier}-candle breaks ({o['n']:,}): still broken after {HELD_AFTER} candles "
            f"{o['held_pct']:.0f}%, back within {FAILED_WITHIN} candles {o['failed_pct']:.0f}%.")


def line_texts(s: dict) -> tuple[list[str], list[str]]:
    """(texts, alerts) for one analyze_line result. Alerts: a tall-candle break
    (⚡) and a NEW near. Everything else is a text line only."""
    if s is None:
        return [], []
    tf, p = s["timeframe"], s["period"]
    texts, alerts = [], []
    b = s["break"]
    if b:
        tier = b["tier"] or "unknown-size"
        size = f"{b['range_vs_avg']}x avg" if b["range_vs_avg"] is not None else "size unknown"
        line = (f"{tf}: closed {b['direction']} EMA {p} ({s['ema']:,.2f}) on a "
                f"{tier.upper() if tier == 'tall' else tier} candle ({size}). "
                f"{_odds_text(b['odds'], tier)}")
        if tier == "tall":
            line = "⚡ " + line
            alerts.append(line)
        texts.append(line)
    elif s["near"]:
        h = s["history"]
        hist = (f" History {tf} EMA {p}: {h['touch_break_pct']:.0f}% of touches ended in a break "
                f"({h['touches']:,})." if h["touch_break_pct"] is not None else "")
        line = (f"{tf}: price {abs(s['distance_pts']):,.2f} {s['side']} EMA {p} ({s['ema']:,.2f}) — near "
                f"(avg candle move {s['avg_move']:,.2f}).{hist}")
        texts.append(line)
        if s["near_new"]:
            alerts.append(line)
    return texts, alerts
