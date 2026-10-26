"""
Manual check: the trendlines Ash could have drawn at given moments of one day
(Ash, 2026-10-20). Read-only first step of S&R type 3 — NOT the module yet.

Rules being tested (Ash, 2026-10-19/20; SUPPORT_RESISTANCE.md type 3 to be written):
  - Price scale linear; lines go through candle WICKS (highs for falling lines,
    lows for rising lines). No Zig Zag, no angles. x-axis = candle count.
  - POINT: a candle whose high is followed by a LOWER high on the next candle
    ("9:50 makes a lower high, so 9:45 counts"); known when the next candle closes.
    The last known candle may also be used as a point (live, "not confirmed").
    Rising lines mirror this with lows (next candle makes a higher low).
  - TOP: the highest high in the look-back window (lowest low for rising lines);
    the fall starts there. Lines may start at the top or at ANY later point
    (Ash's lines on 19 Oct start at 09:15, 09:35 and 10:30).
  - A line runs through two points (the 2nd lower than the 1st). It is drawable
    only if no candle CLOSED beyond it between its two points. After its 2nd
    point, the first close beyond it is its BREAK (wicks through are allowed).
  - TOUCH: a point (or the last candle) whose wick is within the tolerance of the
    line. Tolerance = MEDIAN |close - previous close| of the last 20 candles at
    the cut-off (median, so a few huge opening candles do not widen it; Ash
    2026-10-20: a high 23 pts short of the line at 10:20 is not a touch).
  - A line's 1st point must be a TURN: a high above (or equal to) the candle before
    and above the candle after (Ash's starts 09:15, 09:35, 10:30). Its 2nd point and
    touches are any points.
  - Between the 1st and 2nd point price must move away from the line: some CLOSE more
    than the tolerance away (step 2, 2026-10-21; was wick), and the 2nd point is at
    least 2 candles after the 1st. If the 2nd point is a merged similar-highs run, the
    run's candles are not "between" (step 2b): gap and move-away count up to the run's
    first candle. So stair-step candles do not make lines; candles between the two
    points are not touches. After the 2nd point every point within the
    tolerance is a touch (11:10, 11:15 and 11:20 can all touch one line).
  - SIMILAR HIGHS (step 1, Ash 2026-10-21): points on consecutive candles within the
    equal-swing tolerance (zigzag_settings; 5m 0.05%) of the run's first point are one point, at the run's newest RED candle
    (rising lines: GREEN). If the newest is not red, the run waits and is labelled
    (green at a falling line = possible reversal / sideways / trap).
  - Lines with the same touches are one line, shown through its first two points.
  - ENTRY candles: touches from a line's 2nd point onward while it is unbroken.
  - CHAIN (step 3, Ash 2026-10-21): line 1 from the top to the first bounce candle (red /
    green); at each entry the steepest line ending there, steeper than the line it bounced
    off, becomes line 2 / 3; an entry on line 2 or 3 gives a 'potential vertical candidate'
    from the entry to the next point; entries labelled 'entry n of 3'; a new highest high
    (lowest low) starts a new chain; other lines stay listed as context.
  - Each ENTRY also shows the nearest horizontal S&R in the trade's direction (S1 for
    falling lines, R1 for rising) on the TRADING LADDER: every timeframe's (1M / 1W / 1D /
    60m / 15m / 5m) Zig Zag lines from candles finished by the entry candle's close,
    merged within 0.05%, with the timeframes each line is on (2026-10-23).
  - Similar highs never merge across days (2026-10-23).
  - AFTER THE BREAK (step 4, 2026-10-23): per chain line, after its break: RETEST (wick
    back within the tolerance, close stays on the broken side), FAILED BREAK (close back
    on the original side), BROKE AGAIN; TREND CHANGE CONFIRMED at the first candle where
    every chain line (line 1 included) stands broken.
  - Look-back window: last N trading days known at the cut-off (5m 3, 15m / 60m 25).

Only candles CLOSED by each cut-off time are used: what could be drawn then.

Chart (2026-10-23): the run also writes logs/trendline_test_logs/trendline_chart_<date>.html
for the LAST --at time (open it in a browser; TradingView Lightweight Charts 4.1.3 from
unpkg, data inside the page): candles of the window, chain lines and vertical candidates
extended to the last candle, E1/E2/E3 entry arrows, break dots, the trading ladder's
horizontal S/R lines in the window's price range (orange solid = on the chart's own
timeframe, which Ash trades on; grey dashed = higher timeframes only; each labelled with
its timeframes), the 5m Zig Zag (0.2% / 10).

Read-only: reads stored candles (5m + the ladder's other timeframes) through the indicator reader; in memory;
writes only backend/logs/trendline_test_logs/trendline_check.log
(overwritten each run; first line = the command).

Multi-day run (2026-10-23, "is it right every day"): --last N (the last N trading days
up to --date) or --dates D1 D2 ...; per day a short summary (lines, entries, draft exits,
trend change) as of 15:30, the chain detail, and a chart trendline_chart_<date>.html.

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check --date 2026-10-19 --at 09:50 10:35 11:25 15:30 --side down
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check --date 2026-10-22 --last 10 --side both
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr import (
    timeframe_lines,
    trading_ladder,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
    get_equal_tolerance,
    get_zigzag_settings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import (
    find_zigzag_swings,
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
INTRADAY = {"5m": 5, "15m": 15, "60m": 60}
LADDER_TFS = ("1mo", "1w", "1d", "60m", "15m", "5m")   # trading ladder (SUPPORT_RESISTANCE §4)
DAILY_DOMAIN = "indices"                               # 1d / 1w / 1mo for Nifty
LOOKBACK_TRADING_DAYS = {"5m": 3, "15m": 25, "60m": 25}   # missing = all history
TOL_WINDOW = 20
MIN_GAP = 2            # 2nd point at least this many candles after the 1st
DEFAULT_DATE = "2026-10-19"
DEFAULT_AT = ("09:50", "10:35", "11:25", "11:40", "15:30")
DEFAULT_CANDLES = ("09:15", "11:35")
_IST = "Asia/Kolkata"


# --- pure helpers ---------------------------------------------------------------

def naive_ist(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s)
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_convert(_IST).dt.tz_localize(None)
    return s


def known_at(candles: pd.DataFrame, cutoff: pd.Timestamp, minutes: int) -> pd.DataFrame:
    """Candles that have closed by `cutoff` (start + candle length <= cutoff)."""
    return candles[candles["time"] + pd.Timedelta(minutes=minutes) <= cutoff].reset_index(drop=True)


def tolerance(close: pd.Series, window: int = TOL_WINDOW) -> float:
    """Median |close - previous close| over the last `window` candles."""
    return float(close.iloc[-(window + 1):].astype(float).diff().abs().iloc[-window:].median())


def window_start(times: pd.Series, trading_days: Optional[int]) -> int:
    """Row index of the first candle of the last `trading_days` trading days (0 = all)."""
    if not trading_days:
        return 0
    days = times.dt.normalize()
    keep = sorted(days.unique())[-trading_days:]
    return int(np.argmax(days.isin(keep).to_numpy()))


def points(ext: np.ndarray, start: int, falling: bool) -> list[int]:
    """Candles from `start` whose next candle has a lower high (falling) / higher low (rising).
    The last candle is added as a live point."""
    out = [i for i in range(start, len(ext) - 1)
           if (ext[i + 1] < ext[i] if falling else ext[i + 1] > ext[i])]
    last = len(ext) - 1
    if last >= start:
        out.append(last)
    return out


def turn_points(ext: np.ndarray, start: int, falling: bool) -> list[int]:
    """Turns from `start`: a high above (or equal to) the candle before and above the
    candle after (mirror for lows). Only a turn can be a line's 1st point (Ash's
    starts on 19 Oct: 09:15, 09:35, 10:30)."""
    out = []
    for i in range(start, len(ext) - 1):
        prev_ok = i == 0 or (ext[i] >= ext[i - 1] if falling else ext[i] <= ext[i - 1])
        next_ok = ext[i + 1] < ext[i] if falling else ext[i + 1] > ext[i]
        if prev_ok and next_ok:
            out.append(i)
    return out


def merge_similar(ext: np.ndarray, opn: np.ndarray, close: np.ndarray, pts: list[int],
                  turns: set, equal_pct: float, falling: bool, day: Optional[np.ndarray] = None):
    """Step 1 (Ash, 2026-10-21): points on consecutive candles whose highs (lows) are
    EQUAL — within `equal_pct` % of the run's first point, the equal-swing tolerance
    already used for double / triple tops (5m 0.05%) — are ONE point, at the run's newest RED candle
    for falling lines (GREEN for rising lines) — the bounce that starts the move.
    If the run's newest candle is not red (green), the run waits (no point yet) and is
    labelled: a green candle at a falling line = possible reversal / sideways / trap.
    The merged point is a turn when the run's first candle is a turn.
    Returns (points, turns, runs) — runs = list of dicts for the report."""
    want = (lambda k: close[k] < opn[k]) if falling else (lambda k: close[k] > opn[k])
    groups: list[list[int]] = []
    for k in pts:
        g = groups[-1] if groups else None
        same_day = day is None or day[k] == day[g[-1]] if g else True   # never across days (Ash, 2026-10-23)
        if g and same_day and k == g[-1] + 1 and abs(ext[k] - ext[g[0]]) <= ext[g[0]] * equal_pct / 100.0:
            g.append(k)
        else:
            groups.append([k])
    out_pts, out_turns, runs = [], set(turns), []
    for g in groups:
        if len(g) == 1:
            out_pts.append(g[0])
            continue
        coloured = [k for k in g if want(k)]
        newest = g[-1]
        if want(newest):
            keep = newest
        else:
            keep = None                      # option (a): wait for the bounce candle
        runs.append({"members": g, "keep": keep, "newest": newest})
        if keep is None:
            continue
        out_pts.append(keep)
        if g[0] in turns:
            out_turns.add(keep)
    return out_pts, out_turns, runs


def top_index(ext: np.ndarray, first: int, falling: bool) -> int:
    """Highest high (lowest low) in the window; the latest one if equal."""
    seg = ext[first:]
    best = seg.max() if falling else seg.min()
    return first + int(np.flatnonzero(seg == best)[-1])


def build_line(ext: np.ndarray, close: np.ndarray, pts: list[int], i: int, j: int,
               tol: float, falling: bool, run_start: Optional[dict] = None) -> Optional[dict]:
    """Line through points i and j; None if a candle closed beyond it between them, or
    if price did not move away from the line between i and j (no bounce)."""
    slope = (ext[j] - ext[i]) / (j - i)
    idx = np.arange(i, len(ext))
    line = ext[i] + slope * (idx - i)
    beyond = (close[i:] > line) if falling else (close[i:] < line)
    if beyond[1: j - i + 1].any():
        return None
    # step 2b (Ash, 2026-10-21): if the 2nd point is a merged similar-highs run, the
    # run's candles are not "between" — gap and move-away are measured up to the run start
    j_from = (run_start or {}).get(j, j)
    if j_from - i < MIN_GAP:            # step 2: 2nd point at least 2 candles after the 1st
        return None
    # step 2 (Ash, 2026-10-21): price must CLOSE more than tol away from the line
    # between the two points (close, not wick: line 4 11:20 -> 11:30, the 11:25 close
    # was 17.10 below the line while its wick was only 9.55 below)
    away = (close[i:] < line - tol) if falling else (close[i:] > line + tol)
    if not away[1: j_from - i].any():
        return None
    after = np.flatnonzero(beyond[j - i + 1:])
    brk = None if after.size == 0 else int(j + 1 + after[0])
    end = brk if brk is not None else len(ext) - 1
    touches = []
    for k in pts:
        if k < i or k > end or i < k < j:      # between the two points: no touches (price moved away there)
            continue
        L = ext[i] + slope * (k - i)
        if k in (i, j) or abs(ext[k] - L) <= tol:
            touches.append({"i": k, "price": float(ext[k]), "line": float(L), "gap": float(ext[k] - L)})
    return {"i": i, "j": j, "slope": float(slope), "touches": touches, "break": brk,
            "line_now": float(ext[i] + slope * (len(ext) - 1 - i))}


def lines_for(c: pd.DataFrame, first: int, tol: float, falling: bool, equal_pct: float):
    """(top, points, lines, runs) — all drawable lines from the top onward, one per touch set."""
    ext = c["high" if falling else "low"].to_numpy(dtype=float)
    close = c["close"].to_numpy(dtype=float)
    opn = c["open"].to_numpy(dtype=float)
    top = top_index(ext, first, falling)
    raw = points(ext, top, falling)
    pts, turns, runs = merge_similar(ext, opn, close, raw, set(turn_points(ext, top, falling)), equal_pct, falling,
                                     c["time"].dt.normalize().to_numpy())
    lower = (lambda a, b: ext[b] < ext[a]) if falling else (lambda a, b: ext[b] > ext[a])
    run_start = {r["keep"]: r["members"][0] for r in runs if r["keep"] is not None}
    best: dict = {}
    for a_pos, a in enumerate(pts):
        if a not in turns:                       # a line starts only at a turn
            continue
        for b in pts[a_pos + 1:]:
            if not lower(a, b):
                continue
            l = build_line(ext, close, pts, a, b, tol, falling, run_start)
            if l is None:
                continue
            key = tuple(t["i"] for t in l["touches"])
            if key not in best or (l["j"], l["i"]) < (best[key]["j"], best[key]["i"]):
                best[key] = l      # same touches: keep the line through its first two points
    return top, pts, list(best.values()), runs, turns, run_start


# --- step 3: the chain (Ash, 2026-10-21) ------------------------------------------

def _line_at(ext: np.ndarray, i: int, j: int, k: int) -> float:
    return float(ext[i] + (ext[j] - ext[i]) / (j - i) * (k - i))


def _came_back(ext: np.ndarray, i: int, j: int, falling: bool) -> bool:
    """Price came back to the 2nd point: its high is above the lowest high between the
    two points (falling) / its low below the highest low between (rising). Rejects the
    next candle of a straight drop as a 2nd point (09:25 after 09:15 on 19 Oct)."""
    between = ext[i + 1: j]
    if between.size == 0:
        return False
    return ext[j] > between.min() if falling else ext[j] < between.max()


def candle_facts(c: pd.DataFrame, k: int, window: int = TOL_WINDOW) -> dict:
    """Body % of range and range vs the average range of the last `window` candles."""
    o, h, lo, cl = (float(c[x].iloc[k]) for x in ("open", "high", "low", "close"))
    rng = h - lo
    avg = float((c["high"] - c["low"]).iloc[max(0, k - window + 1): k + 1].mean())
    return {"body_pct": 100.0 * abs(cl - o) / rng if rng > 0 else 0.0,
            "range_x": rng / avg if avg > 0 else float("nan")}


def completed_by(df: pd.DataFrame, tf: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Candles of `tf` finished by `cutoff`: intraday by start + length; 1d / 1w / 1mo
    when their day / week / month is before the cut-off's (works whatever day the
    stored candle is stamped with)."""
    if tf in INTRADAY:
        return known_at(df, cutoff, INTRADAY[tf])
    t, cut = df["time"], pd.Timestamp(cutoff)
    if tf == "1d":
        done = t.dt.normalize() < cut.normalize()
    elif tf == "1w":
        iso, ciso = t.dt.isocalendar(), cut.isocalendar()
        done = (iso["year"] * 100 + iso["week"]) < (ciso[0] * 100 + ciso[1])
    else:
        done = (t.dt.year * 12 + t.dt.month) < (cut.year * 12 + cut.month)
    return df[done.to_numpy()].reset_index(drop=True)


