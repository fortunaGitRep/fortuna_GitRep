"""
Manual check: horizontal S&R lines (every Zig Zag swing) for all six timeframes,
after recency and merging, numbered outward from each timeframe's latest close;
then the TRADING LADDER (all timeframes' lines on the 5m chart). To compare
against Ash's own drawn lines on tv.dhan.co.

Read-only: reads candles through the indicator reader (reader rules applied there),
runs find_zigzag_swings() in memory with the settings table. No writes to R2,
Supabase or the ledger. Output goes to the terminal AND
backend/logs/horizontal_sr_test_logs/horizontal_sr_check.log (overwritten each
run; the first line is the command).

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_check
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_check --timeframe 5m
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_check --show 10
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_check --key "NSE_EQ|INE002A01018" --daily-domain universe
      --show N : lines printed each side of price per timeframe (default: all)
      --daily-domain : 'indices' (default, Nifty) or 'universe' (stocks) for 1mo/1w/1d;
                       5m/15m/60m always read 'universe_intraday'
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import report_date
from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr import (
    RECENT_TRADING_DAYS,
    number_lines,
    timeframe_lines,
    trading_ladder,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
    get_equal_tolerance,
    get_zigzag_settings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import (
    find_zigzag_swings,
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
INTRADAY = ("5m", "15m", "60m")
ALL_TIMEFRAMES = ("1mo", "1w", "1d", "60m", "15m", "5m")
INTRADAY_DOMAIN = "universe_intraday"


def _read(key: str, daily_domain: str, tf: str):
    domain = INTRADAY_DOMAIN if tf in INTRADAY else daily_domain
    return read_for_indicators(key, domain, tf)


def _prev_day(key: str, daily_domain: str):
    """Latest completed daily candle (O/H/L/C + time), or (None, error)."""
    res = _read(key, daily_domain, "1d")
    if not res.ok:
        return None, res.error
    last = res.df.iloc[-1]
    return {"time": last["ts"], "open": float(last["open"]), "high": float(last["high"]),
            "low": float(last["low"]), "close": float(last["close"])}, None


def _ladder_lines(sr: pd.DataFrame, close: float, show, tf_for_dates=None) -> list[str]:
    """Print a numbered ladder. tf_for_dates None = trading ladder (dates per line's own TF)."""
    lines = [f"{'label':>6}  {'price':>11}  {'dist pts':>10}  {'dist %':>7}  {'swing':<5}  "
             f"{'pivot (check on chart)':<24}  {'locked':<10}  {'PD':<8}  "
             f"{'timeframes' if tf_for_dates is None else '':<20}  merged",
             "-" * 120]
    if show is not None:
        sr = pd.concat([sr[sr["side"] == "R"].tail(show), sr[sr["side"] == "AT"],
                        sr[sr["side"] == "S"].head(show)])
    price_marked = False
    for _, r in sr.iterrows():
        if not price_marked and r["side"] in ("AT", "S"):
            lines.append(f"{'':>6}  {'-- price':>11}  {close:>10,.2f}")
            price_marked = True
        dist = r["price"] - close
        tf = tf_for_dates or r["timeframe"]
        merged = (f"+{len(r['merged_from'].split('; '))}: {r['merged_from']}"
                  if isinstance(r["merged_from"], str) and r["merged_from"] else "")
        lines.append(
            f"{r['label']:>6}  {r['price']:>11,.2f}  {dist:>+10,.2f}  {100 * dist / close:>+6.2f}%  "
            f"{r['kind']:<5}  {report_date(r['pivot_time'], tf):<24}  "
            f"{'locked' if r['is_locked'] else 'NOT LOCKED':<10}  {r['pd_tags']:<8}  "
            f"{r['timeframes'] if tf_for_dates is None else '':<20}  {merged}")
    if not price_marked:
        lines.append(f"{'':>6}  {'-- price':>11}  {close:>10,.2f}")
    if show is not None:
        lines.append(f"(showing {show} each side; run without --show for all)")
    return lines


def run_timeframe(key: str, daily_domain: str, tf: str, prev_day, show):
    """Report lines for one timeframe + its merged lines (for the trading ladder) + close."""
    deviation, depth = get_zigzag_settings(tf)
    tol = get_equal_tolerance(tf)
    days = RECENT_TRADING_DAYS.get(tf)
    lines = ["=" * 120,
             f"HORIZONTAL S&R - {key} {tf}  (Zig Zag {deviation}% / {depth}, merge within {tol}%, "
             f"{'last ' + str(days) + ' trading days' if days else 'all history'})",
             "=" * 120]
    res = _read(key, daily_domain, tf)
    if not res.ok:
        return lines + [f"NOT OK -- {res.error}"], None, None

    candles = res.df.rename(columns={"ts": "time"})[["time", "high", "low", "close"]]
    swings = find_zigzag_swings(candles[["time", "high", "low"]], deviation, depth)
    close = float(candles["close"].iloc[-1])
    merged = timeframe_lines(swings, tf, candles["time"], tol, prev_day, close)
    sr = number_lines(merged, close)

    n = {s: int((sr["side"] == s).sum()) for s in ("R", "AT", "S")}
    lines.append(f"as of {report_date(candles['time'].iloc[-1], tf)}: close {close:,.2f}   "
                 f"swings {len(swings):,} -> lines {len(sr):,} (R {n['R']:,} · AT {n['AT']} · S {n['S']:,})")
    lines += _ladder_lines(sr, close, show, tf_for_dates=tf)
    return lines, merged, close


def run_trading_ladder(per_tf: list, close: float, show) -> list[str]:
    tol = get_equal_tolerance("5m")
    sr = trading_ladder(per_tf, close, tol)
    n = {s: int((sr["side"] == s).sum()) for s in ("R", "AT", "S")}
    return (["=" * 120,
             f"TRADING LADDER (5m chart) - lines of all timeframes, merged within {tol}%, "
             f"numbered from the 5m close {close:,.2f}",
             "=" * 120,
             f"lines {len(sr):,} (R {n['R']:,} · AT {n['AT']} · S {n['S']:,})"]
            + _ladder_lines(sr, close, show))


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Horizontal S&R lines from Zig Zag swings (read-only).")
    parser.add_argument("--key", default=NIFTY_KEY)
    parser.add_argument("--daily-domain", default="indices", choices=["indices", "universe"])
    parser.add_argument("--timeframe", default=None, choices=list(ALL_TIMEFRAMES),
                        help="One timeframe only. Default: all six.")
    parser.add_argument("--show", type=int, default=None,
                        help="Lines to print each side of price per timeframe (default: all).")
    args = parser.parse_args()

    command = "python -m " + __spec__.name + " " + " ".join(sys.argv[1:]) if __spec__ else " ".join(sys.argv)
    report = [command.strip(), f"Horizontal S&R check, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]

    prev_day, err = _prev_day(args.key, args.daily_domain)
    if prev_day is None:
        report.append(f"Previous day: NOT OK -- {err} (PD tags left blank)")
    else:
        report.append(f"Previous day ({report_date(prev_day['time'], '1d')}): "
                      f"O {prev_day['open']:,.2f}  H {prev_day['high']:,.2f}  "
                      f"L {prev_day['low']:,.2f}  C {prev_day['close']:,.2f}  "
                      f"-> tags PDO / PDH / PDL / PDC on exact matches")
    report.append("Every Zig Zag swing is a line (swing high = candle high, swing low = candle low). "
                  "60m/15m keep the last 25 trading days, 5m the last 3; 1M/1W/1D all history.")
    report.append("Lines within the timeframe's tolerance merge: all highs -> highest, all lows -> lowest, "
                  "mixed -> earliest; never across price; PD lines never merge. Numbered from each timeframe's latest close: R1 nearest above, S1 nearest below.")
    report.append("")

    timeframes = [args.timeframe] if args.timeframe else list(ALL_TIMEFRAMES)
    per_tf, close_5m = [], None
    for tf in timeframes:
        try:
            text, merged, close = run_timeframe(args.key, args.daily_domain, tf, prev_day, args.show)
            report += text
            if merged is not None:
                per_tf.append(merged)
                if tf == "5m":
                    close_5m = close
        except ValueError as exc:  # bad candles / settings: report, don't crash
            report += [f"{tf}: NOT OK -- {exc}"]
        report.append("")
    if not args.timeframe:
        if close_5m is None:
            report.append("TRADING LADDER: NOT OK -- no 5m close")
        else:
            report += run_trading_ladder(per_tf, close_5m, args.show)
        report.append("")
    report.append("NOT LOCKED = the latest Zig Zag swing; its price can still move until the opposite swing is drawn.")

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "horizontal_sr_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "horizontal_sr_check.log"
    text = "\n".join(report)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
