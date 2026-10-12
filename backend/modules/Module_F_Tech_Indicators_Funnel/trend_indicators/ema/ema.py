"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema/ema.py

EMA calculator.
  Part 1: EMA values (compute_emas).
  Part 2: crosses (detect_crosses) -- close vs each EMA, stack pairs 5/13, 13/26,
          26/50, 50/100, 100/200, and the 50/200 golden/death cross. Same rule as
          TradingView ta.crossover / ta.crossunder: above = A > B now and A <= B on
          the previous bar; below = A < B now and A >= B on the previous bar.
  Part 3: stack_stage (-5..+5), check_states (side, days held, since, margin pts/%,
          whole-candle-clear for close checks). Volume confirmation deferred (Nifty has
          no volume from Upstox; revisit for stocks).
          Facts only -- no strong/weak thresholds yet (to be tested on Nifty history later).
  Later parts: snapshot + plain-English texts.

TradingView parity (decided 2026-10-11): same method as Pine's ta.ema, so values
match what Ash sees on his TradingView charts.
  - alpha = 2 / (n + 1)
  - bars 1 .. n-1  -> blank (NaN): fewer than n closes exist, so no EMA yet
  - bar n          -> simple average of the first n closes (the seed)
  - every later bar -> alpha * close + (1 - alpha) * previous EMA
Because the seed's influence fades bar by bar, long histories (Nifty: 6,657 daily
bars since 2000) give the same values as TradingView even if TradingView's own
history starts on a different date.

Reusable by design: a pure function with no I/O and nothing instrument-specific.
The same compute_emas() runs on Nifty 50 today and on every watchlist / options
stock later, on any timeframe (periods are counted in bars of whatever timeframe
the input holds). Reading the bars is the caller's job (indicator_ohlcv_reader).

Input contract (programming errors raise ValueError -- the caller passes data it
already validated through the reader, so a bad input here is a code bug, not a
data condition to report):
  - DataFrame with a numeric price column (default 'close')
  - rows in ascending time order ('ts' checked when present)
  - periods: positive, unique integers
The input DataFrame is never modified; a copy with ema_<n> columns is returned.

Standards applied: single responsibility (EMA math only), pure function (no I/O,
no global state), input validation, readable/consistent naming, vectorised
pandas (milliseconds for 6 EMAs on ~6,600 bars), unit tests (test_ema.py).
Deferred (with reasons):
  - Logging: none inside the pure function (nothing can fail silently here; bad
    input raises). The manual check below and future callers log their runs.
  - Stage / texts: separate later steps, by agreement (baby steps).

Shared helpers (2026-10-12): ema_tradingview, cross_above and cross_below now live in
../../indicator_common/ (smoothing.py, crosses.py), moved unchanged; this file
imports and re-exports them, so existing imports from ema.py still work.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

# Shared helpers (moved to indicator_common 2026-10-12, unchanged). Re-exported here
# so `from ...ema.ema import ema_tradingview, cross_above, cross_below` keeps working.
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.crosses import (  # noqa: F401
    cross_above,
    cross_below,
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.smoothing import (  # noqa: F401
    ema_tradingview,
)

DEFAULT_PERIODS: tuple[int, ...] = (5, 13, 26, 50, 100, 200)

# Part 2 — crosses. Each check is (A, B): "A crossed above / below B".
#   close vs each EMA (6), the stack pairs (5), and the 50/200 golden/death cross (1).
STACK_PAIRS: tuple[tuple[int, int], ...] = ((5, 13), (13, 26), (26, 50), (50, 100), (100, 200))
GOLDEN_DEATH_PAIR: tuple[int, int] = (50, 200)


def _validate(df: pd.DataFrame, periods: tuple[int, ...], price_col: str) -> None:
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame "
                         f"(columns: {list(df.columns)})")
    if not periods:
        raise ValueError("periods is empty")
    for p in periods:
        if isinstance(p, bool) or not isinstance(p, (int, np.integer)) or p < 1:
            raise ValueError(f"period {p!r} is not a positive integer")
    if len(set(periods)) != len(periods):
        raise ValueError(f"periods contain duplicates: {periods}")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before computing EMAs")


