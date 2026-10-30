"""
Read-only check of the expired Nifty options archive and its computed IV against outside sources.
No Upstox calls, nothing written to R2.

A. Prices / OI vs NSE: SAMPLE_DAYS days spread over the archive (fixed seed), ATM +-2 strikes, CE and PE.
   Our day candle from the 1m band (open first, high max, low min, last close, volume sum, OI last)
   vs NSE's F&O bhavcopy (UDiFF CSV) for the same contract:
     open / high / low / last traded price -> should match (within 0.05)
     OI at end of day                      -> should match
     NSE close (ClsPric)                    -> shown only (NSE's close is an average, not the last trade)
     volume                                 -> ratio shown (units can differ)
   Days from 3 Aug 2026 are reported separately: weeks stored before the 15:40 close rule have no
   15:30-15:40 bars, so their high / low / last can legitimately differ.
   Bhavcopy files are downloaded from NSE's archive into logs/options_verify_logs/bhavcopy/
   (reused next run). If NSE refuses the download, save the files there by hand (same names).
B. IV vs India VIX (chart): daily ATM IV at 10:30 from the nearest expiry, all days and only days
   2 trading days before expiry (same days-to-expiry, so comparable), against India VIX daily close.
   Correlation of levels and of day-to-day changes in the log.
C. IV across strikes (chart): 10:30 on 4 days (calmest, most stressed, latest, a middle day),
   out-of-the-money side only (puts below the forward, calls above). Plus, over every day:
   share of days where 3-strike OTM put IV > 3-strike OTM call IV (Nifty normally has put skew).

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks.verify_options_archive
  ... --skip-nse      (B and C only)   ... --days 30
Output: logs/options_verify_logs/verify.log (+ screen), nse_compare.csv, verify_chart.html
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import zipfile
from datetime import date, time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

from modules.market_data.upstox.expired_archive_reader import (
    PREFIXES,
    _client,
    read_part,
    stored_expiries,
)
from modules.market_data.upstox.fetch_expired_nifty_options import FNO_CLOSE_1540_FROM
from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

SAMPLE_DAYS = 20
SEED = 7
STRIKE_STEP = 50
STRIKES_EACH_SIDE = 2
PRICE_TOL = 0.05
IV_TIME = dtime(10, 30)
COMPARE_DTE = 2
SKEW_STEPS = 3
VIX_KEY = "NSE_INDEX|India VIX"
NSE_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
NSE_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/124.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
NSE_COLS = ["TckrSymb", "XpryDt", "StrkPric", "OptnTp", "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
            "OpnIntrst", "TtlTradgVol"]
LOG_DIR = Path("logs") / "options_verify_logs"
BHAV_DIR = LOG_DIR / "bhavcopy"
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- A. NSE
def sample_days(n: int) -> list[tuple[date, date]]:
    """(day, expiry) pairs: n expiries spread evenly, one random day in each expiry's own week."""
    exps = list(stored_expiries("band"))
    pick = [exps[i] for i in np.linspace(0, len(exps) - 1, min(n, len(exps))).round().astype(int)]
    rng = np.random.default_rng(SEED)
    out = []
    for e in dict.fromkeys(pick):
        band = read_part("band", e)
        week_start = pd.to_datetime(band["week_start"].iloc[0]).date()
        days = sorted(d for d in band["trade_date"].unique() if d >= week_start)
        if days:
            out.append((days[int(rng.integers(len(days)))], e))
    return out


def bhavcopy(day: date) -> pd.DataFrame | None:
    BHAV_DIR.mkdir(parents=True, exist_ok=True)
    path = BHAV_DIR / Path(NSE_URL.format(d=day)).name
    if not path.exists():
        try:
            import requests
            r = requests.get(NSE_URL.format(d=day), headers=NSE_HEADERS, timeout=30)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception as exc:                                    # noqa: BLE001 -- report, continue
            logger.warning("NSE bhavcopy %s not downloaded (%s) -- save it by hand to %s", day, exc, path)
            return None
    try:
        with zipfile.ZipFile(path) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
    except zipfile.BadZipFile:
        logger.warning("NSE bhavcopy %s is not a zip (blocked download?) -- delete %s and save it by hand", day, path)
        return None
    missing = [c for c in NSE_COLS if c not in df.columns]
    if missing:
        logger.warning("bhavcopy %s: columns %s missing; has %s", day, missing, list(df.columns)[:30])
        return None
    df = df[(df["TckrSymb"] == "NIFTY") & df["OptnTp"].isin(["CE", "PE"])].copy()
    df["XpryDt"] = pd.to_datetime(df["XpryDt"]).dt.date
    df["StrkPric"] = df["StrkPric"].astype(float)
    return df


