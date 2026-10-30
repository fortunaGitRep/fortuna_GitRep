"""
IV and Greeks for every expired Nifty option in the archive band (ATM +-9 strikes), every
minute, computed with black76 (checked against Upstox live: TC-GK-01 PASS, 29 Oct 2026).
Reads the 1m band archive from R2, writes one Parquet per expiry; no Upstox calls.

Per minute, per contract:
  forward     Nifty forward for that expiry from put-call parity: at each minute, the strike
              where CE and PE are closest in price, and the 3 nearest strikes with both
              prices -> median of K + (C - P) * exp(rT). Carried forward up to 5 minutes when
              a minute has no pair. Same forward for every contract of that minute.
  t_minutes   minutes from the bar's close (ts + 1 min) to expiry (that day's F&O close)
  otm_steps   strikes out of the money vs the forward (+2 = 2 OTM, 0 = ATM, -2 = 2 ITM),
              CE: (K - F) / 50, PE: (F - K) / 50
  iv          % (Upstox style, 13.0 = 13%), from the bar's close price
  delta, gamma (per point), theta (per day, forward held, Upstox convention), vega (per 1 vol pt)
  oi_chg_1m   OI change vs the contract's previous bar
  oi_chg_day  OI vs the contract's last OI of the previous trading day
Blank (NaN) where the model cannot price: expiry's final minute, price below intrinsic
value, no forward that minute.

Quality line per expiry: share of near-ATM minutes (|otm_steps| <= 2, 09:15-15:10) with an
IV, and the median CE-vs-PE IV gap at the same strike (put-call parity; live check ~0.1 pt).

Refresh: new expiries in the band archive are computed on the next run; stored ones are
skipped (--force recomputes).

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks.archive_greeks --candidates
  python -m modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks.archive_greeks          # all
  ... --expiry 2026-10-13   ... --force   ... --limit 3
Output: R2 upstox/nifty_options_greeks/1m/<expiry>.parquet
        logs/options_greeks_logs/greeks_run.log (+ screen) and greeks_summary.log
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from db.r2_client import get_r2, get_r2_settings
from modules.market_data.upstox.expired_archive_reader import GREEKS_PREFIX, read_part, stored_expiries
from modules.market_data.upstox.fetch_expired_nifty_options import MIN_STORED_BYTES, fno_close_minute
from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks import black76
from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks.live_greeks_check import REPO_RATE

STRIKE_STEP = 50
PARITY_STRIKES = 3
FORWARD_CARRY_MINUTES = 5
NEAR_ATM_STEPS = 2
QUALITY_END_MINUTE = 15 * 60 + 10           # Ash's auto square-off
CANDIDATES_CSV = Path("logs") / "options_candidate_charts" / "candidate_contracts.csv"
LOG_DIR = Path("logs") / "options_greeks_logs"
COLUMNS = ["expiry", "instrument_key", "strike", "option_type", "ts", "trade_date", "close", "volume", "oi",
           "oi_chg_1m", "oi_chg_day", "forward", "t_minutes", "otm_steps", "iv", "delta", "gamma", "theta", "vega"]
FLOAT32 = ["forward", "t_minutes", "otm_steps", "iv", "delta", "gamma", "theta", "vega"]
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- compute
def minutes_to_expiry(ts: pd.Series, expiry: date) -> np.ndarray:
    """Minutes from each bar's close (ts + 1 min) to expiry at that day's F&O close."""
    t = pd.to_datetime(ts)
    end = pd.Timestamp(datetime(expiry.year, expiry.month, expiry.day)) + pd.Timedelta(minutes=fno_close_minute(expiry))
    end = end.tz_localize(t.dt.tz) if t.dt.tz is not None else end
    return ((end - (t + pd.Timedelta(minutes=1))) / pd.Timedelta(minutes=1)).clip(lower=0).to_numpy(dtype=float)


def forward_by_minute(df: pd.DataFrame, expiry: date) -> pd.Series:
    """Parity forward per ts (index ts)."""
    ce = df[df["option_type"] == "CE"].pivot_table(index="ts", columns="strike", values="close", aggfunc="last")
    pe = df[df["option_type"] == "PE"].pivot_table(index="ts", columns="strike", values="close", aggfunc="last")
    idx = ce.index.union(pe.index)
    strikes = ce.columns.union(pe.columns)
    C = ce.reindex(index=idx, columns=strikes).to_numpy(float)
    P = pe.reindex(index=idx, columns=strikes).to_numpy(float)
    K = strikes.to_numpy(float)
    D = C - P
    valid = np.isfinite(D)
    if not valid.any():
        return pd.Series(np.nan, index=idx)
    absd = np.where(valid, np.abs(D), np.inf)
    kstar = K[np.argmin(absd, axis=1)]
    dist = np.where(valid, np.abs(K[None, :] - kstar[:, None]), np.inf)
    near = np.argsort(dist, axis=1)[:, :PARITY_STRIKES]
    rows = np.arange(len(idx))[:, None]
    T = minutes_to_expiry(pd.Series(idx), expiry) / black76.MINUTES_PER_YEAR
    fk = K[near] + D[rows, near] * np.exp(REPO_RATE * T)[:, None]
    fk = np.where(np.isfinite(dist[rows, near]), fk, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # all-NaN minutes -> NaN
        F = np.nanmedian(fk, axis=1)
    s = pd.Series(F, index=idx)
    day = pd.Series(pd.to_datetime(idx).date, index=idx)
    return s.groupby(day).ffill(limit=FORWARD_CARRY_MINUTES)


def compute_expiry(band: pd.DataFrame, expiry: date) -> pd.DataFrame:
    df = band.sort_values(["instrument_key", "ts"]).reset_index(drop=True)
    F = forward_by_minute(df, expiry)
    df["forward"] = df["ts"].map(F).astype(float)
    df["t_minutes"] = minutes_to_expiry(df["ts"], expiry)
    T = df["t_minutes"].to_numpy() / black76.MINUTES_PER_YEAR
    is_call = (df["option_type"] == "CE").to_numpy()
    K, Fv = df["strike"].to_numpy(float), df["forward"].to_numpy(float)
    iv = black76.implied_vol(df["close"].to_numpy(float), Fv, K, T, REPO_RATE, is_call)
    g = black76.greeks(Fv, K, T, REPO_RATE, iv, is_call)
    df["iv"] = iv * 100
    for k, v in g.items():
        df[k] = v
    df["otm_steps"] = np.where(is_call, K - Fv, Fv - K) / STRIKE_STEP
    grp = df.groupby("instrument_key")["oi"]
    df["oi_chg_1m"] = grp.diff()
    last = df.groupby(["instrument_key", "trade_date"])["oi"].last()
    prev = last.groupby(level=0).shift(1).rename("oi_prev_day")
    df = df.join(prev, on=["instrument_key", "trade_date"])
    df["oi_chg_day"] = df["oi"] - df["oi_prev_day"]
    out = df.reindex(columns=COLUMNS)
    out[FLOAT32] = out[FLOAT32].astype("float32")
    return out


def quality(g: pd.DataFrame) -> dict:
    ts = pd.to_datetime(g["ts"])
    minute = ts.dt.hour * 60 + ts.dt.minute
    near = g[(g["otm_steps"].abs() <= NEAR_ATM_STEPS) & (minute < QUALITY_END_MINUTE)]
    cover = float(near["iv"].notna().mean()) if len(near) else float("nan")
    w = near.pivot_table(index=["ts", "strike"], columns="option_type", values="iv")
    gap = float((w["CE"] - w["PE"]).abs().median()) if {"CE", "PE"} <= set(w.columns) else float("nan")
    atm = near[near["otm_steps"].abs() <= 0.5]
    day_iv = atm.groupby("trade_date")["iv"].median()
    return {"iv_cover": cover, "ce_pe_gap": gap,
            "atm_iv_min": float(day_iv.min()) if len(day_iv) else float("nan"),
            "atm_iv_max": float(day_iv.max()) if len(day_iv) else float("nan")}


# ----------------------------------------------------------------------------- R2
class Store:
    def __init__(self):
        self.r2, self.bucket = get_r2(), get_r2_settings().bucket

    def stored(self) -> set[date]:
        out, token = set(), None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": GREEKS_PREFIX + "/"}
            if token:
                kw["ContinuationToken"] = token
            resp = self.r2.list_objects_v2(**kw)
            out |= {date.fromisoformat(o["Key"].rsplit("/", 1)[1][:10]) for o in resp.get("Contents", [])
                    if o["Key"].endswith(".parquet") and o.get("Size", 0) >= MIN_STORED_BYTES}
            if not resp.get("IsTruncated"):
                return out
            token = resp.get("NextContinuationToken")

    def write(self, expiry: date, df: pd.DataFrame) -> int:
        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        self.r2.put_object(Bucket=self.bucket, Key=f"{GREEKS_PREFIX}/{expiry.isoformat()}.parquet", Body=buf.getvalue())
        return buf.tell()


# ----------------------------------------------------------------------------- run
def candidate_expiries() -> set[date]:
    t = pd.read_csv(CANDIDATES_CSV)
    return set(pd.to_datetime(t["expiry"].dropna()).dt.date)


def run(only: date | None, candidates: bool, limit: int | None, force: bool) -> list[str]:
    store = Store()
    band = list(stored_expiries("band"))
    todo = [e for e in band if (only is None or e == only)]
    if candidates:
        want = candidate_expiries()
        todo = [e for e in todo if e in want]
    done = set() if force else store.stored()
    skipped = [e for e in todo if e in done]
    todo = [e for e in todo if e not in done]
    todo = todo[:limit] if limit else todo
    logger.info("band expiries %d; selected %d; already computed %d; computing %d",
                len(band), len(todo) + len(skipped), len(skipped), len(todo))
    rows, failed = [], []
    for k, e in enumerate(todo, 1):
        t0 = time.monotonic()
        try:
            g = compute_expiry(read_part("band", e), e)
            q = quality(g)
            size = store.write(e, g)
        except Exception as exc:                                   # noqa: BLE001 -- record, continue
            failed.append((e, repr(exc)))
            logger.exception("[%d/%d] %s FAILED", k, len(todo), e)
            continue
        read_part.cache_clear()
        rows.append({"expiry": e, "rows": len(g), "mb": size / 1e6, **q})
        logger.info("[%d/%d] %s: %d rows, %.1f MB, near-ATM IV %.1f%%, CE/PE IV gap %.2f pt, ATM IV %.1f-%.1f, %.0fs",
                    k, len(todo), e, len(g), size / 1e6, q["iv_cover"] * 100, q["ce_pe_gap"],
                    q["atm_iv_min"], q["atm_iv_max"], time.monotonic() - t0)
    t = pd.DataFrame(rows)
    lines = ["=" * 78, "NIFTY OPTIONS IV / GREEKS -- summary", "=" * 78,
             f"computed : {len(rows)} expiries, {int(t['rows'].sum()) if len(t) else 0:,} rows",
             f"skipped  : {len(skipped)} already in R2", f"failed   : {len(failed)}"]
    lines += [f"   {e}: {err}" for e, err in failed]
    if len(t):
        lines += [f"near-ATM minutes with an IV : median {t['iv_cover'].median():.1%}, worst {t['iv_cover'].min():.1%} "
                  f"({t.loc[t['iv_cover'].idxmin(), 'expiry']})",
                  f"CE vs PE IV gap, same strike: median {t['ce_pe_gap'].median():.2f} pt, worst {t['ce_pe_gap'].max():.2f} pt "
                  f"({t.loc[t['ce_pe_gap'].idxmax(), 'expiry']})",
                  f"daily ATM IV range          : {t['atm_iv_min'].min():.1f} .. {t['atm_iv_max'].max():.1f}"]
        low = t[(t["iv_cover"] < 0.95) | (t["ce_pe_gap"] > 0.5)]
        if len(low):
            lines.append("check (IV cover < 95% or CE/PE gap > 0.5 pt): " + ", ".join(str(e) for e in low["expiry"]))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compute IV/Greeks for the expired Nifty option archive")
    ap.add_argument("--candidates", action="store_true", help="only expiries of the candidate days")
    ap.add_argument("--expiry", type=lambda v: date.fromisoformat(v))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true", help="recompute expiries already stored")
    args = ap.parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "greeks_run.log", mode="w", encoding="utf-8")])
    try:
        lines = run(args.expiry, args.candidates, args.limit, args.force)
    except Exception:
        logger.exception("Greeks run failed")
        return 1
    text = "\n".join(lines)
    (LOG_DIR / "greeks_summary.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
