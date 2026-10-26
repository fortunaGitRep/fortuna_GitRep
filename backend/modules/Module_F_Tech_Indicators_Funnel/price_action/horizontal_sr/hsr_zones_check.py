"""
Manual check: horizontal S&R ZONES (hsr_zones.py) on the 5m chart, last 7 days (Ash, 2026-10-26).
Read-only. For Ash to compare with her own chart: are the zones right, do we want them?

Each day's zones use only candles finished before that day opens (09:15): Zig Zag swings of
every timeframe (1M / 1W / 1D / 1h / 15m / 5m) -> one zone per swing (wick to body, depth
between the average bar move and half the ATR) -> same turning point counted once -> overlapping
zones merged -> numbered R1 / S1 from the previous close. The band runs across that day in
colour until a wick breaks it (black square "Z break"), then grey. Zones are NOT recomputed
during the day.

Writes logs/horizontal_sr_test_logs/hsr_zones_check.log (first line = the command) and
hsr_zones_<date>.html.

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.hsr_zones_check --date 2026-10-23 --at 15:30
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

from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.hsr_zones import hsr_zones
from modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check import (
    INTRADAY, LWC_URL, NIFTY_KEY, WARMUP_CANDLES, _epoch, _swings, naive_ist)
from modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_draw import (
    TF_NAME, TFS, candles_at, data_check)

SHOW_DAYS = 7
NEAR = 3                    # zones listed in the log per side per day
COLOUR = {"R": "211,47,47", "S": "46,125,50", "AT": "245,124,0"}


def zones_before(series: dict, day: pd.Timestamp, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, float, pd.DataFrame]:
    """Zones known at `day` 09:15, breaks checked on that day's 5m candles up to `cutoff`."""
    start = day + pd.Timedelta(hours=9, minutes=15)
    per = {}
    for tf in TFS:
        known = candles_at(series, tf, start)
        if tf in WARMUP_CANDLES:
            known = known.iloc[-WARMUP_CANDLES[tf]:].reset_index(drop=True)
        if len(known) >= 3:
            per[tf] = (_swings(known, tf), known)
    five = candles_at(series, "5m", cutoff)
    today = five[five["time"].dt.normalize() == day].reset_index(drop=True)
    if "5m" not in per or today.empty:
        return pd.DataFrame(), float("nan"), today
    ref = float(per["5m"][1]["close"].iloc[-1])                # previous close
    return hsr_zones(per, ref, break_candles=today), ref, today


def _tfs(z) -> str:
    return " ".join(TF_NAME[t] for t in TFS if t in str(z["timeframes"]).split())


def zone_text(z) -> str:
    brk = f"  BROKE {z['broken_dir']} {z['broken_at']:%H:%M}" if pd.notna(z["broken_at"]) else ""
    return (f"{z['label']:>4} {z['lo']:,.2f}-{z['hi']:,.2f} ({z['hi'] - z['lo']:,.0f} pts)  touches {z['touches']} "
            f"({z['highs']} high, {z['lows']} low)  [{_tfs(z)}]  last {z['last_touch']:%d %b %Y %H:%M}{brk}")


def chart_html(title: str, candles: pd.DataFrame, bands: list[dict], markers: list[dict]) -> str:
    data = {"candles": [{"time": _epoch(r.time), "open": float(r.open), "high": float(r.high),
                         "low": float(r.low), "close": float(r.close)} for r in candles.itertuples()],
            "bands": bands, "markers": sorted(markers, key=lambda m: m["time"])}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ height:100%; margin:0; background:#ffffff; color:#1f2937; font:14px system-ui, sans-serif; }}
  body {{ display:flex; flex-direction:column; }}
  header {{ padding:10px 16px; }} header small {{ color:#6b7280; }}
  #chart {{ flex:1; min-height:300px; position:relative; }}
</style></head><body>
<header><b>{title}</b><br><small>Horizontal S&amp;R zones (books + studies): each swing = wick to candle body,
at least the average bar move and at most half the ATR deep; the same turning point on several timeframes counts
once; overlapping zones merge (touches = separate swings inside). Each day's zones use only candles finished before
09:15. Red = above the previous close (R), green = below (S), orange = contains it (AT). A wick past the far edge
breaks the zone: black square, the band turns grey after it. Labels on the last day: R1 / S1, touches (t),
timeframes.</small></header>
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
  const fill = 'rgba(' + b.rgb + ',' + b.alpha + ')';
  const z = chart.addBaselineSeries({{ baseValue: {{ type: 'price', price: b.lo }},
    topFillColor1: fill, topFillColor2: fill, topLineColor: 'rgba(' + b.rgb + ',0.7)', lineWidth: 1,
    bottomFillColor1: 'rgba(0,0,0,0)', bottomFillColor2: 'rgba(0,0,0,0)', bottomLineColor: 'rgba(0,0,0,0)',
    priceLineVisible: false, lastValueVisible: !!b.label, title: b.label || '', crosshairMarkerVisible: false,
    autoscaleInfoProvider: () => null }});
  z.setData([{{ time: b.from, value: b.hi }}, {{ time: b.to, value: b.hi }}]);
}}
const candles = chart.addCandlestickSeries({{ upColor:'#26a69a', downColor:'#ef5350', borderVisible:false,
  wickUpColor:'#26a69a', wickDownColor:'#ef5350' }});
