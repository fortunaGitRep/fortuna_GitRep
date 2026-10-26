"""
Manual check: every timeframe combined on ONE 5m chart (Ash, 2026-10-26: "imagine combining
all the timeframes in one"). Read-only and separate: it only reads trendline_draw.py (the
per-timeframe charts stay as they are).

Idea: the lines of different timeframes matter most where they meet. At the last candle every
timeframe's lines are turned into prices:
  - its trendlines (Ash's outline lines; confirmed ones only, the last unconfirmed one is left out),
  - its horizontal S&R (the trading ladder: Zig Zag lines of every timeframe, tagged per timeframe).
Prices within ZONE_PCT of each other form a ZONE. A zone backed by 2+ timeframes is drawn as a
shaded band (red above the price = resistance / target for calls, green below = support / target
for puts) labelled with what built it. Strength = sum of timeframe weights (1M 6 ... 5m 1).

The chart shows the last TRADE_DAYS days of 5m candles (Ash reads the 5m trend from 2 days), the
5m lines in full, and for each higher timeframe its nearest line above and below the price
(both projected straight across the last day). The header carries each timeframe's trend and the
trade direction (5m trades follow 1h).

Writes logs/trendline_test_logs/trendline_confluence.log (first line = the command) and
trendline_confluence_<date>.html.

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_confluence --date 2026-10-23 --at 15:30
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check import (
    INTRADAY, LWC_URL, NIFTY_KEY, _epoch, ladder_at, naive_ist)
from modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_draw import (
    DEFAULT_AT, DEFAULT_DATE, SIDE_COLOUR, TF_NAME, TF_WIDTH, TFS, TRADE_TF, _line_series, _pos_in,
    candles_at, data_check, draw_side, line_value, shown_lines, trend_of, window)

ZONE_PCT = 0.10            # prices within 0.10 % (~23 pts at 23,000) of each other = one zone
MIN_TFS = 2                # a zone needs lines from at least 2 timeframes
TRADE_DAYS = 2             # 5m days shown (Ash: the past 2 days decide the 5m trend)
WEIGHT = {"1mo": 6, "1w": 5, "1d": 4, "60m": 3, "15m": 2, "5m": 1}
LADDER_TF = {"1mo": "1mo", "1w": "1w", "1d": "1d", "60m": "60m", "15m": "15m", "5m": "5m"}


# --- every timeframe's lines as prices at the last candle ---------------------------

def tf_lines(series: dict, cutoff: pd.Timestamp) -> dict:
    """tf -> (window candles, {side: shown lines})."""
    out = {}
    for tf in TFS:
        w = window(candles_at(series, tf, cutoff), tf)
        if len(w) < 2:
            continue
        out[tf] = (w, {side: shown_lines(draw_side(w, side == "falling"), True)
                       for side in ("falling", "rising")})
    return out


def levels_now(lines: dict, ladder: pd.DataFrame, t_now: pd.Timestamp) -> list[dict]:
    """Every line's price at t_now: trendlines of each timeframe + the ladder's horizontal lines."""
    lv = []
    for tf, (w, sides) in lines.items():
        for side, ls in sides.items():
            ext = w["high" if side == "falling" else "low"].to_numpy(dtype=float)
            for l in ls:
                lv.append({"price": line_value(ext, l["i"], l["j"], _pos_in(w["time"], tf, t_now)),
                           "tfs": {tf}, "what": f"{TF_NAME[tf]} {'falling' if side == 'falling' else 'rising'} L{l['n']}",
                           "kind": "trend"})
    for r in ladder.itertuples():
        tfs = {t.strip() for t in str(r.timeframes).split() if t.strip() in LADDER_TF}
        if tfs:
            lv.append({"price": float(r.price), "tfs": tfs, "kind": "hsr",
                       "what": f"HSR {r.price:,.2f} [{' '.join(TF_NAME[t] for t in TFS if t in tfs)}]"})
    return sorted(lv, key=lambda d: d["price"])


def zones(levels: list[dict], close: float) -> list[dict]:
    """Group prices within ZONE_PCT of the group's first price; keep groups with MIN_TFS+ timeframes."""
    out, group = [], []
    for lv in levels:
        if group and lv["price"] - group[0]["price"] > group[0]["price"] * ZONE_PCT / 100:
            out.append(group)
            group = []
        group.append(lv)
    if group:
        out.append(group)
    res = []
    for g in out:
        tfs = set().union(*(lv["tfs"] for lv in g))
        if len(tfs) < MIN_TFS:
            continue
        lo, hi = g[0]["price"], g[-1]["price"]
        mid = (lo + hi) / 2
        res.append({"lo": lo, "hi": hi, "mid": mid, "tfs": tfs,
                    "strength": sum(WEIGHT[t] for t in tfs),
                    "side": "above" if mid > close else "below",
                    "members": [lv["what"] for lv in g]})
    return res


# --- chart ---------------------------------------------------------------------------