_SWING_CACHE: dict = {}


def _swings(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Zig Zag swings of `df`, cached by timeframe, last candle time and length."""
    key = (tf, len(df), df["time"].iloc[-1] if len(df) else None)
    if key not in _SWING_CACHE:
        dev, depth = get_zigzag_settings(tf)
        _SWING_CACHE[key] = find_zigzag_swings(df[["time", "high", "low"]], dev, depth)
    return _SWING_CACHE[key]


# Zig Zag warm-up for the ladder (speed, 2026-10-23): intraday timeframes read only their
# last N trading days (lines use 5m 3 / 15m 25 / 60m 25 days). Same ladder as full history
# on 14 checked cut-offs; 1D / 1W / 1M keep all history.
WARMUP_CANDLES = {"5m": 30 * 75, "15m": 120 * 25, "60m": 120 * 7}
_LADDER_CACHE: dict = {}


def ladder_at(series: dict, cutoff: pd.Timestamp, close: float) -> pd.DataFrame:
    """Trading ladder (all timeframes, merged within the 5m tolerance, numbered from
    `close`) from candles finished by `cutoff` only. `series`: timeframe -> candles;
    a missing timeframe is skipped."""
    key = (pd.Timestamp(cutoff), round(float(close), 2),
           tuple((tf, len(df)) for tf, df in sorted(series.items()) if df is not None))
    if key in _LADDER_CACHE:
        return _LADDER_CACHE[key]
    frames = []
    for tf in LADDER_TFS:
        df = series.get(tf)
        if df is None or df.empty:
            continue
        known = completed_by(df, tf, cutoff)
        if tf in WARMUP_CANDLES:
            known = known.iloc[-WARMUP_CANDLES[tf]:].reset_index(drop=True)
        if len(known) < 3:
            continue
        sw = _swings(known, tf)
        if not sw.empty:
            frames.append(timeframe_lines(sw, tf, known["time"], get_equal_tolerance(tf), None, close))
    _LADDER_CACHE[key] = trading_ladder(frames, close, get_equal_tolerance("5m"))
    return _LADDER_CACHE[key]


def nearest_level(c: pd.DataFrame, k: int, tf: str, falling: bool,
                  series: Optional[dict] = None) -> Optional[dict]:
    """Nearest horizontal S&R line in the trade's direction at candle k (falling lines /
    put: S1 below the close; rising / call: R1 above) on the TRADING LADDER: every
    timeframe's Zig Zag lines from candles finished by candle k's close only
    (Ash, 2026-10-23; Bulkowski 'top trap'). Without `series` only `tf` is used."""
    cutoff = c["time"].iloc[k] + pd.Timedelta(minutes=INTRADAY[tf])
    close = float(c["close"].iloc[k])
    lines = ladder_at({**(series or {}), tf: c.iloc[: k + 1]}, cutoff, close)
    side = lines[lines["label"] == ("S1" if falling else "R1")]
    if side.empty:
        return None
    r = side.iloc[0]
    return {"label": r["label"], "price": float(r["price"]), "dist": float(r["price"]) - close,
            "pivot": r["pivot_time"], "timeframes": r["timeframes"]}


def build_chain(c: pd.DataFrame, top: int, pts: list[int], turns: set, run_start: dict,
                falling: bool, max_entries: int = 3) -> dict:
    """Walk the points after the top in time order, as Ash draws while candles come:
      line 1   = top -> the first point that is a bounce candle (red / green) whose line is
                 drawable; redrawn if it breaks before the next entry
      ENTRY    = a bounce candle touching the newest unbroken chain line (from its 2nd point
                 on); line 1's 2nd point is entry 1. Labelled 'entry n of 3'.
      line 2/3 = at an entry, the steepest drawable line ending at that entry, starting at a
                 turn after the chain's 1st point, steeper than the line it bounced off
      vertical = at every entry: 'potential vertical candidate' (on line 1: 'early') from
                 the entry to the next point at least 2 candles later that gives a drawable
                 line; a newer entry replaces a candidate still waiting
      max 4 lines (3 chain lines + vertical candidates). Tolerance at each point = the
      median candle move known at that candle."""
    ext = c["high" if falling else "low"].to_numpy(dtype=float)
    close = c["close"].to_numpy(dtype=float)
    opn = c["open"].to_numpy(dtype=float)
    bounce = (lambda k: close[k] < opn[k]) if falling else (lambda k: close[k] > opn[k])
    beyond = (lambda k, L: close[k] > L) if falling else (lambda k, L: close[k] < L)
    lower = (lambda a, b: ext[b] < ext[a]) if falling else (lambda a, b: ext[b] > ext[a])
    tol_at = lambda k: tolerance(c["close"].iloc[: k + 1])
    last = len(c) - 1

    def make(i: int, j: int) -> Optional[dict]:
        if not lower(i, j) or not _came_back(ext, i, j, falling):
            return None
        l = build_line(ext, close, pts, i, j, tol_at(j), falling, run_start)
        if l is None:
            return None
        l["kind"] = ""
        return l

    def broken_by(l: dict, k: int) -> bool:
        return l["break"] is not None and l["break"] <= k

    lines: list[dict] = []
    verticals: list[dict] = []
    entries: list[dict] = []
    pending_vertical: Optional[int] = None
    after = [p for p in pts if p > top]
    for p in after:
        if pending_vertical is not None and p - pending_vertical[0] >= MIN_GAP:
            # the next point at least 2 candles after the entry that gives a drawable line
            v = build_line(ext, close, pts, pending_vertical[0], p, tol_at(p), falling, run_start)
            if v is not None and lower(pending_vertical[0], p):
                v["kind"] = pending_vertical[1]
                verticals.append(v)
                pending_vertical = None
        if not bounce(p):
            continue
        active = next((l for l in reversed(lines) if not broken_by(l, p - 1)), None)
        if active is None:                       # line 1 (first, or redrawn after a break)
            l1 = make(top, p)
            if l1 is None:
                continue
            l1["kind"] = "line 1" if not lines else "line 1 (redrawn)"
            lines = [l1]
            entries.append({"i": p, "line": l1, "n": len(entries) + 1})
            pending_vertical = (p, "potential vertical candidate (early, on line 1)")
            continue
        if p <= active["j"]:
            continue
        tol = tol_at(p)
        L = _line_at(ext, active["i"], active["j"], p)
        if abs(ext[p] - L) > tol or beyond(p, L):
            continue
        k = len(entries) + 1
        entries.append({"i": p, "line": active, "n": k, "gap": float(ext[p] - L)})
        on_index = lines.index(active)
        pending_vertical = (p, "potential vertical candidate" if on_index >= 1
                            else "potential vertical candidate (early, on line 1)")
        if len(lines) < 3:
            cands = []
            for a in sorted(t for t in turns if lines[0]["i"] <= t < p):
                l = make(a, p)
                if l is not None and abs(l["slope"]) > abs(active["slope"]):
                    cands.append(l)
            if cands:
                nxt = max(cands, key=lambda l: abs(l["slope"]))
                nxt["kind"] = f"line {len(lines) + 1}"
                lines.append(nxt)
    if pending_vertical is not None:
        verticals.append({"waiting": pending_vertical[0], "kind": pending_vertical[1]})
    return {"lines": lines, "verticals": verticals, "entries": entries, "max_entries": max_entries}


def after_break(c: pd.DataFrame, lines: list[dict], falling: bool) -> dict:
    """Step 4 (Ash, 2026-10-22): what each chain line does after its break. Falling line
    (rising mirrors): the break is a close ABOVE it, so the line may now act as support.
      retest       = a later candle whose LOW comes back within the tolerance of the line
                     and closes on the broken side (consecutive candles = one retest)
      failed break = a later close back BELOW the line (the line is in force again);
                     a close above after that = 'broke again'
      trend change = the first candle at which every chain line (line 1 included) stands
                     broken; not confirmed while any of them is unbroken or failed.
    Tolerance at each candle = the median candle move known at that candle."""
    opp = c["low" if falling else "high"].to_numpy(dtype=float)
    ext = c["high" if falling else "low"].to_numpy(dtype=float)
    close = c["close"].to_numpy(dtype=float)
    over = (lambda k, L: close[k] > L) if falling else (lambda k, L: close[k] < L)
    near = (lambda k, L, t: opp[k] <= L + t) if falling else (lambda k, L, t: opp[k] >= L - t)
    last = len(c) - 1
    out, broken_at = [], []          # broken_at: per line, candles where it stands broken
    for l in lines:
        ev, standing = [], set()
        b = l["break"]
        if b is not None:
            state, ev = "broken", [{"what": "break", "i": b, "line": _line_at(ext, l["i"], l["j"], b)}]
            standing.add(b)
            for k in range(b + 1, last + 1):
                L = _line_at(ext, l["i"], l["j"], k)
                if state == "broken":
                    if not over(k, L):
                        state = "failed"
                        ev.append({"what": "failed break", "i": k, "line": L})
                        continue
                    standing.add(k)
                    if near(k, L, tolerance(c["close"].iloc[: k + 1])):
                        if ev[-1]["what"] == "retest" and ev[-1]["to"] == k - 1:
                            ev[-1]["to"] = k
                        else:
                            ev.append({"what": "retest", "i": k, "to": k, "line": L})
                elif over(k, L):
                    state = "broken"
                    standing.add(k)
                    ev.append({"what": "broke again", "i": k, "line": L})
        out.append({"line": l, "events": ev})
        broken_at.append(standing)
    confirmed = None
    if lines:
        common = set.intersection(*broken_at)
        confirmed = min(common) if common else None
    return {"lines": out, "confirmed": confirmed}


def proven_break(c: pd.DataFrame, l: dict, falling: bool, tf: str = "5m",
                 series: Optional[dict] = None) -> Optional[dict]:
    """DRAFT exit rule (Ash, 2026-10-23, to be tested in the exits step): the first candle
    from the line's first break on that
      1. closes beyond the line by MORE than the tolerance (median candle move),
      2. is a candle in the break direction (green when a falling line breaks), and
      3. is not rejected at a horizontal line: no trading-ladder line (known then) between
         its close and its wick (falling: close < level <= high).
    Returns {i, gap, tol, rejected: [(candle, level), ...]} or None."""
    if l.get("break") is None:
        return None
    ext = c["high" if falling else "low"].to_numpy(dtype=float)
    o, h, lo, cl = (c[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close"))
    rejected = []
    for k in range(l["break"], len(c)):
        L = _line_at(ext, l["i"], l["j"], k)
        gap = cl[k] - L if falling else L - cl[k]
        tol = tolerance(c["close"].iloc[: k + 1])
        if gap <= tol or not (cl[k] > o[k] if falling else cl[k] < o[k]):
            continue
        cutoff = c["time"].iloc[k] + pd.Timedelta(minutes=INTRADAY[tf])
        lad = ladder_at({**(series or {}), tf: c.iloc[: k + 1]}, cutoff, float(cl[k]))
        p = lad["price"].to_numpy(dtype=float)
        hit = p[(p > cl[k]) & (p <= h[k])] if falling else p[(p < cl[k]) & (p >= lo[k])]
        if hit.size:
            rejected.append((k, float(hit[0])))
            continue
        return {"i": k, "gap": float(gap), "tol": tol, "rejected": rejected}
    return {"i": None, "rejected": rejected}


def report_exits(c: pd.DataFrame, ch: dict, falling: bool, tf: str = "5m",
                 series: Optional[dict] = None) -> list[str]:
    """Per entry: its vertical line's proven break (draft exit) and the points made."""
    out = ["    EXIT CANDIDATES (DRAFT: proven break of the entry's vertical line = close beyond by more than "
           "the tolerance + candle in the break direction + not rejected at a horizontal line)"]
    verts = {v["i"]: v for v in ch["verticals"] if "waiting" not in v}
    for e in ch["entries"]:
        lab = f"entry {e['n']}" + ("" if e["n"] <= ch["max_entries"] else " (over limit)")
        v = verts.get(e["i"])
        ent = float(c["close"].iloc[e["i"]])
        if v is None:
            out.append(f"        {lab:<22} {_t(c, e['i'])} close {ent:,.2f}: no vertical line yet")
            continue
        pb = proven_break(c, v, falling, tf, series)
        rej = "; ".join(f"{_t(c, k)} rejected at {p:,.2f}" for k, p in (pb or {}).get("rejected", []))
        if not pb or pb["i"] is None:
            out.append(f"        {lab:<22} {_t(c, e['i'])} close {ent:,.2f}: vertical {_t(c, v['i'])}->{_t(c, v['j'])} "
                       f"not proven broken yet" + (f"   ({rej})" if rej else ""))
            continue
        k = pb["i"]
        ex = float(c["close"].iloc[k])
        pts = (ent - ex) if falling else (ex - ent)
        out.append(f"        {lab:<22} {_t(c, e['i'])} close {ent:,.2f} -> EXIT {_t(c, k)} close {ex:,.2f}   "
                   f"{pts:+,.2f} pts   (vertical {_t(c, v['i'])}->{_t(c, v['j'])}; close {pb['gap']:+.2f} beyond, "
                   f"tolerance {pb['tol']:.2f})" + (f"   [{rej}]" if rej else ""))
    return out


