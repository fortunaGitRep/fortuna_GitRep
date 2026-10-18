"""
Horizontal S&R snapshot: one JSON-safe package per instrument for the frontend,
plus plain-language texts (same shape as the other indicator snapshots).

Views: one per timeframe (1mo, 1w, 1d, 60m, 15m, 5m) and the TRADING LADDER
(all timeframes' lines on the 5m chart). Every view holds ALL its lines (no limit),
nearest first on each side; the texts show R1-R3 and S1-S3 (Ash's booking
targets: R1 first booking, R2 second, R3 final).

No alerts here: "price touched / broke a line" belongs to the level-break engine.

build_horizontal_sr_snapshot() never raises: a failed timeframe is reported in
`errors` and the other views are still built. Read-only; the manual run writes
backend/logs/horizontal_sr_test_logs/horizontal_sr_snapshot.log.

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_snapshot
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_snapshot --json
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_snapshot --key "NSE_EQ|INE002A01018" --name Reliance --daily-domain universe
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import (
    iso,
    num,
    report_date,
)
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

logger = logging.getLogger(__name__)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
TIMEFRAMES = ("1mo", "1w", "1d", "60m", "15m", "5m")
INTRADAY = ("5m", "15m", "60m")
INTRADAY_DOMAIN = "universe_intraday"
TRADING = "trading"
TEXT_LINES_EACH_SIDE = 3


def merged_list(merged_from) -> list[str]:
    """The absorbed lines as a list ('' -> [])."""
    if not isinstance(merged_from, str) or not merged_from:
        return []
    return merged_from.split("; ")


def _line(r: pd.Series, close: float) -> dict:
    price = float(r["price"])
    return {
        "label": r["label"],
        "price": round(price, 2),
        "distance_pts": round(price - close, 2),
        "distance_pct": round(100 * (price - close) / close, 2),
        "kind": r["kind"],
        "timeframe": r["timeframe"],
        "timeframes": r["timeframes"].split(),
        "pivot_time": iso(r["pivot_time"], r["timeframe"]),
        "pivot_text": report_date(r["pivot_time"], r["timeframe"]),
        "is_locked": bool(r["is_locked"]),
        "pd_tags": r["pd_tags"].split() if r["pd_tags"] else [],
        "merged": merged_list(r.get("merged_from", "")),
    }


def _side_text(lines: list[dict], above: bool) -> str:
    if not lines:
        return f"{'Above' if above else 'Below'}: no line."
    shown = lines[:TEXT_LINES_EACH_SIDE]
    if above:
        shown = list(reversed(shown))           # R3 · R2 · R1, read toward price
    parts = []
    for ln in shown:
        tag = f" {' '.join(ln['pd_tags'])}" if ln["pd_tags"] else ""
        parts.append(f"{ln['label']} {ln['price']:,.2f}{tag} ({ln['distance_pts']:+,.2f})")
    return " · ".join(parts)


def snapshot_from_lines(numbered: pd.DataFrame, close: float, as_of, view: str,
                        name: str) -> dict:
    """One view (a timeframe or the trading ladder) as a JSON-safe dict + texts. Pure."""
    tf_for_title = "5m" if view == TRADING else view
    resistances = [_line(r, close) for _, r in numbered[numbered["side"] == "R"]
                   .sort_values("rank").iterrows()]
    supports = [_line(r, close) for _, r in numbered[numbered["side"] == "S"]
                .sort_values("rank").iterrows()]
    at_price = [_line(r, close) for _, r in numbered[numbered["side"] == "AT"].iterrows()]
    title = f"{name} · {'Trading ladder (5m)' if view == TRADING else view}"
    texts = [f"{title} — as of {report_date(as_of, tf_for_title)}: close {close:,.2f}",
             _side_text(resistances, above=True)]
    if at_price:
        texts.append("At price: " + " · ".join(f"{ln['price']:,.2f}" for ln in at_price))
    texts.append(_side_text(supports, above=False))
    return {
        "view": view,
        "title": title,
        "as_of": iso(as_of, tf_for_title),
        "close": num(close),
        "resistances": resistances,     # R1 first
        "at_price": at_price,
        "supports": supports,           # S1 first
        "counts": {"R": len(resistances), "AT": len(at_price), "S": len(supports)},
        "texts": texts,
    }


def summary_line(trading_view: Optional[dict]) -> str:
    if not trading_view:
        return "S&R: trading ladder not available."
    def first(lines):
        if not lines:
            return "none"
        ln = lines[0]
        tag = f" {' '.join(ln['pd_tags'])}" if ln["pd_tags"] else ""
        return f"{ln['label']} {ln['price']:,.2f}{tag}"
    return f"S&R: {first(trading_view['resistances'])} · {first(trading_view['supports'])} (trading ladder)"


def _read(reader: Callable, key: str, daily_domain: str, tf: str):
    return reader(key, INTRADAY_DOMAIN if tf in INTRADAY else daily_domain, tf)


def build_horizontal_sr_snapshot(key: str = NIFTY_KEY, name: str = "Nifty 50",
                                 daily_domain: str = "indices",
                                 reader: Callable = read_for_indicators) -> dict:
    """All views for one instrument. Never raises."""
    result = {"ok": False, "instrument": key, "name": name, "prev_day": None,
              "views": {}, "errors": {}, "summary": "", "texts": []}
    try:
        prev_day = None
        res = _read(reader, key, daily_domain, "1d")
        if res.ok:
            last = res.df.iloc[-1]
            prev_day = {"date": iso(last["ts"], "1d"), "open": num(last["open"]),
                        "high": num(last["high"]), "low": num(last["low"]), "close": num(last["close"])}
        else:
            result["errors"]["prev_day"] = res.error
        result["prev_day"] = prev_day

        per_tf, close_5m, as_of_5m = [], None, None
        for tf in TIMEFRAMES:
            try:
                res = _read(reader, key, daily_domain, tf)
                if not res.ok:
                    result["errors"][tf] = res.error
                    continue
                candles = res.df.rename(columns={"ts": "time"})
                dev, depth = get_zigzag_settings(tf)
                swings = find_zigzag_swings(candles[["time", "high", "low"]], dev, depth)
                close = float(candles["close"].iloc[-1])
                as_of = candles["time"].iloc[-1]
                merged = timeframe_lines(swings, tf, candles["time"], get_equal_tolerance(tf),
                                         prev_day, close)
                view = snapshot_from_lines(number_lines(merged, close), close, as_of, tf, name)
                view["settings"] = {"deviation_pct": dev, "depth": depth,
                                    "merge_tol_pct": get_equal_tolerance(tf),
                                    "recent_trading_days": RECENT_TRADING_DAYS.get(tf)}
                result["views"][tf] = view
                per_tf.append(merged)
                if tf == "5m":
                    close_5m, as_of_5m = close, as_of
            except Exception as exc:   # boundary: one timeframe failing must not stop the rest
                logger.exception("Horizontal S&R failed for %s %s", key, tf)
                result["errors"][tf] = f"{type(exc).__name__}: {exc}"

        if close_5m is None:
            result["errors"][TRADING] = "no 5m close (5m view not built)"
        else:
            ladder = trading_ladder(per_tf, close_5m, get_equal_tolerance("5m"))
            result["views"][TRADING] = snapshot_from_lines(ladder, close_5m, as_of_5m, TRADING, name)

        result["summary"] = summary_line(result["views"].get(TRADING))
        order = [TRADING] + list(TIMEFRAMES)
        result["texts"] = [t for v in order if v in result["views"] for t in result["views"][v]["texts"] + [""]]
        result["ok"] = bool(result["views"])
    except Exception as exc:   # boundary: never raise
        logger.exception("Horizontal S&R snapshot failed for %s", key)
        result["errors"]["snapshot"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Horizontal S&R snapshot (read-only).")
    parser.add_argument("--key", default=NIFTY_KEY)
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--daily-domain", default="indices", choices=["indices", "universe"])
    parser.add_argument("--json", action="store_true", help="Also print the full package.")
    args = parser.parse_args()

    snap = build_horizontal_sr_snapshot(args.key, args.name, args.daily_domain)
    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])
    out = [command.strip(), f"Horizontal S&R snapshot, run at {datetime.now():%Y-%m-%d %H:%M:%S}", "",
           snap["summary"], ""] + snap["texts"]
    if snap["errors"]:
        out += ["Errors:"] + [f"  {k}: {v}" for k, v in snap["errors"].items()]
    if args.json:
        out += ["", json.dumps(snap, indent=2, ensure_ascii=False)]

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "horizontal_sr_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "horizontal_sr_snapshot.log"
    text = "\n".join(out)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
