"""
Manual check: Nifty 50 Zig Zag swings, to compare against Ash's tv.dhan.co chart.

Reads candles through the indicator reader (reader rules applied there), runs
find_zigzag_swings() in memory with the settings table, and prints the swings.
Read-only: no writes to R2, Supabase or the ledger. Output goes to the terminal
AND backend/logs/zigzag_test_logs/zigzag_check.log (overwritten each run).

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_check
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_check --timeframe 5m
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_check --events 0
      (--events N = BOS/CHoCH events printed per timeframe, default 10, 0 = full history)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.level_breaks import (
    find_level_breaks,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.structure_events import (
    current_structure,
    find_structure_events,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.swing_labels import (
    add_swing_labels,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.swing_legs import (
    add_leg_data,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
    get_equal_tolerance,
    get_zigzag_settings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import (
    bars_each_side,
    find_zigzag_swings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.provisional_swings import (
    current_direction,
    provisional_swings,
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
INTRADAY = ("5m", "15m", "60m")
ALL_TIMEFRAMES = ("1mo", "1w", "1d", "60m", "15m", "5m")   # structure section runs all
DEFAULT_SHOW = {"1mo": 30, "1w": 30, "1d": 30, "60m": 30, "15m": 30, "5m": 40}


def _fmt(ts, intraday: bool) -> str:
    """Ash's format: 'Fri 9 Oct 2026' or 'Fri 9 Oct 2026 15:15'."""
    if pd.isna(ts):
        return "-"
    ts = pd.Timestamp(ts)
    text = f"{ts:%a} {ts.day} {ts:%b %Y}"
    return f"{text} {ts:%H:%M}" if intraday else text


def run_check(timeframe: str, show: int) -> list[str]:
    """Return the report lines for one timeframe."""
    intraday = timeframe in INTRADAY
    domain = "universe_intraday" if intraday else "indices"
    deviation, depth = get_zigzag_settings(timeframe)

    lines = ["=" * 78,
             f"ZIG ZAG CHECK - Nifty 50 {timeframe}  (deviation {deviation}%, depth {depth}"
             f" -> {bars_each_side(depth)} bars each side)",
             "=" * 78]

    res = read_for_indicators(NIFTY_KEY, domain, timeframe)
    if not res.ok:
        lines.append(f"NOT OK -- {res.error}")
        return lines

    candles = res.df.rename(columns={"ts": "time"})[["time", "high", "low"]]
    swings = find_zigzag_swings(candles, deviation, depth)
    swings = add_leg_data(swings, candles["time"])
    tol = get_equal_tolerance(timeframe)
    swings = add_swing_labels(swings, tol)

    lines.append(f"bars read   : {len(candles):,}   data as of: {res.last_ts}")
    lines.append(f"swings found: {len(swings):,}   showing the last {min(show, len(swings))}"
                 f"   equal-swing tolerance: {tol:.3f}%")
    lines.append("")
    lines.append(f"{'#':>4}  {'kind':<4}  {'label':<5}  {'price':>10}  {'leg %':>7}  {'retr %':>6}  "
                 f"{'pivot (check on chart)':<22}  {'detected':<22}  {'locked':<22}")
    lines.append("-" * 118)

    tail = swings.tail(show)
    start_no = len(swings) - len(tail) + 1
    for i, (_, s) in enumerate(tail.iterrows(), start=start_no):
        label = s["label"] + ("*" if s["label_can_change"] else "")
        lines.append(
            f"{i:>4}  {s['kind']:<4}  {label:<5}  {s['price']:>10.2f}  "
            f"{_num(s['leg_pct'], '+.2f'):>7}  {_num(s['retrace_pct'], '.0f'):>6}  "
            f"{_fmt(s['pivot_time'], intraday):<22}  "
            f"{_fmt(s['detected_time'], intraday):<22}  "
            f"{_fmt(s['locked_time'], intraday) if s['is_locked'] else 'NOT LOCKED':<22}"
        )
    lines.append("")
    lines.append("* = last swing, NOT LOCKED: its price and label can still change.")

    zone_ids = tail["zone_id"].dropna().unique()
    if len(zone_ids):
        lines.append("")
        lines.append("Equal-high / equal-low zones in this range:")
        for zid in zone_ids:
            z = swings[swings["zone_id"] == zid].iloc[-1]
            name = {2: "double", 3: "triple"}.get(int(z["zone_touches"]), f"{int(z['zone_touches'])}x")
            what = f"{name} {'top' if z['kind'] == 'high' else 'bottom'}"
            first = swings[swings["zone_id"] == zid].iloc[0]
            lines.append(
                f"  {what:<14} {z['zone_low']:.2f}-{z['zone_high']:.2f}, "
                f"neckline {z['neckline']:.2f}, from {_fmt(first['pivot_time'], intraday)} "
                f"to {_fmt(z['pivot_time'], intraday)}")
    return lines


