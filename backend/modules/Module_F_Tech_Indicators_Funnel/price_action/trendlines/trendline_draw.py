"""
Manual check: trendlines drawn the way Ash draws them, top-down on every timeframe
(Ash, 2026-10-25). Read-only. Step A of the simplified plan — lines only; entries and
exits come back on top later (the old chain check stays in trendline_check.py).

Ash's method (her 17 steps on tv.dhan, 23 Oct 2026), as rules:
  1. Top-down: 1M -> 1W -> 1D -> 1h -> 15m -> 5m. Each timeframe's lines stay as S&R.
  2. Start at the extreme in the timeframe's look-back: highest high for falling lines,
     lowest low for rising lines.
  3. A line runs through two candle wicks with NO wick crossing it between them.
  4. A wick crossing the line by any amount is a break (no close needed, no tolerance;
     "prices need to stay above the trendline"). After a break the line is redrawn from
     the same start to the new point.
  5. The next line starts where the previous one ends, so each line is steeper.
  Rules 2-5 together are the outline of the wicks (upper outline of highs for falling
  lines, lower outline of lows for rising lines) from the extreme to the last candle,
  rebuilt candle by candle: a line that existed and disappears was broken by that candle.

Look-back (Ash, 2026-10-25): 1M / 1W 20 years (her monthly chart starts 2006),
1D 1 year (250 trading days; Ash 2026-10-25, was 10 days), 1h / 15m ~2 weeks (10 trading days),
5m the day before yesterday + yesterday + today (3 trading days) for trendline_confluence; the
trendline_draw charts use the last 7 trading days on 5m (DRAW_LOOKBACK, Ash 2026-10-26: "what you
are doing for 3 days i want to see drawing and hsr ... for 7 days").

Trend per timeframe (default, to confirm): the more recent extreme decides — highest high
more recent than lowest low = DOWN (falling from the high), else UP. Ash trades the 5m
chart in the 1h direction ("daily up but hourly down -> buy put").

Candles used at the cut-off (no future data): intraday candles closed by then; 1D candles
of earlier days (and today's after 15:30); 1W / 1M finished periods from storage plus the
running week / month built from the daily candles up to the cut-off.

Writes logs/trendline_test_logs/trendline_draw.log (first line = the command) and charts
trendline_draw_<tf>_<date>.html (one per timeframe) + trendline_draw_all_<date>.html
(the 5m chart with every timeframe's lines).

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_draw
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_draw --date 2026-10-23 --at 15:30
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check import (
    INTRADAY,
    LWC_URL,
    NIFTY_KEY,
    _epoch,
    known_at,
    WARMUP_CANDLES,
    _swings,
    ladder_at,
    naive_ist,
)

TFS = ("1mo", "1w", "1d", "60m", "15m", "5m")
TF_NAME = {"1mo": "1M", "1w": "1W", "1d": "1D", "60m": "1h", "15m": "15m", "5m": "5m"}
LOOKBACK = {"1mo": ("years", 20), "1w": ("years", 20), "1d": ("days", 250),
            "60m": ("days", 10), "15m": ("days", 10), "5m": ("days", 3)}
TRADE_TF = "60m"          # Ash trades 5m in the 1h direction
DRAW_LOOKBACK = {**LOOKBACK, "5m": ("days", 7)}   # trendline_draw charts: 5m 7 days (Ash, 2026-10-26)
SHOW_DAYS_5M = DRAW_LOOKBACK["5m"][1]            # 5m zones chart: same 7 days
DEFAULT_DATE = "2026-10-23"
DEFAULT_AT = "15:30"
SIDE_COLOUR = {"falling": "#d32f2f", "rising": "#2e7d32"}
TF_WIDTH = {"1mo": 3, "1w": 3, "1d": 3, "60m": 2, "15m": 2, "5m": 1}


# --- candles known at the cut-off --------------------------------------------------

def _day_done(cutoff: pd.Timestamp) -> bool:
    return cutoff.hour * 60 + cutoff.minute >= 15 * 60 + 30


def candles_at(series: dict, tf: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Candles of `tf` usable at `cutoff` without future data (see module doc)."""
    df = series.get(tf)
    if df is None or df.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    if tf in INTRADAY:
        return known_at(df, cutoff, INTRADAY[tf])
    day = cutoff.normalize()
    if tf == "1d":
        keep = df["time"].dt.normalize() < day
        if _day_done(cutoff):
            keep |= df["time"].dt.normalize() == day
        return df[keep.to_numpy()].reset_index(drop=True)
    daily = candles_at(series, "1d", cutoff)
    if tf == "1w":
        start = day - pd.Timedelta(days=day.weekday())
        done = df[(df["time"].dt.normalize() + pd.Timedelta(days=7) <= start).to_numpy()]
    else:
        start = day.replace(day=1)
        done = df[(df["time"].dt.normalize() < start).to_numpy()]
        done = done[(done["time"].dt.normalize() + pd.offsets.MonthBegin(1) <= start).to_numpy()]
    run = daily[daily["time"].dt.normalize() >= start]
    if not run.empty:
        done = pd.concat([done, pd.DataFrame([{
            "time": start, "open": run["open"].iloc[0], "high": run["high"].max(),
            "low": run["low"].min(), "close": run["close"].iloc[-1]}])], ignore_index=True)
    return done.reset_index(drop=True)