def our_day(band: pd.DataFrame, day: date) -> pd.DataFrame:
    d = band[band["trade_date"] == day].sort_values("ts")
    g = d.groupby(["strike", "option_type"])
    return g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), last=("close", "last"),
                 volume=("volume", "sum"), oi=("oi", "last")).reset_index()


def compare_day(day: date, expiry: date) -> pd.DataFrame:
    band = read_part("band", expiry)
    ours = our_day(band, day)
    if ours.empty:
        return pd.DataFrame()
    greeks = read_part("greeks", expiry)
    fwd = greeks.loc[greeks["trade_date"] == day, "forward"].median() if not greeks.empty else np.nan
    if not np.isfinite(fwd):
        fwd = float(ours.loc[(ours["option_type"] == "CE"), "strike"].median())
    atm = round(fwd / STRIKE_STEP) * STRIKE_STEP
    want = [atm + k * STRIKE_STEP for k in range(-STRIKES_EACH_SIDE, STRIKES_EACH_SIDE + 1)]
    ours = ours[ours["strike"].isin(want)]
    nse = bhavcopy(day)
    if nse is None:
        return pd.DataFrame()
    nse = nse[nse["XpryDt"] == expiry].rename(columns={"StrkPric": "strike", "OptnTp": "option_type"})
    m = ours.merge(nse[["strike", "option_type", *NSE_COLS[4:]]], on=["strike", "option_type"], how="left")
    m.insert(0, "expiry", expiry)
    m.insert(0, "trade_date", day)
    m["late_era"] = day >= FNO_CLOSE_1540_FROM
    for ours_c, nse_c in (("open", "OpnPric"), ("high", "HghPric"), ("low", "LwPric"), ("last", "LastPric")):
        m[f"{ours_c}_ok"] = (m[ours_c] - m[nse_c]).abs() <= PRICE_TOL
    m["oi_ok"] = m["oi"] == m["OpnIntrst"]
    m["close_gap"] = m["last"] - m["ClsPric"]
    m["volume_ratio"] = m["volume"] / m["TtlTradgVol"].replace(0, np.nan)
    m["in_nse"] = m["OpnPric"].notna()
    return m


def nse_section(n: int) -> tuple[list[str], pd.DataFrame]:
    rows = []
    for day, expiry in sample_days(n):
        c = compare_day(day, expiry)
        logger.info("A. %s (expiry %s): %d contracts compared", day, expiry, int(c["in_nse"].sum()) if len(c) else 0)
        if len(c):
            rows.append(c)
    if not rows:
        return ["A. PRICES / OI vs NSE: no bhavcopy available -- see warnings above"], pd.DataFrame()
    t = pd.concat(rows, ignore_index=True)
    lines = ["A. PRICES / OI vs NSE BHAVCOPY (ATM +-2 strikes, CE + PE)",
             f"   days {t['trade_date'].nunique()}, contracts {len(t)}, found in NSE file {int(t['in_nse'].sum())}"]
    for era, label in ((False, "before 3 Aug 2026"), (True, "from 3 Aug 2026 (15:30-15:40 bars not stored)")):
        s = t[(t["late_era"] == era) & t["in_nse"]]
        if s.empty:
            continue
        pct = {c: s[f"{c}_ok"].mean() for c in ("open", "high", "low", "last", "oi")}
        lines.append(f"   {label}: {len(s)} contracts -- match: " +
                     ", ".join(f"{c} {v:.0%}" for c, v in pct.items()) +
                     f"; NSE close vs our last: median gap {s['close_gap'].abs().median():.2f}; "
                     f"volume ours/NSE median {s['volume_ratio'].median():.2f}")
    bad = t[t["in_nse"] & ~t["late_era"] & ~(t[["open_ok", "high_ok", "low_ok", "last_ok", "oi_ok"]].all(axis=1))]
    if len(bad):
        lines.append(f"   mismatches before 3 Aug 2026 ({len(bad)}), first 12:")
        for r in bad.head(12).itertuples():
            lines.append(f"      {r.trade_date} {int(r.strike)}{r.option_type}: O {r.open}/{r.OpnPric} "
                         f"H {r.high}/{r.HghPric} L {r.low}/{r.LwPric} last {r.last}/{r.LastPric} "
                         f"OI {int(r.oi)}/{int(r.OpnIntrst)}  (ours/NSE)")
    else:
        lines.append("   no mismatches before 3 Aug 2026")
    return lines, t


# ----------------------------------------------------------------------------- B / C. IV
def _read_cols(part: str, expiry: date, cols: list[str]) -> pd.DataFrame:
    r2, bucket = _client()
    body = r2.get_object(Bucket=bucket, Key=f"{PREFIXES[part]}/{expiry.isoformat()}.parquet")["Body"].read()
    return pd.read_parquet(io.BytesIO(body), columns=cols, engine="pyarrow")