def standing_break(events: list[dict]) -> Optional[int]:
    """Candle of the break still standing at the end (break / broke again with no failed
    break after it); None when the line is unbroken or back in force."""
    if not events or events[-1]["what"] == "failed break":
        return None
    for e in reversed(events):
        if e["what"] in ("break", "broke again"):
            return e["i"]
    return None


def _short(kind: str) -> str:
    """'line 2' -> 'L2', 'line 1 (redrawn)' -> 'L1', vertical candidates -> 'V'."""
    if kind.startswith("line "):
        return "L" + kind.split()[1]
    return "V"


def report_after_break(c: pd.DataFrame, ab: dict, falling: bool) -> list[str]:
    side, opp = ("above", "low") if falling else ("below", "high")
    out = [f"    AFTER THE BREAK (chain lines; break = close {side} the line, which may now act as "
           f"{'support' if falling else 'resistance'})"]
    if not ab["lines"]:
        return out + ["        no chain line yet"]
    last = len(c) - 1
    for x in ab["lines"]:
        l = x["line"]
        if not x["events"]:
            gap = c["close"].iloc[last] - l["line_now"]
            out.append(f"        {l['kind']:<18} unbroken, line now {l['line_now']:,.2f} "
                       f"(last close {gap:+,.2f} from it)")
            continue
        out.append(f"        {l['kind']}   T1 {_t(c, l['i'])} -> T2 {_t(c, l['j'])}")
        for e in x["events"]:
            k = e["i"]
            if e["what"] == "retest":
                span = _t(c, k) if e["to"] == k else f"{_t(c, k)}-{_t(c, e['to'])}"
                lo = c[opp].iloc[k: e["to"] + 1]
                best = lo.min() if falling else lo.max()
                out.append(f"            retest       {span:<13} {opp} {best:,.2f}  line {e['line']:,.2f}  "
                           f"gap {best - e['line']:+.2f}  (closes stayed {side})")
            else:
                out.append(f"            {e['what']:<12} {_t(c, k):<13} close {c['close'].iloc[k]:,.2f}  "
                           f"line {e['line']:,.2f}  gap {c['close'].iloc[k] - e['line']:+.2f}")
    if ab["confirmed"] is not None:
        out.append(f"        TREND CHANGE CONFIRMED at {_t(c, ab['confirmed'])}: every chain line stands broken")
    else:
        open_ = [x["line"]["kind"] for x in ab["lines"]
                 if not x["events"] or x["events"][-1]["what"] == "failed break"]
        out.append("        trend change: not confirmed"
                   + (f" -- still in force: {', '.join(open_)}" if open_ else ""))
    return out