def window(df: pd.DataFrame, tf: str, lookback: Optional[dict] = None) -> pd.DataFrame:
    unit, n = (lookback or LOOKBACK)[tf]
    if df.empty:
        return df
    if unit == "years":
        since = df["time"].iloc[-1] - pd.DateOffset(years=n)
        return df[df["time"] >= since].reset_index(drop=True)
    days = sorted(df["time"].dt.normalize().unique())[-n:]
    return df[df["time"].dt.normalize().isin(days).to_numpy()].reset_index(drop=True)


# --- horizontal S&R per chart (Ash, 2026-10-25: previous highs / lows are her targets) --

def hsr_for(series: dict, tf: str, cutoff: pd.Timestamp, close: float) -> pd.DataFrame:
    """Horizontal S&R for the `tf` chart: Zig Zag lines of `tf` and every higher timeframe
    (candles usable at the cut-off), merged within `tf`'s equal tolerance, numbered from
    `close`, each line tagged with its timeframes (same rules as the trading ladder)."""
    from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr import (
        timeframe_lines, trading_ladder)
    from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
        get_equal_tolerance)
    frames = []
    for t2 in TFS[: TFS.index(tf) + 1]:
        known = candles_at(series, t2, cutoff)
        if t2 in WARMUP_CANDLES:
            known = known.iloc[-WARMUP_CANDLES[t2]:].reset_index(drop=True)
        if len(known) < 3:
            continue
        sw = _swings(known, t2)
        if not sw.empty:
            frames.append(timeframe_lines(sw, t2, known["time"], get_equal_tolerance(t2), None, close))
    return trading_ladder(frames, close, get_equal_tolerance(tf))


def zigzag_of(series: dict, tf: str, cutoff: pd.Timestamp, w: pd.DataFrame) -> pd.DataFrame:
    """Zig Zag pivots of `tf` (candles usable at the cut-off) inside the chart window `w`."""
    known = candles_at(series, tf, cutoff)
    if len(known) < 3 or w.empty:
        return pd.DataFrame(columns=["kind", "price", "pivot_time"])
    sw = _swings(known, tf)
    return sw[sw["pivot_time"] >= w["time"].iloc[0]].reset_index(drop=True)


# Zig Zag on the higher charts (Ash, 2026-10-26): 1M / 1W draw the Zig Zag with HSR only at
# its own points (a line from the pivot to the right); 1D draws the Zig Zag on top of its
# usual HSR (this + higher timeframes); 1h draws the Zig Zag with HSR from its own points.
ZIGZAG_CHART = {"1mo": "rays", "1w": "rays_until_crossed", "1d": "hsr", "60m": "rays_until_crossed"}
# rays_until_crossed (weekly, 2026-10-26): a pivot's line stops at the first later candle that
# trades through it; only lines nobody has crossed reach the right edge and get a price label.
COMBINED_HSR_EACH_SIDE = 3   # combined 5m chart: nearest horizontal lines above / below
ZIGZAG_COLOUR = "#1565c0"


# --- the outline lines ------------------------------------------------------------

def _outline(ext: np.ndarray, a: int, end: int, falling: bool) -> list[int]:
    """Points of the upper (falling) / lower (rising) outline of ext[a..end], from a.
    Every wick in a..end is on or inside every line of the outline."""
    hull: list[int] = []
    for k in range(a, end + 1):
        while len(hull) >= 2:
            p, q = hull[-2], hull[-1]
            # q stays only if it sticks out beyond the line p -> k
            cross = (ext[q] - ext[p]) * (k - p) - (ext[k] - ext[p]) * (q - p)
            if (cross > 0) if falling else (cross < 0):
                break
            hull.pop()
        hull.append(k)
    return hull


