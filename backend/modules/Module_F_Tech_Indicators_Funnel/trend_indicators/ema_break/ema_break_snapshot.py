"""
EMA break watch snapshot: one JSON-safe package + texts + alerts per instrument
(same shape as the other indicator snapshots).

Live views (60m / 15m / 5m), EMA 50 / 100 / 200 — only lines where something is
happening (ema_break.line_texts):
  - break on the latest candle: text with size + odds; ⚡ alert only on a TALL candle
  - near (within one average candle move): text; alert only when NEW
  - far from all three EMAs: nothing printed for that timeframe ("quiet")
Context views (1D / 1W / 1M): one line each for the pre-market read, e.g.
  "1D (Fri 16 Oct 2026): close 23,146.15 — below EMA 50 23,431.07 (-1.22%), ..."
  No alerts there: a daily EMA can only break at the close.
Summary line, e.g.
  "EMA break watch: 60m quiet · 15m ⚡ broke below EMA 200 (tall) · 5m near EMA 50"

build_ema_break_snapshot() never raises: a failed timeframe is reported in
`errors` and the others are still built. Read-only; the manual run writes
backend/logs/ema_break_test_logs/ema_break_snapshot.log.

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.ema_break_snapshot
    python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.ema_break_snapshot --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import iso, num, report_date
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import DEFAULT_DOMAIN, is_intraday
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema import compute_emas
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.ema_break import (
    LIVE_TIMEFRAMES,
    WATCH_PERIODS,
    analyze_line,
    line_texts,
)

logger = logging.getLogger(__name__)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
CONTEXT_TIMEFRAMES = ("1mo", "1w", "1d")
TF_LABEL = {"1mo": "1M", "1w": "1W", "1d": "1D", "60m": "60m", "15m": "15m", "5m": "5m"}


def _candles(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={"ts": "time"}).reset_index(drop=True)


def live_view(candles: pd.DataFrame, tf: str) -> dict:
    """Near / break state of EMA 50 / 100 / 200 on the latest candle. Pure."""
    emas = compute_emas(candles, WATCH_PERIODS)
    lines, texts, alerts = [], [], []
    for p in WATCH_PERIODS:
        s = analyze_line(candles, emas[f"ema_{p}"], p, tf)
        if s is None:
            continue
        lines.append(s)
        t, a = line_texts(s)
        texts += t
        alerts += a
    return {"timeframe": tf, "as_of": iso(candles["time"].iloc[-1], tf),
            "as_of_text": report_date(candles["time"].iloc[-1], tf),
            "close": num(candles["close"].iloc[-1]), "lines": lines,
            "texts": texts, "alerts": alerts}


def context_view(candles: pd.DataFrame, tf: str) -> dict:
    """Where the close sits against EMA 50 / 100 / 200 (one line). Pure."""
    emas = compute_emas(candles, WATCH_PERIODS)
    close = float(candles["close"].iloc[-1])
    parts, levels = [], []
    for p in WATCH_PERIODS:
        e = emas[f"ema_{p}"].iloc[-1]
        if pd.isna(e):
            parts.append(f"EMA {p} n/a")
            levels.append({"period": p, "ema": None, "side": None, "distance_pct": None})
            continue
        e = float(e)
        side = "above" if close > e else ("below" if close < e else "at")
        pct = 100.0 * (close - e) / e
        parts.append(f"{side} EMA {p} {e:,.2f} ({pct:+.2f}%)")
        levels.append({"period": p, "ema": round(e, 2), "side": side, "distance_pct": round(pct, 2)})
    text = (f"{TF_LABEL[tf]} ({report_date(candles['time'].iloc[-1], tf)}): close {close:,.2f} — "
            + ", ".join(parts))
    return {"timeframe": tf, "as_of": iso(candles["time"].iloc[-1], tf), "close": round(close, 2),
            "levels": levels, "texts": [text], "alerts": []}


def summary_line(live: dict) -> str:
    parts = []
    for tf in LIVE_TIMEFRAMES:
        v = live.get(tf)
        if v is None:
            parts.append(f"{tf} n/a")
            continue
        items = []
        for s in v["lines"]:
            b = s["break"]
            if b:
                flag = "⚡ " if b["tier"] == "tall" else ""
                items.append(f"{flag}broke {b['direction']} EMA {s['period']} ({b['tier'] or 'size n/a'})")
            elif s["near"]:
                items.append(f"near EMA {s['period']}")
        parts.append(f"{tf} " + (", ".join(items) if items else "quiet"))
    return "EMA break watch: " + " · ".join(parts)


def build_ema_break_snapshot(key: str = NIFTY_KEY, name: str = "Nifty 50", daily_domain: str = "indices",
                             reader: Callable = None) -> dict:
    """Live views (60m/15m/5m) + context (1M/1W/1D) for one instrument. Never raises."""
    result = {"ok": False, "instrument": key, "name": name, "live": {}, "context": {},
              "errors": {}, "summary": "", "alerts": [], "texts": []}
    try:
        if reader is None:
            from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators as reader
        for tf in CONTEXT_TIMEFRAMES + LIVE_TIMEFRAMES:
            try:
                domain = DEFAULT_DOMAIN[tf] if is_intraday(tf) else daily_domain
                res = reader(key, domain, tf)
                if not res.ok:
                    result["errors"][tf] = res.error
                    continue
                candles = _candles(res.df)
                if tf in LIVE_TIMEFRAMES:
                    result["live"][tf] = live_view(candles, tf)
                else:
                    result["context"][tf] = context_view(candles, tf)
            except Exception as exc:   # boundary: one timeframe failing must not stop the rest
                logger.exception("EMA break watch failed for %s %s", key, tf)
                result["errors"][tf] = f"{type(exc).__name__}: {exc}"

        result["summary"] = summary_line(result["live"])
        texts = [f"{name} · EMA break watch (EMA 50 / 100 / 200)", result["summary"], ""]
        for tf in LIVE_TIMEFRAMES:
            v = result["live"].get(tf)
            if v is None:
                continue
            texts.append(f"{tf} — as of {v['as_of_text']}: close {v['close']:,.2f}")
            texts += v["texts"] if v["texts"] else ["  quiet: price not near EMA 50 / 100 / 200"]
            result["alerts"] += v["alerts"]
        texts += ["", "Context (pre-market):"]
        for tf in CONTEXT_TIMEFRAMES:
            v = result["context"].get(tf)
            if v is not None:
                texts += v["texts"]
        result["texts"] = texts
        result["ok"] = bool(result["live"] or result["context"])
    except Exception as exc:   # boundary: never raise
        logger.exception("EMA break watch snapshot failed for %s", key)
        result["errors"]["snapshot"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="EMA break watch snapshot (read-only).")
    parser.add_argument("--key", default=NIFTY_KEY)
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--daily-domain", default="indices", choices=["indices", "universe"])
    parser.add_argument("--json", action="store_true", help="Also print the full package.")
    args = parser.parse_args()

    snap = build_ema_break_snapshot(args.key, args.name, args.daily_domain)
    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])
    out = [command.strip(), f"EMA break watch snapshot, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    out += snap["texts"]
    out += ["", "Alerts:"] + ([f"  {a}" for a in snap["alerts"]] or ["  none"])
    if snap["errors"]:
        out += ["", "Errors:"] + [f"  {k}: {v}" for k, v in snap["errors"].items()]
    if args.json:
        out += ["", json.dumps(snap, indent=2, ensure_ascii=False, default=str)]

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "ema_break_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "ema_break_snapshot.log"
    text = "\n".join(out)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