def report_chain(c: pd.DataFrame, ch: dict, falling: bool, tf: str = "5m",
                 series: Optional[dict] = None) -> list[str]:
    ext = "high" if falling else "low"
    bc = "red" if falling else "green"
    out = [f"    CHAIN (from the top; lines 1-3 + vertical candidates; entries = {bc} bounce on the newest unbroken line)"]
    if not ch["lines"]:
        return out + ["        no chain line yet"]
    for l in ch["lines"] + [v for v in ch["verticals"] if "waiting" not in v]:
        status = ("unbroken, line now " + f"{l['line_now']:,.2f}" if l["break"] is None
                  else f"BROKEN by the {_t(c, l['break'])} close {c['close'].iloc[l['break']]:,.2f}")
        out.append(f"        {l['kind']:<46} {_t(c, l['i'])} {c[ext].iloc[l['i']]:,.2f} -> {_t(c, l['j'])} "
                   f"{c[ext].iloc[l['j']]:,.2f}   slope {l['slope']:+.2f}   {status}")
    for v in ch["verticals"]:
        if "waiting" in v:
            out.append(f"        {v['kind']}  from {_t(c, v['waiting'])}: waiting for the next point")
    for e in ch["entries"]:
        f = candle_facts(c, e["i"])
        n = e["n"]
        lab = f"entry {n} of {ch['max_entries']}" if n <= ch["max_entries"] else f"entry {n} (over the {ch['max_entries']} limit)"
        gap = f"gap {e['gap']:+.2f}" if "gap" in e else "its 2nd point"
        out.append(f"        {lab:<24} {_t(c, e['i'])} {ext} {c[ext].iloc[e['i']]:,.2f}  on {e['line']['kind']} ({gap})   "
                   f"body {f['body_pct']:.0f}% of range, range {f['range_x']:.2f}x the 20-candle average")
        lv = nearest_level(c, e["i"], tf, falling, series)
        tol = tolerance(c["close"].iloc[: e["i"] + 1])
        if lv is None:
            out.append(f"{'':<33}nearest {'S1' if falling else 'R1'} (trading ladder): none")
        else:
            out.append(f"{'':<33}nearest {lv['label']} {lv['price']:,.2f} [{lv['timeframes']}] "
                       f"({lv['dist']:+,.2f} pts from the entry close, {abs(lv['dist']) / tol:.1f}x the candle move; "
                       f"swing {lv['pivot']:%a %d %b %Y %H:%M})")
    out += report_after_break(c, after_break(c, ch["lines"], falling), falling)
    verts = [v for v in ch["verticals"] if "waiting" not in v]
    if verts:
        vb = report_after_break(c, after_break(c, verts, falling), falling)
        out.append("    AFTER THE BREAK, vertical candidates (drawn up to the standing break)")
        out += [x for x in vb[1:] if "trend change" not in x.lower()]
    return out + report_exits(c, ch, falling, tf, series)