def draw_side(w: pd.DataFrame, falling: bool) -> dict:
    """Candle by candle: the current lines from the extreme, and every confirmed line that
    a later wick crossed (broken; it stays as S&R). A line ending on the newest candle is
    'live' (not confirmed) and is not counted as broken when it changes."""
    ext = w["high" if falling else "low"].to_numpy(dtype=float)
    n = len(ext)
    if n < 2:
        return {"anchor": None, "lines": [], "broken": []}
    better = (lambda x, y: x >= y) if falling else (lambda x, y: x <= y)
    anchor = 0
    prev: set = set()
    broken: list[dict] = []
    for k in range(n):
        if better(ext[k], ext[anchor]):
            # new extreme: every confirmed line from the old one is crossed by this wick
            for (i, j) in sorted(prev):
                if j < k - 1:
                    broken.append({"i": i, "j": j, "break": k, "new_extreme": True})
            anchor, prev = k, set()
            continue
        pts = _outline(ext, anchor, k, falling)
        now = set(zip(pts[:-1], pts[1:]))
        for (i, j) in sorted(prev - now):
            if j < k - 1:                       # confirmed line crossed by candle k
                broken.append({"i": i, "j": j, "break": k, "new_extreme": False})
        prev = now
    pts = _outline(ext, anchor, n - 1, falling)
    lines = [{"i": i, "j": j, "n": m + 1, "live": j == n - 1}
             for m, (i, j) in enumerate(zip(pts[:-1], pts[1:]))]
    return {"anchor": anchor, "lines": lines, "broken": broken}


def line_value(ext: np.ndarray, i: int, j: int, x: float) -> float:
    return float(ext[i] + (ext[j] - ext[i]) * (x - i) / (j - i))


def trend_of(w: pd.DataFrame) -> tuple[str, int, int]:
    """DOWN if the window's highest high is more recent than its lowest low, else UP."""
    hi = int(np.flatnonzero(w["high"].to_numpy() == w["high"].max())[-1])
    lo = int(np.flatnonzero(w["low"].to_numpy() == w["low"].min())[-1])
    return ("DOWN" if hi > lo else "UP"), hi, lo


# --- report -------------------------------------------------------------------------

def _t(w: pd.DataFrame, k: int, tf: str) -> str:
    t = w["time"].iloc[k]
    if tf == "1mo":
        return f"{t:%b %Y}"
    if tf == "1w":
        return f"wk {t:%d %b %Y}"
    if tf == "1d":
        return f"{t:%a %d %b %Y}"
    return f"{t:%a %d %b %H:%M}"


def report_tf(w: pd.DataFrame, tf: str, sides: dict, lookback: Optional[dict] = None) -> list[str]:
    name = TF_NAME[tf]
    if w.empty:
        return [f"  {name}: no candles"]
    trend, hi, lo = trend_of(w)
    out = [f"  {name}  look-back {(lookback or LOOKBACK)[tf][1]} {(lookback or LOOKBACK)[tf][0]}: {_t(w, 0, tf)} -> {_t(w, len(w) - 1, tf)}"
           f" ({len(w)} candles)   last close {w['close'].iloc[-1]:,.2f}",
           f"    trend {trend}  (highest high {_t(w, hi, tf)} {w['high'].iloc[hi]:,.2f}, "
           f"lowest low {_t(w, lo, tf)} {w['low'].iloc[lo]:,.2f})"]
    last = len(w) - 1
    for side in ("falling", "rising"):
        s = sides[side]
        ext = w["high" if side == "falling" else "low"].to_numpy(dtype=float)
        col = "high" if side == "falling" else "low"
        if s["anchor"] is None:
            continue
        out.append(f"    {side.upper()} lines (through the {col}s) from {_t(w, s['anchor'], tf)} "
                   f"{ext[s['anchor']]:,.2f}:")
        if not s["lines"]:
            out.append("      none yet (the extreme is the last candle)")
        for l in s["lines"]:
            now = line_value(ext, l["i"], l["j"], last)
            out.append(f"      line {l['n']}  {_t(w, l['i'], tf)} {ext[l['i']]:,.2f} -> {_t(w, l['j'], tf)} "
                       f"{ext[l['j']]:,.2f}   line now {now:,.2f}   last close {w['close'].iloc[-1] - now:+,.2f} from it"
                       + ("   (2nd point = last candle, not confirmed)" if l["live"] else ""))
        recent = s["broken"][-5:]
        if recent:
            out.append(f"      broken (last {len(recent)} of {len(s['broken'])}; drawn up to the crossing wick):")
            for b in recent:
                out.append(f"        {_t(w, b['i'], tf)} {ext[b['i']]:,.2f} -> {_t(w, b['j'], tf)} "
                           f"{ext[b['j']]:,.2f}   wick crossed at {_t(w, b['break'], tf)}"
                           + ("  (new extreme)" if b["new_extreme"] else ""))
    return out


# --- charts -------------------------------------------------------------------------