def compute_emas(
    df: pd.DataFrame,
    periods: Iterable[int] = DEFAULT_PERIODS,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Return a copy of `df` with one column per period: ema_5, ema_13, ... ema_200.

    Args:
        df: bars in ascending time order (e.g. indicator_ohlcv_reader output).
        periods: EMA lengths in bars. Default (5, 13, 26, 50, 100, 200).
        price_col: column to average. Default 'close' (TradingView default source).

    Raises:
        ValueError on a missing price column, bad periods or unsorted bars.
    """
    periods = tuple(periods)
    _validate(df, periods, price_col)

    out = df.copy()
    prices = out[price_col]
    for p in periods:
        out[f"ema_{p}"] = ema_tradingview(prices, p)
    return out


# --- Part 2: crosses -----------------------------------------------------------

def default_cross_checks(periods: Iterable[int] = DEFAULT_PERIODS) -> list[tuple[str, str]]:
    """The 12 (A, B) column pairs: close vs each EMA, stack pairs, 50/200."""
    periods = tuple(periods)
    checks = [("close", f"ema_{p}") for p in periods]
    checks += [(f"ema_{a}", f"ema_{b}") for a, b in STACK_PAIRS
               if a in periods and b in periods]
    a, b = GOLDEN_DEATH_PAIR
    if a in periods and b in periods and (a, b) not in STACK_PAIRS:
        checks.append((f"ema_{a}", f"ema_{b}"))
    return checks


def detect_crosses(
    df: pd.DataFrame,
    checks: Iterable[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """
    Return a copy of `df` (output of compute_emas) with two True/False columns per
    check: cross_above_<A>_<B> and cross_below_<A>_<B>.
      e.g. cross_above_close_ema_50, cross_below_ema_13_ema_26,
           cross_above_ema_50_ema_200 (golden cross), cross_below_ema_50_ema_200 (death cross)

    Both directions are always computed; which ones a caller uses (Nifty: both,
    stocks: cross-above only) is the caller's choice.

    Raises:
        ValueError if a column named in `checks` is missing (run compute_emas first)
        or bars are not in ascending 'ts' order.
    """
    checks = default_cross_checks() if checks is None else list(checks)
    missing = sorted({c for pair in checks for c in pair if c not in df.columns})
    if missing:
        raise ValueError(f"column(s) missing for crosses: {missing} "
                         f"(run compute_emas first)")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before detecting crosses")

    out = df.copy()
    for a, b in checks:
        out[f"cross_above_{a}_{b}"] = cross_above(out[a], out[b])
        out[f"cross_below_{a}_{b}"] = cross_below(out[a], out[b])
    return out


# --- Part 3: stage and check states ---------------------------------------------

def stack_stage(df: pd.DataFrame, periods: Iterable[int] = DEFAULT_PERIODS) -> pd.Series:
    """
    Stage of the EMA stack per bar, -5 .. +5 (with the default 6 EMAs).
      5 > 13            -> count up the ladder while each next pair is also aligned
                           (+1 = only 5 above 13 ... +5 = 5>13>26>50>100>200)
      5 < 13            -> same, downwards (-1 .. -5)
      5 == 13           -> 0
      5 or 13 blank     -> NaN
    A blank EMA further up stops the count (a stock without 200 bars reaches at most +/-4).
    """
    periods = tuple(periods)
    cols = [f"ema_{p}" for p in periods]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for stage: {missing} (run compute_emas first)")

    up_run = pd.Series(True, index=df.index)
    down_run = pd.Series(True, index=df.index)
    stage = pd.Series(0.0, index=df.index)
    for fast, slow in zip(cols, cols[1:]):
        up_run = up_run & (df[fast] > df[slow])
        down_run = down_run & (df[fast] < df[slow])
        stage = stage + up_run.astype(float) - down_run.astype(float)
    stage[df[cols[0]].isna() | df[cols[1]].isna()] = np.nan
    return stage


def check_states(
    df: pd.DataFrame,
    checks: Iterable[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """
    For each (A, B) check, per bar, adds:
      side_<A>_<B>        +1 above, -1 below, 0 equal, NaN blank
      held_<A>_<B>        bars on the current side, counting this bar (cross day = 1)
      since_<A>_<B>       trade_date (or index) where the current side began
      margin_pts_<A>_<B>  A - B
      margin_pct_<A>_<B>  (A - B) / B * 100
      candle_clear_<A>_<B>  close checks only: whole candle beyond the line
                            (above: low > B; below: high < B)
    Returns a copy; the input is not modified.
    """
    checks = default_cross_checks() if checks is None else list(checks)
    missing = sorted({c for pair in checks for c in pair if c not in df.columns})
    if missing:
        raise ValueError(f"column(s) missing for states: {missing} (run compute_emas first)")

    out = df.copy()
    labels = out["trade_date"] if "trade_date" in out.columns else pd.Series(out.index, index=out.index)
    has_hl = "high" in out.columns and "low" in out.columns
    new_cols: dict[str, pd.Series] = {}

    for a, b in checks:
        diff = out[a] - out[b]
        side = np.sign(diff)                      # NaN stays NaN
        run_id = (side != side.shift()).cumsum()  # new run on every change (NaN breaks runs)
        held = side.groupby(run_id).cumcount() + 1
        since = labels.groupby(run_id).transform("first")
        blank = side.isna()

        tag = f"{a}_{b}"
        new_cols[f"side_{tag}"] = side
        new_cols[f"held_{tag}"] = held.astype(float).mask(blank)
        new_cols[f"since_{tag}"] = since.mask(blank)
        new_cols[f"margin_pts_{tag}"] = diff
        new_cols[f"margin_pct_{tag}"] = diff / out[b] * 100
        if a == "close" and has_hl:
            clear = ((side > 0) & (out["low"] > out[b])) | ((side < 0) & (out["high"] < out[b]))
            new_cols[f"candle_clear_{tag}"] = clear

    return pd.concat([out, pd.DataFrame(new_cols, index=out.index)], axis=1)


# --- Manual check: Nifty 50 EMAs on the latest bars, to compare with TradingView ---

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema
    import argparse
    import logging

    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators


    # Output goes to the screen AND to logs/ema_test_logs/ema_check.log (overwritten each run):
    # everything printed and every log line is copied into the file.
    import sys
    from pathlib import Path

    class _Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, text):
            for st in self.streams:
                st.write(text)
        def flush(self):
            for st in self.streams:
                st.flush()

    _log_path = Path("logs") / "ema_test_logs" / "ema_check.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_path, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, _log_file)
    print("command: " + " ".join(sys.argv[1:]) if sys.argv[1:] else "command: (defaults)")

    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    parser = argparse.ArgumentParser(description="Print EMAs for the latest bars (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--domain", default="indices")
    parser.add_argument("--bars", type=int, default=3, help="how many latest bars to print")
    parser.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD",
                        help="print these trade dates instead of the latest bars")
    parser.add_argument("--crosses", type=int, metavar="N",
                        help="print the latest N crosses instead of EMA values")
    parser.add_argument("--state", action="store_true",
                        help="print stage + state of all 12 checks for the latest bar")
    args = parser.parse_args()

    res = read_for_indicators(args.key, args.domain, "1d")
    print("\n" + "=" * 78)
    print(f"EMA CHECK — {args.key} (daily, TradingView method)")
    print("=" * 78)
    if not res.ok:
        print(f"NOT OK -- {res.error}")
    elif args.state:
        emas = compute_emas(res.df)
        states = check_states(emas)
        last = states.iloc[-1]
        stage = stack_stage(emas).iloc[-1]
        name = lambda c: "close" if c == "close" else c.replace("ema_", "") + " EMA"
        print(f"as of {res.last_trade_date}   close {last['close']:.2f}")
        print(f"stage           : {'n/a' if pd.isna(stage) else f'{int(stage):+d}'}  (-5..+5)")
        print("EMAs            : " + "  ".join(
            f"{p}: {last[f'ema_{p}']:.2f}" for p in DEFAULT_PERIODS))
        print()
        for a, b in default_cross_checks():
            tag = f"{a}_{b}"
            side = last[f"side_{tag}"]
            if pd.isna(side):
                print(f"  {name(a):>8} vs {name(b):<8}: blank (not enough history)")
                continue
            word = {1: "above", -1: "below", 0: "equal to"}[int(side)]
            line = (f"  {name(a):>8} vs {name(b):<8}: {word:<8} held {int(last[f'held_{tag}']):>3} day(s) "
                    f"since {last[f'since_{tag}']}  margin {last[f'margin_pts_{tag}']:+.2f} "
                    f"({last[f'margin_pct_{tag}']:+.3f}%)")
            if f"candle_clear_{tag}" in states.columns:
                line += f"  whole candle clear: {'yes' if last[f'candle_clear_{tag}'] else 'no'}"
            print(line)
    elif args.crosses:
        crossed = detect_crosses(compute_emas(res.df))
        events = []
        for a, b in default_cross_checks():
            for direction in ("above", "below"):
                hits = crossed.loc[crossed[f"cross_{direction}_{a}_{b}"], "trade_date"]
                events += [(str(d), a, direction, b) for d in hits]
        events.sort(key=lambda e: e[0])
        print(f"latest {args.crosses} crosses (oldest first):")
        for d, a, direction, b in events[-args.crosses:]:
            name = lambda c: "close" if c == "close" else c.replace("ema_", "") + " EMA"
            tag = ""
            if (a, b) == (f"ema_{GOLDEN_DEATH_PAIR[0]}", f"ema_{GOLDEN_DEATH_PAIR[1]}"):
                tag = "  <-- GOLDEN CROSS" if direction == "above" else "  <-- DEATH CROSS"
            print(f"  {d}  {name(a)} crossed {direction} {name(b)}{tag}")
        print(f"\ntotal crosses in history: {len(events):,}  "
              f"(data as of {res.last_trade_date} close)")
    else:
        emas = compute_emas(res.df)
        cols = [f"ema_{p}" for p in DEFAULT_PERIODS]
        header = f"{'date':<12}{'close':>11}" + "".join(f"{c:>11}" for c in cols)
        print(header)
        if args.dates:
            wanted = set(args.dates)
            rows = emas[emas["trade_date"].astype(str).isin(wanted)]
            found = set(rows["trade_date"].astype(str))
            for d in sorted(wanted - found):
                print(f"{d:<12}  no bar on this date (not a trading day in our data)")
        else:
            rows = emas.tail(args.bars)
        for _, r in rows.iterrows():
            row = f"{str(r['trade_date']):<12}{r['close']:>11.2f}"
            row += "".join(f"{r[c]:>11.2f}" for c in cols)
            print(row)
        print(f"\nbars used: {len(emas):,}  (data as of {res.last_trade_date} close)")
    print("=" * 78 + "\n")
    print(f"log written to {_log_path}")