def _num(value, fmt: str) -> str:
    return "-" if pd.isna(value) else format(value, fmt)


def _candles_for(timeframe: str):
    """Read Nifty OHLC for one timeframe: (candles, last_ts) or (None, error)."""
    domain = "universe_intraday" if timeframe in INTRADAY else "indices"
    res = read_for_indicators(NIFTY_KEY, domain, timeframe)
    if not res.ok:
        return None, res.error
    cols = ["time", "open", "high", "low", "close"]
    return res.df.rename(columns={"ts": "time"})[cols], res.last_ts


def _swings_for(timeframe: str):
    """Read Nifty for one timeframe and return (swings, last_ts) or (None, error)."""
    candles, info = _candles_for(timeframe)
    if candles is None:
        return None, info
    deviation, depth = get_zigzag_settings(timeframe)
    return find_zigzag_swings(candles, deviation, depth), info


def _break_lines(br: pd.DataFrame, intraday: bool) -> list[str]:
    """One line per level: what price did there (labels, not trade calls)."""
    lines = [f"  {'level':<4}  {'price':>10}  {'known at':<22}  {'wick beyond':<22}  "
             f"{'close beyond':<26}  {'cleared (white space)':<22}  {'retest':<28}  outcome"]
    for _, r in br.iterrows():
        conf = _fmt(r["confirmed_time"], intraday)
        if r["gap"]:
            conf += " GAP"
        cleared = _fmt(r["cleared_time"], intraday)
        if pd.isna(r["confirmed_time"]):
            retest = "-"
        elif pd.isna(r["cleared_time"]):
            retest = "-" if isinstance(r["outcome"], str) else "not cleared yet"
        elif pd.isna(r["retest_time"]):
            retest = "no retest yet"
        else:
            n = int(r["bars_to_retest"])
            retest = f"{_fmt(r['retest_time'], intraday)} ({n} bar{'' if n == 1 else 's'})"
        outcome = (f"{r['outcome'].upper()} {_fmt(r['outcome_time'], intraday)}"
                   if isinstance(r["outcome"], str) else ("open" if not pd.isna(r["confirmed_time"]) else "-"))
        if r["outcome"] == "failed" and not pd.isna(r["held_time"]):
            outcome = f"HELD {_fmt(r['held_time'], intraday)} -> {outcome}"
        if r["cycle"] > 1:
            outcome += f"  (re-break #{int(r['cycle'])})"
        lines.append(f"  {r['kind']:<4}  {r['price']:>10.2f}  {_fmt(r['known_at'], intraday):<22}  "
                     f"{_fmt(r['attempt_time'], intraday):<22}  {conf:<26}  {cleared:<22}  "
                     f"{retest:<28}  {outcome}")
    return lines


def run_breaks_check(n_levels: int = 12) -> list[str]:
    """Step 4: what price did at the latest swing levels (real and provisional)."""
    lines = ["=" * 78, "LEVEL BREAKS - Nifty 50 (wick = attempt, close = structure break)", "=" * 78]
    for tf in ("1d", "5m"):
        candles, info = _candles_for(tf)
        if candles is None:
            lines.append(f"{tf}: NOT OK -- {info}")
            continue
        dev, depth = get_zigzag_settings(tf)
        levels = find_zigzag_swings(candles, dev, depth).tail(n_levels)
        levels = levels.rename(columns={"detected_time": "known_at"})
        br = find_level_breaks(candles, levels, get_equal_tolerance(tf))
        lines += ["", f"{tf} levels on {tf} candles (last {br['price'].groupby([br['kind'], br['known_at']]).ngroups} swings), data as of {info}"]
        lines += _break_lines(br, tf in INTRADAY)
    for lower, higher in (("5m", "60m"), ("60m", "1d")):
        candles, info = _candles_for(lower)
        if candles is None:
            lines.append(f"{lower}: NOT OK -- {info}")
            continue
        dev, depth = get_zigzag_settings(lower)
        higher_dev, _ = get_zigzag_settings(higher)
        prov = provisional_swings(find_zigzag_swings(candles, dev, depth), higher_dev)
        br = find_level_breaks(candles, prov.tail(n_levels), get_equal_tolerance(higher))
        lines += ["", f"PROVISIONAL {higher} levels on {lower} candles (last {br['price'].groupby([br['kind'], br['known_at']]).ngroups} swings), "
                      f"data as of {info}"]
        lines += _break_lines(br, True)
    lines += ["", "Cleared = first candle fully outside the band after the break (white space); "
                  "a retest only counts after it.",
              "Not cleared yet = price hugging the level, NOT the strong case.",
              "No retest yet (after cleared) = the stronger case (Bulkowski). FAILED = busted break, "
                  "watch the opposite side. All are labels, not trade calls."]
    return lines