def _pos_in(tf_times: pd.Series, tf: str, t: pd.Timestamp) -> float:
    """Fractional bar position of time t on timeframe tf (for drawing its line on 5m)."""
    starts = tf_times.to_numpy()
    k = int(np.searchsorted(starts, np.datetime64(t), side="right") - 1)
    if k < 0:
        return 0.0
    if k + 1 < len(starts):
        span = (starts[k + 1] - starts[k]) / np.timedelta64(1, "s")
    else:
        span = {"1mo": 30 * 86400, "1w": 7 * 86400, "1d": 86400}.get(tf, INTRADAY.get(tf, 5) * 60)
    frac = min(1.0, max(0.0, (t - pd.Timestamp(starts[k])).total_seconds() / span)) if span else 0.0
    return k + frac


def _line_series(w, tf, side, l, times, tf_for_x: Optional[str] = None) -> dict:
    """Points of one line at the given chart times (on its own timeframe or projected).
    A broken line stops at the candle whose wick crossed it (Ash, 2026-10-26: drawing it on
    past the break puts candles through it)."""
    ext = w["high" if side == "falling" else "low"].to_numpy(dtype=float)
    stop = l.get("stop")
    pts = []
    for t in times:
        x = _pos_in(w["time"], tf, t) if tf_for_x else float(w.index[w["time"] == t][0])
        if x < l["i"] or (stop is not None and x > stop):
            continue
        pts.append({"time": _epoch(t), "value": line_value(ext, l["i"], l["j"], x)})
    return {"name": f"{TF_NAME[tf]} {side} line {l['n']}", "colour": SIDE_COLOUR[side],
            "width": TF_WIDTH[tf], "dashed": l.get("broken", False), "points": pts}


def chart_html(title: str, candles: pd.DataFrame, lines: list[dict], markers: list[dict],
               levels: list[dict], focus_last: Optional[int] = None, legend_extra: str = "",
               bands: Optional[list[dict]] = None) -> str:
    data = {"candles": [{"time": _epoch(r.time), "open": float(r.open), "high": float(r.high),
                         "low": float(r.low), "close": float(r.close)} for r in candles.itertuples()],
            "lines": lines, "markers": sorted(markers, key=lambda m: m["time"]), "levels": levels,
            "focus": focus_last, "extra": legend_extra, "bands": bands or []}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ height:100%; margin:0; background:#ffffff; color:#1f2937; font:14px system-ui, sans-serif; }}
  body {{ display:flex; flex-direction:column; }}
  header {{ padding:10px 16px; }} header small {{ color:#6b7280; }}
  #chart {{ flex:1; min-height:300px; position:relative; }}
  #legend span {{ display:inline-block; margin-right:14px; white-space:nowrap; }}
  #legend span:last-child {{ white-space:normal; }}
</style></head><body>
<header><b>{title}</b><br><small id="legend"></small></header>
<div id="chart"></div>
<script src="{LWC_URL}"></script>
<script>
const D = {json.dumps(data)};
const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#1f2937', fontSize: 11 }},
  grid: {{ vertLines: {{ color: '#f1f1f1' }}, horzLines: {{ color: '#f1f1f1' }} }},
  timeScale: {{ timeVisible: true, secondsVisible: false }},
  rightPriceScale: {{ borderVisible: false }}, autoSize: true, localization: {{ locale: 'en-IN' }} }});
const candles = chart.addCandlestickSeries({{ upColor:'#26a69a', downColor:'#ef5350', borderVisible:false,
  wickUpColor:'#26a69a', wickDownColor:'#ef5350' }});
for (const b of D.bands) {{
  const z = chart.addBaselineSeries({{ baseValue: {{ type: 'price', price: b.lo }},
    topFillColor1: b.above ? 'rgba(211,47,47,0.22)' : 'rgba(46,125,50,0.22)',
    topFillColor2: b.above ? 'rgba(211,47,47,0.22)' : 'rgba(46,125,50,0.22)',
    topLineColor: b.above ? 'rgba(211,47,47,0.6)' : 'rgba(46,125,50,0.6)', lineWidth: 1,
    bottomFillColor1: 'rgba(0,0,0,0)', bottomFillColor2: 'rgba(0,0,0,0)', bottomLineColor: 'rgba(0,0,0,0)',
    priceLineVisible: false, lastValueVisible: !!b.label, title: b.label, crosshairMarkerVisible: false }});
  z.setData([{{ time: b.from, value: b.hi }}, {{ time: b.to, value: b.hi }}]);
}}
candles.setData(D.candles);
candles.setMarkers(D.markers);
for (const lv of D.levels) {{
  if (lv.from !== undefined) {{
    const r = chart.addLineSeries({{ color: '#ff6d00', lineWidth: 1, priceLineVisible: false,
      lastValueVisible: !!lv.label, title: lv.label, crosshairMarkerVisible: false }});
    r.setData([{{ time: lv.from, value: lv.price }}, {{ time: lv.to, value: lv.price }}]);
    continue;
  }}
  candles.createPriceLine({{ price: lv.price, color: '#ff6d00', lineWidth: 1, lineStyle: 0,
    axisLabelVisible: true, title: lv.label }});
}}
const legend = document.getElementById('legend');
for (const ln of D.lines) {{
  if (ln.points.length < 2) continue;
  const s = chart.addLineSeries({{ color: ln.colour, lineWidth: ln.width, lineStyle: ln.dashed ? 2 : 0,
    priceLineVisible: false, lastValueVisible: !!ln.label, title: ln.label || '', crosshairMarkerVisible: false }});
  s.setData(ln.points);
}}
legend.innerHTML = '<span style="color:#d32f2f">&#9473; falling lines (through highs)</span>'
  + '<span style="color:#2e7d32">&#9473; rising lines (through lows)</span>'
  + '<span>thicker = higher timeframe &middot; solid = last confirmed line &middot; dotted = earlier line, or broken (ends at the candle that crossed it) &middot; lines whose 2nd point is the last candle are hidden until confirmed &middot; orange = horizontal S&amp;R &middot; blue = Zig Zag (1M / 1W / 1D / 1h) &middot; scroll left for history</span>';