def chart(five: pd.DataFrame, lines: dict, zs: list[dict], trends: dict, title: str,
          show_from: pd.Timestamp) -> str:
    view = five[five["time"] >= show_from].reset_index(drop=True)
    day = view[view["time"].dt.normalize() == view["time"].iloc[-1].normalize()]
    close = float(view["close"].iloc[-1])
    lo_v, hi_v = float(view["low"].min()), float(view["high"].max())
    pad = (hi_v - lo_v) * 0.30
    series, markers = [], []
    for tf, (w, sides) in lines.items():
        for side, ls in sides.items():
            if tf == "5m":
                for l in ls:
                    ser = _line_series(w, tf, side, l, list(view["time"]))
                    ser["label"] = f"5m L{l['n']}"
                    series.append(ser)
                continue
            ext = w["high" if side == "falling" else "low"].to_numpy(dtype=float)
            best = None
            for l in ls:
                start = max(day["time"].iloc[0], w["time"].iloc[l["i"]])
                t0 = day["time"][day["time"] >= start]
                if len(t0) < 2:
                    continue
                span = [t0.iloc[0], day["time"].iloc[-1]]
                vals = [line_value(ext, l["i"], l["j"], _pos_in(w["time"], tf, t)) for t in span]
                if not (lo_v - pad <= vals[1] <= hi_v + pad):
                    continue
                if (vals[1] >= close) if side == "falling" else (vals[1] <= close):
                    d = abs(vals[1] - close)
                    if best is None or d < best[0]:
                        best = (d, l, span, vals)
            if best:
                _, l, span, vals = best
                series.append({"name": f"{TF_NAME[tf]} {side} L{l['n']}", "colour": SIDE_COLOUR[side],
                               "width": TF_WIDTH[tf], "dashed": l["broken"], "label": f"{TF_NAME[tf]} L{l['n']}",
                               "points": [{"time": _epoch(t), "value": v} for t, v in zip(span, vals)]})
    shown_z = [z for z in zs if lo_v - pad <= z["mid"] <= hi_v + pad]
    bands = [{"lo": z["lo"] - 2 if z["hi"] - z["lo"] < 4 else z["lo"],
              "hi": z["hi"] + 2 if z["hi"] - z["lo"] < 4 else z["hi"],
              "above": z["side"] == "above",
              "label": f"Z{z['strength']} " + " ".join(TF_NAME[t] for t in TFS if t in z["tfs"]),
              "from": _epoch(day["time"].iloc[0]), "to": _epoch(day["time"].iloc[-1])} for z in shown_z]
    trend_txt = " &middot; ".join(f"{TF_NAME[t]} {trends[t]}" for t in TFS if t in trends)
    if TRADE_TF in trends:
        trend_txt += f" &rarr; trade {TF_NAME[TRADE_TF]}: " + ("buy puts" if trends[TRADE_TF] == "DOWN" else "buy calls")
    data = {"candles": [{"time": _epoch(r.time), "open": float(r.open), "high": float(r.high),
                         "low": float(r.low), "close": float(r.close)} for r in view.itertuples()],
            "lines": series, "bands": bands, "markers": markers, "focus": len(day)}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ height:100%; margin:0; background:#ffffff; color:#1f2937; font:14px system-ui, sans-serif; }}
  body {{ display:flex; flex-direction:column; }}
  header {{ padding:10px 16px; }} header small {{ color:#6b7280; }}
  #chart {{ flex:1; min-height:300px; position:relative; }}
</style></head><body>
<header><b>{title}</b><br><b>Trend: {trend_txt}</b><br>
<small>shaded band = zone where lines of 2+ timeframes meet (label: Z + strength, then the timeframes;
strength = 1M 6, 1W 5, 1D 4, 1h 3, 15m 2, 5m 1 added up) &middot; red band above the price = resistance,
green band below = support &middot; red / green lines = falling / rising trendlines, thicker = higher timeframe,
solid = last confirmed, dotted = earlier &middot; scroll left for the day before</small></header>
<div id="chart"></div>
<script src="{LWC_URL}"></script>
<script>
const D = {json.dumps(data)};
const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#1f2937', fontSize: 11 }},
  grid: {{ vertLines: {{ color: '#f1f1f1' }}, horzLines: {{ color: '#f1f1f1' }} }},
  timeScale: {{ timeVisible: true, secondsVisible: false }},
  rightPriceScale: {{ borderVisible: false }}, autoSize: true, localization: {{ locale: 'en-IN' }} }});
for (const b of D.bands) {{
  const z = chart.addBaselineSeries({{ baseValue: {{ type: 'price', price: b.lo }},
    topFillColor1: b.above ? 'rgba(211,47,47,0.22)' : 'rgba(46,125,50,0.22)',
    topFillColor2: b.above ? 'rgba(211,47,47,0.22)' : 'rgba(46,125,50,0.22)',
    topLineColor: b.above ? 'rgba(211,47,47,0.6)' : 'rgba(46,125,50,0.6)', lineWidth: 1,
    bottomFillColor1: 'rgba(0,0,0,0)', bottomFillColor2: 'rgba(0,0,0,0)', bottomLineColor: 'rgba(0,0,0,0)',
    priceLineVisible: false, lastValueVisible: true, title: b.label, crosshairMarkerVisible: false }});
  z.setData([{{ time: b.from, value: b.hi }}, {{ time: b.to, value: b.hi }}]);
}}
const candles = chart.addCandlestickSeries({{ upColor:'#26a69a', downColor:'#ef5350', borderVisible:false,
  wickUpColor:'#26a69a', wickDownColor:'#ef5350' }});
