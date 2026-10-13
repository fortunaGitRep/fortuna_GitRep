"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi/rsi.py

RSI calculator (spec: Fortuna Indicators/RSI.md).
  Part 1: compute_rsi -- RSI (the line TradingView draws) and rsi_ma, the "Smoothed MA"
          line (SMA of RSI). rsi_ma is a HIDDEN extra: Ash's chart has it switched off,
          so it is calculated and kept for testing later, never shown in texts.
  Part 2: rsi_zone -- seven zones (Ash, 2026-10-13):
              >= 80          overbought    OVERBOUGHT (>80)
              70 - < 80      strong_bull   STRONG BULL (70–80)
              > 55 - < 70    bullish       BULLISH (55–70)
              45 - 55        sr_zone       RSI S&R ZONE (45–55)    (45 and 55 inside)
              30 - < 45      bearish       BEARISH (30–45)
              20 - < 30      strong_bear   STRONG BEAR (20–30)
              < 20           oversold      OVERSOLD (<20)
          Zone-change wording (Ash, 2026-10-13), zone_change_text():
              RSI {value} {FROM} ({range}) {verb} into {TO} ({range})
            ranges written in the direction of the move (falling: 45–30, rising: 30–45);
            verb: up into BULLISH / STRONG BULL / OVERBOUGHT -> "rising strong up";
                  up into S&R / BEARISH / STRONG BEAR        -> "rising up";
                  down into BEARISH / STRONG BEAR / OVERSOLD -> "falling strong down";
                  down into S&R / BULLISH / STRONG BULL      -> "falling down".
            e.g. "RSI 33.66 STRONG BEAR (20–30) rising up into BEARISH (30–45)"
          rsi_states -- zone held / since, side of 50, rising / falling, RSI vs its
          hidden MA; events: every zone change (from -> to, up or down), RSI crossing
          50 (TradingView cross rule), RSI crossing its MA (recorded only, hidden).
          Both directions always -- no index / stock filter (Ash, 2026-10-13).
          rsi_label -- the zone label. rsi_all runs it all.
  Part 3 (next): snapshot + plain-English texts per timeframe (every zone change and
          every 50 cross is an alert; RSI-MA crosses are not shown).

TradingView parity (Ash's tv.dhan settings, 2026-10-13: Length 14, source close,
Smoothing Line SMA, Smoothing Length 14, Smoothed MA off). TradingView's ta.rsi:
    change = close - close[1]                     (blank on the first candle)
    up     = rma(max(change, 0), 14)
    down   = rma(max(-change, 0), 14)
    rsi    = 100 if down == 0, else 0 if up == 0, else 100 - 100 / (1 + up / down)
    rsi_ma = sma(rsi, 14)
  rma = Wilder's average (Pine ta.rma) = indicator_common.smoothing.rma_tradingview,
  the same function proven exact on ADX (ADX.md section 3.2). First values: RSI candle
  15 (14 changes needed), rsi_ma candle 28.
  Note the order of Pine's checks: down == 0 is tested first, so a flat stretch (no
  gains, no losses) gives 100, not 0 or 50.

Any timeframe: periods are counted in candles of whatever the input holds.
Reading the bars is the caller's job (indicator_ohlcv_reader).

Input contract (programming errors raise ValueError):
  - DataFrame with a numeric price column (default 'close')
  - rows in ascending time order ('ts' checked when present)
  - lengths positive integers
The input DataFrame is never modified; a copy with the new columns is returned.

Standards applied: single responsibility (RSI maths only), pure function (no I/O),
reuse of indicator_common (DRY), input validation, vectorised pandas, unit tests
(test_rsi.py).
Deferred (with reasons):
  - Logging: none inside the pure function (bad input raises); the manual check logs.
  - Texts / alerts: part 3, by agreement (baby steps).
  - The ~55 support/resistance study: needs price S&R levels first (Phase 5/6).
  - Divergence: not offered in Ash's RSI settings, nothing to prove parity against.
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
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.smoothing import rma_tradingview
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    DEFAULT_DOMAIN,
    TIMEFRAMES,
    UNIT,
    is_intraday,
)

RSI_LEN = 14
MA_LEN = 14                 # "Smoothing Length" -- the hidden Smoothed MA line
RSI_COLS = ("rsi", "rsi_ma")