candles.setData(D.candles);
candles.setMarkers(D.markers);
chart.timeScale().fitContent();
</script></body></html>
"""


def run(series: dict, date: str, at: str, out_dir: Optional[Path] = None) -> list[str]:
    cutoff = pd.Timestamp(f"{date} {at}")
    out = ["", "=" * 100, f"HSR ZONES ON 5m, last {SHOW_DAYS} days up to {cutoff:%a %d %b %Y %H:%M}", "=" * 100]
    out += data_check(series, cutoff)
    five = candles_at(series, "5m", cutoff)
    if five.empty:
        return out + ["  no 5m candles"]
    days = [pd.Timestamp(d) for d in sorted(five["time"].dt.normalize().unique())[-SHOW_DAYS:]]
    shown = five[five["time"].dt.normalize().isin(days)].reset_index(drop=True)
    lo_c, hi_c = float(shown["low"].min()), float(shown["high"].max())
    bands, markers = [], []
    for d in days:
        z, ref, today = zones_before(series, d, cutoff)
        out += ["", f"{d:%a %d %b %Y}: zones known at 09:15, previous close {ref:,.2f}; "
                    f"day high {today['high'].max():,.2f} low {today['low'].min():,.2f}" if not today.empty else ""]
        if z.empty:
            out.append("  no zones (no candles before this day)")
            continue
        near = pd.concat([z[z["side"] == "R"].tail(NEAR), z[z["side"] == "AT"], z[z["side"] == "S"].head(NEAR)])
        out += ["  " + zone_text(r) for _, r in near.iterrows()]
        t0, t1 = today["time"].iloc[0], today["time"].iloc[-1]
        last = d == days[-1]
        for _, r in z.iterrows():
            if r["hi"] < lo_c or r["lo"] > hi_c:
                continue                                       # off this chart
            label = f"{r['label']} {r['touches']}t {_tfs(r)}" if last else ""
            brk = r["broken_at"]
            if pd.notna(brk):
                bands.append({"lo": r["lo"], "hi": r["hi"], "rgb": COLOUR[r["side"]], "alpha": 0.22, "label": "",
                              "from": _epoch(t0), "to": _epoch(brk)})
                if brk < t1:
                    bands.append({"lo": r["lo"], "hi": r["hi"], "rgb": "120,120,120", "alpha": 0.12, "label": label,
                                  "from": _epoch(brk), "to": _epoch(t1)})
                markers.append({"time": _epoch(brk), "position": "aboveBar" if r["broken_dir"] == "up" else "belowBar",
                                "color": "#000000", "shape": "square", "text": f"{r['label']} break"})
            else:
                bands.append({"lo": r["lo"], "hi": r["hi"], "rgb": COLOUR[r["side"]], "alpha": 0.22, "label": label,
                              "from": _epoch(t0), "to": _epoch(t1)})
    for b in bands:                                            # same start and end time: widen to the next candle
        if b["from"] >= b["to"]:
            b["to"] = b["from"] + 300
    if out_dir is not None:
        p = out_dir / f"hsr_zones_{date}.html"
        p.write_text(chart_html(f"Nifty 50 5m - horizontal S&R zones - {days[0]:%d %b} to {cutoff:%d %b %Y %H:%M}",
                                shown, bands, markers), encoding="utf-8")
        out += ["", f"Chart: {p}"]
    return out


def main() -> None:
    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Horizontal S&R zones on the 5m chart, last 7 days (read-only).")
    p.add_argument("--key", default=NIFTY_KEY)
    p.add_argument("--date", default="2026-10-23", help="YYYY-MM-DD")
    p.add_argument("--at", default="15:30", help="HH:MM cut-off (15:30 = after the close)")
    p.add_argument("--daily-domain", default="indices", help="domain for 1d / 1w / 1mo")
    args = p.parse_args()

    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])
    report = [command.strip(), f"HSR zones check, run at {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"instrument {args.key}  up to {args.date} {args.at}"]
    series = {}
    for tf in TFS:
        r = read_for_indicators(args.key, "universe_intraday" if tf in INTRADAY else args.daily_domain, tf)
        if not r.ok:
            report.append(f"{TF_NAME[tf]} not loaded, left out -- {r.error}")
            continue
        d = r.df.rename(columns={"ts": "time"})[["time", "open", "high", "low", "close"]].copy()
        d["time"] = naive_ist(d["time"])
        series[tf] = d.sort_values("time").reset_index(drop=True)
    out_dir = Path(__file__).resolve().parents[4] / "logs" / "horizontal_sr_test_logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        report += run(series, args.date, args.at, out_dir)
    except ValueError as exc:
        report.append(f"NOT OK -- {exc}")
    log_path = out_dir / "hsr_zones_check.log"
    text = "\n".join(report)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
