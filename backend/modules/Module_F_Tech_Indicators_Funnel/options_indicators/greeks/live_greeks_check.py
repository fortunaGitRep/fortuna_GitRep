"""
TC-GK-01: do Fortuna's computed IV and Greeks match Upstox's live ones?
Run during market hours. Each snapshot is 1 Upstox call (Nifty option chain, current weekly
expiry); nothing is written to R2.

Per snapshot, every strike within 9 strikes of spot, CE and PE, with a trade today:
  Upstox  ltp, bid/ask, volume, OI, iv, delta, gamma, theta, vega       (as served)
  Fortuna the same Greeks from black76, under 8 input conventions:
            underlying  parity  forward from put-call parity at the 3 strikes nearest spot
                        spot    Upstox spot price, carried at REPO_RATE
            expiry time close   that day's F&O close (15:40 from 3 Aug 2026)
                        1530    15:30
            premium     ltp     last traded price (what the 1m archive stores)
                        mid     (bid + ask) / 2
  Fortuna's chosen model for the archive = parity / close / ltp.

Result per convention: median |IV diff| (vol points), median |delta diff|, and median
ratios Fortuna/Upstox for gamma, theta, vega (1.00 = same units and model).
PASS when the best convention is within IV_TOLERANCE_PTS and DELTA_TOLERANCE: the maths is
right, and the best convention shows how Upstox computes theirs.

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks.live_greeks_check                     # 3 snapshots, 60 s apart
  ... --snapshots 5 --every 120   ... --expiry 2026-11-03 (default: nearest listed)
Output: logs/live_greeks_check_logs/check.log (+ screen) and snapshots.csv (appended per run)
"""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from modules.market_data.upstox.fetch_expired_nifty_options import SESSION_CLOSE_MINUTE, fno_close_minute
from modules.market_data.upstox.probe_expired_contracts import _get
from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks import black76

NIFTY_KEY = "NSE_INDEX|Nifty 50"
REPO_RATE = 0.055                    # RBI repo rate 5.50% (hiked 25 bps at the Oct 2026 MPC)
STRIKE_STEP = 50
STRIKES_EACH_SIDE = 9
IV_TOLERANCE_PTS = 0.5               # vol points, median over compared rows
DELTA_TOLERANCE = 0.02
CHOSEN = ("parity", "close", "ltp")
IST = ZoneInfo("Asia/Kolkata")
LOG_DIR = Path("logs") / "live_greeks_check_logs"
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- Upstox
def nearest_expiry(today: date | None = None) -> str:
    """Nearest listed Nifty option expiry on/after today (Upstox option contracts, current chain)."""
    today = today or datetime.now(IST).date()
    data = _get("/option/contract?" + urlencode({"instrument_key": NIFTY_KEY}))
    exps = sorted({str(c.get("expiry"))[:10] for c in data or [] if c.get("expiry")})
    exps = [e for e in exps if date.fromisoformat(e) >= today]
    if not exps:
        raise RuntimeError("Upstox listed no current Nifty option expiries")
    return exps[0]


