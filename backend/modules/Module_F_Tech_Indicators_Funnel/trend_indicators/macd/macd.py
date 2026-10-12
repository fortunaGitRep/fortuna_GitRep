"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd/macd.py

MACD calculator (spec: Fortuna Indicators/MACD.md).
  Part 2: compute_macd -- MACD, signal, histogram, the histogram's 4
          TradingView colour states, and PPO (extra column).
  Part 3: trend_macd    -- "which direction?"  MACD vs zero (= EMA12 vs EMA26):
                           side, held, since, zero-line crosses.
          momentum_macd -- "speeding up or slowing down?"  MACD vs signal +
                           histogram: side, held, since, gap, signal crosses
                           tagged below/above/at zero, colour held, momentum turns.
          macd_label    -- one combined label per candle (MACD.md section 7).
          Facts only -- no strong/weak thresholds (to be tested on Nifty later).
  Part 4 (next): snapshot + plain-English texts per timeframe.

TradingView parity (settings confirmed from Ash's chart 2026-10-11):
  Fast 12 · Slow 26 · Source close · Signal 9 · Oscillator MA EMA · Signal MA EMA
    macd   = ta.ema(close, 12) - ta.ema(close, 26)      first value at bar 26
    signal = ta.ema(macd, 9)                            first value at bar 34
    hist   = macd - signal                              first value at bar 34
  ta.ema = the proven ema_tradingview() from ../ema/ema.py (SMA seed, blank
  before). The signal EMA runs over the MACD series from its first non-blank
  value, so its seed is the average of MACD bars 26..34 -- Pine's behaviour.

Histogram colour (copied from TradingView's built-in script, so the state always
equals the bar colour on the chart):
    hist >= 0 and hist >  yesterday -> 'above_growing'  (dark green)
    hist >= 0 and hist <= yesterday -> 'above_fading'   (light green)
    hist <  0 and hist >  yesterday -> 'below_fading'   (light red)
    hist <  0 and hist <= yesterday -> 'below_growing'  (dark red)
  Zero counts as above; equal to yesterday counts as not rising. First histogram
  bar has no yesterday -> blank (None).

PPO = (EMA12 - EMA26) / EMA26 * 100 -- MACD as % of price, for ranking stocks
later. An EXTRA column: it never replaces a TradingView number.

Any timeframe: periods are counted in candles of whatever the input holds
(1M/1W/1D/60m/15m/5m). Reading the bars is the caller's job
(indicator_ohlcv_reader).

Input contract (programming errors raise ValueError -- the reader already
validated the data, so a bad input here is a code bug, not a data condition):
  - DataFrame with a numeric price column (default 'close')
  - rows in ascending time order ('ts' checked when present)
  - fast < slow, all lengths positive integers
The input DataFrame is never modified; a copy with the new columns is returned.

Standards applied: single responsibility (MACD math only), pure function (no I/O,
no global state), reuse of ema_tradingview (DRY), input validation, vectorised
pandas, unit tests (test_macd.py).
Deferred (with reasons):
  - Logging: none inside the pure function (bad input raises); the manual check
    below and future callers log their runs.
  - Events / states / texts: parts 3-4, by agreement (baby steps).

Shared helpers (2026-10-12): ema_tradingview, cross_above / cross_below, the run
helper (_runs), the bar-label helper (_labels) and the timeframe -> domain map
(_DEFAULT_DOMAIN) now live in ../../indicator_common/, moved unchanged. This file
imports them and still exports _runs and _DEFAULT_DOMAIN under the old names.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.crosses import (
    bar_labels as _labels,
    cross_above,
    cross_below,
    runs as _runs,          # re-exported under the old name (tests, adx used M._runs)
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.smoothing import ema_tradingview
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    DEFAULT_DOMAIN as _DEFAULT_DOMAIN,   # re-exported under the old name
)

FAST, SLOW, SIGNAL = 12, 26, 9

HIST_STATES = ("above_growing", "above_fading", "below_fading", "below_growing")
HIST_COLOUR = {                    # TradingView default colours, for texts
    "above_growing": "dark green",
    "above_fading": "light green",
    "below_fading": "light red",
    "below_growing": "dark red",
}
MACD_COLS = ("macd", "macd_signal", "macd_hist", "macd_hist_state", "ppo")


def _ema_from_first_valid(series: pd.Series, period: int) -> pd.Series:
    """ta.ema over a series with leading blanks: seed from its first n values."""
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    valid = series.dropna()
    if valid.empty:
        return out
    start = series.index.get_loc(valid.index[0])
    out.iloc[start:] = ema_tradingview(series.iloc[start:], period).to_numpy()
    return out


def hist_states(hist: pd.Series) -> pd.Series:
    """The 4 TradingView colour states per bar (None where blank / no yesterday)."""
    prev = hist.shift(1)
    rising = hist > prev
    above = hist >= 0
    state = np.select(
        [above & rising, above & ~rising, ~above & rising, ~above & ~rising],
        list(HIST_STATES), default=None,
    ).astype(object)
    state[(hist.isna() | prev.isna()).to_numpy()] = None
    return pd.Series(state, index=hist.index, dtype=object)


def _validate(df: pd.DataFrame, price_col: str, fast: int, slow: int, signal: int) -> None:
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame "
                         f"(columns: {list(df.columns)})")
    for name, n in (("fast", fast), ("slow", slow), ("signal", signal)):
        if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
            raise ValueError(f"{name} length {n!r} is not a positive integer")
    if fast >= slow:
        raise ValueError(f"fast length ({fast}) must be shorter than slow ({slow})")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before computing MACD")