candles.setData(D.candles);
candles.setMarkers(D.markers);
for (const ln of D.lines) {{
  if (ln.points.length < 2) continue;
  const s = chart.addLineSeries({{ color: ln.colour, lineWidth: ln.width, lineStyle: ln.dashed ? 2 : 0,
    priceLineVisible: false, lastValueVisible: !!ln.label, title: ln.label || '', crosshairMarkerVisible: false }});
  s.setData(ln.points);
}}
const n = D.candles.length;
chart.timeScale().setVisibleLogicalRange({{ from: n - D.focus - 1, to: n + 2 }});
</script></body></html>
"""


# --- run -----------------------------------------------------------------------------

def run(series: dict, date: str, at: str, out_dir: Optional[Path] = None) -> list[str]:
    cutoff = pd.Timestamp(f"{date} {at}")
    out = ["", "=" * 100, f"ALL TIMEFRAMES COMBINED, AS OF {cutoff:%a %d %b %Y %H:%M}", "=" * 100]
    out += data_check(series, cutoff)
    lines = tf_lines(series, cutoff)
    if "5m" not in lines:
        return out + ["  no 5m candles -- nothing to combine"]
    five = lines["5m"][0]
    t_now, close = five["time"].iloc[-1], float(five["close"].iloc[-1])
    trends = {tf: trend_of(w)[0] for tf, (w, _) in lines.items()}
    ladder = ladder_at({tf: candles_at(series, tf, cutoff) for tf in TFS}, cutoff, close)
    lv = levels_now(lines, ladder, t_now)
    zs = zones(lv, close)
    out += ["", f"5m last candle {t_now:%a %d %b %H:%M}  close {close:,.2f}",
            "TREND: " + " · ".join(f"{TF_NAME[t]} {trends[t]}" for t in TFS if t in trends)
            + (f"  -> trade {TF_NAME[TRADE_TF]}: " + ("buy puts" if trends[TRADE_TF] == "DOWN" else "buy calls")
               if TRADE_TF in trends else ""),
            f"ZONES (lines of {MIN_TFS}+ timeframes within {ZONE_PCT}% of each other), nearest first:"]
    for side, word in (("above", "ABOVE (resistance / call target)"), ("below", "BELOW (support / put target)")):
        zz = sorted([z for z in zs if z["side"] == side], key=lambda z: abs(z["mid"] - close))[:5]
        out.append(f"  {word}:")
        if not zz:
            out.append("    none")
        for z in zz:
            out.append(f"    {z['lo']:,.2f}-{z['hi']:,.2f}  ({z['mid'] - close:+,.0f} pts)  strength {z['strength']}  "
                       f"[{' '.join(TF_NAME[t] for t in TFS if t in z['tfs'])}]")
            out.append("      " + " | ".join(z["members"]))
    if out_dir is not None:
        days = sorted(five["time"].dt.normalize().unique())[-TRADE_DAYS:]
        p = out_dir / f"trendline_confluence_{date}.html"
        p.write_text(chart(five, lines, zs, trends,
                           f"Nifty 50 - all timeframes on 5m - as of {cutoff:%a %d %b %Y %H:%M}",
                           pd.Timestamp(days[0])), encoding="utf-8")
        out.append(f"Chart: {p}")
    return out


def main() -> None:
    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="All timeframes' lines combined on one 5m chart (read-only).")
    p.add_argument("--key", default=NIFTY_KEY)
    p.add_argument("--date", default=DEFAULT_DATE, help="YYYY-MM-DD")
    p.add_argument("--at", default=DEFAULT_AT, help="HH:MM cut-off (15:30 = after the close)")
    p.add_argument("--daily-domain", default="indices", help="domain for 1d / 1w / 1mo")
    args = p.parse_args()

    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])
    report = [command.strip(), f"Trendline confluence, run at {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"instrument {args.key}  as of {args.date} {args.at}"]
    series = {}
    for tf in TFS:
        r = read_for_indicators(args.key, "universe_intraday" if tf in INTRADAY else args.daily_domain, tf)
        if not r.ok:
            report.append(f"{TF_NAME[tf]} not loaded, left out -- {r.error}")
            continue
        d = r.df.rename(columns={"ts": "time"})[["time", "open", "high", "low", "close"]].copy()
        d["time"] = naive_ist(d["time"])
        series[tf] = d.sort_values("time").reset_index(drop=True)
    out_dir = Path(__file__).resolve().parents[4] / "logs" / "trendline_test_logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        report += run(series, args.date, args.at, out_dir)
    except ValueError as exc:
        report.append(f"NOT OK -- {exc}")
    log_path = out_dir / "trendline_confluence.log"
    text = "\n".join(report)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