# --- chart (Ash, 2026-10-23: "i understand visually") ------------------------------

LWC_URL = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"
CHAIN_COLOURS = {"line 1": "#2e7d32", "line 1 (redrawn)": "#2e7d32", "line 2": "#00acc1", "line 3": "#8e24aa"}
VERTICAL_COLOUR = "#e91e63"
OWN_TF_COLOUR = "#ff6d00"      # horizontal lines on the chart's own timeframe (Ash trades on them)
OTHER_TF_COLOUR = "#757575"    # lines from higher timeframes only, dashed


def _epoch(t) -> int:
    """IST wall-clock time as a UTC timestamp, so the chart axis shows IST."""
    return int((pd.Timestamp(t) - pd.Timestamp("1970-01-01")).total_seconds())


def chart_data(c: pd.DataFrame, first: int, sides, tf: str, series: Optional[dict] = None,
               cutoff: Optional[pd.Timestamp] = None) -> dict:
    """Everything the chart draws, as plain JSON: candles of the window, chain lines and
    vertical candidates extended to the last candle, entries, breaks, and the trading
    ladder's horizontal lines in the window's price range (each with its timeframes)."""
    win = c.iloc[first:]
    last = len(c) - 1
    data = {"candles": [{"time": _epoch(r.time), "open": float(r.open), "high": float(r.high),
                         "low": float(r.low), "close": float(r.close)} for r in win.itertuples()],
            "lines": [], "markers": [], "levels": []}
    for side in sides:
        falling = side == "down"
        ext = c["high" if falling else "low"].to_numpy(dtype=float)
        tol = tolerance(c["close"])
        top, pts, _lines, _runs, turns, run_start = lines_for(c, first, tol, falling, get_equal_tolerance(tf))
        ch = build_chain(c, top, pts, turns, run_start, falling)
        verts = [v for v in ch["verticals"] if "waiting" not in v]
        ab = after_break(c, ch["lines"], falling)
        abv = after_break(c, verts, falling)
        lo_w, hi_w = float(win["low"].min()), float(win["high"].max())
        above, below = ("aboveBar", "belowBar") if falling else ("belowBar", "aboveBar")
        mk = lambda k, pos, colour, shape, text: data["markers"].append(
            {"time": _epoch(c["time"].iloc[k]), "position": pos, "color": colour, "shape": shape, "text": text})
        for x in ab["lines"] + abv["lines"]:
            l = x["line"]
            if l["i"] < first:
                continue
            chain = l["kind"] in CHAIN_COLOURS
            colour = CHAIN_COLOURS.get(l["kind"], VERTICAL_COLOUR)
            short = _short(l["kind"])
            # chain lines stay extended to the last candle (role reversal); a vertical
            # candidate runs through failed breaks up to its standing break
            sb = standing_break(x["events"])
            end = last if (chain or sb is None) else sb
            while end > l["j"] and not (lo_w <= _line_at(ext, l["i"], l["j"], end) <= hi_w):
                end -= 1                      # keep the price scale readable
            data["lines"].append({"name": l["kind"], "colour": colour,
                                  "dashed": "early" in l["kind"],
                                  "points": [{"time": _epoch(c["time"].iloc[l["i"]]), "value": float(ext[l["i"]])},
                                             {"time": _epoch(c["time"].iloc[end]),
                                              "value": _line_at(ext, l["i"], l["j"], end)}]})
            name = ("early vertical" if "early" in l["kind"] else "vertical") if not chain else l["kind"].replace(" (redrawn)", " redrawn")
            mk(l["i"], above, colour, "circle", f"{name} T1")
            mk(l["j"], above, colour, "circle", f"{short} T2")
            for e in x["events"]:
                if e["i"] < first:
                    continue
                word = {"break": "break", "retest": "retest", "failed break": "failed",
                        "broke again": "break again"}[e["what"]]
                if e["i"] == sb and not chain:          # the break that held: stands out
                    mk(e["i"], below, colour, "arrowUp" if falling else "arrowDown", f"{short} BREAK")
                else:
                    mk(e["i"], below, colour, "square", f"{short} {word}")
        if ab["confirmed"] is not None and ab["confirmed"] >= first:
            mk(ab["confirmed"], below, "#000000", "arrowUp" if falling else "arrowDown", "TREND CHANGE")
        vmap = {v["i"]: v for v in verts}
        for e in ch["entries"]:
            v = vmap.get(e["i"])
            pb = proven_break(c, v, falling, tf, series) if v is not None else None
            if pb and pb["i"] is not None and pb["i"] >= first:
                mk(pb["i"], below, "#000000", "arrowUp" if falling else "arrowDown",
                   f"EXIT {_short(e['line']['kind'])}-Entry {_t(c, e['i'])}")
            for k, _p in (pb or {}).get("rejected", []):
                if k >= first:
                    mk(k, below, "#9e9e9e", "square", "rejected")
            lab = _short(e["line"]["kind"]) + "-Entry" + ("" if e["n"] <= ch["max_entries"] else " (over 3)")
            mk(e["i"], above, "#d32f2f" if falling else "#2e7d32", "arrowDown" if falling else "arrowUp", lab)
    dev, depth = get_zigzag_settings(tf)
    swings = find_zigzag_swings(c[["time", "high", "low"]], dev, depth)
    start_t = c["time"].iloc[first]
    data["zigzag"] = [{"time": _epoch(r.pivot_time), "value": float(r.price)}
                      for r in swings.itertuples() if pd.Timestamp(r.pivot_time) >= start_t]
    data["zigzag_label"] = f"Zig Zag {dev}% / {depth} (last swing not locked)"
    close = float(c["close"].iloc[-1])
    if cutoff is None:
        cutoff = c["time"].iloc[-1] + pd.Timedelta(minutes=INTRADAY[tf])
    hl = ladder_at({**(series or {}), tf: c}, cutoff, close)
    lo, hi = float(win["low"].min()), float(win["high"].max())
    pad = (hi - lo) * 0.05
    data["levels"] = [{"price": float(r.price), "label": r.label, "timeframes": r.timeframes,
                       "own": tf in str(r.timeframes).split()}
                      for r in hl.itertuples() if lo - pad <= r.price <= hi + pad]
    data["level_tf"] = tf
    data["markers"].sort(key=lambda m: m["time"])
    _spread_markers(data["markers"], [x["time"] for x in data["candles"]])
    day0 = c["time"].iloc[-1].normalize()
    data["focus_from"] = _epoch(c["time"][c["time"] >= day0].iloc[0])
    return data