def iv_at_time() -> pd.DataFrame:
    """Per trading day, from the nearest expiry on/after it: 10:30 rows (strike, type, otm_steps, iv, forward)."""
    exps = list(stored_expiries("greeks"))
    out, prev = [], None
    for k, e in enumerate(exps, 1):
        g = _read_cols("greeks", e, ["ts", "trade_date", "strike", "option_type", "otm_steps", "iv", "forward"])
        ts = pd.to_datetime(g["ts"])
        g = g[(ts.dt.time == IV_TIME)]
        g = g.assign(trade_date=pd.to_datetime(g["trade_date"]).dt.date)
        g = g[(g["trade_date"] <= e) & (g["trade_date"] > (prev or date.min))]
        out.append(g.assign(expiry=e))
        prev = e
        if k % 20 == 0:
            logger.info("B. read %d / %d greeks files", k, len(exps))
    t = pd.concat(out, ignore_index=True)
    t["dte"] = [int(np.busday_count(d, e)) for d, e in zip(t["trade_date"], t["expiry"])]
    return t


def atm_series(t: pd.DataFrame) -> pd.DataFrame:
    atm = t[t["otm_steps"].abs() <= 0.5].groupby(["trade_date", "expiry", "dte"])["iv"].median().rename("atm_iv")
    return atm.reset_index().sort_values("trade_date")


def skew_share(t: pd.DataFrame) -> tuple[float, int]:
    near = t[(t["otm_steps"] - SKEW_STEPS).abs() <= 0.5]
    w = near.groupby(["trade_date", "option_type"])["iv"].median().unstack()
    w = w.dropna(subset=[c for c in ("CE", "PE") if c in w.columns])
    if not {"CE", "PE"} <= set(w.columns) or w.empty:
        return float("nan"), 0
    return float((w["PE"] > w["CE"]).mean()), len(w)


