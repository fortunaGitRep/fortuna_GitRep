"""
Runner for Fortuna Predictor step A (read-only): builds the day table and the day viewer.

Reads Nifty 1d and 5m through the indicator reader and every stored near-month futures file
from the expired-contract archive. Fetches nothing.

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.predictor_days_run
  ... --start 2024-09-27     (default: the archive's first week)
Output (logs/predictor_days_logs/):
  predictor_days.csv        one row per trading day
  predictor_days.html       day viewer: one page, all days -- Nifty 5m with the first hour,
                            futures volume, the day's numbers; prev / next / date picker / arrow keys
  predictor_days.log        every stage as it runs (+ screen), summary, futures volume parity list
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time as clock
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.predictor_days import (
    build_predictor_days, futures_volume, intraday_measures, near_month, ordered, to_5m,
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
DEFAULT_START = date(2024, 9, 27)
LOG_DIR = Path("logs") / "predictor_days_logs"
IST_OFFSET = 19800
STAGES = 7
PARITY_DAYS = [(date(2025, 1, 2), "09:30"), (date(2026, 2, 24), "09:30"), (date(2026, 2, 24), "11:40")]
KEY_COLUMNS = ["ib_width", "ib_width_x", "ext_up_pts", "h1_0915", "first30_pts", "fut_vol_day", "fut_vol_day_x"]
logger = logging.getLogger(__name__)


class Stage:
    """Logs '[n/7] what ...' at the start and '... done in Xs' at the end of each stage."""
    def __init__(self, n: int, what: str):
        self.n, self.what = n, what

    def __enter__(self):
        self.t0 = clock.monotonic()
        logger.info("[%d/%d] %s ...", self.n, STAGES, self.what)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            logger.info("[%d/%d] %s -- done in %.1fs", self.n, STAGES, self.what, clock.monotonic() - self.t0)


def _read(domain: str, timeframe: str) -> pd.DataFrame:
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
    res = read_for_indicators(NIFTY_KEY, domain, timeframe)
    if not res.ok:
        raise RuntimeError(f"Nifty {timeframe} read failed: {res.error}")
    return res.df


def run(start: date) -> list[str]:
    from modules.market_data.upstox.expired_archive_reader import read_part, stored_expiries
    from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
        get_equal_tolerance, get_zigzag_settings)
    from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import find_zigzag_swings
    from modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.sample_days import build_day_table

    logger.info("Predictor days, step A -- study window from %s", start)
    with Stage(1, "reading Nifty 1d and 5m (indicator reader)"):
        daily, five = _read("indices", "1d"), _read("universe_intraday", "5m")
        logger.info("      1d: %d candles, 5m: %d bars (last %s)", len(daily), len(five), five["ts"].max())

    with Stage(2, "sample-day table (candle, gap, expiry, phase, day move) from sample_days.py"):
        dev, depth = get_zigzag_settings("1d")
        swings = find_zigzag_swings(daily.rename(columns={"ts": "time"})[["time", "high", "low"]], dev, depth)
        days = build_day_table(daily, five, swings, get_equal_tolerance("1d"), None, start)
        logger.info("      %d trading days %s .. %s", len(days), days["trade_date"].min(), days["trade_date"].max())

    with Stage(3, "first hour, extension, hour blocks, first 30 min (every day of Nifty 5m)"):
        dl = daily.assign(trade_date=pd.to_datetime(daily["trade_date"]).dt.date).sort_values("trade_date")
        prev_close = dict(zip(dl["trade_date"], dl["close"].shift(1)))
        step = 100

        def progress(i, n, d):
            if i % step == 0 or i == n:
                logger.info("      %d / %d days (at %s)", i, n, d)
        intra = intraday_measures(five, prev_close, progress)

    with Stage(4, "near-month futures, 1m, from the archive"):
        exps = list(stored_expiries("futures"))
        frames = []
        for k, e in enumerate(exps, 1):
            f = read_part("futures", e)
            frames.append(f)
            logger.info("      futures %2d / %d  expiry %s: %s rows", k, len(exps), e, f"{len(f):,}")
        fut = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        futvol = futures_volume(fut, exps)
        logger.info("      near-month volume on %d days", len(futvol))

    with Stage(5, "combining, 20-day averages, narrow-range flags"):
        table = ordered(build_predictor_days(days, daily, intra, futvol, start))
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        table.to_csv(LOG_DIR / "predictor_days.csv", index=False)
        logger.info("      wrote %s (%d rows, %d columns)", LOG_DIR / "predictor_days.csv", len(table), table.shape[1])

    with Stage(6, "day viewer page"):
        viewer = viewer_data(table, five, fut, exps, start)
        (LOG_DIR / "predictor_days.html").write_text(
            PAGE.replace("__DATA__", json.dumps(viewer, separators=(",", ":"))), encoding="utf-8")
        logger.info("      wrote %s (%d days)", LOG_DIR / "predictor_days.html", len(viewer["days"]))

    with Stage(7, "summary and futures volume parity list"):
        lines = summary(table) + parity_lines(fut, exps)
    return lines


# ----------------------------------------------------------------------------- viewer
def _epoch(ts: pd.Series) -> pd.Series:
    t = pd.to_datetime(ts)
    t = t.dt.tz_localize("Asia/Kolkata") if t.dt.tz is None else t
    return ((t.dt.tz_convert("UTC") - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1) + IST_OFFSET).astype(int)


def _clean(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.floating, float)):
        return round(float(v), 2)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    return str(v)


def viewer_data(table: pd.DataFrame, five: pd.DataFrame, fut: pd.DataFrame, exps: list, start: date) -> dict:
    n = five.assign(trade_date=pd.to_datetime(five["trade_date"]).dt.date)
    n = n[n["trade_date"] >= start].sort_values("ts")
    n["e"] = _epoch(n["ts"])
    bars = {d: g[["e", "open", "high", "low", "close"]].round(2).values.tolist() for d, g in n.groupby("trade_date")}
    vols = {}
    if len(fut):
        f = fut.assign(trade_date=pd.to_datetime(fut["trade_date"]).dt.date, ts=pd.to_datetime(fut["ts"]),
                       expiry=pd.to_datetime(fut["expiry"]).dt.date)
        f = f[f["trade_date"] >= start]
        f = to_5m(f[f["expiry"] == f["trade_date"].map(lambda d: near_month(d, exps))])
        f["e"] = _epoch(f["ts"])
        vols = {d: g[["e", "volume"]].values.tolist() for d, g in f.groupby("trade_date")}
    days = []
    for r in table.to_dict("records"):
        d = r["trade_date"]
        days.append({"day": str(d), "row": {k: _clean(v) for k, v in r.items() if k != "trade_date"},
                     "bars": bars.get(d, []), "vol": vols.get(d, [])})
    return {"days": days}


# ----------------------------------------------------------------------------- summary
def summary(t: pd.DataFrame) -> list[str]:
    lines = ["=" * 78, "PREDICTOR DAYS -- step A", "=" * 78,
             f"days            : {len(t)}  ({t['trade_date'].min()} .. {t['trade_date'].max()})",
             f"columns         : {t.shape[1]}"]
    for c in KEY_COLUMNS:
        if c in t.columns:
            blank = t[t[c].isna()]["trade_date"].astype(str).tolist()
            lines.append(f"blank {c:<14}: {len(blank):>3}" + (f"  e.g. {', '.join(blank[:5])}" if blank else ""))
    if "first_break" in t.columns:
        lines.append("first break of the first hour: " + ", ".join(
            f"{k} {v}" for k, v in t["first_break"].replace("", "n/a").value_counts().items()))
    lines.append("(20-day averages are blank for the first 20 days of available history; first hour blank on "
                 "evening-only sessions)")
    return lines


def parity_lines(fut: pd.DataFrame, exps: list) -> list[str]:
    """Futures 5m volume at a few exact candles, to compare with the Nifty futures chart on Dhan."""
    lines = ["", "FUTURES VOLUME PARITY -- compare with the near-month NIFTY FUT chart on Dhan, 5m"]
    if fut.empty:
        return lines + ["   no futures stored"]
    f = fut.assign(trade_date=pd.to_datetime(fut["trade_date"]).dt.date, ts=pd.to_datetime(fut["ts"]),
                   expiry=pd.to_datetime(fut["expiry"]).dt.date)
    for d, hhmm in PARITY_DAYS:
        e = near_month(d, exps)
        c = f[(f["trade_date"] == d) & (f["expiry"] == e)]
        b = c[c["ts"].dt.floor("5min").dt.strftime("%H:%M") == hhmm]
        if b.empty:
            lines.append(f"   {pd.Timestamp(d):%a %d %b %Y} {hhmm} 5m: no bars stored")
            continue
        lot = float(c["lot_size"].dropna().iloc[0]) if c["lot_size"].notna().any() else np.nan
        vol = float(b["volume"].sum())
        o, h, l, cl = float(b["open"].iloc[0]), float(b["high"].max()), float(b["low"].min()), float(b["close"].iloc[-1])
        sym = str(c["trading_symbol"].iloc[0]) if "trading_symbol" in c else str(e)
        lines.append(f"   {pd.Timestamp(d):%a %d %b %Y} {hhmm} 5m  {sym}: O {o:.2f} H {h:.2f} L {l:.2f} C {cl:.2f}  "
                     f"volume {vol:,.0f} units = {vol / lot:,.0f} lots (lot {lot:.0f})")
    return lines


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Predictor days</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
body{font-family:Arial,sans-serif;margin:10px;background:#fff;color:#222;font-size:13px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.bar button{padding:3px 10px;border:1px solid #bbb;background:#f6f6f6;border-radius:4px;cursor:pointer}
#title{font-size:15px;font-weight:bold}.g{color:#0F6E56}.r{color:#A32D2D}
.pane{position:relative;border-top:1px solid #eee}.leg{position:absolute;left:6px;top:4px;z-index:3;font-size:12px;background:rgba(255,255,255,.85);padding:1px 4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin-top:10px}
.card{border:1px solid #e3e3e3;border-radius:6px;padding:6px 8px}.card h4{margin:0 0 4px;font-size:12px;color:#555}
.card table{width:100%;border-collapse:collapse}.card td{padding:1px 2px}.card td:last-child{text-align:right}
.blocks{display:flex;gap:4px;margin-top:4px}.blocks div{flex:1;text-align:center;font-size:11px;padding:3px 0;border-radius:3px}
</style></head><body>
<div class="bar"><button id="prev">&larr; prev</button><select id="pick"></select><button id="next">next &rarr;</button>
<span id="title"></span><span style="color:#777">arrow keys also move; blue dashed lines = first hour (09:15–10:15) high / low</span></div>
<div class="pane" id="p0" style="height:360px"><div class="leg" id="l0"></div></div>
<div class="pane" id="p1" style="height:130px"><div class="leg" id="l1">Near-month futures volume (5m, units)</div></div>
<div class="cards" id="cards"></div>
<script>
const D=__DATA__, UP='#1D9E75', DN='#D85A30';
const mk=(el,h)=>LightweightCharts.createChart(document.getElementById(el),{height:h,layout:{background:{color:'#fff'},textColor:'#222'},
  timeScale:{timeVisible:true,secondsVisible:false},rightPriceScale:{minimumWidth:90},crosshair:{mode:0}});
const c0=mk('p0',360), c1=mk('p1',130);
const cs=c0.addCandlestickSeries({upColor:UP,downColor:DN,borderVisible:false,wickUpColor:UP,wickDownColor:DN});
const vs=c1.addHistogramSeries({color:'#85B7EB',priceFormat:{type:'volume'}});
let lines=[], i=D.days.length-1, cur=[];
const pick=document.getElementById('pick');
D.days.forEach((d,k)=>{const o=document.createElement('option');o.value=k;
  const w=new Date(d.day+'T00:00:00Z').toUTCString().slice(0,3);o.textContent=w+' '+d.day;pick.appendChild(o);});
const f=(v,n=2)=>v===null||v===undefined?'–':typeof v==='boolean'?(v?'yes':'no'):(typeof v==='number'?v.toLocaleString('en-IN',{maximumFractionDigits:n}):v);
function card(t,rows){return '<div class="card"><h4>'+t+'</h4><table>'+rows.map(([a,b])=>'<tr><td>'+a+'</td><td>'+b+'</td></tr>').join('')+'</table></div>';}
function show(k){
  i=Math.max(0,Math.min(D.days.length-1,k)); pick.value=i; const d=D.days[i], r=d.row;
  cur=d.bars; cs.setData(d.bars.map(b=>({time:b[0],open:b[1],high:b[2],low:b[3],close:b[4]})));
  vs.setData(d.vol.map(v=>({time:v[0],value:v[1]})));
  lines.forEach(l=>cs.removePriceLine(l)); lines=[];
  if(r.ib_high!==null){ lines.push(cs.createPriceLine({price:r.ib_high,color:'#378ADD',lineStyle:2,lineWidth:1,title:'first hour high'}));
    lines.push(cs.createPriceLine({price:r.ib_low,color:'#378ADD',lineStyle:2,lineWidth:1,title:'first hour low'})); }
  const t0=d.bars.length?d.bars[0][0]:0; const end=d.bars.find(b=>b[0]>=t0+3600);
  cs.setMarkers(end?[{time:end[0],position:'aboveBar',color:'#378ADD',shape:'arrowDown',text:'10:15'}]:[]);
  c0.timeScale().fitContent(); c1.timeScale().fitContent();
  const cl=r.colour==='green'?'g':(r.colour==='red'?'r':'');
  document.getElementById('title').innerHTML=r.weekday+' '+d.day+' &nbsp;<span class="'+cl+'">'+f(r.day_move_pts)+' pts ('+f(r.move_pct)+'%)</span> &nbsp;range '+f(r.day_range_pts)+' &nbsp;DTE '+f(r.dte)+(r.dte===0?' (expiry)':'');
  const blk=['h1_0915','h2_1015','h3_1115','h4_1215','h5_1315','h6_1415'], nm=['09:15','10:15','11:15','12:15','13:15','14:15'];
  const blocks='<div class="blocks">'+blk.map((b,j)=>{const v=r[b];const bg=v===null?'#eee':(v>=0?'#E1F5EE':'#FAECE7');const fg=v===null?'#777':(v>=0?'#085041':'#712B13');
    return '<div style="background:'+bg+';color:'+fg+'">'+nm[j]+'<br>'+f(v,0)+'</div>';}).join('')+'</div>';
  document.getElementById('cards').innerHTML=
    card('Day',[['Open / close',f(r.open)+' / '+f(r.close)],['High / low',f(r.high)+' / '+f(r.low)],['Gap',f(r.gap_pct)+'% '+f(r.gap_type)],['Phase',f(r.phase)+' ('+f(r.phase_basis)+')'],['Strong',f(r.strong)+', body '+f(r.body_ratio)]])+
    card('First hour 09:15–10:15',[['High / low',f(r.ib_high)+' / '+f(r.ib_low)],['Width',f(r.ib_width)+' pts'],['vs 20-day avg',f(r.ib_width_x)+'× (avg '+f(r.ib_width_avg20,0)+')'],['First break',f(r.first_break)+' '+f(r.first_break_time)],['Extension up / down',f(r.ext_up_pts,0)+' ('+f(r.ext_up_x)+'×) / '+f(r.ext_down_pts,0)+' ('+f(r.ext_down_x)+'×)']])+
    card('Early clues',[['First 30 min vs prev close',f(r.first30_pts)+' ('+f(r.first30_pct)+'%)'],['Prev day narrowest of 4 / 7',f(r.prev_nr4)+' / '+f(r.prev_nr7)],['09:30–11:30 move / run',f(r.window_move_pts)+' / '+f(r.window_run_pts)],['Timing',f(r.move_timing)+' ('+f(r.share_by_1130)+' by 11:30)']])+
    card('Futures volume (near month '+f(r.fut_expiry)+')',[['Day',f(r.fut_vol_day,0)+' units = '+f(r.fut_vol_day_lots,0)+' lots ('+f(r.fut_vol_day_x)+'× avg)'],['First hour',f(r.fut_vol_ib,0)+' units = '+f(r.fut_vol_ib_lots,0)+' lots ('+f(r.fut_vol_ib_x)+'× avg)'],['Lot size',f(r.fut_lot_size,0)],['<span style="color:#A32D2D">Note</span>','<span style="color:#A32D2D">lots changed 25 → 75 → 65; compare units or × avg, not lots</span>']])+
    '<div class="card" style="grid-column:1/-1"><h4>Nifty move per hour block (points)</h4>'+blocks+'</div>';
  legend(null);
}
function legend(t){ let b=null; if(t!==null){for(const x of cur){if(x[0]<=t)b=x;else break;}} if(!b)b=cur[cur.length-1];
  document.getElementById('l0').innerHTML='<b>Nifty 50 5m</b>'+(b?' &nbsp;O '+b[1]+' H '+b[2]+' L '+b[3]+' C '+b[4]:''); }
c0.subscribeCrosshairMove(p=>legend(p&&p.time!==undefined?p.time:null));
let sy=false; [[c0,c1],[c1,c0]].forEach(([a,b])=>a.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(sy||!r)return;sy=true;b.timeScale().setVisibleLogicalRange(r);sy=false;}));
document.getElementById('prev').onclick=()=>show(i-1); document.getElementById('next').onclick=()=>show(i+1);
pick.onchange=()=>show(+pick.value); document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(i-1);if(e.key==='ArrowRight')show(i+1);});
show(i);
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fortuna Predictor step A: day table + day viewer")
    ap.add_argument("--start", type=lambda v: date.fromisoformat(v), default=DEFAULT_START,
                    help=f"first study day (default {DEFAULT_START}, the archive's first week)")
    args = ap.parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "predictor_days.log", mode="w", encoding="utf-8")])
    t0 = clock.monotonic()
    try:
        lines = run(args.start)
    except Exception:
        logger.exception("Predictor days run FAILED -- the last '[n/7]' line above shows the stage")
        return 1
    for line in lines:
        logger.info(line)
    logger.info("finished in %.1fs", clock.monotonic() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