if (D.extra) legend.innerHTML += '<br><span>' + D.extra + '</span>';
if (D.focus) {{
  const n = D.candles.length;
  chart.timeScale().setVisibleLogicalRange({{ from: n - D.focus - 1, to: n + 2 }});
}} else {{
  chart.timeScale().fitContent();
}}
</script></body></html>
"""


def shown_lines(s: dict, hide_live: bool) -> list[dict]:
    """Current lines to draw: unconfirmed ones (2nd point = last candle) left out when
    hide_live; the last confirmed line is solid, the earlier ones dotted (Ash, 2026-10-26)."""
    keep = [dict(l) for l in s["lines"] if not (hide_live and l["live"])]
    for k, l in enumerate(keep):
        l["broken"] = k < len(keep) - 1 or l["live"]          # drawn dotted
    return keep


def tf_chart(w: pd.DataFrame, tf: str, sides: dict, show_broken: int = 3,
             hide_live: bool = True) -> tuple[list, list]:
    lines, markers = [], []
    for side, s in sides.items():
        ext = w["high" if side == "falling" else "low"].to_numpy(dtype=float)
        pos = "aboveBar" if side == "falling" else "belowBar"
        for l in shown_lines(s, hide_live):
            lines.append(_line_series(w, tf, side, l, list(w["time"])))
            markers.append({"time": _epoch(w["time"].iloc[l["i"]]), "position": pos,
                            "color": SIDE_COLOUR[side], "shape": "circle", "text": f"{TF_NAME[tf]} L{l['n']} T1"})
            markers.append({"time": _epoch(w["time"].iloc[l["j"]]), "position": pos,
                            "color": SIDE_COLOUR[side], "shape": "circle", "text": f"L{l['n']} T2"})
        for b in s["broken"][-show_broken:]:
            bl = {"i": b["i"], "j": b["j"], "n": "x", "broken": True, "stop": b["break"]}
            ser = _line_series(w, tf, side, bl, list(w["time"]))
            ser["name"] = f"{TF_NAME[tf]} {side} broken"
            lines.append(ser)
            markers.append({"time": _epoch(w["time"].iloc[b["break"]]), "position": pos,
                            "color": "#000000", "shape": "square", "text": "break"})
        del ext
    return lines, markers


def zone_bands(series: dict, five: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Horizontal S&R as zones on every day of the 5m chart (Ash, 2026-10-26: "zones for all
    candles we show ... current day is live, on what basis would I trade?").
    Each day's zones are built only from candles finished before that day opens (09:15): the
    trading ladder of every timeframe at that moment, ladder lines within ZONE_PCT of each other
    grouped, 2+ timeframes needed (same rules as trendline_confluence.py). So each band is what
    was known before the day started, and the earlier days show whether those zones held.
    Returns the bands and report lines for the last day."""
    from modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_confluence import (
        MIN_TFS, ZONE_PCT, levels_now, zones)
    if five.empty:
        return [], []
    lo, hi = float(five["low"].min()), float(five["high"].max())
    pad = (hi - lo) * 0.10
    days = sorted(five["time"].dt.normalize().unique())
    bands, report = [], []
    for d in days:
        d = pd.Timestamp(d)
        start = d + pd.Timedelta(hours=9, minutes=15)
        known = {tf: candles_at(series, tf, start) for tf in TFS}
        if known.get("5m") is None or known["5m"].empty:
            continue                                   # no candles before this day
        ref = float(known["5m"]["close"].iloc[-1])     # previous close
        ladder = ladder_at(known, start, ref)
        zs = zones(levels_now({}, ladder, start), ref)
        day = five[five["time"].dt.normalize() == d]
        last = d == pd.Timestamp(days[-1])
        for z in zs:
            if not (lo - pad <= z["mid"] <= hi + pad):
                continue
            thin = z["hi"] - z["lo"] < 4                   # a single price: give the band some height
            label = f"Z{z['strength']} " + " ".join(TF_NAME[t] for t in TFS if t in z["tfs"])
            bands.append({"lo": z["lo"] - 2 if thin else z["lo"], "hi": z["hi"] + 2 if thin else z["hi"],
                          "above": z["side"] == "above", "label": label if last else "",
                          "from": _epoch(day["time"].iloc[0]), "to": _epoch(day["time"].iloc[-1])})
        if last:
            report.append(f"    zones for {d:%a %d %b} (known before 09:15, previous close {ref:,.2f}; "
                          f"horizontal S&R of {MIN_TFS}+ timeframes within {ZONE_PCT}%):")
            for side in ("above", "below"):
                zz = sorted([z for z in zs if z["side"] == side], key=lambda z: abs(z["mid"] - ref))[:5]
                report.append(f"      {side}: " + (" · ".join(
                    f"{z['lo']:,.2f}-{z['hi']:,.2f} Z{z['strength']} [{' '.join(TF_NAME[t] for t in TFS if t in z['tfs'])}]"
                    for z in zz) or "none"))
    return bands, report