def _spread_markers(markers: list[dict], times: list[int], gap: int = 3) -> None:
    """Labels on bars less than `gap` candles apart overlap; move such a label to the
    other side of its bar when that side is free there (several labels on one bar stack
    by themselves)."""
    pos = {t: n for n, t in enumerate(times)}
    last = {"aboveBar": {}, "belowBar": {}}             # side -> {bar: True}
    flip = {"aboveBar": "belowBar", "belowBar": "aboveBar"}
    def crowded(side, n):
        return any(abs(n - b) < gap and b != n for b in last[side])
    for m in markers:
        n = pos.get(m["time"])
        if n is None:
            continue
        side = m["position"]
        if crowded(side, n) and not crowded(flip[side], n) and n not in last[flip[side]]:
            m["position"] = side = flip[side]
        last[side][n] = True


def chart_html(data: dict, title: str) -> str:
    import json
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --bg:#ffffff; --fg:#1f2937; --muted:#6b7280; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:14px system-ui, sans-serif; }}
  header {{ padding:10px 16px; }} header small {{ color:var(--muted); }}
  html, body {{ height:100%; }} body {{ display:flex; flex-direction:column; }}
  #chart {{ flex:1; min-height:300px; position:relative; }}
  #legend span {{ display:inline-block; margin-right:14px; white-space:nowrap; }}
</style></head><body>
<header><b>{title}</b><br><small id="legend"></small></header>
<div id="chart"></div>
<script src="{LWC_URL}"></script>
<script>
const D = {json.dumps(data)};
const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#1f2937', fontSize: 11 }},
  grid: {{ vertLines: {{ color: '#f1f1f1' }}, horzLines: {{ color: '#f1f1f1' }} }},
  timeScale: {{ timeVisible: true, secondsVisible: false }},
  rightPriceScale: {{ borderVisible: false }}, autoSize: true,
  localization: {{ locale: 'en-IN' }} }});
const candles = chart.addCandlestickSeries({{ upColor:'#26a69a', downColor:'#ef5350', borderVisible:false,
  wickUpColor:'#26a69a', wickDownColor:'#ef5350' }});
candles.setData(D.candles);
candles.setMarkers(D.markers);
for (const lv of D.levels) {{
  candles.createPriceLine({{ price: lv.price, color: lv.own ? '{OWN_TF_COLOUR}' : '{OTHER_TF_COLOUR}',
    lineWidth: lv.own ? 2 : 1, lineStyle: lv.own ? 0 : 2, axisLabelVisible: true,
    title: lv.label + ' ' + lv.timeframes }});
}}
const legend = document.getElementById('legend');
if (D.zigzag && D.zigzag.length > 1) {{
  const zz = chart.addLineSeries({{ color: '#2962ff', lineWidth: 1, priceLineVisible: false,
    lastValueVisible: false, crosshairMarkerVisible: false }});
  zz.setData(D.zigzag);
  legend.insertAdjacentHTML('beforeend', `<span style="color:#2962ff">&#9473; ${{D.zigzag_label}}</span>`);
}}
for (const ln of D.lines) {{
  const s = chart.addLineSeries({{ color: ln.colour, lineWidth: 2, lineStyle: ln.dashed ? 2 : 0,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }});
  s.setData(ln.points);
  legend.insertAdjacentHTML('beforeend', `<span style="color:${{ln.colour}}">&#9473; ${{ln.name}}</span>`);
}}
legend.insertAdjacentHTML('beforeend', '<span>&#9679; T1 / T2 = the two points of each line &middot; L1/L2/L3 = line 1/2/3, V = vertical &middot; &#9632; = break / retest / failed break &middot; Lx-Entry = entry on line x</span>');
legend.insertAdjacentHTML('beforeend', `<span style="color:{OWN_TF_COLOUR}">&#9473; horizontal S/R on ${{D.level_tf}}</span>`
  + `<span style="color:{OTHER_TF_COLOUR}">&#9476; horizontal S/R from other timeframes only</span>`
  + '<span>trading ladder, rule A by side of price &middot; scroll left for earlier days</span>');
chart.timeScale().fitContent();
if (D.focus_from) {{ const i0 = D.candles.findIndex(c => c.time >= D.focus_from);
  chart.timeScale().setVisibleLogicalRange({{ from: i0 - 6, to: D.candles.length + 4 }}); }}
