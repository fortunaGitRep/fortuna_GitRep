"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/stoch_rsi.py

Stochastic RSI calculator (spec: Fortuna Indicators/STOCH_RSI.md).
  Part 1: compute_stoch_rsi -- %K and %D (the two lines TradingView draws), plus the RSI
          it is built on and the unsmoothed value (both for checking only).
  Part 2: zones / states / events / label (Ash, 2026-10-13):
          srsi_zone -- three zones on %K (the pink line), the 80 / 20 bands on the chart:
              >= 80          overbought    OVERBOUGHT (>80)
              20 - < 80      middle        MIDDLE (20–80)        (80 and 20 belong upward)
              < 20           oversold      OVERSOLD (<20)
          Events (all alerts in part 3, both directions, every timeframe, index and stocks):
            - zone change of %K (= %K crossing 80 or 20), wording, zone_change_text():
                '%K 83.12 MIDDLE (20–80) rising into OVERBOUGHT (>80)'
                '%K 18.40 MIDDLE (80–20) falling into OVERSOLD (<20)'
              (ranges written in the direction of the move, as RSI)
            - %K crossing %D, tagged with %K's zone on that candle, kd_cross_text():
                '%K crossed below %D in OVERBOUGHT (%K 91.20, %D 93.05)'
          States: zone held / since, %K vs %D side held / since, %K rising / falling,
          candles %K has been pinned at 100 or 0.
          srsi_label -- the zone label. srsi_all runs it all.
  Part 3 (next): snapshot + plain-English texts per timeframe.

TradingView parity (Ash's tv.dhan settings, 2026-10-13: LengthRSI 14, LengthStoch 14,
SmoothK 3, SmoothD 3, source close; bands 80 / 20). TradingView's built-in script:
    rsi1 = ta.rsi(close, 14)
    k    = ta.sma(ta.stoch(rsi1, rsi1, rsi1, 14), 3)
    d    = ta.sma(k, 3)
  with ta.stoch(x, x, x, n) = 100 * (x - lowest(x, n)) / (highest(x, n) - lowest(x, n)).
  The RSI is oscillators.rsi.rsi.compute_rsi -- imported, not copied (proven exact on
  all six timeframes, RSI.md section 3.2).
  First values (default settings): RSI candle 15, raw candle 28, %K candle 30, %D candle 32.
  Part 1 verified exact against tv.dhan on all six timeframes (22 values, 2026-10-13).

Decisions (Ash, 2026-10-13):
  - Columns: srsi_rsi (the RSI it is built on), srsi_raw (unsmoothed, checks only),
    srsi_k, srsi_d. The 'srsi_' prefix keeps them apart from a plain Stochastic later.
  - Flat window: if the 14 RSI values in the window are all equal (range 0), the
    division is by zero -> raw is blank (Pine na). %K is then blank for the next
    smooth_k candles that include it and %D for smooth_k + smooth_d - 1 candles; values
    come back by themselves. A near-flat window (range tiny but not 0) is NOT changed --
    Pine computes it as is. --flat on real Nifty data (2026-10-13): no flat or near-flat
    window on any timeframe (smallest range 1.59 RSI points, 5m).
  - -0.00: TradingView shows -0.00 when %K/%D sit at 0 (a float leftover of its running
    SMA sum). Fortuna keeps the calculated values untouched and prints 0.00 (fmt2).
  - Start of history: blank until 14 RSI values exist (strict window). Whether
    TradingView's lowest/highest skip the blank RSI candles at the very start is a
    known unknown; it can only affect the first ~30 candles of an instrument.
  - %K / %D equal (Ash, 2026-10-13): when %K and %D are equal (e.g. both 100.00) Fortuna
    says "%K equal to %D" and reports no cross; the cross is reported on the candle where
    they separate. Equal = closer than CROSS_TOL (1e-9), i.e. only float leftovers count
    as equal. Seen on the chart: 1D Wed 5 Jul 2023 100.00 / 99.27, Thu 6 Jul 100.00 /
    100.00 (equal, no cross), Fri 7 Jul 85.87 / 95.29 (cross below reported here).
    --crosscheck shows the difference against TradingView's raw rule (tolerance 0).
  - Slope and pinned use a fixed tiny tolerance (FLAT_TOL) so float leftovers at 100 / 0
    never show as "rising" / "falling" or break a pinned run. These are facts shown to
    Ash, not TradingView numbers, so parity is not affected.

