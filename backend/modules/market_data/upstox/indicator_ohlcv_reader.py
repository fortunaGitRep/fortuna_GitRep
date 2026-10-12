"""
modules/market_data/upstox/indicator_ohlcv_reader.py

Read-side accessor for the INDICATOR layer. Every indicator module (EMA first,
later RSI/StochRSI/MACD/...) reads OHLCV through this one function, so the
indicator READER RULES are applied in exactly one place.

Shared foundation layer (sits beside ohlcv_store.py), NOT inside any indicator
folder: Nifty 50 today, watchlist / options stocks later, all read through here.

How it reads (decided 2026-10-11):
  - Does NOT touch R2 itself. It calls the documented store reader
    ohlcv_store.read_candles(instrument_key, domain, timeframe), which already
    owns key derivation (e.g. 'NSE_INDEX|Nifty 50' + 'indices' ->
    upstox/indices/Nifty_50.parquet), the bucket, and the missing-file case.
  - Applies reader rule 1: drop bars where any of open/high/low/close is not
    positive (a few old histories contain zero-price bars).
  - Applies reader rule 2 (intraday only, added 2026-10-11 for MACD): drop bars
    that START at/after 15:30 IST on a day that also has regular-session bars.
    Nifty 50's stored history has such after-close bars on 92 days
    (2022-03-24 .. 2025-05-21); TradingView shows none. A day whose bars are
    ALL after 15:30 (a Muhurat evening session) is kept whole -- reader rule 3
    says special sessions are short days, not gaps.
  - Returns bars sorted by ts, columns: ts, trade_date, open, high, low, close, volume.

Safe to run any number of times, at any time (pre-market, weekend, holiday):
  - Read-only: never writes to R2, Supabase or the ledger.
  - Never raises to the caller. Every outcome comes back as an
    IndicatorReadResult with ok=True/False and a plain-English `error`, so a
    pre-market run reports "no data for X" instead of crashing. Covered: missing
    R2 config, R2/network failure, bad instrument key, file not in R2, no bars
    for the timeframe, unexpected file layout, every bar invalid.
  - The latest bar is whatever the last refresh stored (Upstox never returns the
    current day), so callers should show `last_trade_date` as "as of".

Timeframes: 1d / 1w / 1mo (domain 'indices' or 'universe') and 5m / 15m / 60m
(domain 'universe_intraday' -- Nifty 50's intraday file and the F&O stocks').
Reader rule 3 (special sessions = short days) needs no code: indicators count
candles, so a short day simply contributes fewer candles. Reader rule 4
(official daily candle for daily signals) holds because daily indicators read
the 1d file, never the last intraday close.

Logging (one line per outcome, no secrets):
  - INFO    on success: bars returned, bars dropped by rule 1, last trade date.
  - WARNING on an expected miss (no file, no bars, missing column, all bars bad,
            unsupported timeframe): the plain-English reason.
  - ERROR   with full traceback on an unexpected read failure (config, network,
            R2, corrupt file) -- logged once, then returned as ok=False.

Standards applied: single responsibility (read + clean, no indicator math),
reuse of the documented store reader (DRY), input validation (timeframe;
bad key/domain caught via the store), graceful error handling at the boundary,
structured logging (no secrets), read-only + idempotent, no I/O beyond one R2
read per call, unit tests without R2 (test_indicator_ohlcv_reader.py).

Deliberate trade-off: read_candles() is wrapped in a catch-all at this one
boundary so a pre-market run never crashes. Cost: an unexpected bug surfaces as
ok=False + an ERROR log with traceback instead of a crash.

Deferred (with reasons):
  - Timeouts / retries on the R2 read: inherited boto3 defaults from
    db/r2_client.py, not set here. Revisit if R2 reads ever hang or fail
    intermittently.
  - 2h / 4h timeframes: not stored; resampling from 60m is an open item
    (MACD.md section 12).
  - Per-run memo (read each file once per scan): not needed for a single Nifty
    read; add when the stock scanner reads several timeframes per stock.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from modules.market_data.upstox.ohlcv_store import read_candles

logger = logging.getLogger(__name__)

_DAILY_PLUS = ("1d", "1w", "1mo")
_INTRADAY = ("5m", "15m", "60m")
_SUPPORTED_TIMEFRAMES = _DAILY_PLUS + _INTRADAY
_INTRADAY_DOMAIN = "universe_intraday"
_IST = "Asia/Kolkata"
_SESSION_CLOSE_MINUTE = 15 * 60 + 30     # 15:30 IST
_PRICE_COLS = ["open", "high", "low", "close"]
_OUT_COLS = ["ts", "trade_date", "open", "high", "low", "close", "volume"]


@dataclass
class IndicatorReadResult:
    """Outcome of one read. `ok` is the single flag; `error` explains a False."""
    ok: bool
    instrument_key: str
    timeframe: str
    df: Optional[pd.DataFrame] = None
    rows_read: int = 0          # bars in the file for this timeframe
    rows_dropped: int = 0       # removed by reader rule 1 (non-positive price)
    rows_dropped_after_close: int = 0   # removed by reader rule 2 (intraday only)
    days_after_close: int = 0           # trading days that had rule-2 bars
    last_trade_date: Optional[str] = None
    last_ts: Optional[str] = None       # start time of the last bar, IST
    error: Optional[str] = None


def _fail(instrument_key: str, timeframe: str, error: str,
          rows_read: int = 0, log: bool = True) -> IndicatorReadResult:
    if log:
        logger.warning("Indicator read not ok for %s (%s): %s",
                       instrument_key, timeframe, error)
    return IndicatorReadResult(ok=False, instrument_key=instrument_key,
                               timeframe=timeframe, rows_read=rows_read, error=error)


def _after_close_mask(df: pd.DataFrame) -> pd.Series:
    """
    Reader rule 2. True for intraday bars that start at/after 15:30 IST on a
    day that also has bars before 15:30. Evening-only days (Muhurat) -> False.
    """
    ts = df["ts"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        ts = pd.to_datetime(ts, format="ISO8601")   # stored ts is already datetime
    ts = ts.dt.tz_localize(_IST) if ts.dt.tz is None else ts.dt.tz_convert(_IST)
    minute = ts.dt.hour * 60 + ts.dt.minute
    after = minute >= _SESSION_CLOSE_MINUTE
    day = ts.dt.date
    day_has_regular = (~after).groupby(day).transform("any")
    return after & day_has_regular


def read_for_indicators(
    instrument_key: str,
    domain: str,
    timeframe: str = "1d",
) -> IndicatorReadResult:
    """
    Read one instrument's bars for one timeframe, apply reader rule 1, sort.

    Args:
        instrument_key: e.g. 'NSE_INDEX|Nifty 50' or 'NSE_EQ|INE002A01018'.
        domain: 'indices' or 'universe' for 1d/1w/1mo;
                'universe_intraday' for 5m/15m/60m (same values as ohlcv_store).
        timeframe: '1d' (default), '1w', '1mo', '5m', '15m' or '60m'.

    Returns:
        IndicatorReadResult. Never raises.
    """
    if timeframe not in _SUPPORTED_TIMEFRAMES:
        return _fail(instrument_key, timeframe,
                     f"timeframe '{timeframe}' not supported "
                     f"(supported: {', '.join(_SUPPORTED_TIMEFRAMES)}; "
                     f"2h/4h not stored yet)")
    intraday = timeframe in _INTRADAY

    try:
        raw = read_candles(instrument_key, domain, timeframe)
    except Exception as exc:  # boundary: config, network, R2, bad key, bad file
        error = f"could not read OHLCV ({type(exc).__name__}: {exc})"
        # Logged once, with traceback; _fail must not log it a second time.
        logger.exception("Indicator read failed for %s (%s, domain=%s): %s",
                         instrument_key, timeframe, domain, error)
        return _fail(instrument_key, timeframe, error, log=False)

    if raw is None:
        hint = ""
        if intraday and domain != _INTRADAY_DOMAIN:
            hint = f"; intraday bars live in domain '{_INTRADAY_DOMAIN}'"
        elif not intraday and domain == _INTRADAY_DOMAIN:
            hint = "; daily/weekly/monthly bars live in 'indices' or 'universe'"
        return _fail(instrument_key, timeframe,
                     f"no OHLCV file in R2 for this instrument (domain='{domain}'){hint}")
    if raw.empty:
        return _fail(instrument_key, timeframe,
                     f"OHLCV file has no '{timeframe}' bars")

    missing = [c for c in _OUT_COLS if c not in raw.columns]
    if missing:
        return _fail(instrument_key, timeframe,
                     f"OHLCV file is missing column(s): {', '.join(missing)}",
                     rows_read=len(raw))

    # Reader rule 1: keep only bars whose four prices are all > 0.
    valid = (raw[_PRICE_COLS] > 0).all(axis=1)
    rows_dropped = int((~valid).sum())
    if rows_dropped:
        logger.info("Reader rule 1: dropped %d bar(s) with non-positive prices "
                    "for %s (%s).", rows_dropped, instrument_key, timeframe)

    df = raw.loc[valid, _OUT_COLS]

    # Reader rule 2 (intraday only): drop after-close bars on regular days.
    after_close, days_after_close = 0, 0
    if intraday and not df.empty:
        try:
            mask = _after_close_mask(df)
        except Exception as exc:  # unexpected ts layout -> not ok, never raise
            error = f"could not read bar times ({type(exc).__name__}: {exc})"
            logger.exception("Indicator read failed for %s (%s): %s",
                             instrument_key, timeframe, error)
            return _fail(instrument_key, timeframe, error,
                         rows_read=len(raw), log=False)
        after_close = int(mask.sum())
        if after_close:
            days_after_close = int(df.loc[mask, "trade_date"].nunique())
            logger.info("Reader rule 2: dropped %d bar(s) starting at/after 15:30 "
                        "on %d day(s) for %s (%s).", after_close,
                        days_after_close, instrument_key, timeframe)
            df = df.loc[~mask]

    df = df.sort_values("ts").reset_index(drop=True)
    if df.empty:
        return _fail(instrument_key, timeframe,
                     "every bar had a non-positive price; nothing usable",
                     rows_read=len(raw))

    last_trade_date = str(df["trade_date"].iloc[-1])
    last_ts = str(df["ts"].iloc[-1])
    logger.info("Indicator read ok for %s (%s): %d bars, %d dropped (rule 1), "
                "%d dropped (rule 2), last %s.", instrument_key, timeframe,
                len(df), rows_dropped, after_close, last_ts)
    return IndicatorReadResult(
        ok=True,
        instrument_key=instrument_key,
        timeframe=timeframe,
        df=df,
        rows_read=len(raw),
        rows_dropped=rows_dropped,
        rows_dropped_after_close=after_close,
        days_after_close=days_after_close,
        last_trade_date=last_trade_date,
        last_ts=last_ts,
    )


# --- Manual check: read one instrument and print what came back -------------

if __name__ == "__main__":
    #   python -m modules.market_data.upstox.indicator_ohlcv_reader
    #   python -m modules.market_data.upstox.indicator_ohlcv_reader --key "NSE_EQ|INE002A01018" --domain universe
    #   python -m modules.market_data.upstox.indicator_ohlcv_reader --domain universe_intraday --timeframe 5m
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Read OHLCV for indicators (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--domain", default="indices")
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()

    res = read_for_indicators(args.key, args.domain, args.timeframe)

    print("\n" + "=" * 60)
    print(f"INDICATOR READER — {args.key} ({args.domain}, {args.timeframe})")
    print("=" * 60)
    if not res.ok:
        print(f"NOT OK -- {res.error}")
    else:
        d = res.df
        print(f"bars read      : {res.rows_read:,}")
        print(f"bars dropped   : {res.rows_dropped:,}  (reader rule 1)")
        if args.timeframe in _INTRADAY:
            print(f"bars dropped   : {res.rows_dropped_after_close:,}  (reader rule 2, "
                  f"on {res.days_after_close} day(s))")
        print(f"bars returned  : {len(d):,}")
        print(f"first bar      : {d['ts'].iloc[0]}")
        print(f"last bar       : {res.last_ts}  (data as of this candle)")
        print("last 3 bars    :")
        for _, r in d.tail(3).iterrows():
            print(f"   {r['ts']}  O {r['open']:.2f}  H {r['high']:.2f}  "
                  f"L {r['low']:.2f}  C {r['close']:.2f}")
    print("=" * 60 + "\n")
