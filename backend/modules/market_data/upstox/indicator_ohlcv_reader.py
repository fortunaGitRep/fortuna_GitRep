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

Scope now: D/W/M timeframes (1d/1w/1mo). Intraday is refused with a clear
message until reader rule 2 (drop Nifty 50 intraday bars at/after 15:30) is
added here -- rules 2-4 belong to intraday work.

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
  - Reader rules 2-4 (intraday 15:30 bars, special sessions, official daily
    candle vs last intraday close): not needed until intraday indicators are
    built; intraday requests are refused with a clear message until then.
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

_SUPPORTED_TIMEFRAMES = ("1d", "1w", "1mo")
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
    rows_dropped: int = 0       # removed by reader rule 1
    last_trade_date: Optional[str] = None
    error: Optional[str] = None


def _fail(instrument_key: str, timeframe: str, error: str,
          rows_read: int = 0, log: bool = True) -> IndicatorReadResult:
    if log:
        logger.warning("Indicator read not ok for %s (%s): %s",
                       instrument_key, timeframe, error)
    return IndicatorReadResult(ok=False, instrument_key=instrument_key,
                               timeframe=timeframe, rows_read=rows_read, error=error)


def read_for_indicators(
    instrument_key: str,
    domain: str,
    timeframe: str = "1d",
) -> IndicatorReadResult:
    """
    Read one instrument's bars for one timeframe, apply reader rule 1, sort.

    Args:
        instrument_key: e.g. 'NSE_INDEX|Nifty 50' or 'NSE_EQ|INE002A01018'.
        domain: 'indices' or 'universe' (same values as ohlcv_store).
        timeframe: '1d' (default), '1w' or '1mo'.

    Returns:
        IndicatorReadResult. Never raises.
    """
    if timeframe not in _SUPPORTED_TIMEFRAMES:
        return _fail(instrument_key, timeframe,
                     f"timeframe '{timeframe}' not supported yet "
                     f"(supported: {', '.join(_SUPPORTED_TIMEFRAMES)}; "
                     f"intraday waits for reader rule 2)")

    try:
        raw = read_candles(instrument_key, domain, timeframe)
    except Exception as exc:  # boundary: config, network, R2, bad key, bad file
        error = f"could not read OHLCV ({type(exc).__name__}: {exc})"
        # Logged once, with traceback; _fail must not log it a second time.
        logger.exception("Indicator read failed for %s (%s, domain=%s): %s",
                         instrument_key, timeframe, domain, error)
        return _fail(instrument_key, timeframe, error, log=False)

    if raw is None:
        return _fail(instrument_key, timeframe,
                     f"no OHLCV file in R2 for this instrument (domain='{domain}')")
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

    df = (raw.loc[valid, _OUT_COLS]
             .sort_values("ts")
             .reset_index(drop=True))
    if df.empty:
        return _fail(instrument_key, timeframe,
                     "every bar had a non-positive price; nothing usable",
                     rows_read=len(raw))

    last_trade_date = str(df["trade_date"].iloc[-1])
    logger.info("Indicator read ok for %s (%s): %d bars, %d dropped, last %s.",
                instrument_key, timeframe, len(df), rows_dropped, last_trade_date)
    return IndicatorReadResult(
        ok=True,
        instrument_key=instrument_key,
        timeframe=timeframe,
        df=df,
        rows_read=len(raw),
        rows_dropped=rows_dropped,
        last_trade_date=last_trade_date,
    )


# --- Manual check: read one instrument and print what came back -------------

if __name__ == "__main__":
    #   python -m modules.market_data.upstox.indicator_ohlcv_reader
    #   python -m modules.market_data.upstox.indicator_ohlcv_reader --key "NSE_EQ|INE002A01018" --domain universe
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
        print(f"bars returned  : {len(d):,}")
        print(f"first date     : {d['trade_date'].iloc[0]}")
        print(f"last date      : {res.last_trade_date}  (data as of this close)")
        print("last 3 bars    :")
        for _, r in d.tail(3).iterrows():
            print(f"   {r['trade_date']}  O {r['open']:.2f}  H {r['high']:.2f}  "
                  f"L {r['low']:.2f}  C {r['close']:.2f}")
    print("=" * 60 + "\n")