# --- run ----------------------------------------------------------------------------

def data_check(series: dict, cutoff: pd.Timestamp) -> list[str]:
    """Last stored candle per timeframe; warns when a timeframe stops before the as-of day."""
    out = ["DATA: last stored candle per timeframe"]
    for tf in TFS:
        df = series.get(tf)
        if df is None or df.empty:
            out.append(f"  {TF_NAME[tf]:>3}: none")
            continue
        last = df["time"].iloc[-1]
        short = tf in INTRADAY and last.normalize() < cutoff.normalize()
        out.append(f"  {TF_NAME[tf]:>3}: {last:%a %d %b %Y %H:%M}"
                   + (f"   <-- MISSING {cutoff:%d %b}: intraday stops before the as-of day" if short else ""))
    return out


def run(series: dict, date: str, at: str, out_dir: Optional[Path] = None,
        hide_live: bool = True) -> list[str]:
    cutoff = pd.Timestamp(f"{date} {at}")
    out = ["", "=" * 110, f"AS OF {cutoff:%a %d %b %Y %H:%M} (candles usable then)", "=" * 110]
    out += data_check(series, cutoff)
    result = {}
    for tf in TFS:
        w = window(candles_at(series, tf, cutoff), tf, DRAW_LOOKBACK)
        sides = {"falling": draw_side(w, True), "rising": draw_side(w, False)} if len(w) >= 2 else \
            {"falling": {"anchor": None, "lines": [], "broken": []}, "rising": {"anchor": None, "lines": [], "broken": []}}
        result[tf] = (w, sides)
        out.append("")
        out += report_tf(w, tf, sides, DRAW_LOOKBACK)
        if not w.empty:
            hs = hsr_for(series, tf, cutoff, float(w["close"].iloc[-1]))
            r3 = hs[hs["side"] == "R"].sort_values("price").head(3)
            s3 = hs[hs["side"] == "S"].sort_values("price", ascending=False).head(3)
            fmt = lambda d: " · ".join(f"{r.label} {r.price:,.2f} [{r.timeframes}]" for r in d.itertuples())
            out.insert(len(out) - (len(report_tf(w, tf, sides, DRAW_LOOKBACK)) - 2),
                       f"    targets (horizontal S&R, this + higher timeframes): above {fmt(r3) or 'none'}"
                       f"  |  below {fmt(s3) or 'none'}")
    trends = {tf: trend_of(result[tf][0])[0] for tf in TFS if not result[tf][0].empty}
    out += ["", "TREND BY TIMEFRAME: " + " · ".join(f"{TF_NAME[tf]} {trends[tf]}" for tf in TFS if tf in trends)]
    if TRADE_TF in trends:
        out.append(f"  5m trades follow {TF_NAME[TRADE_TF]}: {trends[TRADE_TF]} -> "
                   + ("buy puts" if trends[TRADE_TF] == "DOWN" else "buy calls"))
    if out_dir is not None:
        five = result["5m"][0]
        close = float(five["close"].iloc[-1]) if not five.empty else None
        levels = []
        if close:
            lad = ladder_at({tf: candles_at(series, tf, cutoff) for tf in TFS}, cutoff, close)
            lo, hi = float(five["low"].min()), float(five["high"].max())
            pad = (hi - lo) * 0.05
            levels = [{"price": float(r.price), "label": f"{r.label} {r.timeframes}"}
                      for r in lad.itertuples() if lo - pad <= r.price <= hi + pad]
        for tf in TFS:
            w, sides = result[tf]
            if w.empty:
                continue
            lines, markers = tf_chart(w, tf, sides, hide_live=hide_live)
            lo_w, hi_w = float(w["low"].min()), float(w["high"].max())
            pad_w = (hi_w - lo_w) * 0.05
            if tf == "5m":
                tf_levels = levels
            elif tf in ZIGZAG_CHART:
                zz = zigzag_of(series, tf, cutoff, w)
                if len(zz) >= 2:
                    lines.append({"name": f"{TF_NAME[tf]} zig zag", "colour": ZIGZAG_COLOUR, "width": 2,
                                  "dashed": False, "points": [{"time": _epoch(r.pivot_time), "value": float(r.price)}
                                                              for r in zz.itertuples()]})
                tf_levels = []
                if ZIGZAG_CHART[tf] == "hsr":
                    hs = hsr_for(series, tf, cutoff, float(w["close"].iloc[-1]))
                    tf_levels = [{"price": float(r.price), "label": f"{r.label} {r.timeframes}"}
                                 for r in hs.itertuples() if lo_w - pad_w <= r.price <= hi_w + pad_w]
                elif ZIGZAG_CHART[tf] in ("rays", "rays_until_crossed"):
                    tf_levels = []
                    for r in zz.itertuples():
                        if r.pivot_time >= w["time"].iloc[-1]:
                            continue
                        when = f"{r.pivot_time:%b %Y}" if tf in ("1mo", "1w") else f"{r.pivot_time:%d %b %H:%M}"
                        label = f"{'R' if r.kind == 'high' else 'S'} {when}"
                        end = w["time"].iloc[-1]
                        if ZIGZAG_CHART[tf] == "rays_until_crossed":
                            later = w[w["time"] > r.pivot_time]
                            hit = later[(later["high"] > r.price) if r.kind == "high" else (later["low"] < r.price)]
                            if not hit.empty:
                                end, label = hit["time"].iloc[0], ""
                        tf_levels.append({"price": float(r.price), "from": _epoch(r.pivot_time),
                                          "to": _epoch(end), "label": label})
            else:
                hs = hsr_for(series, tf, cutoff, float(w["close"].iloc[-1]))
                tf_levels = [{"price": float(r.price), "label": f"{r.label} {r.timeframes}"}
                             for r in hs.itertuples() if lo_w - pad_w <= r.price <= hi_w + pad_w]
            p = out_dir / f"trendline_draw_{TF_NAME[tf]}_{date}.html"
            p.write_text(chart_html(f"Nifty 50 {TF_NAME[tf]} trendlines - as of {cutoff:%a %d %b %Y %H:%M}",
                                    w, lines, markers, tf_levels), encoding="utf-8")
            out.append(f"Chart {TF_NAME[tf]}: {p}")
            if tf == "5m":
                p = out_dir / f"trendline_draw_5m_zones_{date}.html"
                c5 = candles_at(series, "5m", cutoff)           # zones chart: last SHOW_DAYS_5M days
                keep = sorted(c5["time"].dt.normalize().unique())[-SHOW_DAYS_5M:]
                shown = c5[c5["time"].dt.normalize().isin(keep).to_numpy()].reset_index(drop=True)
                bands, zrep = zone_bands(series, shown)
                p.write_text(chart_html(f"Nifty 50 5m trendlines + zones - as of {cutoff:%a %d %b %Y %H:%M}",
                                        shown, lines, markers, [], bands=bands,
                                        legend_extra="shaded band = horizontal S&amp;R zone: lines of 2+ timeframes "
                                                     "within 0.1% of each other. Each day's zones use only candles "
                                                     "finished before that day opened (09:15), so earlier days show "
                                                     "whether the zones held. Red = above the previous close "
                                                     "(resistance), green = below (support). Label on the last day: "
                                                     "Z + strength (1M 6, 1W 5, 1D 4, 1h 3, 15m 2, 5m 1 added up), "
                                                     "then the timeframes. Orange lines are left out here (they are "
                                                     "the zones)."), encoding="utf-8")
                out.append(f"Chart 5m + zones: {p}")
                out[len(out) - 1:len(out) - 1] = zrep
        if not five.empty:
            # Combined 5m chart, kept readable (Ash, 2026-10-26): opens on the last day; per
            # higher timeframe only the nearest falling line above and rising line below the
            # close; their names and values on the price axis; nearest HSR above / below only.
            all_lines, markers = [], []
            day = five[five["time"].dt.normalize() == five["time"].iloc[-1].normalize()]
            ends = [day["time"].iloc[0], day["time"].iloc[-1]]
            close5 = float(five["close"].iloc[-1])
            lo5, hi5 = float(five["low"].min()), float(five["high"].max())
            pad5 = (hi5 - lo5) * 0.25                   # higher-timeframe lines far off this chart are left out
            for tf in TFS:
                w, sides = result[tf]
                if w.empty:
                    continue
                for side, s in sides.items():
                    ext = w["high" if side == "falling" else "low"].to_numpy(dtype=float)
                    live_ok = shown_lines(s, hide_live)
                    if tf == "5m":
                        for l in live_ok:
                            ser = _line_series(w, tf, side, l, list(day["time"]))
                            ser["label"] = f"5m L{l['n']}"
                            all_lines.append(ser)
                            if w["time"].iloc[l["i"]] >= ends[0]:
                                markers.append({"time": _epoch(w["time"].iloc[l["i"]]),
                                                "position": "aboveBar" if side == "falling" else "belowBar",
                                                "color": SIDE_COLOUR[side], "shape": "circle",
                                                "text": f"5m L{l['n']} T1"})
                        continue
                    cands = []
                    for l in live_ok:
                        start = max(ends[0], w["time"].iloc[l["i"]])       # not before its 1st point
                        t0 = day["time"][day["time"] >= start]
                        if t0.empty:
                            continue
                        span = [t0.iloc[0], ends[1]]
                        if span[0] >= span[1]:
                            continue
                        vals = [line_value(ext, l["i"], l["j"], _pos_in(w["time"], tf, t)) for t in span]
                        if not (lo5 - pad5 <= vals[1] <= hi5 + pad5):
                            continue
                        if (vals[1] >= close5) if side == "falling" else (vals[1] <= close5):
                            cands.append((abs(vals[1] - close5), vals, l, span))
                    if not cands:
                        continue
                    _, vals, l, span = min(cands, key=lambda c: c[0])
                    all_lines.append({"name": f"{TF_NAME[tf]} {side} line {l['n']}",
                                      "colour": SIDE_COLOUR[side], "width": TF_WIDTH[tf],
                                      "dashed": l["broken"], "label": f"{TF_NAME[tf]} L{l['n']}",
                                      "points": [{"time": _epoch(t), "value": v} for t, v in zip(span, vals)]})
            above = sorted([lv for lv in levels if lv["price"] > close5], key=lambda lv: lv["price"])
            below = sorted([lv for lv in levels if lv["price"] <= close5], key=lambda lv: -lv["price"])
            near = above[:COMBINED_HSR_EACH_SIDE] + below[:COMBINED_HSR_EACH_SIDE]
            p = out_dir / f"trendline_draw_all_{date}.html"
            p.write_text(chart_html(f"Nifty 50 5m with every timeframe's trendlines - as of {cutoff:%a %d %b %Y %H:%M}",
                                    five, all_lines, markers, near, focus_last=len(day),
                                    legend_extra="<b>Trend: " + " &middot; ".join(
                                        f"{TF_NAME[t]} {trends[t]}" for t in TFS if t in trends)
                                        + (f" &rarr; trade {TF_NAME[TRADE_TF]}: "
                                           + ("buy puts" if trends.get(TRADE_TF) == "DOWN" else "buy calls")
                                           if TRADE_TF in trends else "") + "</b><br>"
                                        "combined chart: last day, nearest line of each higher "
                                                 "timeframe above (red) and below (green) the close, "
                                                 f"{COMBINED_HSR_EACH_SIDE} nearest horizontal lines each side; "
                                                 "scroll left for the earlier days"), encoding="utf-8")
            out.append(f"Chart 5m + all timeframes: {p}")
    return out


def main() -> None:
    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Trendlines drawn Ash's way on every timeframe (read-only).")
    p.add_argument("--key", default=NIFTY_KEY)
    p.add_argument("--date", default=DEFAULT_DATE, help="YYYY-MM-DD")
    p.add_argument("--at", default=DEFAULT_AT, help="HH:MM cut-off (15:30 = after the close)")
    p.add_argument("--daily-domain", default="indices", help="domain for 1d / 1w / 1mo")
    p.add_argument("--show-live", action="store_true",
                   help="also draw lines whose 2nd point is the last candle (not confirmed yet; hidden by default)")
    args = p.parse_args()

    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])
    report = [command.strip(), f"Trendline draw, run at {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"instrument {args.key}  as of {args.date} {args.at}",
              "Lines: from the extreme of each timeframe's look-back, through wicks, no wick crossing between "
              "the two points; any wick crossing later = break (redrawn from the same extreme); next line starts "
              "where the last one ends."]
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
        report += run(series, args.date, args.at, out_dir, hide_live=not args.show_live)
    except ValueError as exc:
        report.append(f"NOT OK -- {exc}")
    log_path = out_dir / "trendline_draw.log"
    text = "\n".join(report)
    log_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