def _validate(df: pd.DataFrame, price_col: str, length: int, ma_length: int) -> None:
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame "
                         f"(columns: {list(df.columns)})")
    for name, n in (("length", length), ("ma_length", ma_length)):
        if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
            raise ValueError(f"{name} {n!r} is not a positive integer")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before computing RSI")


def compute_rsi(
    df: pd.DataFrame,
    length: int = RSI_LEN,
    ma_length: int = MA_LEN,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Return a copy of `df` with:
      rsi     TradingView RSI (0-100), blank before candle length + 1
      rsi_ma  SMA of RSI over ma_length (hidden extra), blank until ma_length RSI values exist

    Raises:
        ValueError on a missing price column, bad lengths or unsorted bars.
    """
    _validate(df, price_col, length, ma_length)
    out = df.copy()
    change = out[price_col].diff()                       # blank on the first candle
    gain = change.clip(lower=0)                          # NaN stays NaN
    loss = (-change).clip(lower=0)
    up = rma_tradingview(gain, length)
    down = rma_tradingview(loss, length)

    rsi = 100 - 100 / (1 + up / down.where(down != 0))
    rsi = rsi.mask(up == 0, 0.0).mask(down == 0, 100.0)   # Pine order: down == 0 wins
    rsi = rsi.where(up.notna() & down.notna())

    out["rsi"] = rsi
    out["rsi_ma"] = rsi.rolling(ma_length, min_periods=ma_length).mean()
    return out


# --- Part 2: zones, states, events, label --------------------------------------------

# Lowest to highest; the rank decides whether a zone change is upward or downward.
ZONES = ("oversold", "strong_bear", "bearish", "sr_zone", "bullish", "strong_bull", "overbought")
ZONE_RANK = {z: i for i, z in enumerate(ZONES)}
ZONE_NAME = {
    "overbought": "OVERBOUGHT", "strong_bull": "STRONG BULL", "bullish": "BULLISH",
    "sr_zone": "RSI S&R ZONE", "bearish": "BEARISH", "strong_bear": "STRONG BEAR",
    "oversold": "OVERSOLD",
}
RANGE_RISING = {                     # range written low -> high (rising, and the label)
    "overbought": ">80", "strong_bull": "70–80", "bullish": "55–70", "sr_zone": "45–55",
    "bearish": "30–45", "strong_bear": "20–30", "oversold": "<20",
}
RANGE_FALLING = {                    # range written high -> low (falling)
    "overbought": ">80", "strong_bull": "80–70", "bullish": "70–55", "sr_zone": "55–45",
    "bearish": "45–30", "strong_bear": "30–20", "oversold": "<20",
}
ZONE_LABEL = {z: f"{ZONE_NAME[z]} ({RANGE_RISING[z]})" for z in ZONES}   # e.g. "BEARISH (30–45)"
_STRONG_UP_INTO = {"bullish", "strong_bull", "overbought"}       # up into these -> "rising strong up"
_STRONG_DOWN_INTO = {"bearish", "strong_bear", "oversold"}       # down into these -> "falling strong down"
MID_LEVEL = 50.0
LABEL_NA = "n/a (not enough history)"


def zone_change_text(rsi_value: float, zone_from: str, zone_to: str) -> str:
    """
    The zone-change sentence (Ash, 2026-10-13), e.g.
      'RSI 33.66 STRONG BEAR (20–30) rising up into BEARISH (30–45)'
      'RSI 26.44 BEARISH (45–30) falling strong down into STRONG BEAR (30–20)'
    Ranges follow the direction of the move. Raises ValueError on an unknown zone or
    zone_from == zone_to (not a change).
    """
    if zone_from not in ZONE_RANK or zone_to not in ZONE_RANK:
        raise ValueError(f"unknown zone: {zone_from!r} -> {zone_to!r}")
    if zone_from == zone_to:
        raise ValueError(f"not a zone change: {zone_from!r} -> {zone_to!r}")
    rising = ZONE_RANK[zone_to] > ZONE_RANK[zone_from]
    if rising:
        verb = "rising strong up" if zone_to in _STRONG_UP_INTO else "rising up"
        ranges = RANGE_RISING
    else:
        verb = "falling strong down" if zone_to in _STRONG_DOWN_INTO else "falling down"
        ranges = RANGE_FALLING
    return (f"RSI {rsi_value:.2f} {ZONE_NAME[zone_from]} ({ranges[zone_from]}) {verb} into "
            f"{ZONE_NAME[zone_to]} ({ranges[zone_to]})")


def rsi_zone(rsi: pd.Series) -> pd.Series:
    """Zone per candle (boundaries in the module docstring); blank RSI -> None."""
    conditions = [rsi >= 80, rsi >= 70, rsi > 55, rsi >= 45, rsi >= 30, rsi >= 20, rsi < 20]
    names = ["overbought", "strong_bull", "bullish", "sr_zone", "bearish", "strong_bear",
             "oversold"]
    zone = np.select(conditions, names, default=None).astype(object)
    zone[rsi.isna().to_numpy()] = None
    return pd.Series(zone, index=rsi.index, dtype=object)


def rsi_states(df: pd.DataFrame) -> pd.DataFrame:
    """
    From compute_rsi output, adds per candle:
      rsi_zone                     one of ZONES (None when RSI is blank)
      rsi_zone_held / _since / _from_start   candles in this zone (first = 1), when it began,
                                   True if the zone began with the history (no change seen)
      zone_change                  True on the candle RSI moved into a different zone
      zone_from                    the zone it came from (None if no change)
      zone_change_up               True if the move was upward (to a higher zone), False if
                                   downward, None if no change
      rsi_side50                   +1 above 50, -1 below, 0 exactly 50, NaN blank
      rsi_side50_held / _since / _from_start
      rsi_cross_above_50 / rsi_cross_below_50   TradingView crossover / crossunder of 50
      rsi_slope                    +1 rising, -1 falling, 0 flat (vs previous candle)
      rsi_slope_held               candles the slope has kept its direction (first = 1)
      rsi_ma_side                  +1 RSI above its MA, -1 below, 0 equal (hidden)
      rsi_ma_cross_above / rsi_ma_cross_below   RSI crossing its MA (hidden, recorded only)
    Returns a copy; raises ValueError if compute_rsi has not been run or bars are unsorted.
    """
    missing = [c for c in RSI_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for rsi_states: {missing} (run compute_rsi first)")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before rsi_states")

    out = df.copy()
    rsi, ma = out["rsi"], out["rsi_ma"]
    labels = bar_labels(out)

    zone = rsi_zone(rsi)
    held, since, from_start = runs(zone, labels)
    prev = zone.shift(1)
    change = zone.notna() & prev.notna() & (zone != prev)
    out["rsi_zone"] = zone
    out["rsi_zone_held"] = held
    out["rsi_zone_since"] = since
    out["rsi_zone_from_start"] = from_start
    out["zone_change"] = change.astype(bool)
    out["zone_from"] = prev.where(change, None)
    up = [None if not c else ZONE_RANK[z] > ZONE_RANK[p] for c, z, p in zip(change, zone, prev)]
    out["zone_change_up"] = pd.Series(up, index=out.index, dtype=object)

    side = np.sign(rsi - MID_LEVEL)
    held, since, from_start = runs(side, labels)
    level = pd.Series(MID_LEVEL, index=out.index)
    out["rsi_side50"] = side
    out["rsi_side50_held"] = held
    out["rsi_side50_since"] = since
    out["rsi_side50_from_start"] = from_start
    out["rsi_cross_above_50"] = cross_above(rsi, level)
    out["rsi_cross_below_50"] = cross_below(rsi, level)

    slope = np.sign(rsi - rsi.shift(1))
    held, _, _ = runs(slope, labels)
    out["rsi_slope"] = slope
    out["rsi_slope_held"] = held

    out["rsi_ma_side"] = np.sign(rsi - ma)
    out["rsi_ma_cross_above"] = cross_above(rsi, ma)
    out["rsi_ma_cross_below"] = cross_below(rsi, ma)
    return out


def rsi_label(df: pd.DataFrame) -> pd.Series:
    """The zone label per candle, e.g. 'RSI S&R ZONE (45–55)'; blank -> 'n/a (not enough history)'."""
    if "rsi_zone" not in df.columns:
        raise ValueError("column 'rsi_zone' missing for rsi_label (run rsi_states first)")
    return pd.Series([ZONE_LABEL[z] if isinstance(z, str) else LABEL_NA for z in df["rsi_zone"]],
                     index=df.index, dtype=object)


def rsi_all(df: pd.DataFrame) -> pd.DataFrame:
    """compute_rsi -> rsi_states -> rsi_label, in one call."""
    out = rsi_states(compute_rsi(df))
    out["rsi_label"] = rsi_label(out)
    return out


# --- Manual check: RSI on the latest bars, to compare with TradingView ---------

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi
    #   ... rsi --dates 2026-10-07 2026-10-08 2026-10-09
    #   ... rsi --timeframe 60m --dates 2026-10-09 --ohlc
    #   ... rsi --timeframe all                 (latest candles on 1M, 1W, 1D, 60m, 15m, 5m)
    #   ... rsi --state [--timeframe 15m]       (zone, side of 50, slope, last events)
    #   ... rsi --timeframe all --state         (all six timeframes + summary table)
    #   ... rsi --crosses 15 [--timeframe 5m]   (latest zone changes and 50 crosses)
    # Output goes to the screen AND to one log per timeframe and mode (overwritten each
    # run; first line = the command):
    #   logs/rsi_test_logs/rsi_check_<timeframe>.log          (--bars / --dates)
    #   logs/rsi_test_logs/rsi_check_<timeframe>_<mode>.log   (mode = state, crosses)
    import argparse
    import logging
    from pathlib import Path

    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    parser = argparse.ArgumentParser(description="Print RSI (read-only).")
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
    mode_group.add_argument("--state", action="store_true",
                            help="print zone / side of 50 / slope and last events for the latest candle")
    mode_group.add_argument("--crosses", type=int, metavar="N",
                            help="print the latest N events (zone changes, RSI crossing 50)")
    args = parser.parse_args()
    mode = "state" if args.state else "crosses" if args.crosses else None
    timeframes = list(TIMEFRAMES) if args.timeframe == "all" else [args.timeframe]

    load_dotenv()
    log_path = (Path("logs") / "rsi_test_logs"
                / f"rsi_check_{args.timeframe}{'_' + mode if mode else ''}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    log = logging.getLogger("rsi_check")
    log.info("command: rsi --timeframe %s --domain %s --key %s %s", args.timeframe,
             args.domain or "default", args.key,
             "--state" if args.state else
             f"--crosses {args.crosses}" if args.crosses else
             (f"--dates {' '.join(args.dates)}" if args.dates else f"--bars {args.bars}")
             + (" --ohlc" if args.ohlc else ""))

    summary = []      # (timeframe, as of, RSI, label, held) for --timeframe all --state

    def check_one(tf: str) -> None:
        domain = args.domain or DEFAULT_DOMAIN[tf]
        intraday = is_intraday(tf)
        unit = UNIT.get(tf, "candle")
        f = lambda v: "n/a" if pd.isna(v) else f"{v:.2f}"
        when_of = ((lambda v: pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")) if intraday
                   else (lambda v: pd.Timestamp(v).strftime("%Y-%m-%d")))

        res = read_for_indicators(args.key, domain, tf)
        log.info("=" * 96)
        log.info("RSI CHECK — %s (%s, RSI 14 close, TradingView method)", args.key, tf)
        log.info("=" * 96)
        if not res.ok:
            log.warning("NOT OK -- %s", res.error)
            summary.append((tf, "-", "-", "NOT OK", res.error))
            return

        if args.state:
            a = rsi_all(res.df)
            r = a.iloc[-1]
            partial = f" ({unit} to date)" if tf in ("1w", "1mo") else ""
            log.info("as of %s%s   close %.2f", when_of(r["ts"]), partial, r["close"])
            log.info("RSI %s   (RSI MA, hidden: %s)", f(r["rsi"]), f(r["rsi_ma"]))
            log.info("zone            : %s", r["rsi_label"])
            if isinstance(r["rsi_zone"], str):
                start = " (start of data)" if r["rsi_zone_from_start"] else ""
                log.info("zone held       : %d %s(s) since %s%s", int(r["rsi_zone_held"]), unit,
                         when_of(r["rsi_zone_since"]), start)
            if pd.notna(r["rsi_side50"]):
                word = {1: "above 50", -1: "below 50", 0: "exactly 50"}[int(r["rsi_side50"])]
                start = " (start of data)" if r["rsi_side50_from_start"] else ""
                log.info("side of 50      : %s, held %d %s(s) since %s%s", word,
                         int(r["rsi_side50_held"]), unit, when_of(r["rsi_side50_since"]), start)
            if pd.notna(r["rsi_slope"]) and pd.notna(r["rsi_slope_held"]):
                word = {1: "rising", -1: "falling", 0: "flat"}[int(r["rsi_slope"])]
                log.info("slope           : %s for %d %s(s)", word, int(r["rsi_slope_held"]), unit)
            changes = a.loc[a["zone_change"]]
            if len(changes):
                c = changes.iloc[-1]
                log.info("last zone change: %s  %s", when_of(c["ts"]),
                         zone_change_text(c["rsi"], c["zone_from"], c["rsi_zone"]))
            else:
                log.info("last zone change: none in history")
            for col, text in (("rsi_cross_above_50", "last cross above 50"),
                              ("rsi_cross_below_50", "last cross below 50")):
                hits = a.loc[a[col].astype(bool), "ts"]
                log.info("%-16s: %s", text, when_of(hits.iloc[-1]) if len(hits) else "none in history")
            summary.append((tf, when_of(r["ts"]) + partial, f(r["rsi"]), r["rsi_label"],
                            f"{int(r['rsi_zone_held'])} {unit}(s)"
                            if isinstance(r["rsi_zone"], str) else ""))
            return

        if args.crosses:
            a = rsi_all(res.df)
            events = []
            mask = a["zone_change"] | a["rsi_cross_above_50"] | a["rsi_cross_below_50"]
            for _, r in a.loc[mask].iterrows():
                w = when_of(r["ts"])
                if r["zone_change"]:
                    events.append(f"{w}  {zone_change_text(r['rsi'], r['zone_from'], r['rsi_zone'])}")
                if r["rsi_cross_above_50"]:
                    events.append(f"{w}  RSI {r['rsi']:.2f} crossed ABOVE 50")
                if r["rsi_cross_below_50"]:
                    events.append(f"{w}  RSI {r['rsi']:.2f} crossed BELOW 50")
            log.info("latest %d events (zone changes + 50 crosses, oldest first):", args.crosses)
            for text in events[-args.crosses:]:
                log.info("  %s", text)
            log.info("total events in history: %s  (data as of %s)", f"{len(events):,}", res.last_ts)
            return

        r_all = compute_rsi(res.df)
        if args.dates:
            wanted = set(args.dates)
            rows = r_all[r_all["trade_date"].astype(str).isin(wanted)]
            for d in sorted(wanted - set(rows["trade_date"].astype(str))):
                log.info("%s  no bar on this date (not a trading day in our data)", d)
        else:
            rows = r_all.tail(args.bars)
        w = 26 if intraday else 12
        ohlc_head = f"{'open':>11}{'high':>11}{'low':>11}" if args.ohlc else ""
        log.info(f"{'bar':<{w}}{ohlc_head}{'close':>11}{'RSI':>9}{'RSI MA (hidden)':>18}")
        for _, r in rows.iterrows():
            when = str(r["ts"]) if intraday else str(r["trade_date"])
            ohlc = (f"{r['open']:>11.2f}{r['high']:>11.2f}{r['low']:>11.2f}" if args.ohlc else "")
            log.info(f"{when:<{w}}{ohlc}{r['close']:>11.2f}{f(r['rsi']):>9}{f(r['rsi_ma']):>18}")
        partial = f"  (latest {UNIT[tf]} is {UNIT[tf]} to date)" if tf in ("1w", "1mo") else ""
        log.info("bars used: %s  (data as of %s)%s", f"{len(r_all):,}", res.last_ts, partial)
        log.info("TradingView legend: 'RSI 14' value = the RSI column. "
                 "RSI MA is the Smoothed MA line (switched off on Ash's chart).")

    for tf in timeframes:
        check_one(tf)
    if args.state and len(timeframes) > 1:
        log.info("=" * 96)
        log.info("SUMMARY — RSI on each timeframe (latest stored candle)")
        for row in summary:
            log.info("  %-4s %-26s RSI %-7s %-24s %s", *row)
    log.info("=" * 96)
    log.info("log written to %s", log_path)
