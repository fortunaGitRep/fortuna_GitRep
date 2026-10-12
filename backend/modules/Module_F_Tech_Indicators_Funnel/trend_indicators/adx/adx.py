"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx/adx.py

ADX / DMI calculator (spec: Fortuna Indicators/ADX.md).
  Part 1: compute_adx -- +DI, -DI, DX, ADX, ADXR, the five lines TradingView's
          "Directional Movement Index" (DMI 14 14) shows.
  Part 2: adx_states -- strength band (convention: <20 / 20-25 / 25-40 / 40-50 / 50+),
          ADX rising / falling and for how long, +DI vs -DI side / held / since,
          events: +DI/-DI cross and ADX crossing 25 (up = trend confirmed, down =
          trend fading). adx_label -- e.g. "STRONG TREND DOWN". adx_all runs it all.
          ADX turning up/down on single candles is NOT an event (too noisy) -- it
          shows only as "rising/falling for N candles".
  Part 3 (next): snapshot + plain-English texts per timeframe.

TradingView parity (Ash's chart: "DMI 14 14" = DI Length 14, ADX Smoothing 14).
TradingView's built-in method (Wilder):
    up       = high - high[1]                 down = low[1] - low
    +DM      = up   if up > down and up > 0 else 0     (blank on the first candle)
    -DM      = down if down > up and down > 0 else 0
    TR       = max(high - low, |high - close[1]|, |low - close[1]|)   (blank on the first candle)
    +DI      = 100 * rma(+DM, 14) / rma(TR, 14)      -DI likewise   (a blank is carried
               forward from the last value, Pine's fixnan)
    DX       = 100 * |+DI - -DI| / (+DI + -DI)        (sum 0 -> divide by 1)
    ADX      = rma(DX, 14)
    ADXR     = (ADX + ADX 13 candles ago) / 2     (n - 1 back, confirmed on Ash's chart)
  rma = Wilder's average (Pine ta.rma): alpha = 1/n, seeded with the simple average
  of the first n values, blank before. First values: +DI/-DI/DX candle 15,
  ADX candle 28, ADXR candle 41.

  ADXR lookback settled 2026-10-12: Nifty daily 9 Oct 2026 Fortuna 13-back = 37.4798
  = TradingView exactly (14-back gave 37.8067). All five lines equal Ash's chart to
  4 decimals on that candle.

Any timeframe: periods are counted in candles of whatever the input holds.
Reading the bars is the caller's job (indicator_ohlcv_reader).

Input contract (programming errors raise ValueError):
  - DataFrame with numeric high, low, close
  - rows in ascending time order ('ts' checked when present)
  - lengths positive integers
The input DataFrame is never modified; a copy with the new columns is returned.

Standards applied: single responsibility (ADX maths only), pure function (no I/O),
input validation, vectorised pandas, unit tests (test_adx.py).
Deferred (with reasons):
  - Logging: none inside the pure function (bad input raises); the manual check logs.
  - The timeframe -> domain map is repeated from macd.py, and the run-length helper
    (_runs) is imported from macd.py; move both into one shared indicator helper
    module when the next indicator needs them.
  - States / events / texts: parts 2-3, by agreement (baby steps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema import (
    cross_above,
    cross_below,
)
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd import _runs

DI_LEN, ADX_LEN = 14, 14
ADXR_LOOKBACK = 13          # n - 1 candles back -- matches TradingView (module docstring)
ADX_COLS = ("plus_di", "minus_di", "dx", "adx", "adxr")


def rma_tradingview(series: pd.Series, period: int) -> pd.Series:
    """
    Pine ta.rma (Wilder's average) over a series that may start with blanks:
    alpha = 1/period, seeded with the simple average of the first `period`
    non-blank values, blank before that.
    """
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    valid = series.dropna()
    if len(valid) < period:
        return out
    start = series.index.get_loc(valid.index[0])
    values = series.iloc[start:].to_numpy(dtype="float64")
    tail = values[period - 1:].copy()
    tail[0] = values[:period].mean()
    rma = pd.Series(tail).ewm(alpha=1.0 / period, adjust=False).mean().to_numpy()
    out.iloc[start + period - 1:] = rma
    return out


def _validate(df: pd.DataFrame, di_len: int, adx_len: int, adxr_lookback: int) -> None:
    missing = [c for c in ("high", "low", "close") if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for ADX: {missing}")
    for name, n in (("di_len", di_len), ("adx_len", adx_len), ("adxr_lookback", adxr_lookback)):
        if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
            raise ValueError(f"{name} {n!r} is not a positive integer")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before computing ADX")


def compute_adx(
    df: pd.DataFrame,
    di_len: int = DI_LEN,
    adx_len: int = ADX_LEN,
    adxr_lookback: int = ADXR_LOOKBACK,
) -> pd.DataFrame:
    """
    Return a copy of `df` with plus_di, minus_di, dx, adx, adxr (TradingView DMI).
    Blank (NaN) where there is not enough history yet.

    Raises:
        ValueError on missing high/low/close, bad lengths or unsorted bars.
    """
    _validate(df, di_len, adx_len, adxr_lookback)
    out = df.copy()
    high, low, close = out["high"], out["low"], out["close"]

    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=out.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=out.index)
    plus_dm[up.isna()] = np.nan
    minus_dm[down.isna()] = np.nan

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()],
                   axis=1).max(axis=1, skipna=False)
    tr[prev_close.isna()] = np.nan

    tr_s = rma_tradingview(tr, di_len)
    started = tr_s.notna().cumsum() > 0
    # Pine: x / 0 -> na, then fixnan carries the last value forward
    plus = (100 * rma_tradingview(plus_dm, di_len) / tr_s.where(tr_s != 0)).ffill().where(started)
    minus = (100 * rma_tradingview(minus_dm, di_len) / tr_s.where(tr_s != 0)).ffill().where(started)

    total = plus + minus
    dx = 100 * (plus - minus).abs() / total.where(total != 0, 1.0)
    adx = rma_tradingview(dx, adx_len)

    out["plus_di"] = plus
    out["minus_di"] = minus
    out["dx"] = dx
    out["adx"] = adx
    out["adxr"] = (adx + adx.shift(adxr_lookback)) / 2
    return out



# --- Part 2: strength band, slope, direction, events, label -------------------------

LEVEL = 25.0                                   # ADX crossing this = trend confirmed / fading
BANDS = ((20.0, "no_trend"), (25.0, "forming"), (40.0, "trending"), (50.0, "strong"),
         (float("inf"), "very_strong"))
BAND_TEXT = {"no_trend": "NO TREND", "forming": "TREND FORMING", "trending": "TRENDING",
             "strong": "STRONG TREND", "very_strong": "VERY STRONG TREND"}
LABEL_NA = "n/a (not enough history)"


def strength_band(adx: pd.Series) -> pd.Series:
    """Band per candle (convention, not a tested threshold): <20 no_trend, 20-25 forming,
    25-40 trending, 40-50 strong, 50+ very_strong. Blank ADX -> None."""
    out = pd.Series(np.full(len(adx), None, dtype=object), index=adx.index)
    lower = -np.inf
    for upper, name in BANDS:
        out[(adx >= lower) & (adx < upper)] = name
        lower = upper
    return out


def _labels(df: pd.DataFrame) -> pd.Series:
    if "ts" in df.columns:
        return df["ts"]
    if "trade_date" in df.columns:
        return df["trade_date"]
    return pd.Series(df.index, index=df.index)


def adx_states(df: pd.DataFrame) -> pd.DataFrame:
    """
    From compute_adx output, adds per candle:
      adx_band              no_trend / forming / trending / strong / very_strong
      adx_slope             +1 rising, -1 falling, 0 flat (vs previous candle), NaN blank
      adx_slope_held        candles the slope has kept its direction (first = 1)
      di_side               +1 +DI above -DI (bulls), -1 below (bears), 0 equal, NaN blank
      di_held / di_since / di_from_start   as in MACD (cross candle = 1)
      di_cross_above        +DI crossed above -DI (TradingView crossover)
      di_cross_below        +DI crossed below -DI
      adx_cross_above_25 / adx_cross_below_25
    Returns a copy; raises ValueError if compute_adx has not been run.
    """
    missing = [c for c in ("plus_di", "minus_di", "adx") if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) missing for adx_states: {missing} (run compute_adx first)")
    if "ts" in df.columns and not df["ts"].is_monotonic_increasing:
        raise ValueError("bars are not in ascending 'ts' order; sort before adx_states")

    out = df.copy()
    adx, plus, minus = out["adx"], out["plus_di"], out["minus_di"]
    labels = _labels(out)

    out["adx_band"] = strength_band(adx)
    slope = np.sign(adx - adx.shift(1))
    held, _, _ = _runs(slope, labels)
    out["adx_slope"] = slope
    out["adx_slope_held"] = held

    side = np.sign(plus - minus)
    held, since, from_start = _runs(side, labels)
    out["di_side"] = side
    out["di_held"] = held
    out["di_since"] = since
    out["di_from_start"] = from_start
    out["di_cross_above"] = cross_above(plus, minus)
    out["di_cross_below"] = cross_below(plus, minus)

    level = pd.Series(LEVEL, index=out.index)
    out["adx_cross_above_25"] = cross_above(adx, level)
    out["adx_cross_below_25"] = cross_below(adx, level)
    return out


def adx_label(df: pd.DataFrame) -> pd.Series:
    """
    One label per candle from adx_band and di_side, e.g. "STRONG TREND DOWN",
    "TRENDING UP", "TREND FORMING UP", "NO TREND" (no direction shown when there is no
    trend), "VERY STRONG TREND DOWN"; DI equal -> "... (no direction)"; blank -> n/a.
    """
    for c in ("adx_band", "di_side"):
        if c not in df.columns:
            raise ValueError(f"column {c!r} missing for adx_label (run adx_states first)")
    out = []
    for band, side in zip(df["adx_band"], df["di_side"]):
        if not isinstance(band, str) or pd.isna(side):
            out.append(LABEL_NA)
        elif band == "no_trend":
            out.append(BAND_TEXT[band])
        else:
            way = {1: "UP", -1: "DOWN"}.get(int(side), "(no direction)")
            out.append(f"{BAND_TEXT[band]} {way}")
    return pd.Series(out, index=df.index, dtype=object)


def adx_all(df: pd.DataFrame) -> pd.DataFrame:
    """compute_adx -> adx_states -> adx_label, in one call."""
    out = adx_states(compute_adx(df))
    out["adx_label"] = adx_label(out)
    return out

# --- Manual check: ADX on the latest bars, to compare with TradingView ---------

_DEFAULT_DOMAIN = {"1d": "indices", "1w": "indices", "1mo": "indices",
                   "5m": "universe_intraday", "15m": "universe_intraday",
                   "60m": "universe_intraday"}

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx
    #   ... adx --dates 2026-10-07 2026-10-08 2026-10-09
    #   ... adx --timeframe 60m --dates 2026-10-09 [--ohlc]
    #   ... adx --state [--timeframe 15m]          (where we stand on the latest candle)
    #   ... adx --crosses 15 [--timeframe 1d]      (latest DI crosses and ADX-25 crosses)
    #   ... adx --timeframe all --state            (all six timeframes + summary table)
    # Output goes to the screen AND to logs/adx_test_logs/adx_check_<timeframe>.log
    # (overwritten each run).
    import argparse
    import logging
    from pathlib import Path

    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    parser = argparse.ArgumentParser(description="Print ADX / DMI (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--timeframe", default="1d", choices=list(_DEFAULT_DOMAIN) + ["all"],
                        help="'all' = 1mo, 1w, 1d, 60m, 15m, 5m in one run")
    parser.add_argument("--domain", help="default: indices (1d/1w/1mo), "
                                         "universe_intraday (5m/15m/60m)")
    parser.add_argument("--bars", type=int, default=3, help="how many latest bars to print")
    parser.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD",
                        help="print all bars on these trade dates instead of the latest bars")
    parser.add_argument("--ohlc", action="store_true", help="also print open/high/low")
    parser.add_argument("--state", action="store_true",
                        help="print band / slope / direction / label for the latest candle")
    parser.add_argument("--crosses", type=int, metavar="N",
                        help="print the latest N events (DI crosses, ADX crossing 25)")
    args = parser.parse_args()
    timeframes = (["1mo", "1w", "1d", "60m", "15m", "5m"] if args.timeframe == "all"
                  else [args.timeframe])

    load_dotenv()
    log_path = Path("logs") / "adx_test_logs" / f"adx_check_{args.timeframe}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    log = logging.getLogger("adx_check")
    log.info("command: adx --timeframe %s --domain %s --key %s %s", args.timeframe,
             args.domain or "default", args.key,
             "--state" if args.state else
             f"--crosses {args.crosses}" if args.crosses else
             (f"--dates {' '.join(args.dates)}" if args.dates else f"--bars {args.bars}")
             + (" --ohlc" if args.ohlc else ""))

    summary = []      # (timeframe, as of, label, ADX + slope, DI) for --state

    def check_one(tf: str) -> None:
        domain = args.domain or _DEFAULT_DOMAIN[tf]
        intraday = tf in ("5m", "15m", "60m")
        unit = {"1d": "day", "1w": "week", "1mo": "month"}.get(tf, "candle")
        when_of = ((lambda v: pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")) if intraday
                   else (lambda v: pd.Timestamp(v).strftime("%Y-%m-%d")))
        f = lambda v: "n/a" if pd.isna(v) else f"{v:.4f}"

        res = read_for_indicators(args.key, domain, tf)
        log.info("=" * 110)
        log.info("ADX / DMI CHECK — %s (%s, DMI 14 14, TradingView method)", args.key, tf)
        log.info("=" * 110)
        if not res.ok:
            log.warning("NOT OK -- %s", res.error)
            summary.append((tf, "-", "NOT OK", res.error, ""))
            return

        if args.state:
            a = adx_all(res.df)
            r = a.iloc[-1]
            partial = f" ({unit} to date)" if tf in ("1w", "1mo") else ""
            slope = {1: "rising", -1: "falling", 0: "flat"}.get(
                None if pd.isna(r["adx_slope"]) else int(r["adx_slope"]), "n/a")
            log.info("as of %s%s   close %.2f", when_of(r["ts"]), partial, r["close"])
            log.info("+DI %s · -DI %s · DX %s · ADX %s · ADXR %s", f(r["plus_di"]),
                     f(r["minus_di"]), f(r["dx"]), f(r["adx"]), f(r["adxr"]))
            log.info("label           : %s", r["adx_label"])
            if pd.notna(r["adx_slope_held"]):
                log.info("ADX             : %s (%s), %s for %d %s(s)", f(r["adx"]), r["adx_band"],
                         slope, int(r["adx_slope_held"]), unit)
            if pd.notna(r["di_side"]):
                who = {1: "+DI above -DI (bulls)", -1: "-DI above +DI (bears)", 0: "+DI = -DI"}
                start = " (start of data)" if r["di_from_start"] else ""
                log.info("direction       : %s, held %d %s(s) since %s%s",
                         who[int(r["di_side"])], int(r["di_held"]), unit,
                         when_of(r["di_since"]), start)
            for col, text in (("di_cross_above", "last +DI cross above -DI"),
                              ("di_cross_below", "last +DI cross below -DI"),
                              ("adx_cross_above_25", "last ADX cross above 25"),
                              ("adx_cross_below_25", "last ADX cross below 25")):
                hits = a.loc[a[col].astype(bool), "ts"]
                log.info("%-26s: %s", text, when_of(hits.iloc[-1]) if len(hits) else "none in history")
            summary.append((tf, when_of(r["ts"]) + partial, r["adx_label"],
                            f"ADX {r['adx']:.2f} {slope} {int(r['adx_slope_held'])} {unit}(s)"
                            if pd.notna(r["adx_slope_held"]) else "n/a",
                            f"+DI {r['plus_di']:.2f} / -DI {r['minus_di']:.2f}"
                            if pd.notna(r["plus_di"]) else ""))
        elif args.crosses:
            a = adx_all(res.df)
            band_word = {"no_trend": "no trend, weak signal", "forming": "trend forming",
                         "trending": "trending, meaningful", "strong": "strong trend, meaningful",
                         "very_strong": "very strong trend (often late)"}
            events = []
            for _, r in a.loc[a["di_cross_above"] | a["di_cross_below"]
                              | a["adx_cross_above_25"] | a["adx_cross_below_25"]].iterrows():
                w = when_of(r["ts"])
                if r["di_cross_above"]:
                    events.append(f"{w}  +DI crossed ABOVE -DI (bulls take over)  ADX {r['adx']:.2f}"
                                  f" — {band_word.get(r['adx_band'], 'n/a')}")
                if r["di_cross_below"]:
                    events.append(f"{w}  +DI crossed BELOW -DI (bears take over)  ADX {r['adx']:.2f}"
                                  f" — {band_word.get(r['adx_band'], 'n/a')}")
                if r["adx_cross_above_25"]:
                    events.append(f"{w}  ADX crossed ABOVE 25 (trend confirmed, "
                                  f"{'up' if r['di_side'] > 0 else 'down'})")
                if r["adx_cross_below_25"]:
                    events.append(f"{w}  ADX crossed BELOW 25 (trend fading)")
            log.info("latest %d events (oldest first):", args.crosses)
            for text in events[-args.crosses:]:
                log.info("  %s", text)
            log.info("total events in history: %s  (data as of %s)", f"{len(events):,}", res.last_ts)
        else:
            a = compute_adx(res.df)
            if args.dates:
                wanted = set(args.dates)
                rows = a[a["trade_date"].astype(str).isin(wanted)]
                for d in sorted(wanted - set(rows["trade_date"].astype(str))):
                    log.info("%s  no bar on this date (not a trading day in our data)", d)
            else:
                rows = a.tail(args.bars)
            w = 26 if intraday else 12
            ohlc_head = f"{'open':>11}{'high':>11}{'low':>11}" if args.ohlc else ""
            log.info(f"{'bar':<{w}}{ohlc_head}{'close':>11}{'+DI':>10}{'-DI':>10}{'DX':>10}"
                     f"{'ADX':>10}{'ADXR':>10}")
            for _, r in rows.iterrows():
                when = str(r["ts"]) if intraday else str(r["trade_date"])
                ohlc = (f"{r['open']:>11.2f}{r['high']:>11.2f}{r['low']:>11.2f}"
                        if args.ohlc else "")
                log.info(f"{when:<{w}}{ohlc}{r['close']:>11.2f}{f(r['plus_di']):>10}"
                         f"{f(r['minus_di']):>10}{f(r['dx']):>10}{f(r['adx']):>10}"
                         f"{f(r['adxr']):>10}")
            log.info("bars used: %s  (data as of %s)", f"{len(a):,}", res.last_ts)
            log.info("TradingView DMI legend order: +DI, -DI, DX, ADX, ADXR (same as the columns).")

    for tf in timeframes:
        check_one(tf)

    if args.state and len(timeframes) > 1:
        log.info("=" * 110)
        log.info("SUMMARY — ADX on each timeframe (latest stored candle)")
        for row in summary:
            log.info("  %-4s %-26s %-26s %-30s %s", *row)
    log.info("=" * 110)
    log.info("log written to %s", log_path)
