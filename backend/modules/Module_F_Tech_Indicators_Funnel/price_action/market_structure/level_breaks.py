"""
Level breaks (plan step 4, decided 16 Oct 2026).

For each level (a swing high or low, active from the time it became known),
scan the candles that follow and record what price did there. Every event is
a LABEL, not a trade decision: whether to trade is decided later, when all
indicators and chart patterns are combined. Low-weight labels (attempts,
retests, failures) are kept on purpose -- markets change and they may become
high-weight indicators later.

Events per level, each fires once (high level shown; low levels mirror it):
  attempt   : first candle whose HIGH goes above the level (wick beyond)
  confirmed : first candle whose CLOSE is above the level  <- structure break
              (used for BOS/CHoCH in step 5)
  gap       : the confirming candle OPENED above the level (strong break)
  cleared   : from the confirming candle on, first candle fully outside the
              tolerance band (LOW above level * (1 + tol)) = the "white space"
              Bulkowski requires before a throwback counts (16 Oct 2026).
              Not cleared yet = price is hugging the level; that is NOT the
              strong no-retest case.
  retest    : after cleared, first later candle whose LOW comes back to
              within tolerance of the level (level * (1 + tol)). The candle
              right after a break overlapping the band is not a retest.
  outcome   : 'held'   = after a retest, a candle closes back above the level
              'failed' = after confirmed, a candle closes below
                         level * (1 - tol) before any hold (busted break:
                         a signal on the opposite side)
              None     = not resolved yet (no retest so far = the stronger
                         case per Bulkowski)
              Held is NOT final (Ash, 16 Oct 2026: 22534.40 held Fri 9 Oct,
              failed Mon 12 Oct). The level is still watched after a hold;
              a later failure sets outcome 'failed' and keeps held_time, so
              the row reads "held, then failed". A new cycle then starts.
  cycle     : 1 for the first break. After a FAILED break the level is
              watched again from the next candle (Ash, 16 Oct 2026: Wed 4 Mar
              2026 gap break of 24571.75 failed Thu 5 Mar, broke again Fri 6
              Mar). Each re-break is a new row with cycle 2, 3, ...
              So a level can appear on more than one row.

Research behind it: Brooks (wick = breakout, close = stronger), Bulkowski
(closes for breakouts; 58-65% retest; no-retest moves stronger; gaps help;
busted patterns outperform), Murphy (close-based). No study compared wick vs
close; the backtest can overturn the close rule.

Provisional breaks (Ash's method): pass HIGHER-timeframe levels with
LOWER-timeframe candles, e.g. daily levels + 60m candles = provisional daily
breaks; the higher timeframe's own close confirms.

Pure function, no I/O. Each level is a numpy scan from its known time, so
callers pass the levels they need (e.g. the latest N swings).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BREAK_COLUMNS = ["attempt_time", "confirmed_time", "gap", "cleared_time", "retest_time",
                 "bars_to_retest", "held_time", "outcome", "outcome_time"]


def _first(mask: np.ndarray, start: int) -> int:
    """Index of the first True at or after start, or -1."""
    if start >= len(mask):
        return -1
    hit = np.flatnonzero(mask[start:])
    return int(start + hit[0]) if hit.size else -1


def find_level_breaks(candles: pd.DataFrame, levels: pd.DataFrame,
                      tol_pct: float) -> pd.DataFrame:
    """
    candles : columns time, open, high, low, close (sorted by time).
    levels  : columns kind ('high'/'low'), price, known_at (level active from
              the first candle AFTER this time).
    tol_pct : retest / failure tolerance in percent (the equal tolerance).
    Returns one row per break cycle: the level's columns + BREAK_COLUMNS +
    cycle. A level never attempted still gets one row (cycle 1, blanks).
    """
    need_c = {"time", "open", "high", "low", "close"}
    need_l = {"kind", "price", "known_at"}
    if need_c - set(candles.columns):
        raise ValueError(f"candles is missing columns: {sorted(need_c - set(candles.columns))}")
    if need_l - set(levels.columns):
        raise ValueError(f"levels is missing columns: {sorted(need_l - set(levels.columns))}")
    if not (isinstance(tol_pct, (int, float)) and tol_pct >= 0):
        raise ValueError(f"tol_pct must be >= 0, got {tol_pct!r}")

    times = pd.DatetimeIndex(pd.to_datetime(candles["time"]))   # keeps the timezone (IST)
    o = candles["open"].to_numpy(float)
    h = candles["high"].to_numpy(float)
    lo = candles["low"].to_numpy(float)
    c = candles["close"].to_numpy(float)
    k = tol_pct / 100.0

    src = levels.reset_index(drop=True)
    rows, keep = [], []
    for i, lv in enumerate(src.itertuples(index=False)):
        start = int(times.searchsorted(pd.Timestamp(lv.known_at), side="right"))
        p = float(lv.price)
        up = lv.kind == "high"          # breaking a high = upward break

        beyond_wick = h > p if up else lo < p
        beyond_close = c > p if up else c < p
        back_in = lo <= p * (1 + k) if up else h >= p * (1 - k)
        fail_close = c < p * (1 - k) if up else c > p * (1 + k)
        clear = lo > p * (1 + k) if up else h < p * (1 - k)

        cycle = 1
        while True:                     # a FAILED break starts a new cycle (re-break)
            res = dict.fromkeys(BREAK_COLUMNS)
            res["gap"], res["cycle"] = False, cycle
            next_start = -1
            a = _first(beyond_wick, start)
            if a >= 0:
                res["attempt_time"] = times[a]
            b = _first(beyond_close, start)
            if b >= 0:
                res["confirmed_time"] = times[b]
                res["gap"] = bool(o[b] > p if up else o[b] < p)
                f = _first(fail_close, b + 1)
                cl = _first(clear, b)
                if cl >= 0 and (f < 0 or cl < f):
                    res["cleared_time"] = times[cl]
                    r = _first(back_in, cl + 1)
                else:
                    r = -1                  # no white space yet: no retest possible
                if r >= 0 and (f < 0 or r <= f):
                    res["retest_time"] = times[r]
                    res["bars_to_retest"] = r - b
                    held = _first(beyond_close, r)
                    if held >= 0 and (f < 0 or held < f):
                        res["held_time"] = times[held]
                        if f >= 0:          # held, then failed later: held is not final
                            res["outcome"], res["outcome_time"] = "failed", times[f]
                            next_start = f + 1
                        else:
                            res["outcome"], res["outcome_time"] = "held", times[held]
                    elif f >= 0:
                        res["outcome"], res["outcome_time"] = "failed", times[f]
                        next_start = f + 1
                elif f >= 0:
                    res["outcome"], res["outcome_time"] = "failed", times[f]
                    next_start = f + 1
            # a later cycle with no new attempt is not worth a row
            if cycle == 1 or a >= 0:
                rows.append(res)
                keep.append(i)
            if next_start < 0:
                break
            start, cycle = next_start, cycle + 1

    out = src.iloc[keep].reset_index(drop=True)
    extra = pd.DataFrame(rows, columns=BREAK_COLUMNS + ["cycle"], index=out.index)
    for col in ("attempt_time", "confirmed_time", "cleared_time", "retest_time", "held_time",
                "outcome_time"):
        extra[col] = pd.to_datetime(extra[col])
    extra["gap"] = extra["gap"].astype(bool)
    outcome = extra["outcome"].astype(object)
    extra["outcome"] = outcome.where(outcome.notna(), None)   # None, never NaN
    return pd.concat([out, extra], axis=1)
