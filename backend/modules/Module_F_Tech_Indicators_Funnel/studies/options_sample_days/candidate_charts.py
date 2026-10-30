"""
HTML charts for the sample-day candidates, from the expired-contract archive (test plan
TC-DATA-07, TC-DATA-08, TC-SEL-07). Reads candidate_contracts.csv, R2 and Nifty data;
no Upstox calls.

One page per candidate day, four panes on one time axis, from the start of the contract's
expiry week (week_start) to the candidate day:
  Nifty 5m  |  CE (ITM2 / ATM / OTM2, default OTM2)  |  PE (same)  |  near-month futures
  timeframe 5m (default) / 15m / 1m (1m = candidate day only; Nifty has no 1m, stays 5m)
  arrows at 09:30 and 11:30 on the candidate day; legend shows O H L C (+ volume, OI) under the cursor
Plus index.html linking every day with its labels.

Run from backend/ after candidate_contracts:
  python -m modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.candidate_charts
  ... --day 2026-10-13        one day only
Output: logs/options_candidate_charts/index.html and <date>.html
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from modules.market_data.upstox.expired_archive_reader import read_part, to_bars
from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.candidate_contracts import (
    LEGS,
    NIFTY_KEY,
    OUT_DIR,
)

IST_OFFSET = 19800                    # chart library shows UTC; shift so the axis reads IST
LABEL_COLS = ("weekday", "era", "dte", "colour", "body_ratio", "phase", "move_timing", "gap_type",
              "window_move_pts", "covers")
logger = logging.getLogger(__name__)


def _epoch(ts: pd.Series) -> pd.Series:
    t = pd.to_datetime(ts)
    t = t.dt.tz_localize("Asia/Kolkata") if t.dt.tz is None else t
    secs = (t.dt.tz_convert("UTC") - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)
    return (secs + IST_OFFSET).astype(int)            # unit-safe (ns or us storage)


def _rows(df: pd.DataFrame, extra: bool) -> list[list]:
    if df is None or df.empty:
        return []
    cols = ["open", "high", "low", "close"] + (["volume", "oi"] if extra else [])
    d = df.sort_values("ts")
    out = pd.concat([_epoch(d["ts"]).rename("t"), d[cols].astype(float).round(2)], axis=1)
    return out.values.tolist()


def contract_series(part_df: pd.DataFrame, strike: float, typ: str, start: date, day: date) -> dict:
    c = part_df[(part_df["strike"] == strike) & (part_df["option_type"] == typ)] if typ != "FUT" else part_df
    c = c[(c["trade_date"] >= start) & (c["trade_date"] <= day)]
    sym = str(c["trading_symbol"].iloc[0]) if len(c) else f"{int(strike)} {typ}"
    return {"label": sym, "b5": _rows(to_bars(c, 5), True), "b1": _rows(c[c["trade_date"] == day], True)}


def page_data(row: pd.Series, nifty5: pd.DataFrame) -> dict:
    day, start = row["trade_date"], row["week_start"]
    n = nifty5[(nifty5["trade_date"] >= start) & (nifty5["trade_date"] <= day)]
    data = {"day": str(day), "nifty": _rows(n, False), "legs": {}, "fut": None}
    band = read_part("band", row["expiry"]) if pd.notna(row.get("expiry")) else pd.DataFrame()
    if not band.empty and pd.notna(row.get("atm")):
        for leg in LEGS:
            data["legs"][leg] = contract_series(band, float(row[leg]), leg[:2].upper(), start, day)
    if pd.notna(row.get("futures_expiry")):
        fut = read_part("futures", row["futures_expiry"])
        if not fut.empty:
            data["fut"] = contract_series(fut, 0, "FUT", start, day)
    return data


def _labels(row: pd.Series) -> str:
    parts = [f"<b>{row['trade_date']}</b>"]
    for c in LABEL_COLS:
        if c in row and pd.notna(row[c]) and str(row[c]) != "":
            v = row[c]
            v = f"{v:.2f}" if isinstance(v, float) and c == "body_ratio" else (f"{v:+.0f}" if c == "window_move_pts" else v)
            parts.append(f"{c}: <b>{html.escape(str(v))}</b>")
    parts.append(f"expiry <b>{row.get('expiry')}</b> (week from {row.get('week_start')}), ATM <b>{row.get('atm', '-')}</b>, "
                 f"futures <b>{row.get('futures_expiry', '-')}</b>")
    if isinstance(row.get("flags"), str) and row["flags"]:
        parts.append(f"<span class='flag'>{html.escape(row['flags'])}</span>")
    return " &nbsp;|&nbsp; ".join(parts)


def write_page(row: pd.Series, data: dict, path: Path, prev_next: tuple) -> None:
    nav = " ".join(f"<a href='{d}.html'>{lbl}</a>" for d, lbl in zip(prev_next, ("&larr; prev", "next &rarr;")) if d)
    path.write_text(PAGE.replace("__TITLE__", f"Nifty options {data['day']}")
                        .replace("__LABELS__", _labels(row))
                        .replace("__NAV__", f"<a href='index.html'>index</a> {nav}")
                        .replace("__DATA__", json.dumps(data, separators=(",", ":"))), encoding="utf-8")


def write_index(table: pd.DataFrame, path: Path) -> None:
    cols = ["trade_date", *[c for c in LABEL_COLS if c in table.columns], "expiry", "atm", "flags"]
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = []
    for r in table.itertuples(index=False):
        rd = r._asdict()
        cells = []
        for c in cols:
            v = rd.get(c, "")
            v = "" if pd.isna(v) else (f"{v:.2f}" if isinstance(v, float) and c == "body_ratio" else v)
            v = f"<a href='{rd['trade_date']}.html'>{v}</a>" if c == "trade_date" else html.escape(str(v))
            cells.append(f"<td class='{c} {html.escape(str(rd.get('colour', '')))}'>{v}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    path.write_text(INDEX.replace("__HEAD__", head).replace("__BODY__", "\n".join(body))
                         .replace("__N__", str(len(table))), encoding="utf-8")


def run(only: date | None) -> list[str]:
    table = pd.read_csv(OUT_DIR / "candidate_contracts.csv")
    for c in ("trade_date", "expiry", "week_start", "futures_expiry"):
        table[c] = pd.to_datetime(table[c]).dt.date
    table = table.sort_values("trade_date").reset_index(drop=True)
    n5 = read_for_indicators(NIFTY_KEY, "universe_intraday", "5m")
    if not n5.ok:
        raise RuntimeError(f"Nifty 5m read failed: {n5.error}")
    nifty5 = n5.df.assign(trade_date=pd.to_datetime(n5.df["trade_date"]).dt.date)
    days = list(table["trade_date"])
    written = []
    for i, row in table.iterrows():
        if only and row["trade_date"] != only:
            continue
        nav = (days[i - 1] if i else None, days[i + 1] if i + 1 < len(days) else None)
        write_page(row, page_data(row, nifty5), OUT_DIR / f"{row['trade_date']}.html", nav)
        written.append(row["trade_date"])
        logger.info("chart %s written", row["trade_date"])
    write_index(table, OUT_DIR / "index.html")
    return [f"charts written: {len(written)} -> {OUT_DIR}", f"open {OUT_DIR / 'index.html'} in a browser"]


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
body{font-family:Arial,sans-serif;margin:10px;background:#fff;color:#222;font-size:13px}
.lab{line-height:1.7}.flag{color:#A32D2D;font-weight:bold}
.bar{margin:8px 0;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.bar button{padding:3px 10px;border:1px solid #bbb;background:#f6f6f6;border-radius:4px;cursor:pointer}
.bar button.on{background:#083F41;color:#fff;border-color:#083F41}
.pane{position:relative;height:220px;border-top:1px solid #eee}
.leg{position:absolute;left:6px;top:4px;z-index:3;font-size:12px;background:rgba(255,255,255,.85);padding:1px 4px}
.note{color:#777}
</style></head><body>
<div>__NAV__</div><div class="lab">__LABELS__</div>
<div class="bar">
 <span>Timeframe <button data-tf="5" class="on">5m</button><button data-tf="15">15m</button><button data-tf="1">1m (day only)</button></span>
 <span>CE <select id="ce"><option value="ce_itm2">ITM2</option><option value="ce_atm">ATM</option><option value="ce_otm2" selected>OTM2</option></select></span>
 <span>PE <select id="pe"><option value="pe_itm2">ITM2</option><option value="pe_atm">ATM</option><option value="pe_otm2" selected>OTM2</option></select></span>
 <span class="note">arrows = 09:30 and 11:30 on the candidate day; scroll/zoom any pane, all follow</span>
</div>
<div class="pane" id="p0"><div class="leg" id="l0"></div></div>
<div class="pane" id="p1"><div class="leg" id="l1"></div></div>
<div class="pane" id="p2"><div class="leg" id="l2"></div></div>
<div class="pane" id="p3"><div class="leg" id="l3"></div></div>
<script>
const D=__DATA__, dayStart=Date.parse(D.day+"T00:00:00Z")/1000;
let tf=5;
const UP='#1D9E75', DN='#D85A30';
const charts=[], series=[], names=['Nifty 50 (5m)','','','Futures'];
for(let i=0;i<4;i++){
  const el=document.getElementById('p'+i);
  const c=LightweightCharts.createChart(el,{height:220,layout:{background:{color:'#fff'},textColor:'#222'},
    timeScale:{timeVisible:true,secondsVisible:false,rightOffset:4},rightPriceScale:{scaleMargins:{top:.12,bottom:.06},minimumWidth:90},
    crosshair:{mode:0}});
  const s=c.addCandlestickSeries({upColor:UP,downColor:DN,borderVisible:false,wickUpColor:UP,wickDownColor:DN});
  charts.push(c); series.push(s);
}
function agg(rows,mins){
  if(mins<=5) return rows;
  const out=[]; let cur=null, k=null;
  for(const r of rows){ const b=Math.floor(r[0]/(mins*60))*mins*60;
    if(b!==k){ if(cur) out.push(cur); k=b; cur=[b,r[1],r[2],r[3],r[4],r[5]||0,r[6]]; }
    else { cur[2]=Math.max(cur[2],r[2]); cur[3]=Math.min(cur[3],r[3]); cur[4]=r[4]; cur[5]+=(r[5]||0); cur[6]=r[6]; } }
  if(cur) out.push(cur); return out;
}
function pick(obj){ if(!obj) return []; return tf===1 ? obj.b1 : agg(obj.b5, tf); }
function toBars(rows){ return rows.map(r=>({time:r[0],open:r[1],high:r[2],low:r[3],close:r[4]})); }
function marks(rows){
  const m=[]; for(const [hh,mm,txt] of [[9,30,'09:30'],[11,30,'11:30']]){
    const t=dayStart+hh*3600+mm*60; const r=rows.find(x=>x[0]>=t);
    if(r) m.push({time:r[0],position:'aboveBar',color:'#534AB7',shape:'arrowDown',text:txt}); }
  return m;
}
const cache=[[],[],[],[]];
function draw(){
  const ce=document.getElementById('ce').value, pe=document.getElementById('pe').value;
  const nif = tf===1 ? D.nifty.filter(r=>r[0]>=dayStart) : agg(D.nifty, tf);
  const sets=[nif, pick(D.legs[ce]), pick(D.legs[pe]), pick(D.fut)];
  names[1]=(D.legs[ce]||{label:'CE: no data'}).label; names[2]=(D.legs[pe]||{label:'PE: no data'}).label;
  names[3]='Futures '+((D.fut||{label:'no data'}).label);
  sets.forEach((rows,i)=>{ cache[i]=rows; series[i].setData(toBars(rows)); series[i].setMarkers(marks(rows));
    legend(i,null); });
  charts.forEach(c=>c.timeScale().fitContent());
}
function legend(i,t){
  const rows=cache[i]; let r=null;
  if(t!==null){ for(const x of rows){ if(x[0]<=t) r=x; else break; } } if(!r) r=rows[rows.length-1];
  const tag=(i===0&&tf===1)?' (5m: no 1m for Nifty)':'';
  document.getElementById('l'+i).innerHTML='<b>'+names[i]+'</b>'+tag+(r?
    ` &nbsp;O ${r[1]} H ${r[2]} L ${r[3]} C ${r[4]}`+(r.length>5?` &nbsp;Vol ${r[5]} OI ${r[6]}`:''):' &nbsp;no data');
}
let syncing=false;
charts.forEach((c,i)=>{
  c.timeScale().subscribeVisibleTimeRangeChange(r=>{ if(syncing||!r) return; syncing=true;
    charts.forEach((o,j)=>{ if(j!==i){ try{o.timeScale().setVisibleRange(r);}catch(e){} } }); syncing=false; });
  c.subscribeCrosshairMove(p=>{ const t=p&&p.time!==undefined?p.time:null; for(let j=0;j<4;j++) legend(j,t); });
});
document.querySelectorAll('[data-tf]').forEach(b=>b.onclick=()=>{ tf=+b.dataset.tf;
  document.querySelectorAll('[data-tf]').forEach(x=>x.classList.toggle('on',x===b)); draw(); });
document.getElementById('ce').onchange=draw; document.getElementById('pe').onchange=draw;
draw();
</script></body></html>"""

INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>Candidate charts</title>
<style>body{font-family:Arial,sans-serif;margin:12px;font-size:13px}table{border-collapse:collapse}
th,td{border:1px solid #ddd;padding:3px 7px;text-align:left}th{background:#083F41;color:#fff;position:sticky;top:0}
td.colour.green{color:#0F6E56;font-weight:bold}td.colour.red{color:#A32D2D;font-weight:bold}td.flags{color:#A32D2D}
tr:hover{background:#f4f4f4}</style></head><body>
<h3>Sample-day candidates (__N__) &mdash; click a date for its chart</h3>
<table><tr>__HEAD__</tr>
__BODY__
</table></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HTML charts for sample-day candidates")
    ap.add_argument("--day", type=lambda v: date.fromisoformat(v), help="one day only")
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    try:
        lines = run(args.day)
    except Exception:
        logger.exception("Charts failed")
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
