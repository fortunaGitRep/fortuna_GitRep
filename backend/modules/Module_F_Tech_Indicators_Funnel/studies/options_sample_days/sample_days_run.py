"""
Runner for the options sample-day study (step 1). Read-only: reads Nifty 50 1d and 5m
through the indicator reader, runs the daily Zig Zag, labels every day from the start
date (default 3 Jan 2022, first stored 5m bar), picks candidates and writes everything to
logs/options_sample_days_logs/:

  day_table.csv           every trading day with all labels (TC-SEL / TC-NB / TC-DATA-02)
  candidates.csv          sample-day candidates; fill the 'keep' column (TC-SEL-07)
  sample_days_report.log  coverage per month / phase / dte, gaps, timing summary
  sample_days_chart.html  daily chart of the window: phase band + candidate markers

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.sample_days_run
  ... --events path/to/event_days.csv    (columns: date, event) -- optional, TC-NB-05
  ... --start 2024-10-01                  trim to the expired-contract window (TC-DATA-01)

Fetches nothing; uses whatever the last OHLCV refresh stored.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
    get_equal_tolerance,
    get_zigzag_settings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import (
    find_zigzag_swings,
)
from modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.sample_days import (
    DEFAULT_START,
    FIRST_TUE_EXPIRY,
    build_day_table,
    coverage_report,
    pick_candidates,
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
LOG_DIR = Path("logs") / "options_sample_days_logs"
logger = logging.getLogger(__name__)

PHASE_COLOURS = {"markup": "#1D9E75", "markdown": "#D85A30",
                 "accumulation": "#378ADD", "distribution": "#BA7517"}


def _read(domain: str, timeframe: str) -> pd.DataFrame:
    res = read_for_indicators(NIFTY_KEY, domain, timeframe)
    if not res.ok:
        raise RuntimeError(f"Nifty {timeframe} read failed: {res.error}")
    return res.df


def run(events_path: str | None = None, start=DEFAULT_START) -> list[str]:
    daily = _read("indices", "1d")
    five = _read("universe_intraday", "5m")

    dev, depth = get_zigzag_settings("1d")
    swings = find_zigzag_swings(daily.rename(columns={"ts": "time"})[["time", "high", "low"]], dev, depth)

    events = None
    if events_path:
        events = pd.read_csv(events_path)
        missing = {"date", "event"} - set(events.columns)
        if missing:
            raise ValueError(f"event file needs columns date, event (missing {sorted(missing)})")

    days = build_day_table(daily, five, swings, get_equal_tolerance("1d"), events, start)
    cands = pick_candidates(days)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    days.to_csv(LOG_DIR / "day_table.csv", index=False)
    cands.to_csv(LOG_DIR / "candidates.csv", index=False)
    _write_chart(daily, days, cands, start, LOG_DIR / "sample_days_chart.html")

    lines = _report(days, cands, events_path, dev, depth, start)
    (LOG_DIR / "sample_days_report.log").write_text("\n".join(lines), encoding="utf-8")
    return lines


def _report(days, cands, events_path, dev, depth, start) -> list[str]:
    strong = days[days["strong"]]
    no5m = days[days["move_timing"] == "no 5m data"]
    lines = [
        "=" * 78,
        "OPTIONS SAMPLE DAYS -- Nifty 50",
        "=" * 78,
        f"window          : {days['trade_date'].min()} .. {days['trade_date'].max()}  "
        f"({len(days)} trading days; start {start})",
        f"expiry eras     : Thursday {int((days['era'] == 'thu').sum())} days, Tuesday "
        f"{int((days['era'] == 'tue').sum())} days (Tuesday expiry from {FIRST_TUE_EXPIRY}; "
        f"dte coverage uses Tuesday era only)",
        f"strong days     : {len(strong)}  (green {int((strong['colour'] == 'green').sum())}, "
        f"red {int((strong['colour'] == 'red').sum())})",
        f"candidates      : {len(cands)}  -> candidates.csv, fill 'keep' (TC-SEL-07)",
        f"phase from      : daily Zig Zag {dev}% / depth {depth}, locked swings only",
        f"days without 5m : {len(no5m)}" + (f"  first: {', '.join(map(str, no5m['trade_date'].head(10)))}"
                                            + (" ..." if len(no5m) > 10 else "") if len(no5m) else ""),
        f"events          : {'from ' + events_path if events_path else 'none given (TC-NB-05 pending)'}",
        "",
    ]
    lines += coverage_report(days, cands)

    lines.append("TC-DATA-02  expiry weeks shifted by a holiday or not yet in the data")
    odd = days[days["holiday_shifted"] | days["expiry_assumed"]].groupby("expiry_date").size()
    for exp, n in odd.items():
        tag = "ASSUMED (beyond data)" if exp > days["trade_date"].max() else "holiday-shifted"
        lines.append(f"   expiry {exp} ({pd.Timestamp(exp).day_name()[:3]})  {n} day(s)  {tag}")
    if odd.empty:
        lines.append("   none")
    lines.append("")

    lines.append("TC-NB-01  move timing on strong days (green / red)")
    for t in ("morning", "all_day", "late", "flat", "no 5m data"):
        g = int(((strong["move_timing"] == t) & (strong["colour"] == "green")).sum())
        r = int(((strong["move_timing"] == t) & (strong["colour"] == "red")).sum())
        lines.append(f"   {t:<11} green {g:>3}   red {r:>3}")
    lines.append("")

    lines.append("TC-NB-04  gap type, all days / strong days")
    for t in ("full_up", "up", "none", "down", "full_down"):
        lines.append(f"   {t:<10} {int((days['gap_type'] == t).sum()):>4} / {int((strong['gap_type'] == t).sum()):>3}")
    lines.append("")

    lines.append("CANDIDATES  (date  wkday era dte colour body phase timing gap | covers)")
    for r in cands.itertuples(index=False):
        lines.append(f"   {r.trade_date} {r.weekday} {r.era} {r.dte} {r.colour:<5} {r.body_ratio:.2f} "
                     f"{_txt(r.phase):<12} {r.move_timing:<8} {_txt(r.gap_type):<9} | {r.covers}")
    return lines


def _txt(v) -> str:
    return "none" if pd.isna(v) else str(v)


def _write_chart(daily, days, cands, start, path: Path) -> None:
    d = daily.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"]).dt.date
    d = d[d["trade_date"] >= start]
    candles = [{"time": str(r.trade_date), "open": r.open, "high": r.high, "low": r.low, "close": r.close}
               for r in d.itertuples(index=False)]
    phase = [{"time": str(r.trade_date), "value": 1,
              "color": PHASE_COLOURS.get(r.phase, "#B4B2A9")} for r in days.itertuples(index=False)]
    markers = [{"time": str(r.trade_date),
                "position": "belowBar" if r.colour == "green" else "aboveBar",
                "color": "#1D9E75" if r.colour == "green" else "#D85A30",
                "shape": "arrowUp" if r.colour == "green" else "arrowDown",
                "text": f"{r.weekday} D{r.dte}" + ("" if r.era == "tue" else " (Thu exp)")}
               for r in cands.itertuples(index=False)]
    path.write_text(_HTML.replace("__START__", f"{start:%d %b %Y}").replace("__CANDLES__", json.dumps(candles))
                         .replace("__PHASE__", json.dumps(phase))
                         .replace("__MARKERS__", json.dumps(markers)), encoding="utf-8")


_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Nifty sample days</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>body{font-family:Arial;margin:12px;background:#fff;color:#222}#c{height:620px}
.k span{display:inline-block;width:12px;height:12px;margin:0 4px 0 14px;vertical-align:middle}</style></head>
<body><b>Nifty 50 daily since __START__</b> &mdash; arrows = sample-day candidates (weekday, D = days to expiry);
bottom band = phase
<div class="k"><span style="background:#1D9E75"></span>markup<span style="background:#D85A30"></span>markdown
<span style="background:#378ADD"></span>accumulation<span style="background:#BA7517"></span>distribution
<span style="background:#B4B2A9"></span>no phase</div><div id="c"></div>
<script>
const chart = LightweightCharts.createChart(document.getElementById('c'), {layout:{background:{color:'#fff'},textColor:'#222'},
  rightPriceScale:{scaleMargins:{top:0.05,bottom:0.12}}, timeScale:{rightOffset:3}});
const s = chart.addCandlestickSeries({upColor:'#1D9E75',downColor:'#D85A30',borderVisible:false,
  wickUpColor:'#1D9E75',wickDownColor:'#D85A30'});
s.setData(__CANDLES__); s.setMarkers(__MARKERS__);
const p = chart.addHistogramSeries({priceScaleId:'phase',priceLineVisible:false,lastValueVisible:false});
chart.priceScale('phase').applyOptions({scaleMargins:{top:0.92,bottom:0}});
p.setData(__PHASE__); chart.timeScale().fitContent();
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Options sample-day study, step 1")
    ap.add_argument("--events", help="CSV with columns date, event (optional)")
    ap.add_argument("--start", type=lambda v: pd.Timestamp(v).date(), default=DEFAULT_START,
                    help=f"first day of the window, YYYY-MM-DD (default {DEFAULT_START})")
    args = ap.parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "sample_days_run.log", mode="w", encoding="utf-8")])
    try:
        lines = run(args.events, args.start)
    except Exception:
        logger.exception("Sample-day run failed")
        return 1
    print("\n".join(lines))
    logger.info("Wrote day_table.csv, candidates.csv, sample_days_report.log, sample_days_chart.html to %s", LOG_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
