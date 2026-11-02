"""
Futures 5m parity check (read-only, nothing written to R2).

Old contracts can't be checked on a 5m chart: Dhan and Upstox chart only the three live
futures. So the method is checked on a live contract instead: fetch its 1m and Upstox's own 5m
from the Upstox V3 historical API (same engine as the OHLCV pipeline), build 5m from the 1m with
predictor_days.to_5m() -- the code the predictor uses on the archive -- and compare every candle.
A few exact candles are listed for Ash to compare on the Dhan / Upstox 5m chart.

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.futures_parity_check
  ... --key "NSE_FO|61471" --from 2026-08-26 --to 2026-10-30
Output: logs/predictor_days_logs/futures_parity_check.log (+ screen), futures_parity_check.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.predictor_days import to_5m

DEFAULT_KEY = "NSE_FO|61471"            # NIFTY 23NOV26 FUT (Ash's Upstox chart URL)
DEFAULT_FROM, DEFAULT_TO = date(2026, 8, 26), date(2026, 10, 30)
SHOW = [("2026-08-26", "09:15"), ("2026-10-29", "09:30"), ("2026-10-30", "11:40")]
FIELDS = ["open", "high", "low", "close", "volume"]
LOG_DIR = Path("logs") / "predictor_days_logs"
logger = logging.getLogger(__name__)


def candles_frame(candles) -> pd.DataFrame:
    """Engine Candle objects -> ts, open, high, low, close, volume."""
    return pd.DataFrame([{"ts": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close,
                          "volume": c.volume} for c in candles])


def compare(ours: pd.DataFrame, upstox: pd.DataFrame) -> pd.DataFrame:
    """Join our 5m (built from 1m) with Upstox's 5m on the candle start; one row per candle."""
    a = ours.assign(ts=pd.to_datetime(ours["ts"]))[["ts"] + FIELDS]
    b = upstox.assign(ts=pd.to_datetime(upstox["ts"]))[["ts"] + FIELDS]
    m = a.merge(b, on="ts", how="outer", suffixes=("_ours", "_upstox"), indicator=True).sort_values("ts")
    for f in FIELDS:
        m[f"{f}_diff"] = m[f"{f}_ours"] - m[f"{f}_upstox"]
    return m


def report(m: pd.DataFrame) -> list[str]:
    both = m[m["_merge"] == "both"]
    lines = [f"candles: {len(both)} in both, {int((m['_merge'] == 'left_only').sum())} only ours, "
             f"{int((m['_merge'] == 'right_only').sum())} only Upstox"]
    for f in FIELDS:
        d = both[f"{f}_diff"].abs()
        exact = int((d < 1e-6).sum())
        line = f"  {f:<7} exact {exact} / {len(both)}"
        if len(both) and exact < len(both):
            worst = both.loc[d.idxmax()]
            line += (f"   largest gap {d.max():,.2f} at {worst['ts']:%a %d %b %Y %H:%M} "
                     f"(ours {worst[f + '_ours']:,.2f}, Upstox {worst[f + '_upstox']:,.2f})")
        lines.append(line)
    return lines


def show_lines(m: pd.DataFrame) -> list[str]:
    lines = ["", "CHECK ON THE CHART (Dhan or Upstox, NIFTY NOV FUT, 5m):"]
    for day, hhmm in SHOW:
        r = m[(m["ts"].dt.strftime("%Y-%m-%d") == day) & (m["ts"].dt.strftime("%H:%M") == hhmm)]
        if r.empty:
            lines.append(f"  {pd.Timestamp(day):%a %d %b %Y} {hhmm}: not in the data")
            continue
        r = r.iloc[0]
        lines.append(f"  {r['ts']:%a %d %b %Y %H:%M}  ours O {r['open_ours']:,.2f} H {r['high_ours']:,.2f} "
                     f"L {r['low_ours']:,.2f} C {r['close_ours']:,.2f} Vol {r['volume_ours']:,.0f}  |  "
                     f"Upstox 5m O {r['open_upstox']:,.2f} H {r['high_upstox']:,.2f} L {r['low_upstox']:,.2f} "
                     f"C {r['close_upstox']:,.2f} Vol {r['volume_upstox']:,.0f}")
    return lines


def run(key: str, start: date, end: date) -> list[str]:
    from modules.market_data.upstox._ohlcv_engine import fetch_full_history

    logger.info("[1/3] fetching %s 1m from Upstox, %s .. %s ...", key, start, end)
    one = fetch_full_history(key, "minutes", "1", from_date=start, to_date=end)
    if not one.ok:
        raise RuntimeError(f"1m fetch failed: {one.error}")
    logger.info("      %d one-minute candles", one.count)
    logger.info("[2/3] fetching %s 5m from Upstox ...", key)
    five = fetch_full_history(key, "minutes", "5", from_date=start, to_date=end)
    if not five.ok:
        raise RuntimeError(f"5m fetch failed: {five.error}")
    logger.info("      %d five-minute candles", five.count)
    logger.info("[3/3] building 5m from 1m (predictor_days.to_5m) and comparing ...")
    m = compare(to_5m(candles_frame(one.candles)), candles_frame(five.candles))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    m.drop(columns="_merge").assign(where=m["_merge"].astype(str)).to_csv(LOG_DIR / "futures_parity_check.csv", index=False)
    return (["=" * 78, f"FUTURES 5m PARITY -- {key}, {start} .. {end}", "=" * 78]
            + report(m) + show_lines(m) + [f"every candle: {LOG_DIR / 'futures_parity_check.csv'}"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check 5m futures built from 1m against Upstox's 5m")
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--from", dest="start", type=lambda v: date.fromisoformat(v), default=DEFAULT_FROM)
    ap.add_argument("--to", dest="end", type=lambda v: date.fromisoformat(v), default=DEFAULT_TO)
    args = ap.parse_args(argv)
    from dotenv import load_dotenv          # Upstox token, as the OHLCV engine's own run does
    load_dotenv()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "futures_parity_check.log", mode="w", encoding="utf-8")])
    try:
        lines = run(args.key, args.start, args.end)
    except Exception:
        logger.exception("Parity check FAILED -- the last '[n/3]' line above shows the step")
        return 1
    for line in lines:
        logger.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