def _structure_lines(ev: pd.DataFrame, st: dict, intraday: bool, show: int) -> list[str]:
    """Latest BOS/CHoCH events + trend now (labels, not trade calls)."""
    up_text = ("BOS, uptrend continues" if st["trend"] == "uptrend"
               else f"CHoCH, {st['trend']} to uptrend")
    down_text = ("BOS, downtrend continues" if st["trend"] == "downtrend"
                 else f"CHoCH, {st['trend']} to downtrend")
    lines = [f"  TREND NOW: {st['trend'].upper()}",
             f"    close above {_num(st['up_target'], '.2f')} = {up_text}",
             f"    close below {_num(st['down_target'], '.2f')} = {down_text}"]
    if st["up_target"] is None or st["down_target"] is None:
        lines.append("    (- = latest swing already broken, waiting for a new swing)")
    shown = ev if show <= 0 else ev.tail(show)
    lines += [f"  events in history: {len(ev):,}   "
              f"{'showing all' if show <= 0 else f'showing the last {len(shown)}'}",
              f"  {'time (close of breaking candle)':<31}  {'event':<38}  {'broken level':>12}  "
              f"{'level pivot':<22}  {'retest (1st break)':<22}  latest outcome"]
    for _, r in shown.iterrows():
        if r["event"] == "BOS":
            name = f"BOS, {r['trend_after']} continues"
        else:
            name = f"CHoCH, {r['trend_before']} to {r['trend_after']}"
        level = f"{r['level_price']:.2f}"
        when = _fmt(r["time"], intraday) + (" GAP" if r["gap"] else "")
        if pd.isna(r["cleared_time"]):
            retest = "not cleared" if not isinstance(r["outcome"], str) else "-"
        else:
            retest = _fmt(r["retest_time"], intraday) if not pd.isna(r["retest_time"]) else "no retest yet"
        out = (f"{r['outcome'].upper()} {_fmt(r['outcome_time'], intraday)}"
               if isinstance(r["outcome"], str) else "open")
        if r["rebreaks"]:
            out += f"  (re-broken {int(r['rebreaks'])}x)"
        lines.append(f"  {when:<31}  {name:<38}  {level:>12}  "
                     f"{_fmt(r['level_pivot_time'], intraday):<22}  {retest:<22}  {out}")
    return lines


def run_structure_check(show: int = 10) -> list[str]:
    """Step 5: BOS / CHoCH and trend state, real and provisional."""
    lines = ["=" * 78, "STRUCTURE - Nifty 50 BOS / CHoCH (close beyond the latest swing known that day)",
             "=" * 78,
             "BOS  : Break of Structure  - indicates a trend continuation",
             "CHoCH: Change of Character - indicates a potential trend reversal"]
    for tf in ALL_TIMEFRAMES:
        candles, info = _candles_for(tf)
        if candles is None:
            lines.append(f"{tf}: NOT OK -- {info}")
            continue
        dev, depth = get_zigzag_settings(tf)
        sw = find_zigzag_swings(candles, dev, depth)
        lv = sw.rename(columns={"detected_time": "active_from"})
        lv = lv[["kind", "price", "pivot_time", "active_from"]]
        ev = find_structure_events(candles, lv, get_equal_tolerance(tf))
        st = current_structure(candles, lv)
        lines += ["", f"{tf} structure on {tf} candles, data as of {info}"]
        lines += _structure_lines(ev, st, tf in INTRADAY, show)
    for lower, higher in (("5m", "60m"), ("60m", "1d")):
        candles, info = _candles_for(lower)
        if candles is None:
            lines.append(f"{lower}: NOT OK -- {info}")
            continue
        dev, depth = get_zigzag_settings(lower)
        higher_dev, _ = get_zigzag_settings(higher)
        prov = provisional_swings(find_zigzag_swings(candles, dev, depth), higher_dev)
        lv = prov.rename(columns={"known_at": "active_from"})
        lv = lv[["kind", "price", "pivot_time", "active_from"]]
        ev = find_structure_events(candles, lv, get_equal_tolerance(higher))
        st = current_structure(candles, lv)
        lines += ["", f"PROVISIONAL {higher} structure on {lower} candles, data as of {info}"]
        lines += _structure_lines(ev, st, True, show)
    lines += ["", "Each line uses only what was known that day. Event and trend flip are final at "
                  "the close of the breaking candle. "
                  "Outcome / re-breaks are labels and keep updating; they never undo an event."]
    return lines