def smile_days(atm: pd.DataFrame) -> list[date]:
    mid = atm[atm["dte"] >= 2]
    if mid.empty:
        mid = atm
    picks = [mid.loc[mid["atm_iv"].idxmin(), "trade_date"], mid.loc[mid["atm_iv"].idxmax(), "trade_date"],
             mid["trade_date"].iloc[-1], mid["trade_date"].iloc[len(mid) // 2]]
    return list(dict.fromkeys(picks))


def smile(t: pd.DataFrame, day: date) -> list[list[float]]:
    d = t[t["trade_date"] == day]
    otm = d[d["otm_steps"] >= -0.5]                                    # OTM side of each type
    otm = otm.assign(x=(otm["strike"] / otm["forward"] - 1) * 100).sort_values("x")
    otm = otm[otm["x"].abs() <= 4]
    return otm[["x", "iv"]].dropna().round(3).values.tolist()


def iv_section() -> tuple[list[str], dict]:
    np.seterr(all="ignore")                      # short / flat series give NaN correlations, reported as nan
    t = iv_at_time()
    atm = atm_series(t)
    vix = read_for_indicators(VIX_KEY, "indices", "1d")
    lines = ["B. ATM IV (10:30, nearest expiry) vs INDIA VIX"]
    chart = {"days": [], "vix": [], "iv_all": [], "iv_dte": [], "smiles": []}
    if vix.ok:
        v = vix.df.assign(trade_date=pd.to_datetime(vix.df["trade_date"]).dt.date)[["trade_date", "close"]]
        j = atm.merge(v.rename(columns={"close": "vix"}), on="trade_date", how="left")
        same = j[j["dte"] == COMPARE_DTE].dropna(subset=["vix"])
        lvl = same["atm_iv"].corr(same["vix"])
        chg = same["atm_iv"].diff().corr(same["vix"].diff())
        allc = j.dropna(subset=["vix"])
        lines += [f"   days {len(j)}; with VIX {len(allc)}",
                  f"   days {COMPARE_DTE} trading days before expiry: {len(same)}; correlation with VIX: "
                  f"levels {lvl:.2f}, changes {chg:.2f}",
                  f"   all days: correlation of levels {allc['atm_iv'].corr(allc['vix']):.2f} "
                  "(weaker: days-to-expiry pattern mixed in)",
                  f"   median ATM IV / VIX at {COMPARE_DTE} days: {(same['atm_iv'] / same['vix']).median():.2f}"]
        chart.update(days=[str(d) for d in j["trade_date"]], vix=j["vix"].round(2).where(j["vix"].notna(), None).tolist(),
                     iv_all=j["atm_iv"].round(2).tolist(),
                     iv_dte=[round(x, 2) if d == COMPARE_DTE else None for x, d in zip(j["atm_iv"], j["dte"])])
    else:
        lines.append(f"   India VIX not readable ({vix.error}) -- chart shows IV only")
        chart.update(days=[str(d) for d in atm["trade_date"]], vix=[None] * len(atm),
                     iv_all=atm["atm_iv"].round(2).tolist(),
                     iv_dte=[round(x, 2) if d == COMPARE_DTE else None for x, d in zip(atm["atm_iv"], atm["dte"])])
    share, n = skew_share(t)
    lines += ["", "C. IV ACROSS STRIKES",
              f"   days where {SKEW_STEPS}-strike OTM put IV > {SKEW_STEPS}-strike OTM call IV: {share:.0%} of {n}"]
    for d in smile_days(atm):
        pts = smile(t, d)
        row = atm[atm["trade_date"] == d].iloc[0]
        chart["smiles"].append({"label": f"{d} (ATM IV {row['atm_iv']:.1f}, {int(row['dte'])}d to expiry)", "pts": pts})
        lines.append(f"   smile {d}: {len(pts)} strikes, ATM IV {row['atm_iv']:.1f}")
    return lines, chart


# ----------------------------------------------------------------------------- output
def write_chart(chart: dict, path: Path) -> None:
    path.write_text(CHART.replace("__DATA__", json.dumps(chart, separators=(",", ":"))), encoding="utf-8")


CHART = """<!doctype html><html><head><meta charset="utf-8"><title>Options archive check</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>body{font-family:Arial,sans-serif;margin:14px;color:#222}h3{margin:18px 0 4px}p{margin:2px 0 8px;color:#555;font-size:13px}
.box{position:relative;height:380px;max-width:1300px}</style></head><body>
<h3>B. ATM IV at 10:30 vs India VIX</h3>
<p>Grey dots: every day (dips on Fridays/Mondays = weekend effect). Blue: days 2 trading days before expiry only (comparable). Orange: India VIX close. They should rise and fall together.</p>
<div class="box"><canvas id="b"></canvas></div>
<h3>C. IV across strikes at 10:30 (out-of-the-money side)</h3>
<p>Left of 0 = puts below the forward, right = calls above. Normal Nifty shape: higher on the left (put skew), smooth curve.</p>
<div class="box"><canvas id="c"></canvas></div>
<script>
const D=__DATA__;
new Chart(document.getElementById('b'),{type:'line',data:{labels:D.days,datasets:[
 {label:'ATM IV, all days',data:D.iv_all,showLine:false,pointRadius:1.5,borderColor:'#bbb',backgroundColor:'#bbb'},
 {label:'ATM IV, 2 days before expiry',data:D.iv_dte,spanGaps:true,pointRadius:2.5,borderColor:'#185FA5',backgroundColor:'#185FA5',borderWidth:1.5},
 {label:'India VIX (right axis)',data:D.vix,spanGaps:true,pointRadius:0,borderColor:'#D85A30',borderWidth:1.5,yAxisID:'y2'}]},
 options:{maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},
  scales:{x:{ticks:{maxTicksLimit:16}},y:{title:{display:true,text:'ATM IV %'}},y2:{position:'right',grid:{drawOnChartArea:false},title:{display:true,text:'India VIX'}}}}});
const cols=['#185FA5','#D85A30','#1D9E75','#7F77DD'];
new Chart(document.getElementById('c'),{type:'scatter',data:{datasets:D.smiles.map((s,i)=>({label:s.label,
 data:s.pts.map(p=>({x:p[0],y:p[1]})),showLine:true,borderColor:cols[i%4],backgroundColor:cols[i%4],pointRadius:2}))},
 options:{maintainAspectRatio:false,animation:false,scales:{x:{title:{display:true,text:'strike vs forward, %'}},
  y:{title:{display:true,text:'IV %'}}}}});
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the options archive and IV against NSE and India VIX")
    ap.add_argument("--days", type=int, default=SAMPLE_DAYS, help="days for the NSE comparison")
    ap.add_argument("--skip-nse", action="store_true")
    args = ap.parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    lines = ["=" * 78, "OPTIONS ARCHIVE CHECK (NSE bhavcopy, India VIX)", "=" * 78]
    try:
        if not args.skip_nse:
            a, table = nse_section(args.days)
            lines += a + [""]
            if len(table):
                table.to_csv(LOG_DIR / "nse_compare.csv", index=False)
        b, chart = iv_section()
        lines += b
        write_chart(chart, LOG_DIR / "verify_chart.html")
        lines += ["", f"chart: {LOG_DIR / 'verify_chart.html'}"]
    except Exception:
        logger.exception("Check failed")
        return 1
    text = "\n".join(lines)
    (LOG_DIR / "verify.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
