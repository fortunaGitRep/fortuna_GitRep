"""
Contract pick study, step 2: on one day, compare the 9 option contracts from ITM 4 to OTM 4
(CE or PE) bought at 09:30, to find which contract to always trade.

Per contract (1m bars from the expired-contract archive, lot size from the contract record):
  entry            premium at 09:30 = open of the 09:30 bar (next bar if 09:30 has none)
  lot cost         entry x lot size;  lots with the capital (default Rs 1,00,000) + cash left
  high             highest premium from 09:30 up to the 15:10 exit, and its time
  11:30 / 15:10    premium at 11:30 and at 15:10 (close of the last bar before that time)
  move             high - entry, points and %
  profit           with the capital's lots, at the high, at 11:30 and at 15:10 (before charges)
  dip              deepest low below entry before the high, points and %
  Greeks 09:30     delta, theta, IV (stored Greeks, computed on the 09:30 bar's close)
  volume / OI      at the 09:30 bar, in lots (Upstox volume and OI are in units)

Chart: Nifty 5m on top, then one pane per contract with real premium candles, 1m or 5m (5m
default, Ash's trading chart), and the session VWAP of the shown timeframe -- TradingView /
Dhan "VWAP hlc3 Session": sum((high+low+close)/3 x volume) / sum(volume), from the day's first
bar. Nifty has no index volume, so no VWAP on the Nifty pane.

ATM = strike nearest Nifty at 09:30 (open of the 09:30 5m bar). CE: ITM k = ATM - k strikes,
OTM k = ATM + k strikes. PE: the mirror.

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.studies.options_contract_pick.contract_pick --day 2025-01-02
  ... --side PE   ... --capital 100000
Reads R2 and Nifty data only; no Upstox calls.
Output: logs/options_contract_pick_logs/contract_pick_<day>_<side>.html (chart + table),
        contract_pick_<day>_<side>.csv, contract_pick.log
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import math
import sys
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

NIFTY_KEY = "NSE_INDEX|Nifty 50"
STRIKE_STEP = 50
STRIKES_EACH_SIDE = 4
ENTRY_TIME = time(9, 30)
MID_TIME = time(11, 30)
EXIT_TIME = time(15, 10)                 # broker auto square-off
DEFAULT_CAPITAL = 100_000.0
IST_OFFSET = 19800                       # chart library shows UTC; shift so the axis reads IST
LOG_DIR = Path("logs") / "options_contract_pick_logs"
logger = logging.getLogger(__name__)

TABLE_COLUMNS = [
    "position", "strike", "symbol", "entry_0930", "lot_size", "lot_cost", "lots", "cash_left",
    "high", "high_time", "move_pts", "move_pct", "p_1130", "p_1510",
    "profit_high", "profit_1130", "profit_1510", "dip_pts", "dip_pct",
    "delta_0930", "theta_0930", "iv_0930", "volume_0930_lots", "oi_0930_lots",
]


# ----------------------------------------------------------------------------- pure helpers
def atm_strike(nifty_price: float) -> float:
    return float(round(nifty_price / STRIKE_STEP) * STRIKE_STEP)


def ladder(atm: float, side: str, n: int = STRIKES_EACH_SIDE) -> list[tuple[str, float]]:
    """(position, strike) from ITM n to OTM n. CE: ITM below ATM; PE: ITM above ATM."""
    sign = 1 if side == "CE" else -1
    out = []
    for k in range(-n, n + 1):
        pos = "ATM" if k == 0 else (f"ITM {-k}" if k < 0 else f"OTM {k}")
        out.append((pos, atm + sign * k * STRIKE_STEP))
    return out


def _price_before(bars: pd.DataFrame, t: time) -> float:
    """Close of the last bar starting before t (the price at t)."""
    b = bars[bars["t"] < t]
    return float(b["close"].iloc[-1]) if len(b) else np.nan


def contract_stats(bars: pd.DataFrame, lot_size: float | None, capital: float = DEFAULT_CAPITAL) -> dict:
    """
    bars: one contract, one day, 1m: ts, open, high, low, close, volume, oi (any order).
    Returns the table fields (Greeks excluded). Blank (NaN) where the data cannot give a value.
    """
    b = bars.copy()
    b["t"] = pd.to_datetime(b["ts"]).dt.time
    b = b.sort_values("ts")
    trade = b[(b["t"] >= ENTRY_TIME) & (b["t"] < EXIT_TIME)]
    out = {c: np.nan for c in TABLE_COLUMNS if c not in ("position", "strike", "symbol")}
    out["high_time"] = out["entry_time"] = ""
    if trade.empty:
        return out
    first = trade.iloc[0]
    entry = float(first["open"])
    out["entry_0930"], out["entry_time"] = entry, first["t"].strftime("%H:%M")
    hi_idx = trade["high"].idxmax()
    high = float(trade.loc[hi_idx, "high"])
    out["high"], out["high_time"] = high, trade.loc[hi_idx, "t"].strftime("%H:%M")
    out["move_pts"] = high - entry
    out["move_pct"] = 100.0 * (high - entry) / entry
    before_high = trade.loc[:hi_idx]
    dip = max(0.0, entry - float(before_high["low"].min()))
    out["dip_pts"], out["dip_pct"] = dip, 100.0 * dip / entry
    out["p_1130"], out["p_1510"] = _price_before(b, MID_TIME), _price_before(b, EXIT_TIME)
    if lot_size and lot_size > 0:
        lot_cost = entry * lot_size
        lots = math.floor(capital / lot_cost)
        qty = lots * lot_size
        out.update(lot_size=lot_size, lot_cost=lot_cost, lots=lots, cash_left=capital - lots * lot_cost,
                   profit_high=qty * (high - entry),
                   profit_1130=qty * (out["p_1130"] - entry),
                   profit_1510=qty * (out["p_1510"] - entry))
        out["volume_0930_lots"] = float(first["volume"]) / lot_size
        out["oi_0930_lots"] = float(first["oi"]) / lot_size
    return out


def to_5m(bars: pd.DataFrame) -> pd.DataFrame:
    """1m -> 5m bars (labelled by start): open first, high max, low min, close last, volume sum, OI last."""
    if bars.empty:
        return bars
    b = bars.assign(ts=pd.to_datetime(bars["ts"])).sort_values("ts")
    g = b.groupby(b["ts"].dt.floor("5min"), sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"), oi=("oi", "last"))
    return out.reset_index()


def session_vwap(bars: pd.DataFrame) -> pd.Series:
    """VWAP hlc3, session anchored (one day of bars): cumulative typical price x volume / cumulative volume."""
    b = bars.sort_values("ts")
    vol = b["volume"].astype(float)
    cum_vol = vol.cumsum()
    cum_pv = ((b["high"] + b["low"] + b["close"]) / 3.0 * vol).cumsum()
    return (cum_pv / cum_vol.where(cum_vol > 0)).reindex(bars.index)


def reading_notes(day: date, expiry: date) -> list[str]:
    """Reading traps to show next to the IV column."""
    notes = []
    if day == expiry:
        notes.append("Expiry day: IV reads high because little time is left, not because of fear.")
    elif pd.Timestamp(day).day_name() in ("Friday", "Monday"):
        notes.append("Friday / Monday: IV reads low because the weekend is counted in the time left; "
                     "compare IV only with days at the same days-to-expiry.")
    return notes


# ----------------------------------------------------------------------------- build
def build(day: date, side: str, capital: float, band: pd.DataFrame, greeks: pd.DataFrame,
          nifty5: pd.DataFrame, expiry: date) -> tuple[pd.DataFrame, dict]:
    n = nifty5[nifty5["trade_date"] == day].copy()
    n["t"] = pd.to_datetime(n["ts"]).dt.time
    n0930 = n[n["t"] >= ENTRY_TIME]
    if n0930.empty:
        raise ValueError(f"no Nifty 5m bar at/after 09:30 on {day}")
    nifty_0930 = float(n0930.iloc[0]["open"])
    atm = atm_strike(nifty_0930)

    day_band = band[(band["trade_date"] == day) & (band["option_type"] == side)]
    g = greeks[(greeks["trade_date"] == day) & (greeks["option_type"] == side)].copy() if len(greeks) else greeks
    if len(g):
        g["t"] = pd.to_datetime(g["ts"]).dt.time

    rows, legs = [], []
    for pos, strike in ladder(atm, side):
        c = day_band[day_band["strike"] == strike]
        lot = c["lot_size"].dropna()
        lot_size = float(lot.iloc[0]) if len(lot) else None
        st = contract_stats(c, lot_size, capital)
        sym = str(c["trading_symbol"].iloc[0]) if len(c) else f"{int(strike)} {side} (no bars)"
        row = {"position": pos, "strike": strike, "symbol": sym, **st}
        if len(g) and st.get("entry_time"):
            gt = g[(g["strike"] == strike) & (g["t"] == time.fromisoformat(st["entry_time"]))]
            if len(gt):
                row.update(delta_0930=float(gt["delta"].iloc[0]), theta_0930=float(gt["theta"].iloc[0]),
                           iv_0930=float(gt["iv"].iloc[0]))
        rows.append(row)
        c5 = to_5m(c)
        legs.append({"label": f"{pos} · {sym}", "entry": st["entry_0930"],
                     "b1": _rows(c.assign(vwap=session_vwap(c)) if len(c) else c, extra=True),
                     "b5": _rows(c5.assign(vwap=session_vwap(c5)) if len(c5) else c5, extra=True)})

    table = pd.DataFrame(rows)
    meta = {"day": str(day), "side": side, "expiry": str(expiry), "nifty_0930": nifty_0930, "atm": atm,
            "capital": capital, "nifty": _rows(n, extra=False), "legs": legs,
            "notes": reading_notes(day, expiry)}
    return table, meta


def _epoch(ts: pd.Series) -> pd.Series:
    t = pd.to_datetime(ts)
    t = t.dt.tz_localize("Asia/Kolkata") if t.dt.tz is None else t
    secs = (t.dt.tz_convert("UTC") - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)
    return (secs + IST_OFFSET).astype(int)


def _rows(df: pd.DataFrame, extra: bool) -> list[list]:
    if df is None or df.empty:
        return []
    cols = ["open", "high", "low", "close"] + (["volume", "oi", "vwap"] if extra else [])
    d = df.sort_values("ts")
    vals = pd.concat([_epoch(d["ts"]).rename("t"), d[cols].astype(float).round(2)], axis=1)
    return [[None if isinstance(x, float) and np.isnan(x) else x for x in r] for r in vals.values.tolist()]


# ----------------------------------------------------------------------------- output
def _fmt(v, kind: str = "num") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == "":
        return "–"
    if kind == "rs":
        return f"₹{v:,.0f}"
    if kind == "pct":
        return f"{v:+.1f}%"
    if kind == "int":
        return f"{v:,.0f}"
    if kind == "g":
        return f"{v:.3f}"
    return f"{v:,.2f}" if isinstance(v, float) else html.escape(str(v))


TABLE_VIEW = [  # (header, column, kind)
    ("Position", "position", "s"), ("Contract", "symbol", "s"), ("Premium 09:30", "entry_0930", "num"),
    ("Lot size", "lot_size", "int"), ("1 lot cost", "lot_cost", "rs"), ("Lots with ₹1L", "lots", "int"),
    ("Cash left", "cash_left", "rs"), ("High", "high", "num"), ("High at", "high_time", "s"),
    ("Move to high", "move_pts", "num"), ("Move %", "move_pct", "pct"), ("Premium 11:30", "p_1130", "num"),
    ("Premium 15:10", "p_1510", "num"), ("Profit at high", "profit_high", "rs"),
    ("Profit 11:30", "profit_1130", "rs"), ("Profit 15:10", "profit_1510", "rs"),
    ("Dip before high", "dip_pts", "num"), ("Dip %", "dip_pct", "pct"), ("Delta", "delta_0930", "g"),
    ("Theta/day", "theta_0930", "num"), ("IV", "iv_0930", "num"), ("Vol 09:30 (lots)", "volume_0930_lots", "int"),
    ("OI 09:30 (lots)", "oi_0930_lots", "int"),
]


def table_html(table: pd.DataFrame, meta: dict) -> str:
    head = "".join(f"<th>{h}{' *' if c == 'iv_0930' and meta['notes'] else ''}</th>" for h, c, _ in TABLE_VIEW)
    body = []
    for r in table.to_dict("records"):
        cls = "atm" if r["position"] == "ATM" else ""
        cells = "".join(f"<td>{_fmt(r.get(c), k)}</td>" for _, c, k in TABLE_VIEW)
        body.append(f"<tr class='{cls}'>{cells}</tr>")
    return f"<table><tr>{head}</tr>{''.join(body)}</table>"


def write_outputs(table: pd.DataFrame, meta: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"contract_pick_{meta['day']}_{meta['side']}"
    csv_path, html_path = out_dir / f"{stem}.csv", out_dir / f"{stem}.html"
    table.to_csv(csv_path, index=False)
    notes = "".join(f"<div class='note'>* {html.escape(n)}</div>" for n in meta["notes"])
    title = (f"{meta['side']} contracts on {meta['day']} (expiry {meta['expiry']}) — Nifty at 09:30 "
             f"{meta['nifty_0930']:,.2f}, ATM {meta['atm']:,.0f}, capital ₹{meta['capital']:,.0f}")
    page = (PAGE.replace("__TITLE__", html.escape(title))
                .replace("__TABLE__", table_html(table, meta) + notes)
                .replace("__DATA__", json.dumps({k: meta[k] for k in ("day", "nifty", "legs")}, separators=(",", ":"))))
    html_path.write_text(page, encoding="utf-8")
    return csv_path, html_path


def summary_lines(table: pd.DataFrame, meta: dict) -> list[str]:
    lines = ["=" * 78, f"CONTRACT PICK -- {meta['side']} on {meta['day']} (expiry {meta['expiry']})", "=" * 78,
             f"Nifty 09:30 {meta['nifty_0930']:,.2f}  ATM {meta['atm']:,.0f}  capital Rs {meta['capital']:,.0f}",
             f"{'position':<8} {'contract':<26} {'09:30':>8} {'lot cost':>10} {'lots':>5} {'high':>8} {'at':>6} "
             f"{'move%':>7} {'profit@high':>12} {'dip%':>6}"]
    for r in table.to_dict("records"):
        lines.append(f"{r['position']:<8} {str(r['symbol'])[:26]:<26} {_n(r['entry_0930']):>8} {_n(r['lot_cost'], 0):>10} "
                     f"{_n(r['lots'], 0):>5} {_n(r['high']):>8} {r['high_time'] or '-':>6} {_n(r['move_pct'], 1):>7} "
                     f"{_n(r['profit_high'], 0):>12} {_n(r['dip_pct'], 1):>6}")
    missing = table[table["lot_size"].isna()]["symbol"].tolist()
    if missing:
        lines.append("no lot size / no bars (Rs columns blank): " + ", ".join(map(str, missing)))
    lines += [f"note: {n}" for n in meta["notes"]]
    lines.append("profits are before charges")
    return lines


def _n(v, d: int = 2) -> str:
    return "-" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.{d}f}"


# ----------------------------------------------------------------------------- run
def run(day: date, side: str, capital: float) -> list[str]:
    from modules.market_data.upstox.expired_archive_reader import read_part, stored_expiries
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    expiry = next((e for e in stored_expiries("band") if e >= day), None)
    if expiry is None:
        raise ValueError(f"no stored option expiry on/after {day}")
    band = read_part("band", expiry)
    if band.empty or not (band["trade_date"] == day).any():
        raise ValueError(f"expiry {expiry} has no option bars on {day}")
    greeks = read_part("greeks", expiry)
    if greeks.empty:
        logger.warning("no stored Greeks for expiry %s -- Greek columns stay blank", expiry)
    n5 = read_for_indicators(NIFTY_KEY, "universe_intraday", "5m")
    if not n5.ok:
        raise RuntimeError(f"Nifty 5m read failed: {n5.error}")
    nifty5 = n5.df.assign(trade_date=pd.to_datetime(n5.df["trade_date"]).dt.date)

    table, meta = build(day, side, capital, band, greeks, nifty5, expiry)
    csv_path, html_path = write_outputs(table, meta, LOG_DIR)
    return summary_lines(table, meta) + [f"written: {html_path}", f"         {csv_path}"]


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Contract pick</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
body{font-family:Arial,sans-serif;margin:10px;background:#fff;color:#222;font-size:13px}
h3{font-size:15px;margin:4px 0 8px}
.pane{position:relative;border-top:1px solid #eee}
.leg{position:absolute;left:6px;top:4px;z-index:3;font-size:12px;background:rgba(255,255,255,.85);padding:1px 4px}
table{border-collapse:collapse;margin-top:14px}th,td{border:1px solid #ddd;padding:3px 7px;text-align:right;white-space:nowrap}
th{background:#083F41;color:#fff;position:sticky;top:0}td:nth-child(1),td:nth-child(2){text-align:left}
tr.atm td{font-weight:bold;background:#f3f7f7}.note{color:#A32D2D;margin-top:6px}
.bar{margin:6px 0}.bar button{padding:3px 10px;border:1px solid #bbb;background:#f6f6f6;border-radius:4px;cursor:pointer}
.bar button.on{background:#083F41;color:#fff;border-color:#083F41}.key{margin-left:14px;color:#555}
.key i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}
</style></head><body>
<h3>__TITLE__</h3>
<div class="bar">Timeframe <button data-tf="5" class="on">5m</button><button data-tf="1">1m</button>
 <span class="key"><i style="background:#2962FF"></i>VWAP (hlc3, session) &nbsp; <i style="background:#534AB7"></i>09:30 premium
 &nbsp; Nifty pane: 5m always, no VWAP (no index volume)</span></div>
<div id="panes"></div>
__TABLE__
<script>
const D=__DATA__, dayStart=Date.parse(D.day+"T00:00:00Z")/1000;
const UP='#1D9E75', DN='#D85A30', host=document.getElementById('panes');
let tf=5;
const sets=[{label:'Nifty 50 (5m)',nifty:true,entry:null,h:220}].concat(D.legs.map(l=>({label:l.label,leg:l,entry:l.entry,h:170})));
const panes=[];
function rowsOf(s){ return s.nifty ? D.nifty : (tf===1 ? s.leg.b1 : s.leg.b5); }
function marks(rows){ const m=[]; for(const [hh,mm,txt] of [[9,30,'09:30'],[11,30,'11:30']]){
  const t=dayStart+hh*3600+mm*60; const r=rows.find(x=>x[0]>=t);
  if(r && r[0]-t<300) m.push({time:r[0],position:'aboveBar',color:'#534AB7',shape:'arrowDown',text:txt}); } return m; }
sets.forEach(s=>{
  const el=document.createElement('div'); el.className='pane'; el.style.height=s.h+'px';
  const lg=document.createElement('div'); lg.className='leg'; el.appendChild(lg); host.appendChild(el);
  const c=LightweightCharts.createChart(el,{height:s.h,layout:{background:{color:'#fff'},textColor:'#222'},
    timeScale:{timeVisible:true,secondsVisible:false,rightOffset:4},rightPriceScale:{scaleMargins:{top:.15,bottom:.05},minimumWidth:100},crosshair:{mode:0}});
  const se=c.addCandlestickSeries({upColor:UP,downColor:DN,borderVisible:false,wickUpColor:UP,wickDownColor:DN});
  const vw=s.nifty?null:c.addLineSeries({color:'#2962FF',lineWidth:2,priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:false});
  if(s.entry!==null&&s.entry!==undefined&&!Number.isNaN(s.entry)) se.createPriceLine({price:s.entry,color:'#534AB7',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'09:30 ₹'+s.entry});
  panes.push({s,c,se,vw,lg,rows:[]});
});
function legend(p,t){ const rows=p.rows; let r=null;
  if(t!==null){ for(const x of rows){ if(x[0]<=t) r=x; else break; } } if(!r) r=rows[rows.length-1];
  p.lg.innerHTML='<b>'+p.s.label+'</b>'+(r?` &nbsp;O ${r[1]} H ${r[2]} L ${r[3]} C ${r[4]}`
    +(r.length>5?` &nbsp;Vol ${r[5]} OI ${r[6]} &nbsp;<span style="color:#2962FF">VWAP ${r[7]===null?'–':r[7]}</span>`:''):' &nbsp;no data'); }
function draw(){
  panes.forEach(p=>{ p.rows=rowsOf(p.s); });
  // one shared time grid: a pane missing a bar gets an empty slot, so every pane has the same bar
  // positions and zoom / scroll can be copied pane to pane by position
  const grid=[...new Set(panes.flatMap(p=>p.rows.map(r=>r[0])))].sort((a,b)=>a-b);
  panes.forEach(p=>{ const by=new Map(p.rows.map(r=>[r[0],r]));
    p.se.setData(grid.map(t=>{ const r=by.get(t); return r?{time:t,open:r[1],high:r[2],low:r[3],close:r[4]}:{time:t}; }));
    p.se.setMarkers(marks(p.rows));
    if(p.vw) p.vw.setData(grid.map(t=>{ const r=by.get(t); return (r&&r[7]!==null)?{time:t,value:r[7]}:{time:t}; }));
    legend(p,null); });
  panes.forEach(p=>p.c.timeScale().fitContent());
}
const same=(a,b)=>a&&b&&Math.abs(a.from-b.from)<1e-6&&Math.abs(a.to-b.to)<1e-6;
panes.forEach((o,i)=>{
  o.c.timeScale().subscribeVisibleLogicalRangeChange(r=>{ if(!r) return;
    panes.forEach((q,j)=>{ if(j!==i && !same(q.c.timeScale().getVisibleLogicalRange(),r)) q.c.timeScale().setVisibleLogicalRange(r); }); });
  o.c.subscribeCrosshairMove(p=>{ const t=p&&p.time!==undefined?p.time:null; panes.forEach(q=>legend(q,t)); });
});
document.querySelectorAll('[data-tf]').forEach(b=>b.onclick=()=>{ tf=+b.dataset.tf;
  document.querySelectorAll('[data-tf]').forEach(x=>x.classList.toggle('on',x===b)); draw(); });
draw();
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare the 9 option contracts ITM 4 .. OTM 4 on one day")
    ap.add_argument("--day", required=True, type=lambda v: date.fromisoformat(v), help="YYYY-MM-DD")
    ap.add_argument("--side", default="CE", choices=["CE", "PE"])
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="rupees (default 100000)")
    args = ap.parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "contract_pick.log", mode="w", encoding="utf-8")])
    try:
        lines = run(args.day, args.side, args.capital)
    except Exception:
        logger.exception("Contract pick failed")
        return 1
    for line in lines:
        logger.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
