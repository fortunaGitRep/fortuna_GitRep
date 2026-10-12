"""
modules/Module_F_Tech_Indicators_Funnel/indicator_common/crosses.py

Crosses and runs, shared by every indicator.

  cross_above(a, b)    Pine ta.crossover:  a > b now AND a <= b on the previous bar
  cross_below(a, b)    Pine ta.crossunder: a < b now AND a >= b on the previous bar
                       (a blank on either bar -> False)
  runs(values, labels) per bar: held (first bar of the run = 1), since (label of the
                       run's first bar), from_start (run began with the history)
  bar_labels(df)       what `since` points at: 'ts', else 'trade_date', else the index

Moved unchanged 2026-10-12: cross_above / cross_below from trend_indicators/ema/ema.py,
runs from trend_indicators/macd/macd.py (was _runs), bar_labels from macd.py / adx.py
(was _labels, identical in both). The old names are still re-exported there.

Pure functions: no I/O, inputs never modified.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_above(a: pd.Series, b: pd.Series) -> pd.Series:
    """TradingView ta.crossover: a > b on this bar AND a <= b on the previous bar.
    A blank (NaN) on either bar gives False."""
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_below(a: pd.Series, b: pd.Series) -> pd.Series:
    """TradingView ta.crossunder: a < b on this bar AND a >= b on the previous bar.
    A blank (NaN) on either bar gives False."""
    return (a < b) & (a.shift(1) >= b.shift(1))


def runs(values: pd.Series, labels: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    For a series of states (NaN/None = blank), per bar:
      held       -- bars in the current run, counting this bar (first bar = 1)
      since      -- label (ts / trade_date) of the run's first bar
      from_start -- True if the run began on the series' first non-blank bar, i.e.
                    the side was already there when the history starts (no cross seen)
    Blank bars give NaN / None / False. A blank bar ends a run.
    """
    blank = values.isna()
    key = values.astype(object).where(~blank, None)
    changed = key.ne(key.shift()) | blank | blank.shift(fill_value=True)
    run_id = changed.cumsum()
    held = values.groupby(run_id).cumcount() + 1
    since = labels.groupby(run_id).transform("first")
    pos = pd.Series(np.arange(len(values)), index=values.index)
    run_start = pos.groupby(run_id).transform("first")
    first_valid = pos[~blank].iloc[0] if (~blank).any() else -1
    from_start = (run_start == first_valid) & ~blank
    return held.astype(float).mask(blank), since.mask(blank), from_start


def bar_labels(df: pd.DataFrame) -> pd.Series:
    """The label for each bar: 'ts' if present, else 'trade_date', else the index."""
    if "ts" in df.columns:
        return df["ts"]
    if "trade_date" in df.columns:
        return df["trade_date"]
    return pd.Series(df.index, index=df.index)