def run_mtf_check(show: int = 8) -> list[str]:
    """Ash's temporary-lock view: 5m locks -> provisional 60m; 60m locks -> provisional 1D."""
    lines = ["=" * 78, "TEMPORARY-LOCK VIEW - Nifty 50 (lower timeframe locks, higher deviation)",
             "=" * 78]
    for lower, higher in (("5m", "60m"), ("60m", "1d")):
        lower_swings, info = _swings_for(lower)
        if lower_swings is None:
            lines.append(f"{lower} -> {higher}: NOT OK -- {info}")
            continue
        higher_dev, _ = get_zigzag_settings(higher)
        prov = provisional_swings(lower_swings, higher_dev)
        d = current_direction(prov, higher_dev)
        intraday = True  # known_at is always a lower-timeframe (intraday) time here
        lines.append("")
        lines.append(f"Provisional {higher} from {lower} locks  (deviation {higher_dev}%), "
                     f"data as of {info}")
        if d["direction"] == "unknown":
            lines.append("  direction: unknown (no locked swings yet)")
            continue
        lines.append(f"  {higher} DIRECTION NOW: {_leg_text(d)}, "
                     f"known at {_fmt(d['since'], intraday)}")
        lines.append(f"  {'kind':<4}  {'price':>10}  {'pivot':<22}  {'known at':<22}  {'confirmed':<22}")
        for _, p in prov.tail(show).iterrows():
            lines.append(
                f"  {p['kind']:<4}  {p['price']:>10.2f}  {_fmt(p['pivot_time'], True):<22}  "
                f"{_fmt(p['known_at'], True):<22}  "
                f"{_fmt(p['confirmed_at'], True) if p['is_confirmed'] else 'can still extend':<22}"
            )
        real, _ = _swings_for(higher)
        if real is not None and not real.empty:
            rd = current_direction(real.rename(columns={"detected_time": "known_at"}), higher_dev)
            last = real.iloc[-1]
            lines.append(f"  For comparison, real {higher} Zig Zag: {_leg_text(rd)} "
                         f"(last pivot {_fmt(last['pivot_time'], higher in INTRADAY)}, "
                         f"detected {_fmt(last['detected_time'], higher in INTRADAY)})")
    return lines


def _leg_text(d: dict) -> str:
    """e.g. 'UP 22288.45 -> 22581.15, turns DOWN below 22298.89'."""
    up = d["direction"] == "up"
    start = f"{d['from_price']:.2f} -> " if d["from_price"] is not None else "to "
    return (f"{d['direction'].upper()} {start}{d['extreme']:.2f}, "
            f"turns {'DOWN below' if up else 'UP above'} {d['reverses_at']:.2f}")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Nifty 50 Zig Zag swings (read-only).")
    parser.add_argument("--timeframe", default=None,
                        help="1mo, 1w, 1d, 60m, 15m or 5m. Default: 1d and 5m.")
    parser.add_argument("--events", type=int, default=10,
                        help="BOS/CHoCH events to print per timeframe (0 = full history).")
    parser.add_argument("--show", type=int, default=None,
                        help="How many of the latest swings to print.")
    args = parser.parse_args()

    timeframes = [args.timeframe] if args.timeframe else ["1d", "5m"]

    report = [f"Zig Zag check, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for tf in timeframes:
        try:
            report += run_check(tf, args.show or DEFAULT_SHOW.get(tf, 30))
        except ValueError as exc:  # bad timeframe or bad candles: report, don't crash
            report += [f"{tf}: NOT OK -- {exc}"]
        report.append("")
    if not args.timeframe:
        report += run_mtf_check()
        report.append("")
        report += run_breaks_check()
        report.append("")
        report += run_structure_check(args.events)
        report.append("")

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "zigzag_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "zigzag_check.log"
    text = "\n".join(report)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