def compute_macd(
    df: pd.DataFrame,
    fast: int = FAST,
    slow: int = SLOW,
    signal: int = SIGNAL,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Return a copy of `df` with: macd, macd_signal, macd_hist, macd_hist_state, ppo.

    Defaults are TradingView's (12, 26, 9, close). Blank (NaN / None) where there
    is not enough history yet: MACD before bar `slow`, signal/hist before bar
    slow + signal - 1, hist state one bar later.

    Raises:
        ValueError on a missing price column, bad lengths or unsorted bars.
    """
    _validate(df, price_col, fast, slow, signal)

    out = df.copy()
    prices = out[price_col]
    ema_fast = ema_tradingview(prices, fast)
    ema_slow = ema_tradingview(prices, slow)

    out["macd"] = ema_fast - ema_slow
    out["macd_signal"] = _ema_from_first_valid(out["macd"], signal)
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    out["macd_hist_state"] = hist_states(out["macd_hist"])
    out["ppo"] = (ema_fast - ema_slow) / ema_slow * 100
    return out



# --- Part 3: trend_macd, momentum_macd, combined label ---------------------------

LABELS = {                         # (trend side, momentum side) -> label (MACD.md section 7)
    (1, 1): "STRONG UPTREND",
    (1, -1): "UPTREND PAUSING",
    (-1, 1): "DOWNTREND WEAKENING",
    (-1, -1): "STRONG DOWNTREND",
}
LABEL_NEUTRAL = "NEUTRAL"
LABEL_NA = "n/a (not enough history)"
ZONES = ("below_zero", "above_zero", "at_zero")


def _require(df: pd.DataFrame, cols: tuple[str, ...], what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for {what}: {missing} (run compute_macd first)")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError(f"bars are not in ascending 'ts' order; sort before {what}")


def trend_macd(df: pd.DataFrame) -> pd.DataFrame:
    """
    MACD vs zero (identical to EMA12 vs EMA26). Adds per candle:
      trend_side        +1 above zero, -1 below, 0 on zero, NaN blank
      trend_held        candles on this side, cross candle = 1
      trend_since       ts (or trade_date) the side began
      trend_from_start  True if the side began with the history (no cross seen)
      zero_cross_above / zero_cross_below   TradingView crossover / crossunder vs 0
    Returns a copy; raises ValueError if compute_macd has not been run.
    """
    _require(df, ("macd",), "trend_macd")
    out = df.copy()
    macd = out["macd"]
    zero = pd.Series(0.0, index=out.index)
    side = np.sign(macd)
    held, since, from_start = _runs(side, _labels(out))
    out["trend_side"] = side
    out["trend_held"] = held
    out["trend_since"] = since
    out["trend_from_start"] = from_start
    out["zero_cross_above"] = cross_above(macd, zero)
    out["zero_cross_below"] = cross_below(macd, zero)
    return out


def momentum_macd(df: pd.DataFrame) -> pd.DataFrame:
    """
    MACD vs signal + histogram. Adds per candle:
      mom_side           +1 MACD above signal, -1 below, 0 equal, NaN blank
      mom_held / mom_since / mom_from_start   as for trend_macd
      mom_gap            MACD - signal (= histogram), points
      signal_cross_above / signal_cross_below   TradingView crossover / crossunder
      signal_cross_zone  on a cross candle: 'below_zero' / 'above_zero' / 'at_zero'
                         (where MACD is on that candle), else None
      hist_state_held    candles the histogram has kept its current colour state
      momentum_turn      True when the colour changes between growing and fading on
                         the SAME side of zero (e.g. below_growing -> below_fading).
                         A change of side is a signal cross, not a turn.
    Returns a copy; raises ValueError if compute_macd has not been run.
    """
    _require(df, ("macd", "macd_signal", "macd_hist", "macd_hist_state"), "momentum_macd")
    out = df.copy()
    macd, signal, hist = out["macd"], out["macd_signal"], out["macd_hist"]
    labels = _labels(out)

    side = np.sign(hist)
    held, since, from_start = _runs(side, labels)
    out["mom_side"] = side
    out["mom_held"] = held
    out["mom_since"] = since
    out["mom_from_start"] = from_start
    out["mom_gap"] = hist

    up = cross_above(macd, signal)
    down = cross_below(macd, signal)
    zone = np.select([macd < 0, macd > 0], ["below_zero", "above_zero"], default="at_zero")
    out["signal_cross_above"] = up
    out["signal_cross_below"] = down
    out["signal_cross_zone"] = pd.Series(zone, index=out.index, dtype=object).where(up | down, None)

    state = out["macd_hist_state"]
    state_held, _, _ = _runs(state, labels)
    out["hist_state_held"] = state_held
    prev = state.shift(1)
    both = state.notna() & prev.notna()
    same_side = both & (state.str.split("_").str[0] == prev.str.split("_").str[0])
    out["momentum_turn"] = (same_side & (state != prev)).fillna(False).astype(bool)
    return out


def macd_label(df: pd.DataFrame) -> pd.Series:
    """
    Combined label per candle (MACD.md section 7) from trend_side and mom_side:
      above/above STRONG UPTREND · above/below UPTREND PAUSING ·
      below/above DOWNTREND WEAKENING · below/below STRONG DOWNTREND ·
      either equal NEUTRAL · either blank 'n/a (not enough history)'.
    Needs trend_macd and momentum_macd columns.
    """
    _require(df, ("trend_side", "mom_side"), "macd_label")
    t, m = df["trend_side"], df["mom_side"]
    out = []
    for tv, mv in zip(t, m):
        if pd.isna(tv) or pd.isna(mv):
            out.append(LABEL_NA)
        elif tv == 0 or mv == 0:
            out.append(LABEL_NEUTRAL)
        else:
            out.append(LABELS[(int(tv), int(mv))])
    return pd.Series(out, index=df.index, dtype=object)


def macd_all(df: pd.DataFrame) -> pd.DataFrame:
    """compute_macd -> trend_macd -> momentum_macd -> macd_label, in one call."""
    out = momentum_macd(trend_macd(compute_macd(df)))
    out["macd_label"] = macd_label(out)
    return out

# --- Manual check: MACD on the latest bars, to compare with TradingView ---------
# (_DEFAULT_DOMAIN: timeframe -> R2 domain, now from indicator_common/timeframes.py)

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd
    #   ... macd --timeframe 1w --bars 5
    #   ... macd --dates 2026-10-07 2026-10-08 2026-10-09
    #   ... macd --timeframe 60m --dates 2026-10-09 --ohlc     (candles + MACD)
    #   ... macd --state [--timeframe 15m]                       (where we stand now)
    #   ... macd --crosses 15 [--timeframe 1d]   (latest zero + signal crosses)
    #   ... macd --turns 15 [--timeframe 5m]     (latest momentum turns = histogram colour changes)
    #   ... macd --events 15                     (all three kinds together, as before 2026-10-12)
    #   ... macd --timeframe all --state     (where we stand on 1M, 1W, 1D, 60m, 15m, 5m)
    # Output goes to the screen AND to one log per timeframe and mode, overwritten each run:
    #   logs/macd_test_logs/macd_check_<timeframe>.log          (--bars / --dates)
    #   logs/macd_test_logs/macd_check_<timeframe>_<mode>.log   (mode = state, crosses, turns, events)
    import argparse
    import logging
    from pathlib import Path

    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    parser = argparse.ArgumentParser(description="Print MACD for the latest bars (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--timeframe", default="1d", choices=list(_DEFAULT_DOMAIN) + ["all"],
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
                            help="print trend / momentum state and label for the latest candle")
    mode_group.add_argument("--crosses", type=int, metavar="N",
                            help="print the latest N crosses (zero-line and signal-line)")
    mode_group.add_argument("--turns", type=int, metavar="N",
                            help="print the latest N momentum turns (histogram colour changes "
                                 "growing <-> fading on the same side of zero)")
    mode_group.add_argument("--events", type=int, metavar="N",
                            help="print the latest N events of all three kinds together "
                                 "(the list --crosses printed before 2026-10-12)")
    args = parser.parse_args()
    mode = ("state" if args.state else "crosses" if args.crosses else
            "turns" if args.turns else "events" if args.events else None)
    n_events = args.crosses or args.turns or args.events
    timeframes = (["1mo", "1w", "1d", "60m", "15m", "5m"] if args.timeframe == "all"
                  else [args.timeframe])

    load_dotenv()
    log_path = (Path("logs") / "macd_test_logs"
                / f"macd_check_{args.timeframe}{'_' + mode if mode else ''}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    log = logging.getLogger("macd_check")
    log.info("command: macd --timeframe %s --domain %s --key %s %s", args.timeframe,
             args.domain or "default", args.key,
             "--state" if args.state else
             f"--{mode} {n_events}" if n_events else
             (f"--dates {' '.join(args.dates)}" if args.dates else f"--bars {args.bars}")
             + (" --ohlc" if args.ohlc else ""))

    summary = []      # (timeframe, as of, label, histogram) for --state

    def check_one(tf: str) -> None:
        domain = args.domain or _DEFAULT_DOMAIN[tf]
        intraday = tf in ("5m", "15m", "60m")
        res = read_for_indicators(args.key, domain, tf)
        log.info("=" * 96)
        log.info("MACD CHECK — %s (%s, 12 26 close 9 EMA EMA, TradingView method)",
                 args.key, tf)
        log.info("=" * 96)
        unit = {"1d": "day", "1w": "week", "1mo": "month"}.get(tf, "candle")
        when_of = (lambda v: pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")) if intraday \
            else (lambda v: pd.Timestamp(v).strftime("%Y-%m-%d"))
        if not res.ok:
            log.warning("NOT OK -- %s", res.error)
            summary.append((tf, "-", "NOT OK", res.error))
        elif args.state:
            m = macd_all(res.df)
            r = m.iloc[-1]
            f = lambda v: "n/a" if pd.isna(v) else f"{v:.2f}"
            word = {1: "above", -1: "below", 0: "on"}
            partial = (" (" + unit + " to date)") if tf in ("1w", "1mo") else ""
            log.info("as of %s%s   close %.2f", when_of(r["ts"]), partial, r["close"])
            log.info("MACD %s · signal %s · histogram %s (%s)", f(r["macd"]), f(r["macd_signal"]),
                     f(r["macd_hist"]), HIST_COLOUR.get(r["macd_hist_state"], "n/a")
                     if r["macd_hist_state"] else "n/a")
            log.info("label           : %s", r["macd_label"])
            st0 = r["macd_hist_state"]
            summary.append((tf, when_of(r["ts"]) + partial, r["macd_label"],
                            f"{st0.replace('_', ' ')} ({HIST_COLOUR[st0]}), "
                            f"{int(r['hist_state_held'])} {unit}(s)" if st0 else "n/a"))

            def run_line(name, side, held, since, from_start, other):
                if pd.isna(side):
                    return f"{name:<16}: blank (not enough history)"
                start = " (start of data)" if from_start else ""
                return (f"{name:<16}: MACD {word[int(side)]} {other}, held {int(held)} "
                        f"{unit}(s) since {when_of(since)}{start}")

            log.info(run_line("trend (vs 0)", r["trend_side"], r["trend_held"], r["trend_since"],
                              r["trend_from_start"], "zero"))
            log.info(run_line("momentum (vs sig)", r["mom_side"], r["mom_held"], r["mom_since"],
                              r["mom_from_start"], "signal") + f", gap {f(r['mom_gap'])}")
            st = r["macd_hist_state"]
            if st:
                log.info("histogram       : %s (%s) for %d %s(s)", st.replace("_", " "),
                         HIST_COLOUR[st], int(r["hist_state_held"]), unit)

            def last_event(mask, text):
                hits = m.loc[mask]
                if hits.empty:
                    return f"{text:<22}: none in history"
                h = hits.iloc[-1]
                zone = (f" ({h['signal_cross_zone'].replace('_', ' ')})"
                        if "signal" in text and h["signal_cross_zone"] else "")
                return f"{text:<22}: {when_of(h['ts'])}{zone}"

            log.info(last_event(m["zero_cross_above"], "last zero cross above"))
            log.info(last_event(m["zero_cross_below"], "last zero cross below"))
            log.info(last_event(m["signal_cross_above"], "last signal cross above"))
            log.info(last_event(m["signal_cross_below"], "last signal cross below"))
            log.info(last_event(m["momentum_turn"], "last momentum turn"))
        elif n_events:
            m = macd_all(res.df)
            want_crosses = mode in ("crosses", "events")
            want_turns = mode in ("turns", "events")
            mask = pd.Series(False, index=m.index)
            if want_crosses:
                mask |= (m["zero_cross_above"] | m["zero_cross_below"]
                         | m["signal_cross_above"] | m["signal_cross_below"])
            if want_turns:
                mask |= m["momentum_turn"].astype(bool)
            events = []
            for _, r in m.loc[mask].iterrows():
                when = when_of(r["ts"])
                if want_crosses and r["zero_cross_above"]:
                    events.append((r["ts"], f"{when}  MACD crossed ABOVE zero (12 EMA above 26 EMA)"))
                if want_crosses and r["zero_cross_below"]:
                    events.append((r["ts"], f"{when}  MACD crossed BELOW zero (12 EMA below 26 EMA)"))
                if want_crosses and r["signal_cross_above"]:
                    events.append((r["ts"], f"{when}  MACD crossed ABOVE signal, "
                                            f"{r['signal_cross_zone'].replace('_', ' ')}"))
                if want_crosses and r["signal_cross_below"]:
                    events.append((r["ts"], f"{when}  MACD crossed BELOW signal, "
                                            f"{r['signal_cross_zone'].replace('_', ' ')}"))
                if want_turns and r["momentum_turn"]:
                    events.append((r["ts"], f"{when}  momentum turn: histogram now "
                                            f"{r['macd_hist_state'].replace('_', ' ')} "
                                            f"({HIST_COLOUR[r['macd_hist_state']]})"))
            what = {"crosses": "crosses (zero + signal)", "turns": "momentum turns",
                    "events": "events (crosses + momentum turns)"}[mode]
            log.info("latest %d %s (oldest first):", n_events, what)
            for _, text in events[-n_events:]:
                log.info("  %s", text)
            log.info("total %s in history: %s  (data as of %s)", what, f"{len(events):,}",
                     res.last_ts)
        else:
            m = compute_macd(res.df)
            if args.dates:
                wanted = set(args.dates)
                rows = m[m["trade_date"].astype(str).isin(wanted)]
                for d in sorted(wanted - set(rows["trade_date"].astype(str))):
                    log.info("%s  no bar on this date (not a trading day in our data)", d)
            else:
                rows = m.tail(args.bars)
            when_w = 26 if intraday else 12
            f = lambda v: "n/a" if pd.isna(v) else f"{v:.2f}"
            ohlc_head = (f"{'open':>11}{'high':>11}{'low':>11}" if args.ohlc else "")
            log.info(f"{'bar':<{when_w}}{ohlc_head}{'close':>11}{'histogram':>12}{'MACD':>11}{'signal':>11}"
                     f"   {'colour':<12}{'PPO %':>9}")
            for _, r in rows.iterrows():
                when = str(r["ts"]) if intraday else str(r["trade_date"])
                state = r["macd_hist_state"]
                colour = HIST_COLOUR.get(state, "n/a") if state else "n/a"
                ppo = "n/a" if pd.isna(r["ppo"]) else f"{r['ppo']:+.3f}"
                ohlc = (f"{r['open']:>11.2f}{r['high']:>11.2f}{r['low']:>11.2f}"
                        if args.ohlc else "")
                log.info(f"{when:<{when_w}}{ohlc}{r['close']:>11.2f}{f(r['macd_hist']):>12}"
                         f"{f(r['macd']):>11}{f(r['macd_signal']):>11}   {colour:<12}{ppo:>9}")
            log.info("bars used: %s  (data as of %s)", f"{len(m):,}", res.last_ts)
            log.info("TradingView legend order is: histogram, MACD, signal "
                     "(same as the columns above).")
        log.info("=" * 96)

    for tf in timeframes:
        check_one(tf)

    if args.state and len(timeframes) > 1:
        log.info("SUMMARY — where Nifty stands on each timeframe (latest stored candle)")
        for tf, asof, label, hist in summary:
            log.info("  %-4s %-26s %-24s %s", tf, asof, label, hist)
        log.info("=" * 96)
    log.info("log written to %s", log_path)