</script></body></html>
"""


# --- report ---------------------------------------------------------------------

def _t(c: pd.DataFrame, i: int) -> str:
    same_day = c["time"].iloc[i].normalize() == c["time"].iloc[-1].normalize()
    return f"{c['time'].iloc[i]:%H:%M}" if same_day else f"{c['time'].iloc[i]:%a %d %b %H:%M}"


def _colour(c: pd.DataFrame, i: int) -> str:
    o, cl = c["open"].iloc[i], c["close"].iloc[i]
    return "green" if cl > o else "red" if cl < o else "doji"


def _line_text(c: pd.DataFrame, l: dict, falling: bool) -> list[str]:
    ext = "high" if falling else "low"
    last = len(c) - 1
    status = "unbroken" if l["break"] is None else f"BROKEN by the {_t(c, l['break'])} close {c['close'].iloc[l['break']]:,.2f}"
    out = [f"    line {_t(c, l['i'])} {c[ext].iloc[l['i']]:,.2f} -> {_t(c, l['j'])} {c[ext].iloc[l['j']]:,.2f}"
           f"   slope {l['slope']:+.2f} pts/candle   touches {len(l['touches'])}   {status}"
           + (f"   line now {l['line_now']:,.2f}" if l["break"] is None else "")]
    for t in l["touches"]:
        role = "1st point" if t["i"] == l["i"] else "2nd point" if t["i"] == l["j"] else "touch"
        live = "   (last candle, not confirmed)" if t["i"] == last else ""
        out.append(f"        {role:<9} {_t(c, t['i'])}  {ext} {t['price']:,.2f}  line {t['line']:,.2f}  gap {t['gap']:+.2f}{live}")
    return out


def report_side(c: pd.DataFrame, first: int, tol: float, falling: bool, show: int,
                equal_pct: float, tf: str = "5m", series: Optional[dict] = None,
                compact: bool = False) -> list[str]:
    ext = "high" if falling else "low"
    name = "FALLING lines through highs (resistance)" if falling else "RISING lines through lows (support)"
    top, pts, lines, runs, turns, run_start = lines_for(c, first, tol, falling, equal_pct)
    good = [l for l in lines if len(l["touches"]) >= 3]
    unbroken = sorted([l for l in good if l["break"] is None], key=lambda l: abs(l["slope"]))
    broken = sorted([l for l in good if l["break"] is not None], key=lambda l: l["break"])
    last = len(c) - 1
    live = sorted([l for l in lines if l["break"] is None and l["touches"][-1]["i"] == last],
                  key=lambda l: (-len(l["touches"]), abs(l["slope"])))
    out = [f"  {name}",
           f"    {'top (highest high)' if falling else 'bottom (lowest low)'} in window: {_t(c, top)} {c[ext].iloc[top]:,.2f}",
           f"    points from there ({len(pts)}): " + ", ".join(f"{_t(c, i)} {c[ext].iloc[i]:,.2f}" for i in pts)]
    good_colour, bad_colour = ("red", "green") if falling else ("green", "red")
    out.append(f"    SIMILAR {ext.upper()}S merged (consecutive candles within {equal_pct}% -> newest {good_colour}): {len(runs)}")
    for r in runs:
        members = ", ".join(f"{_t(c, k)} {c[ext].iloc[k]:,.2f} {_colour(c, k)}" for k in r["members"])
        if r["keep"] is not None:
            out.append(f"        x{len(r['members'])}: {members}  ->  point {_t(c, r['keep'])} ({good_colour} bounce)")
        else:
            out.append(f"        x{len(r['members'])}: {members}  ->  WAITING, newest {_t(c, r['newest'])} is "
                       f"{_colour(c, r['newest'])} at the line: possible reversal / sideways / trap")
    out += report_chain(c, build_chain(c, top, pts, turns, run_start, falling), falling, tf, series)
    if compact:                       # multi-day run: chain, after-break and exits only
        return out
    out.append(f"    LIVE: unbroken lines the last candle touches (entry moment): {len(live)}"
               + (f", showing {show}" if len(live) > show else ""))
    for l in live[:show]:
        out += _line_text(c, l, falling)
    out.append(f"    UNBROKEN LINES, 3+ touches (shallow to steep): {len(unbroken)}"
               + (f", showing {show}" if len(unbroken) > show else ""))
    for l in unbroken[:show]:
        out += _line_text(c, l, falling)
    out.append(f"    BROKEN LINES, 3+ touches (earliest break first): {len(broken)}"
               + (f", showing {show}" if len(broken) > show else ""))
    for l in broken[:show]:
        out += _line_text(c, l, falling)
    entries: dict[int, list[str]] = {}
    for l in good + live:
        for t in l["touches"]:
            if t["i"] >= l["j"] and (l["break"] is None or t["i"] < l["break"]):
                entries.setdefault(t["i"], []).append(f"{_t(c, l['i'])}->{_t(c, l['j'])}")
    out.append("    ENTRY CANDLES (touch from a line's 2nd point on, line unbroken then): "
               + (", ".join(f"{_t(c, k)} [{'; '.join(sorted(set(v)))}]" for k, v in sorted(entries.items())) or "none"))
    return out


def candle_table(candles: pd.DataFrame, date: str, frm: str, to: str) -> list[str]:
    d = candles[(candles["time"] >= pd.Timestamp(f"{date} {frm}")) & (candles["time"] <= pd.Timestamp(f"{date} {to}"))]
    out = [f"CANDLES {date} {frm}-{to}  (hp = point for falling lines: next high lower; "
           "lp = point for rising lines: next low higher)",
           f"  {'time':<6} {'open':>10} {'high':>10} {'low':>10} {'close':>10}  colour  points"]
    hi, lo = candles["high"].to_numpy(), candles["low"].to_numpy()
    for k in d.index:
        nxt = k + 1 < len(candles)
        tags = []
        if nxt and hi[k + 1] < hi[k]:
            tags.append("hp")
        if nxt and lo[k + 1] > lo[k]:
            tags.append("lp")
        r = candles.loc[k]
        colour = "green" if r["close"] > r["open"] else "red" if r["close"] < r["open"] else "doji"
        out.append(f"  {r['time']:%H:%M}  {r['open']:>10,.2f} {r['high']:>10,.2f} {r['low']:>10,.2f} "
                   f"{r['close']:>10,.2f}  {colour:<6}  {' '.join(tags)}")
    return out


def run(candles: pd.DataFrame, tf: str, date: str, ats, sides, show: int,
        chart_path: Optional[Path] = None, series: Optional[dict] = None,
        compact: bool = False) -> list[str]:
    """Report lines; with chart_path also writes the chart of the LAST --at time.
    `series`: other timeframes' candles (timeframe -> candles) for the trading ladder."""
    minutes = INTRADAY[tf]
    out = []
    last_view = None
    for at in ats:
        cutoff = pd.Timestamp(f"{date} {at}")
        c = known_at(candles, cutoff, minutes)
        out += ["", "=" * 110, f"AT {cutoff:%a %d %b %Y %H:%M}  ({tf}, candles closed by then)", "=" * 110]
        if len(c) < TOL_WINDOW + 3 or c["time"].iloc[-1].normalize() != cutoff.normalize():
            out.append("  no candles of that day yet (or not enough history)")
            continue
        tol = tolerance(c["close"])
        first = window_start(c["time"], LOOKBACK_TRADING_DAYS.get(tf))
        last = c.iloc[-1]
        out.append(f"  last candle {last['time']:%H:%M}  O {last['open']:,.2f} H {last['high']:,.2f} "
                   f"L {last['low']:,.2f} C {last['close']:,.2f}")
        out.append(f"  touch tolerance (median candle move, last {TOL_WINDOW}) = {tol:.2f} pts   "
                   f"window from {c['time'].iloc[first]:%a %d %b %Y %H:%M}")
        for s in sides:
            out.append("")
            out += report_side(c, first, tol, s == "down", show, get_equal_tolerance(tf), tf, series, compact)
        last_view = (c, first, cutoff)
    if chart_path is not None and last_view is not None:
        c, first, cutoff = last_view
        chart_path.write_text(chart_html(chart_data(c, first, sides, tf, series, cutoff),
                                         f"Nifty 50 {tf} trendlines - as of {cutoff:%a %d %b %Y %H:%M}"),
                              encoding="utf-8")
        out += ["", f"Chart (as of {cutoff:%a %d %b %Y %H:%M}) saved to: {chart_path}"]
    return out


