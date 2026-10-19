"""
Line reaction study: how price behaves when it comes to a line (Ash, 2026-10-19).

Shared helper (moved to indicator_common/ 2026-10-19): used by the EMA S&R study
(studies/ema_sr/) and the live EMA break watch (trend_indicators/ema_break/), so the
live alert uses exactly the definitions that were tested.

Generic and pure (no file, R2 or database access): the line can be an EMA, a
shifted control line, a horizontal S&R level, RSI 55 later. The caller passes
candles and one line value per candle; this module returns one row per
"touch episode".

Touch episode (Ash, 2026-10-19 — "how many touches does it take"):
  - ARMED when a candle is fully clear of the line on one side
    (low > line = price above, the line is SUPPORT; high < line = price below,
    the line is RESISTANCE).
  - STARTS on the first later candle that touches the line:
      touch_mode "wick"  : the wick reaches the line (support: low <= line)
      touch_mode "close" : the close comes within X of the line
  - Every candle in the episode that touches counts one touch.
  - ENDS on the first candle that closes:
      BREAK  : beyond the line (support: close < line)     -- Ash's rule, close = break
      BOUNCE : at least X away on the original side (support: close >= line + X)
    Break is checked first. An episode can end on its first candle.
  - After a BOUNCE the side stays; after a BREAK the side flips. Either way the
    next episode needs a fully clear candle first.
  - Still unresolved at the end of the data: outcome "open".

X (Ash, 2026-10-19, option a): the average candle move, the method of the S&R
studies (Garzarelli et al. 2014; Chung & Bellotti 2021 — mean |close - previous
close|). The studies averaged the whole series; here it is the mean over the
last `x_window` candles known at that candle, so it follows the price scale
(Nifty ~1,000 -> ~25,000) and never uses future candles.

Recorded per episode: start/end time, side, touches, candles, outcome, line
and X at the end, how many candles price stayed clear before the episode
(first touch after a long time away = Brooks' "gap bar"), the deciding
candle's strength (body % of range, range vs the average range, close position
in the range) and, for a break, after how many candles price first closed
back on the original side (reclaimed_after; NaN = never). Labels only — no
thresholds on these are applied here.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

EPISODE_COLUMNS = [
    "start_time", "end_time", "side", "touches", "candles", "outcome",
    "line_start", "line_end", "x_end", "close_end", "candles_clear_before",
    "body_pct", "range_vs_avg", "close_pos", "reclaimed_after",
]
TOUCH_MODES = ("wick", "close")
DEFAULT_X_WINDOW = 20


def average_move(close: pd.Series, window: int = DEFAULT_X_WINDOW) -> pd.Series:
    """X per candle: mean |close - previous close| over the last `window` candles."""
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window!r}")
    return close.astype(float).diff().abs().rolling(window, min_periods=window).mean()


def _validate(candles: pd.DataFrame, line: pd.Series) -> None:
    missing = {"time", "open", "high", "low", "close"} - set(candles.columns)
    if missing:
        raise ValueError(f"candles is missing columns: {sorted(missing)}")
    if len(line) != len(candles):
        raise ValueError(f"line has {len(line)} values for {len(candles)} candles")
    if not candles["time"].is_monotonic_increasing:
        raise ValueError("candles must be sorted by time")


def find_episodes(candles: pd.DataFrame, line: pd.Series, touch_mode: str = "wick",
                  x: Optional[pd.Series] = None,
                  x_window: int = DEFAULT_X_WINDOW) -> pd.DataFrame:
    """Touch episodes of `candles` at `line` (one value per candle, NaN = no line yet)."""
    _validate(candles, line)
    if touch_mode not in TOUCH_MODES:
        raise ValueError(f"touch_mode must be one of {TOUCH_MODES}, got {touch_mode!r}")

    t = candles["time"].to_numpy()
    o = candles["open"].to_numpy(dtype=float)
    h = candles["high"].to_numpy(dtype=float)
    lo = candles["low"].to_numpy(dtype=float)
    c = candles["close"].to_numpy(dtype=float)
    ln = np.asarray(line, dtype=float)
    xs = (average_move(candles["close"], x_window) if x is None else x).to_numpy(dtype=float)
    rng = h - lo
    avg_rng = pd.Series(rng).rolling(x_window, min_periods=x_window).mean().to_numpy()

    rows: list[dict] = []
    side: Optional[str] = None      # "support" (price above) / "resistance" (price below)
    armed = False
    clear_run = 0                   # fully clear candles since the last episode ended
    ep: Optional[dict] = None

    for i in range(len(c)):
        L, X = ln[i], xs[i]
        if math.isnan(L) or math.isnan(X):
            continue

        if ep is None:
            # Touch is checked first: in "close" mode a candle can be clear of the
            # line by its wick yet close within X (that is a touch). In "wick" mode
            # a clear candle can never touch, so the order changes nothing there.
            if armed and _touches(side, touch_mode, h[i], lo[i], c[i], L, X):
                ep = {"start_time": t[i], "side": side, "touches": 0, "candles": 0,
                      "line_start": L, "candles_clear_before": clear_run}
            else:
                if lo[i] > L:
                    side, armed = "support", True
                    clear_run += 1
                elif h[i] < L:
                    side, armed = "resistance", True
                    clear_run += 1
                continue

        # inside an episode (including its first candle)
        ep["candles"] += 1
        if _touches(ep["side"], touch_mode, h[i], lo[i], c[i], L, X):
            ep["touches"] += 1
        outcome = _outcome(ep["side"], c[i], L, X)
        if outcome is None:
            continue

        r = rng[i]
        ep.update({
            "end_time": t[i], "outcome": outcome, "line_end": L, "x_end": X, "close_end": c[i],
            "body_pct": 100.0 * abs(c[i] - o[i]) / r if r > 0 else 0.0,
            "range_vs_avg": r / avg_rng[i] if avg_rng[i] and not math.isnan(avg_rng[i]) else math.nan,
            "close_pos": (c[i] - lo[i]) / r if r > 0 else 0.5,
            "reclaimed_after": _reclaimed_after(ep["side"], c, ln, i) if outcome == "break" else math.nan,
        })
        rows.append(ep)
        if outcome == "break":
            side = "resistance" if ep["side"] == "support" else "support"
        ep, armed, clear_run = None, False, 0

    if ep is not None:   # unresolved at the end of the data
        ep.update({"end_time": pd.NaT, "outcome": "open", "line_end": math.nan, "x_end": math.nan,
                   "close_end": math.nan, "body_pct": math.nan, "range_vs_avg": math.nan,
                   "close_pos": math.nan, "reclaimed_after": math.nan})
        rows.append(ep)

    out = pd.DataFrame(rows, columns=EPISODE_COLUMNS)
    for col in ("start_time", "end_time"):
        out[col] = pd.to_datetime(out[col])
    return out


def _touches(side: str, mode: str, high: float, low: float, close: float, L: float, X: float) -> bool:
    if mode == "wick":
        return low <= L if side == "support" else high >= L
    return close <= L + X if side == "support" else close >= L - X


def _outcome(side: str, close: float, L: float, X: float) -> Optional[str]:
    if side == "support":
        if close < L:
            return "break"
        if close >= L + X:
            return "bounce"
    else:
        if close > L:
            return "break"
        if close <= L - X:
            return "bounce"
    return None


def _reclaimed_after(side: str, c: np.ndarray, ln: np.ndarray, i: int) -> float:
    """Candles after a break until the first close back on the original side (NaN = never)."""
    for j in range(i + 1, len(c)):
        if math.isnan(ln[j]):
            continue
        back = c[j] >= ln[j] if side == "support" else c[j] <= ln[j]
        if back:
            return float(j - i)
    return math.nan


def touch_table(episodes: pd.DataFrame, max_k: int = 5) -> pd.DataFrame:
    """'After k touches, what happened': for k = 1..max_k, the episodes that
    reached k touches, and how many ended on exactly k touches by bounce or break
    or went on to more touches. The last row (k = max_k) counts "max_k or more"."""
    done = episodes[episodes["outcome"].isin(["bounce", "break"])]
    rows = []
    for k in range(1, max_k + 1):
        last = k == max_k
        reached = done[done["touches"] >= k]
        here = reached if last else reached[reached["touches"] == k]
        n = len(reached)
        bounce = int((here["outcome"] == "bounce").sum())
        brk = int((here["outcome"] == "break").sum())
        rows.append({
            "touches": f"{k}+" if last else str(k),
            "reached": n,
            "bounce": bounce,
            "break": brk,
            "more_touches": 0 if last else n - bounce - brk,
            "bounce_pct": round(100.0 * bounce / n, 1) if n else math.nan,
            "break_pct": round(100.0 * brk / n, 1) if n else math.nan,
        })
    return pd.DataFrame(rows)