def fetch_chain(expiry: str) -> tuple[pd.DataFrame, datetime]:
    """Option chain -> one row per contract. expiry: 'YYYY-MM-DD' or Upstox keyword (current_week)."""
    data = _get("/option/chain?" + urlencode({"instrument_key": NIFTY_KEY, "expiry_date": expiry}))
    at = datetime.now(IST)
    rows = []
    for item in data or []:
        for side, typ in (("call_options", "CE"), ("put_options", "PE")):
            leg = item.get(side) or {}
            md, gk = leg.get("market_data") or {}, leg.get("option_greeks") or {}
            rows.append({
                "snapshot_at": at, "expiry": str(item.get("expiry"))[:10],
                "spot": item.get("underlying_spot_price"), "strike": item.get("strike_price"),
                "option_type": typ, "instrument_key": leg.get("instrument_key"),
                "ltp": md.get("ltp"), "bid": md.get("bid_price"), "ask": md.get("ask_price"),
                "volume": md.get("volume"), "oi": md.get("oi"), "prev_oi": md.get("prev_oi"),
                "u_iv": gk.get("iv"), "u_delta": gk.get("delta"), "u_gamma": gk.get("gamma"),
                "u_theta": gk.get("theta"), "u_vega": gk.get("vega"), "u_pop": gk.get("pop"),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"Upstox returned an empty option chain for expiry '{expiry}'")
    num = [c for c in df.columns if c not in ("snapshot_at", "expiry", "option_type", "instrument_key")]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    return df, at


# ----------------------------------------------------------------------------- compute
def years_to_expiry(at: datetime, expiry: date, close_rule: str) -> float:
    minute = fno_close_minute(expiry) if close_rule == "close" else SESSION_CLOSE_MINUTE
    end = datetime(expiry.year, expiry.month, expiry.day, tzinfo=IST) + timedelta(minutes=minute)
    return max((end - at).total_seconds() / 60.0, 0.0) / black76.MINUTES_PER_YEAR


def premium(df: pd.DataFrame, source: str) -> pd.Series:
    if source == "ltp":
        return df["ltp"]
    two_sided = (df["bid"] > 0) & (df["ask"] > 0) & (df["ask"] >= df["bid"])
    return ((df["bid"] + df["ask"]) / 2).where(two_sided)


def compute(df: pd.DataFrame, at: datetime, underlying: str, close_rule: str, source: str) -> pd.DataFrame:
    expiry = date.fromisoformat(df["expiry"].iloc[0])
    spot = float(df["spot"].iloc[0])
    T = years_to_expiry(at, expiry, close_rule)
    px = premium(df, source)
    if underlying == "parity":
        wide = df.assign(px=px).pivot_table(index="strike", columns="option_type", values="px")
        F = black76.forward_from_parity(wide.index.values, wide.get("CE"), wide.get("PE"), spot, T, REPO_RATE)
    else:
        F = spot * np.exp(REPO_RATE * T)
    is_call = (df["option_type"] == "CE").values
    iv = black76.implied_vol(px.values, F, df["strike"].values, T, REPO_RATE, is_call)
    g = black76.greeks(F, df["strike"].values, T, REPO_RATE, iv, is_call)
    return pd.DataFrame({"forward": F, "T_minutes": T * black76.MINUTES_PER_YEAR, "iv": iv * 100, **g},
                        index=df.index)


def in_scope(df: pd.DataFrame) -> pd.Series:
    spot = df["spot"].iloc[0]
    near = (df["strike"] - spot).abs() <= STRIKES_EACH_SIDE * STRIKE_STEP + STRIKE_STEP / 2
    return near & (df["ltp"] > 0) & (df["volume"] > 0) & (df["u_iv"] > 0)


def compare(df: pd.DataFrame, ours: pd.DataFrame) -> dict:
    m = in_scope(df) & ours["iv"].notna()
    a, b = ours[m], df[m]

    def ratio(col):
        r = (a[col] / b[f"u_{col}"]).replace([np.inf, -np.inf], np.nan)
        return float(r.median())

    return {"rows": int(m.sum()),
            "iv_pts": float((a["iv"] - b["u_iv"]).abs().median()),
            "delta": float((a["delta"] - b["u_delta"]).abs().median()),
            "gamma_x": ratio("gamma"), "theta_x": ratio("theta"), "vega_x": ratio("vega")}


VARIANTS = list(itertools.product(("parity", "spot"), ("close", "1530"), ("ltp", "mid")))


def check_snapshot(df: pd.DataFrame, at: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (rows with Fortuna's chosen-model values, per-variant comparison table)"""
    table, chosen = [], None
    for v in VARIANTS:
        ours = compute(df, at, *v)
        table.append({"underlying": v[0], "expiry_time": v[1], "premium": v[2],
                      "forward": float(ours["forward"].iloc[0]), **compare(df, ours)})
        if v == CHOSEN:
            chosen = ours
    rows = df.join(chosen.add_prefix("f_"))
    rows["in_scope"] = in_scope(df)
    return rows, pd.DataFrame(table)


# ----------------------------------------------------------------------------- report
def report(tables: list[pd.DataFrame], snaps: list[pd.DataFrame]) -> list[str]:
    t = pd.concat(tables).groupby(["underlying", "expiry_time", "premium"], as_index=False).median(numeric_only=True)
    t = t.sort_values(["iv_pts", "delta"]).reset_index(drop=True)
    first = snaps[0]
    lines = ["=" * 78, "TC-GK-01  LIVE GREEKS CHECK  (Fortuna black76 vs Upstox option chain)", "=" * 78,
             f"snapshots : {len(snaps)}  ({snaps[0]['snapshot_at'].iloc[0]:%H:%M:%S} .. "
             f"{snaps[-1]['snapshot_at'].iloc[0]:%H:%M:%S} IST)",
             f"expiry    : {first['expiry'].iloc[0]}   spot at first: {first['spot'].iloc[0]:.2f}   "
             f"rate {REPO_RATE:.2%}",
             f"compared  : strikes within {STRIKES_EACH_SIDE} of spot, CE+PE, traded today "
             f"(~{int(t['rows'].median())} rows per snapshot)",
             "", "median over snapshots; iv_pts / delta = median abs diff; *_x = Fortuna / Upstox",
             t.to_string(index=False, float_format=lambda x: f"{x:.3f}"), ""]
    best = t.iloc[0]
    ch = t[(t["underlying"] == CHOSEN[0]) & (t["expiry_time"] == CHOSEN[1]) & (t["premium"] == CHOSEN[2])].iloc[0]
    ok = best["iv_pts"] <= IV_TOLERANCE_PTS and best["delta"] <= DELTA_TOLERANCE
    lines += [f"closest to Upstox : {best['underlying']} / {best['expiry_time']} / {best['premium']}  "
              f"(IV {best['iv_pts']:.2f} pts, delta {best['delta']:.3f})",
              f"Fortuna's model   : {'/'.join(CHOSEN)}  (IV {ch['iv_pts']:.2f} pts, delta {ch['delta']:.3f})",
              f"RESULT: {'PASS' if ok else 'FAIL'} -- tolerance IV {IV_TOLERANCE_PTS} pts, delta {DELTA_TOLERANCE}"]
    if ok and (best[["underlying", "expiry_time", "premium"]].tolist() != list(CHOSEN)):
        lines.append("   the maths matches; the gap to Fortuna's model is Upstox's different input convention")
    for col, name in (("gamma_x", "gamma"), ("theta_x", "theta"), ("vega_x", "vega")):
        if abs(best[col] - 1) > 0.05:
            lines.append(f"   {name}: Fortuna/Upstox = {best[col]:.3f} -> different units or convention, see CSV")
    s = snaps[-1]
    s = s[s["in_scope"]].assign(dist=lambda x: (x["strike"] - x["spot"]).abs()).nsmallest(6, "dist")
    lines += ["", "last snapshot, strikes nearest spot (u_ = Upstox, f_ = Fortuna's model):",
              s[["strike", "option_type", "ltp", "u_iv", "f_iv", "u_delta", "f_delta", "u_gamma", "f_gamma",
                 "u_theta", "f_theta", "u_vega", "f_vega"]].to_string(index=False, float_format=lambda x: f"{x:.5g}")]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare Fortuna's IV/Greeks with Upstox live (TC-GK-01)")
    ap.add_argument("--snapshots", type=int, default=3)
    ap.add_argument("--every", type=int, default=60, help="seconds between snapshots")
    ap.add_argument("--expiry", help="YYYY-MM-DD (default: nearest listed expiry)")
    args = ap.parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    snaps, tables = [], []
    try:
        if not args.expiry:
            args.expiry = nearest_expiry()
            logger.info("Expiry: %s (nearest listed)", args.expiry)
        for k in range(args.snapshots):
            if k:
                time.sleep(args.every)
            df, at = fetch_chain(args.expiry)
            rows, table = check_snapshot(df, at)
            snaps.append(rows)
            tables.append(table)
            ch = table[(table["underlying"] == CHOSEN[0]) & (table["expiry_time"] == CHOSEN[1])
                       & (table["premium"] == CHOSEN[2])].iloc[0]
            logger.info("snapshot %d/%d %s: %d rows, chosen model IV diff %.2f pts, delta diff %.3f",
                        k + 1, args.snapshots, f"{at:%H:%M:%S}", ch["rows"], ch["iv_pts"], ch["delta"])
    except KeyboardInterrupt:
        logger.warning("Stopped; reporting the snapshots taken")
    except Exception:
        logger.exception("Live check failed")
        if not snaps:
            return 1
    if not snaps:
        return 1
    out = pd.concat(snaps, ignore_index=True)
    path = LOG_DIR / "snapshots.csv"
    out.to_csv(path, mode="a", header=not path.exists(), index=False)
    text = "\n".join(report(tables, snaps))
    (LOG_DIR / "check.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