def day_summary(candles: pd.DataFrame, tf: str, date: str, sides,
                series: Optional[dict] = None, at: str = "15:30") -> list[str]:
    """One block per day for the multi-day run: chain lines (T1 -> T2), entries, draft
    exits and trend change, as Fortuna sees them at `at`."""
    cutoff = pd.Timestamp(f"{date} {at}")
    c = known_at(candles, cutoff, INTRADAY[tf])
    head = f"  {cutoff:%a %d %b %Y}"
    if len(c) < TOL_WINDOW + 3 or c["time"].iloc[-1].normalize() != cutoff.normalize():
        return [head + "   no candles that day"]
    first = window_start(c["time"], LOOKBACK_TRADING_DAYS.get(tf))
    tol = tolerance(c["close"])
    day = c[c["time"].dt.normalize() == cutoff.normalize()]
    out = [head + f"   open {day['open'].iloc[0]:,.2f}  close {day['close'].iloc[-1]:,.2f}  "
                  f"({day['close'].iloc[-1] - day['open'].iloc[0]:+,.2f})"]
    for s in sides:
        falling = s == "down"
        top, pts, _l, _r, turns, run_start = lines_for(c, first, tol, falling, get_equal_tolerance(tf))
        ch = build_chain(c, top, pts, turns, run_start, falling)
        name = "DOWN (falling lines, put entries)" if falling else "UP (rising lines, call entries)"
        out.append(f"    {name}: {'top' if falling else 'bottom'} {_t(c, top)}")
        if not ch["lines"]:
            out.append("      no chain line")
            continue
        out.append("      lines:   " + "; ".join(f"{l['kind']} {_t(c, l['i'])}->{_t(c, l['j'])}"
                                              + ("" if l["break"] is None else f" (broken {_t(c, l['break'])})")
                                              for l in ch["lines"]))
        verts = {v["i"]: v for v in ch["verticals"] if "waiting" not in v}
        rows = []
        today = [e for e in ch["entries"] if c["time"].iloc[e["i"]].normalize() == cutoff.normalize()]
        before = len(ch["entries"]) - len(today)
        for e in today:
            lab = f"{_short(e['line']['kind'])}-Entry {_t(c, e['i'])}" + ("" if e["n"] <= ch["max_entries"] else " (over 3)")
            v = verts.get(e["i"])
            pb = proven_break(c, v, falling, tf, series) if v is not None else None
            if pb and pb["i"] is not None:
                ent, ex = float(c["close"].iloc[e["i"]]), float(c["close"].iloc[pb["i"]])
                lab += f" -> exit {_t(c, pb['i'])} {(ent - ex) if falling else (ex - ent):+,.2f}"
            else:
                lab += " -> no exit yet"
            rows.append(lab)
        out.append("      entries: " + ("; ".join(rows) if rows else "none today")
                   + (f"   (+{before} on earlier days of the window)" if before else ""))
        ab = after_break(c, ch["lines"], falling)
        out.append("      trend change: " + (f"confirmed {_t(c, ab['confirmed'])}" if ab["confirmed"] is not None
                                            else "not confirmed"))
    return out


def main() -> None:
    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Trendlines that could be drawn at given times (read-only check).")
    p.add_argument("--key", default=NIFTY_KEY)
    p.add_argument("--timeframe", default="5m", choices=list(INTRADAY))
    p.add_argument("--date", default=DEFAULT_DATE, help="YYYY-MM-DD")
    p.add_argument("--at", nargs="+", default=list(DEFAULT_AT), help="clock times HH:MM (candles closed by then)")
    p.add_argument("--side", default="down", choices=["down", "up", "both"])
    p.add_argument("--daily-domain", default=DAILY_DOMAIN, help="domain for 1d / 1w / 1mo (indices | universe)")
    p.add_argument("--show", type=int, default=10, help="lines printed per list")
    p.add_argument("--last", type=int, default=0,
                   help="multi-day run: the last N trading days up to --date (chart per day, short log)")
    p.add_argument("--dates", nargs="+", default=None, help="multi-day run: these dates YYYY-MM-DD")
    p.add_argument("--candles", nargs=2, default=list(DEFAULT_CANDLES), metavar=("FROM", "TO"),
                   help="candle table range HH:MM HH:MM")
    args = p.parse_args()

    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])
    report = [command.strip(), f"Trendline check, run at {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"instrument {args.key}  timeframe {args.timeframe}  date {args.date}  "
              f"look-back {LOOKBACK_TRADING_DAYS.get(args.timeframe, 'all')} trading days",
              "Lines through wicks between two points (point = next candle makes a lower high / higher low); "
              "drawable if no close beyond between the points; first close beyond after = break; "
              "touch tolerance = median candle move.", ""]
    res = read_for_indicators(args.key, "universe_intraday", args.timeframe)
    if not res.ok:
        report.append(f"NOT OK -- {res.error}")
    else:
        candles = res.df.rename(columns={"ts": "time"})[["time", "open", "high", "low", "close"]].copy()
        candles["time"] = naive_ist(candles["time"])
        candles = candles.reset_index(drop=True)
        sides = ["down", "up"] if args.side == "both" else [args.side]
        series = {}   # other timeframes for the trading ladder (horizontal S&R)
        for tf in LADDER_TFS:
            if tf == args.timeframe:
                continue
            r = read_for_indicators(args.key, "universe_intraday" if tf in INTRADAY else args.daily_domain, tf)
            if not r.ok:
                report.append(f"trading ladder: {tf} not loaded, left out -- {r.error}")
                continue
            d = r.df.rename(columns={"ts": "time"})[["time", "open", "high", "low", "close"]].copy()
            d["time"] = naive_ist(d["time"])
            series[tf] = d.sort_values("time").reset_index(drop=True)
        report.append("trading ladder timeframes: " + " ".join(t for t in LADDER_TFS if t in series or t == args.timeframe))
        backend_dir_ = Path(__file__).resolve().parents[4]
        chart_dir = backend_dir_ / "logs" / "trendline_test_logs"
        chart_dir.mkdir(parents=True, exist_ok=True)
        chart_path = chart_dir / f"trendline_chart_{args.date}.html"
        days = list(args.dates or [])
        if args.last:
            all_days = sorted(candles["time"].dt.normalize().unique())
            upto = [d for d in all_days if d <= pd.Timestamp(args.date)]
            days = [f"{pd.Timestamp(d):%Y-%m-%d}" for d in upto[-args.last:]]
        try:
            if days:
                report.append(f"MULTI-DAY RUN: {len(days)} days, as of 15:30 each day (chart per day: "
                              f"trendline_chart_<date>.html)")
                detail = []
                for n, d in enumerate(days, 1):
                    t0 = datetime.now()
                    report += day_summary(candles, args.timeframe, d, sides, series)
                    detail += run(candles, args.timeframe, d, ["15:30"], sides, args.show,
                                  chart_dir / f"trendline_chart_{d}.html", series, compact=True)
                    print(f"  day {n}/{len(days)} {d} done in {(datetime.now() - t0).total_seconds():.0f} s", flush=True)
                report += ["", "DETAIL PER DAY"] + detail
            else:
                report += candle_table(candles, args.date, *args.candles)
                report += run(candles, args.timeframe, args.date, args.at, sides, args.show, chart_path, series)
        except ValueError as exc:
            report.append(f"NOT OK -- {exc}")

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "trendline_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "trendline_check.log"
    text = "\n".join(report)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