Any timeframe: periods are counted in candles of whatever the input holds.
Reading the bars is the caller's job (indicator_ohlcv_reader).

Input contract (programming errors raise ValueError):
  - DataFrame with a numeric price column (default 'close')
  - rows in ascending time order ('ts' checked when present)
  - lengths positive integers; cross_tol >= 0
The input DataFrame is never modified; a copy with the new columns is returned.

Standards applied: single responsibility (Stoch RSI maths only), pure functions (no I/O),
reuse of compute_rsi and indicator_common (DRY), input validation, vectorised pandas,
unit tests (test_stoch_rsi.py).
Deferred (with reasons):
  - Logging: none inside the pure functions (bad input raises); the manual check logs.
  - Snapshot, texts, alerts: part 3, by agreement (baby steps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.crosses import (
    bar_labels,
    cross_above,
    cross_below,
    runs,
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    DEFAULT_DOMAIN,
    TIMEFRAMES,
    UNIT,
    is_intraday,
)
from modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi import RSI_LEN, compute_rsi

STOCH_LEN = 14
SMOOTH_K = 3
SMOOTH_D = 3
SRSI_COLS = ("srsi_rsi", "srsi_raw", "srsi_k", "srsi_d")
NEAR_FLAT = 1e-6          # --flat diagnostic: a window range below this (but > 0) is "near flat"


def _check_length(name: str, n) -> None:
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
        raise ValueError(f"{name} {n!r} is not a positive integer")


def stoch_from_rsi(
    rsi: pd.Series,
    stoch_length: int = STOCH_LEN,
    smooth_k: int = SMOOTH_K,
    smooth_d: int = SMOOTH_D,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    The Stochastic part on an RSI series: returns (raw, %K, %D).
      raw = 100 * (rsi - lowest) / (highest - lowest) over the last stoch_length values;
            blank if any value in the window is blank or the range is 0 (Pine na)
      %K  = SMA(raw, smooth_k); %D = SMA(%K, smooth_d); blank if any value in the window is blank
    Raises ValueError on a non-Series input or bad lengths.
    """
    if not isinstance(rsi, pd.Series):
        raise ValueError(f"rsi must be a pandas Series, got {type(rsi).__name__}")
    for name, n in (("stoch_length", stoch_length), ("smooth_k", smooth_k),
                    ("smooth_d", smooth_d)):
        _check_length(name, n)
    lowest = rsi.rolling(stoch_length, min_periods=stoch_length).min()
    highest = rsi.rolling(stoch_length, min_periods=stoch_length).max()
    rng = highest - lowest
    raw = 100 * (rsi - lowest) / rng.where(rng != 0)          # range 0 -> blank (Pine na)
    k = raw.rolling(smooth_k, min_periods=smooth_k).mean()
    d = k.rolling(smooth_d, min_periods=smooth_d).mean()
    return raw, k, d


def compute_stoch_rsi(
    df: pd.DataFrame,
    rsi_length: int = RSI_LEN,
    stoch_length: int = STOCH_LEN,
    smooth_k: int = SMOOTH_K,
    smooth_d: int = SMOOTH_D,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Return a copy of `df` with:
      srsi_rsi  the RSI it is built on (= compute_rsi 'rsi')
      srsi_raw  unsmoothed Stochastic of RSI, 0-100 (checks only)
      srsi_k    %K -- the TradingView line (pink on Ash's chart)
      srsi_d    %D -- the TradingView line (black on Ash's chart)

    Raises:
        ValueError on a missing price column, bad lengths or unsorted bars
        (price column, rsi_length and order are checked by compute_rsi).
    """
    for name, n in (("stoch_length", stoch_length), ("smooth_k", smooth_k),
                    ("smooth_d", smooth_d)):
        _check_length(name, n)
    rsi = compute_rsi(df, length=rsi_length, price_col=price_col)["rsi"]
    raw, k, d = stoch_from_rsi(rsi, stoch_length, smooth_k, smooth_d)
    out = df.copy()
    out["srsi_rsi"] = rsi
    out["srsi_raw"] = raw
    out["srsi_k"] = k
    out["srsi_d"] = d
    return out


def flat_windows(df: pd.DataFrame, stoch_length: int = STOCH_LEN,
                 near: float = NEAR_FLAT) -> dict:
    """
    Diagnostic (read-only): how many RSI windows are flat on this data.
    Returns {'windows', 'exact', 'near', 'exact_at', 'near_at', 'smallest', 'smallest_at'}:
      exact = range exactly 0 (raw blank, Pine na); near = 0 < range < `near`
      (computed as is, but sensitive to the last digits); *_at = row index labels;
      smallest = smallest non-zero range seen (None if none) and where.
    Raises ValueError if compute_stoch_rsi has not been run.
    """
    if "srsi_rsi" not in df.columns:
        raise ValueError("column 'srsi_rsi' missing for flat_windows (run compute_stoch_rsi first)")
    _check_length("stoch_length", stoch_length)
    rsi = df["srsi_rsi"]
    rng = (rsi.rolling(stoch_length, min_periods=stoch_length).max()
           - rsi.rolling(stoch_length, min_periods=stoch_length).min())
    valid = rng.notna()
    exact = valid & (rng == 0)
    near_mask = valid & (rng > 0) & (rng < near)
    positive = rng.where(valid & (rng > 0))
    has_pos = bool(positive.notna().any())
    return {
        "windows": int(valid.sum()),
        "exact": int(exact.sum()),
        "near": int(near_mask.sum()),
        "exact_at": list(df.index[exact.to_numpy()]),
        "near_at": list(df.index[near_mask.to_numpy()]),
        "smallest": float(positive.min()) if has_pos else None,
        "smallest_at": positive.idxmin() if has_pos else None,
    }


def fmt2(v) -> str:
    """Two decimals for printing; blank -> 'n/a'; '-0.00' -> '0.00' (Ash, 2026-10-13)."""
    if v is None or pd.isna(v):
        return "n/a"
    s = f"{float(v):.2f}"
    return "0.00" if s == "-0.00" else s


# --- Part 2: zones, states, events, label --------------------------------------------

UPPER = 80.0
LOWER = 20.0
CROSS_TOL = 1e-9          # %K/%D closer than this = equal, no cross (Ash, 2026-10-13)
ALT_CROSS_TOL = CROSS_TOL # --crosscheck compares this with TradingView's raw rule (0)
FLAT_TOL = 1e-9           # slope and pinned: closer than this counts as equal / at 100 or 0
SRSI_STATE_INPUT = ("srsi_k", "srsi_d")

# Lowest to highest; the rank decides whether a zone change is upward or downward.
ZONES = ("oversold", "middle", "overbought")
ZONE_RANK = {z: i for i, z in enumerate(ZONES)}
ZONE_NAME = {"overbought": "OVERBOUGHT", "middle": "MIDDLE", "oversold": "OVERSOLD"}
RANGE_RISING = {"overbought": ">80", "middle": "20–80", "oversold": "<20"}
RANGE_FALLING = {"overbought": ">80", "middle": "80–20", "oversold": "<20"}
ZONE_LABEL = {z: f"{ZONE_NAME[z]} ({RANGE_RISING[z]})" for z in ZONES}
LABEL_NA = "n/a (not enough history)"


def srsi_zone(k: pd.Series) -> pd.Series:
    """Zone of %K per candle (>= 80 overbought, 20 - < 80 middle, < 20 oversold); blank -> None."""
    zone = np.select([k >= UPPER, k >= LOWER, k < LOWER],
                     ["overbought", "middle", "oversold"], default=None).astype(object)
    zone[k.isna().to_numpy()] = None
    return pd.Series(zone, index=k.index, dtype=object)


def zone_change_text(k_value: float, zone_from: str, zone_to: str) -> str:
    """
    The zone-change sentence, e.g.
      '%K 83.12 MIDDLE (20–80) rising into OVERBOUGHT (>80)'
      '%K 18.40 MIDDLE (80–20) falling into OVERSOLD (<20)'
    Ranges follow the direction of the move. Raises ValueError on an unknown zone or
    zone_from == zone_to (not a change).
    """
    if zone_from not in ZONE_RANK or zone_to not in ZONE_RANK:
        raise ValueError(f"unknown zone: {zone_from!r} -> {zone_to!r}")
    if zone_from == zone_to:
        raise ValueError(f"not a zone change: {zone_from!r} -> {zone_to!r}")
    rising = ZONE_RANK[zone_to] > ZONE_RANK[zone_from]
    verb, ranges = ("rising into", RANGE_RISING) if rising else ("falling into", RANGE_FALLING)
    return (f"%K {fmt2(k_value)} {ZONE_NAME[zone_from]} ({ranges[zone_from]}) {verb} "
            f"{ZONE_NAME[zone_to]} ({ranges[zone_to]})")


def kd_cross_text(k_value: float, d_value: float, above: bool, zone: str) -> str:
    """'%K crossed below %D in OVERBOUGHT (%K 91.20, %D 93.05)'. Raises ValueError on an unknown zone."""
    if zone not in ZONE_RANK:
        raise ValueError(f"unknown zone: {zone!r}")
    return (f"%K crossed {'above' if above else 'below'} %D in {ZONE_NAME[zone]} "
            f"(%K {fmt2(k_value)}, %D {fmt2(d_value)})")


def _check_tol(cross_tol) -> None:
    if isinstance(cross_tol, bool) or not isinstance(cross_tol, (int, float, np.floating)) \
            or not np.isfinite(cross_tol) or cross_tol < 0:
        raise ValueError(f"cross_tol {cross_tol!r} is not a number >= 0")


def _side(diff: pd.Series, tol: float) -> pd.Series:
    """+1 / -1 / 0 by sign of diff; |diff| < tol counts as 0; blank stays blank."""
    side = np.sign(diff)
    if tol > 0:
        side = side.where(diff.abs() >= tol, 0.0).where(diff.notna())
    return side


def kd_crosses(k: pd.Series, d: pd.Series, cross_tol: float = CROSS_TOL) -> tuple[pd.Series, pd.Series]:
    """
    %K crossing %D with TradingView's rule (ta.crossover / ta.crossunder) via
    indicator_common.crosses. cross_tol > 0: %K closer than cross_tol to %D is treated as
    equal to %D first, so float leftovers at 100 / 0 do not make a cross.
    Returns (cross_above, cross_below) boolean Series.
    """
    _check_tol(cross_tol)
    kk = k.mask((k - d).abs() < cross_tol, d) if cross_tol > 0 else k
    return cross_above(kk, d).astype(bool), cross_below(kk, d).astype(bool)


def srsi_states(df: pd.DataFrame, cross_tol: float = CROSS_TOL) -> pd.DataFrame:
    """
    From compute_stoch_rsi output, adds per candle:
      srsi_zone                              one of ZONES on %K (None when %K is blank)
      srsi_zone_held / _since / _from_start  candles in this zone (first = 1), when it began,
                                             True if the zone began with the history
      srsi_zone_change                       True on the candle %K moved into a different zone
      srsi_zone_from                         the zone it came from (None if no change)
      srsi_zone_change_up                    True upward, False downward, None if no change
      srsi_kd_side                           +1 %K above %D, -1 below, 0 equal, NaN blank
      srsi_kd_held / _since / _from_start
      srsi_kd_cross_above / _below           %K crossing %D (TradingView rule, cross_tol)
      srsi_kd_cross_zone                     %K's zone on a cross candle, else None
      srsi_slope                             +1 %K rising, -1 falling, 0 flat (vs previous)
      srsi_slope_held                        candles the slope has kept its direction
      srsi_pinned                            +1 %K at 100, -1 at 0, 0 neither, NaN blank
      srsi_pinned_held                       candles in that pinned state (first = 1)
    Returns a copy; raises ValueError if compute_stoch_rsi has not been run, bars are
    unsorted or cross_tol is invalid.
    """
    missing = [c for c in SRSI_STATE_INPUT if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for srsi_states: {missing} "
                         f"(run compute_stoch_rsi first)")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before srsi_states")
    _check_tol(cross_tol)

    out = df.copy()
    k, d = out["srsi_k"], out["srsi_d"]
    labels = bar_labels(out)

    zone = srsi_zone(k)
    held, since, from_start = runs(zone, labels)
    prev = zone.shift(1)
    change = zone.notna() & prev.notna() & (zone != prev)
    out["srsi_zone"] = zone
    out["srsi_zone_held"] = held
    out["srsi_zone_since"] = since
    out["srsi_zone_from_start"] = from_start
    out["srsi_zone_change"] = change.astype(bool)
    out["srsi_zone_from"] = prev.where(change, None)
    up = [None if not c else ZONE_RANK[z] > ZONE_RANK[p] for c, z, p in zip(change, zone, prev)]
    out["srsi_zone_change_up"] = pd.Series(up, index=out.index, dtype=object)

    side = _side(k - d, cross_tol)
    held, since, from_start = runs(side, labels)
    above, below = kd_crosses(k, d, cross_tol)
    out["srsi_kd_side"] = side
    out["srsi_kd_held"] = held
    out["srsi_kd_since"] = since
    out["srsi_kd_from_start"] = from_start
    out["srsi_kd_cross_above"] = above
    out["srsi_kd_cross_below"] = below
    out["srsi_kd_cross_zone"] = zone.where(above | below, None)

    slope = _side(k - k.shift(1), FLAT_TOL)
    held, _, _ = runs(slope, labels)
    out["srsi_slope"] = slope
    out["srsi_slope_held"] = held

    pinned = pd.Series(np.where(k >= 100 - FLAT_TOL, 1.0, np.where(k <= FLAT_TOL, -1.0, 0.0)),
                       index=out.index).where(k.notna())
    held, _, _ = runs(pinned, labels)
    out["srsi_pinned"] = pinned
    out["srsi_pinned_held"] = held
    return out


def srsi_label(df: pd.DataFrame) -> pd.Series:
    """The zone label per candle, e.g. 'OVERBOUGHT (>80)'; blank -> 'n/a (not enough history)'."""
    if "srsi_zone" not in df.columns:
        raise ValueError("column 'srsi_zone' missing for srsi_label (run srsi_states first)")
    return pd.Series([ZONE_LABEL[z] if isinstance(z, str) else LABEL_NA for z in df["srsi_zone"]],
                     index=df.index, dtype=object)


def srsi_all(df: pd.DataFrame, cross_tol: float = CROSS_TOL) -> pd.DataFrame:
    """compute_stoch_rsi -> srsi_states -> srsi_label, in one call."""
    out = srsi_states(compute_stoch_rsi(df), cross_tol)
    out["srsi_label"] = srsi_label(out)
    return out


def compare_cross_rules(df: pd.DataFrame, tol: float = ALT_CROSS_TOL) -> dict:
    """
    Diagnostic (read-only) for the open %K/%D cross decision: crosses with TradingView's raw
    rule (tol 0) vs with `tol`. Returns {'raw_above', 'raw_below', 'tol_above', 'tol_below',
    'only_raw', 'only_tol'}; only_* = row index labels where the two rules disagree.
    Raises ValueError if compute_stoch_rsi has not been run or tol is invalid.
    """
    missing = [c for c in SRSI_STATE_INPUT if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for compare_cross_rules: {missing} "
                         f"(run compute_stoch_rsi first)")
    _check_tol(tol)
    k, d = df["srsi_k"], df["srsi_d"]
    ra, rb = kd_crosses(k, d, 0.0)
    ta, tb = kd_crosses(k, d, tol)
    raw_any, tol_any = ra | rb, ta | tb
    # a candle counts as "different" if either rule marks a cross the other doesn't
    differ_raw = raw_any & ~((ra & ta) | (rb & tb))
    differ_tol = tol_any & ~((ra & ta) | (rb & tb))
    return {
        "raw_above": int(ra.sum()), "raw_below": int(rb.sum()),
        "tol_above": int(ta.sum()), "tol_below": int(tb.sum()),
        "only_raw": list(df.index[differ_raw.to_numpy()]),
        "only_tol": list(df.index[differ_tol.to_numpy()]),
    }


# --- Manual check: Stoch RSI on the latest bars, to compare with TradingView ----------

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi
    #   ... stoch_rsi --dates 2026-10-07 2026-10-08 2026-10-09
    #   ... stoch_rsi --timeframe 60m --dates 2026-10-09 --ohlc
    #   ... stoch_rsi --timeframe all                (latest candles on 1M, 1W, 1D, 60m, 15m, 5m)
    #   ... stoch_rsi --timeframe all --flat         (count flat / near-flat RSI windows)
    #   ... stoch_rsi --state [--timeframe 15m]      (zone, %K vs %D, slope, pinned, last events)
    #   ... stoch_rsi --timeframe all --state        (all six timeframes + summary table)
    #   ... stoch_rsi --crosses 15 [--timeframe 5m]  (latest zone changes and %K/%D crosses)
    #   ... stoch_rsi --timeframe all --crosscheck   (raw TradingView cross rule vs tolerance)
    # Output goes to the screen AND to one log per timeframe and mode (overwritten each
    # run; first line = the command):
    #   logs/stoch_rsi_test_logs/stoch_rsi_check_<timeframe>.log          (--bars / --dates)
    #   logs/stoch_rsi_test_logs/stoch_rsi_check_<timeframe>_<mode>.log   (flat, state,
    #                                                                       crosses, crosscheck)
    import argparse
    import logging
    from pathlib import Path

    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    parser = argparse.ArgumentParser(description="Print Stochastic RSI (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--timeframe", default="1d", choices=list(DEFAULT_DOMAIN) + ["all"],
                        help="'all' = 1mo, 1w, 1d, 60m, 15m, 5m in one run")
    parser.add_argument("--domain", help="default: indices (1d/1w/1mo), "
                                         "universe_intraday (5m/15m/60m)")
    parser.add_argument("--bars", type=int, default=3, help="how many latest bars to print")
    parser.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD",
                        help="print all bars on these trade dates instead of the latest bars")
    parser.add_argument("--ohlc", action="store_true",
                        help="also print open/high/low (to compare candles with TradingView)")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--flat", action="store_true",
                            help="count 14-candle RSI windows that are flat (range 0) or near flat")
    mode_group.add_argument("--state", action="store_true",
                            help="print zone / %%K vs %%D / slope / pinned and last events")
    mode_group.add_argument("--crosses", type=int, metavar="N",
                            help="print the latest N events (zone changes, %%K/%%D crosses)")
    mode_group.add_argument("--crosscheck", action="store_true",
                            help="compare %%K/%%D crosses: TradingView raw rule vs tolerance")
    args = parser.parse_args()
    mode = ("flat" if args.flat else "state" if args.state else
            "crosses" if args.crosses else "crosscheck" if args.crosscheck else None)
    timeframes = list(TIMEFRAMES) if args.timeframe == "all" else [args.timeframe]

    load_dotenv()
    log_path = (Path("logs") / "stoch_rsi_test_logs"
                / f"stoch_rsi_check_{args.timeframe}{'_' + mode if mode else ''}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    log = logging.getLogger("stoch_rsi_check")
    log.info("command: stoch_rsi --timeframe %s --domain %s --key %s %s", args.timeframe,
             args.domain or "default", args.key,
             "--flat" if args.flat else "--state" if args.state else
             f"--crosses {args.crosses}" if args.crosses else
             "--crosscheck" if args.crosscheck else
             (f"--dates {' '.join(args.dates)}" if args.dates else f"--bars {args.bars}")
             + (" --ohlc" if args.ohlc else ""))

    summary = []      # per-timeframe rows for the --timeframe all tables

    def check_one(tf: str) -> None:
        domain = args.domain or DEFAULT_DOMAIN[tf]
        intraday = is_intraday(tf)
        unit = UNIT.get(tf, "candle")
        when_of = ((lambda v: pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")) if intraday
                   else (lambda v: pd.Timestamp(v).strftime("%Y-%m-%d")))

        res = read_for_indicators(args.key, domain, tf)
        log.info("=" * 96)
        log.info("STOCH RSI CHECK — %s (%s, Stoch RSI 14 14 3 3 close, TradingView method)",
                 args.key, tf)
        log.info("=" * 96)
        if not res.ok:
            log.warning("NOT OK -- %s", res.error)
            summary.append((tf, "-", "-", "-", "NOT OK"))
            return

        if args.state:
            a = srsi_all(res.df)
            r = a.iloc[-1]
            partial = f" ({unit} to date)" if tf in ("1w", "1mo") else ""
            log.info("as of %s%s   close %.2f", when_of(r["ts"]), partial, r["close"])
            log.info("%%K %s   %%D %s   (RSI %s)", fmt2(r["srsi_k"]), fmt2(r["srsi_d"]),
                     fmt2(r["srsi_rsi"]))
            log.info("zone            : %s", r["srsi_label"])
            if isinstance(r["srsi_zone"], str):
                start = " (start of data)" if r["srsi_zone_from_start"] else ""
                log.info("zone held       : %d %s(s) since %s%s", int(r["srsi_zone_held"]), unit,
                         when_of(r["srsi_zone_since"]), start)
            if pd.notna(r["srsi_kd_side"]):
                word = {1: "%K above %D", -1: "%K below %D", 0: "%K equal to %D"}[int(r["srsi_kd_side"])]
                start = " (start of data)" if r["srsi_kd_from_start"] else ""
                log.info("%%K vs %%D        : %s, held %d %s(s) since %s%s", word,
                         int(r["srsi_kd_held"]), unit, when_of(r["srsi_kd_since"]), start)
            if pd.notna(r["srsi_slope"]) and pd.notna(r["srsi_slope_held"]):
                word = {1: "rising", -1: "falling", 0: "flat"}[int(r["srsi_slope"])]
                log.info("%%K slope        : %s for %d %s(s)", word, int(r["srsi_slope_held"]), unit)
            if pd.notna(r["srsi_pinned"]) and int(r["srsi_pinned"]) != 0:
                log.info("pinned          : %%K at %s for %d %s(s)",
                         "100" if int(r["srsi_pinned"]) == 1 else "0",
                         int(r["srsi_pinned_held"]), unit)
            changes = a.loc[a["srsi_zone_change"]]
            if len(changes):
                c = changes.iloc[-1]
                log.info("last zone change: %s  %s", when_of(c["ts"]),
                         zone_change_text(c["srsi_k"], c["srsi_zone_from"], c["srsi_zone"]))
            else:
                log.info("last zone change: none in history")
            for col, above in (("srsi_kd_cross_above", True), ("srsi_kd_cross_below", False)):
                hits = a.loc[a[col]]
                if len(hits):
                    c = hits.iloc[-1]
                    log.info("last cross %-5s: %s  %s", "above" if above else "below",
                             when_of(c["ts"]),
                             kd_cross_text(c["srsi_k"], c["srsi_d"], above, c["srsi_kd_cross_zone"]))
                else:
                    log.info("last cross %-5s: none in history", "above" if above else "below")
            summary.append((tf, when_of(r["ts"]) + partial, fmt2(r["srsi_k"]), fmt2(r["srsi_d"]),
                            r["srsi_label"]))
            return

        if args.crosses:
            a = srsi_all(res.df)
            events = []
            mask = a["srsi_zone_change"] | a["srsi_kd_cross_above"] | a["srsi_kd_cross_below"]
            for _, r in a.loc[mask].iterrows():
                w = when_of(r["ts"])
                if r["srsi_zone_change"]:
                    events.append(f"{w}  {zone_change_text(r['srsi_k'], r['srsi_zone_from'], r['srsi_zone'])}")
                if r["srsi_kd_cross_above"]:
                    events.append(f"{w}  {kd_cross_text(r['srsi_k'], r['srsi_d'], True, r['srsi_kd_cross_zone'])}")
                if r["srsi_kd_cross_below"]:
                    events.append(f"{w}  {kd_cross_text(r['srsi_k'], r['srsi_d'], False, r['srsi_kd_cross_zone'])}")
            log.info("latest %d events (zone changes + %%K/%%D crosses, oldest first):", args.crosses)
            for text in events[-args.crosses:]:
                log.info("  %s", text)
            log.info("total events in history: %s  (data as of %s)", f"{len(events):,}", res.last_ts)
            return

        s = compute_stoch_rsi(res.df)

        if args.crosscheck:
            cc = compare_cross_rules(s)
            log.info("%%K/%%D crosses, TradingView raw rule : %s above, %s below",
                     f"{cc['raw_above']:,}", f"{cc['raw_below']:,}")
            log.info("%%K/%%D crosses, tolerance %g     : %s above, %s below", ALT_CROSS_TOL,
                     f"{cc['tol_above']:,}", f"{cc['tol_below']:,}")
            log.info("candles where only the raw rule crosses : %d", len(cc["only_raw"]))
            for i in cc["only_raw"][:10]:
                log.info("    %s  %%K %s  %%D %s  (%%K-%%D = %.3g)", when_of(s.loc[i, "ts"]),
                         fmt2(s.loc[i, "srsi_k"]), fmt2(s.loc[i, "srsi_d"]),
                         s.loc[i, "srsi_k"] - s.loc[i, "srsi_d"])
            if len(cc["only_raw"]) > 10:
                log.info("    ... and %d more", len(cc["only_raw"]) - 10)
            log.info("candles where only the tolerance crosses: %d", len(cc["only_tol"]))
            for i in cc["only_tol"][:10]:
                log.info("    %s  %%K %s  %%D %s", when_of(s.loc[i, "ts"]),
                         fmt2(s.loc[i, "srsi_k"]), fmt2(s.loc[i, "srsi_d"]))
            if len(cc["only_tol"]) > 10:
                log.info("    ... and %d more", len(cc["only_tol"]) - 10)
            log.info("data as of %s", res.last_ts)
            summary.append((tf, f"{cc['raw_above'] + cc['raw_below']:,}",
                            f"{cc['tol_above'] + cc['tol_below']:,}",
                            len(cc["only_raw"]), len(cc["only_tol"])))
            return

        if args.flat:
            fw = flat_windows(s)
            log.info("14-candle RSI windows checked : %s", f"{fw['windows']:,}")
            log.info("exactly flat (range 0 -> raw blank, Pine na): %d", fw["exact"])
            for i in fw["exact_at"][:10]:
                log.info("    %s", when_of(s.loc[i, "ts"]))
            if fw["exact"] > 10:
                log.info("    ... and %d more", fw["exact"] - 10)
            log.info("near flat (0 < range < %g, computed as is): %d", NEAR_FLAT, fw["near"])
            for i in fw["near_at"][:10]:
                log.info("    %s", when_of(s.loc[i, "ts"]))
            if fw["near"] > 10:
                log.info("    ... and %d more", fw["near"] - 10)
            smallest = "none"
            if fw["smallest_at"] is not None:
                smallest = f"{fw['smallest']:.6g} on {when_of(s.loc[fw['smallest_at'], 'ts'])}"
            log.info("smallest non-zero range       : %s", smallest)
            log.info("data as of %s", res.last_ts)
            summary.append((tf, f"{fw['windows']:,}", fw["exact"], fw["near"], smallest))
            return

        if args.dates:
            wanted = set(args.dates)
            rows = s[s["trade_date"].astype(str).isin(wanted)]
            for d in sorted(wanted - set(rows["trade_date"].astype(str))):
                log.info("%s  no bar on this date (not a trading day in our data)", d)
        else:
            rows = s.tail(args.bars)
        w = 26 if intraday else 12
        ohlc_head = f"{'open':>11}{'high':>11}{'low':>11}" if args.ohlc else ""
        log.info(f"{'bar':<{w}}{ohlc_head}{'close':>11}{'%K':>9}{'%D':>9}"
                 f"{'RSI':>9}{'raw (hidden)':>15}")
        for _, r in rows.iterrows():
            when = str(r["ts"]) if intraday else str(r["trade_date"])
            ohlc = (f"{r['open']:>11.2f}{r['high']:>11.2f}{r['low']:>11.2f}" if args.ohlc else "")
            log.info(f"{when:<{w}}{ohlc}{r['close']:>11.2f}{fmt2(r['srsi_k']):>9}"
                     f"{fmt2(r['srsi_d']):>9}{fmt2(r['srsi_rsi']):>9}{fmt2(r['srsi_raw']):>15}")
        partial = f"  (latest {UNIT[tf]} is {UNIT[tf]} to date)" if tf in ("1w", "1mo") else ""
        log.info("bars used: %s  (data as of %s)%s", f"{len(s):,}", res.last_ts, partial)
        log.info("TradingView legend: 'Stoch RSI 14 14 3 3  <%K>  <%D>'. RSI = the RSI it is "
                 "built on (same as the RSI panel); raw = unsmoothed, checks only.")

    for tf in timeframes:
        check_one(tf)
    if len(timeframes) > 1 and mode in ("flat", "state", "crosscheck"):
        log.info("=" * 96)
        if args.flat:
            log.info("SUMMARY — flat RSI windows on each timeframe")
            log.info("  %-4s %10s %7s %7s  %s", "tf", "windows", "exact", "near",
                     "smallest non-zero range")
            for row in summary:
                log.info("  %-4s %10s %7s %7s  %s", *row)
        elif args.state:
            log.info("SUMMARY — Stoch RSI on each timeframe (latest stored candle)")
            for row in summary:
                log.info("  %-4s %-26s %%K %-7s %%D %-7s %s", *row)
        else:
            log.info("SUMMARY — %%K/%%D crosses: TradingView raw rule vs tolerance %g", ALT_CROSS_TOL)
            log.info("  %-4s %10s %10s %10s %10s", "tf", "raw", "tolerance", "only raw", "only tol")
            for row in summary:
                log.info("  %-4s %10s %10s %10s %10s", *row)
    log.info("=" * 96)
    log.info("log written to %s", log_path)
