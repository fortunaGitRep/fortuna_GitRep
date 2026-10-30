"""
Read-only audit of the expired Nifty contracts archive in R2 (options band 1m, rest-of-chain
30m, futures 1m). Reads every stored file, makes 1 Upstox call (expiry list), writes nothing
to R2.

Per option expiry (band file):
  present / rows / contracts / days
  strikes   : every trading day in the window has every CE and PE from (day low - 9 strikes)
              to (day high + 9 strikes)                         -> missing ones listed
  ATM bars  : CE and PE nearest the 09:15 Nifty open have 1m bars each trading day;
              days with < MIN_ATM_BARS bars listed
  nifty     : every trading day of the window has Nifty 5m bars (else the band is unverified)
  hygiene   : no bars at/after the close, no non-positive prices, no duplicate (contract, ts)
  chain     : band and rest share no contract
Per option expiry (rest file): present / rows / contracts / hygiene
Per futures month: one file, one contract, trading days covered vs Nifty days, bars per day

Run from backend/:
  python -m modules.market_data.upstox.audit_expired_archive
Output: logs/expired_options_audit_logs/audit.log (+ screen) and audit_by_expiry.csv
"""

from __future__ import annotations

import io
import logging
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from db.r2_client import get_r2, get_r2_settings
from modules.market_data.upstox.fetch_expired_nifty_options import (
    PARTS,
    PREVIOUS_WEEK_DAYS,
    after_close,
    STRIKE_STEP,
    STRIKES_EACH_SIDE,
    month_candidates,
    week_windows,
)
from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.market_data.upstox.probe_expired_contracts import get_expiries

NIFTY_KEY = "NSE_INDEX|Nifty 50"
MIN_ATM_BARS = 300                       # of 375 1m bars in a full session
LOG_DIR = Path("logs") / "expired_options_audit_logs"
logger = logging.getLogger(__name__)


class R2:
    def __init__(self):
        self.r2, self.bucket = get_r2(), get_r2_settings().bucket

    def listing(self, prefix: str) -> dict[str, int]:
        out, token = {}, None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix + "/"}
            if token:
                kw["ContinuationToken"] = token
            resp = self.r2.list_objects_v2(**kw)
            out.update({o["Key"]: o.get("Size", 0) for o in resp.get("Contents", [])})
            if not resp.get("IsTruncated"):
                return out
            token = resp.get("NextContinuationToken")

    def read(self, key: str) -> pd.DataFrame:
        body = self.r2.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return pd.read_parquet(io.BytesIO(body), engine="pyarrow")


SHORT_SESSION_BARS = 40                  # Nifty 5m bars; a full day has 75, Muhurat ~12


def hygiene(df: pd.DataFrame, short_days: set) -> list[str]:
    """short_days: special short sessions (Muhurat) where evening bars are correct."""
    issues = []
    ts = pd.to_datetime(df["ts"])
    late_mask = after_close(ts) & ~ts.dt.date.isin(short_days)
    late = int(late_mask.sum())
    if late:
        issues.append(f"{late} bars after the F&O close on regular days")
    bad = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    if bad:
        issues.append(f"{bad} bars with non-positive price")
    dup = int(df.duplicated(["instrument_key", "ts"]).sum())
    if dup:
        issues.append(f"{dup} duplicate bars")
    return issues


def check_band(df: pd.DataFrame, days: list[date], nifty_day: pd.DataFrame, short_days: set) -> list[str]:
    issues = []
    have = set(zip(df["strike"].astype(float), df["option_type"]))
    bars = df.assign(trade_date=pd.to_datetime(df["trade_date"]).dt.date) \
             .groupby(["strike", "option_type", "trade_date"]).size()
    missing_strikes, thin = set(), []
    for d in days:
        if d not in nifty_day.index:
            continue
        row = nifty_day.loc[d]
        lo = math.floor(row["low"] / STRIKE_STEP) * STRIKE_STEP - STRIKES_EACH_SIDE * STRIKE_STEP
        hi = math.ceil(row["high"] / STRIKE_STEP) * STRIKE_STEP + STRIKES_EACH_SIDE * STRIKE_STEP
        for k in range(int(lo), int(hi) + 1, STRIKE_STEP):
            for t in ("CE", "PE"):
                if (float(k), t) not in have:
                    missing_strikes.add(f"{k}{t}")
        atm = float(round(row["open"] / STRIKE_STEP) * STRIKE_STEP)
        if d in short_days:
            continue
        for t in ("CE", "PE"):
            n = int(bars.get((atm, t, d), 0))
            if n < MIN_ATM_BARS:
                thin.append(f"{d} {int(atm)}{t}={n}")
    if missing_strikes:
        issues.append(f"{len(missing_strikes)} required strikes missing: {sorted(missing_strikes)[:8]}")
    if thin:
        issues.append(f"{len(thin)} ATM day(s) under {MIN_ATM_BARS} bars: {thin[:6]}")
    return issues


def run() -> tuple[list[str], pd.DataFrame]:
    r2 = R2()
    expiries = get_expiries()
    d1 = read_for_indicators(NIFTY_KEY, "indices", "1d")
    n5 = read_for_indicators(NIFTY_KEY, "universe_intraday", "5m")
    if not (d1.ok and n5.ok):
        raise RuntimeError(f"Nifty read failed: {d1.error or n5.error}")
    trading = sorted(pd.to_datetime(d1.df["trade_date"]).dt.date.unique())
    f5 = n5.df.assign(trade_date=pd.to_datetime(n5.df["trade_date"]).dt.date)
    nifty_day = f5.groupby("trade_date").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                             bars=("open", "size"))
    short_days = set(nifty_day.index[nifty_day["bars"] < SHORT_SESSION_BARS])

    files = {p: r2.listing(PARTS[p]["prefix"]) for p in PARTS}
    rows, lines = [], ["=" * 78, "EXPIRED NIFTY ARCHIVE AUDIT", "=" * 78,
                       f"expiries listed by Upstox: {len(expiries)} ({expiries[0]} .. {expiries[-1]})", ""]

    for week_start, expiry in week_windows(expiries):
        window = [d for d in trading if week_start - timedelta(days=PREVIOUS_WEEK_DAYS) <= d <= expiry]
        rec = {"part": "options", "expiry": expiry, "window_days": len(window)}
        issues = []
        band_key, rest_key = (f"{PARTS[p]['prefix']}/{expiry}.parquet" for p in ("band", "rest"))
        band = rest = None
        no_nifty = [d for d in window if d not in nifty_day.index]
        if nifty_day.index.max() < expiry:
            issues.append(f"Nifty 5m data ends {nifty_day.index.max()}, before this expiry -- strike band not "
                          "verified; update Nifty, then refetch with --expiry --force")
        elif no_nifty:
            issues.append(f"Nifty 5m missing for {len(no_nifty)} window day(s) {[str(d) for d in no_nifty[:4]]} "
                          "-- strike band not verified; update Nifty, then refetch with --expiry --force")
        if band_key in files["band"]:
            band = r2.read(band_key)
            rec.update(band_rows=len(band), band_contracts=band["instrument_key"].nunique(),
                       band_days=pd.to_datetime(band["trade_date"]).dt.date.nunique() if len(band) else 0)
            if band.empty:
                issues.append("band file has 0 rows")
            else:
                issues += [f"band: {x}" for x in hygiene(band, short_days)]
                issues += [f"band: {x}" for x in check_band(band, window, nifty_day, short_days)]
                if rec["band_days"] < len(window):
                    got = set(pd.to_datetime(band["trade_date"]).dt.date)
                    issues.append(f"band: trading days with no bars: {[str(d) for d in window if d not in got][:6]}")
        else:
            issues.append("band file MISSING")
        if rest_key in files["rest"]:
            rest = r2.read(rest_key)
            rec.update(rest_rows=len(rest), rest_contracts=rest["instrument_key"].nunique())
            issues += [f"rest: {x}" for x in hygiene(rest, short_days)] if len(rest) else ["rest file has 0 rows"]
        else:
            issues.append("rest file MISSING")
        if band is not None and rest is not None:
            both = set(band["instrument_key"]) & set(rest["instrument_key"])
            if both:
                issues.append(f"{len(both)} contracts in both band and rest")
        rec["issues"] = "; ".join(issues)
        rows.append(rec)

    stored_fut = {Path(k).stem for k in files["futures"]}
    prev = None
    for (y, m), cands in month_candidates(expiries):
        found = next((e for e in cands if str(e) in stored_fut), None)
        rec = {"part": "futures", "expiry": found or cands[0]}
        if found is None:
            pending = (y, m) >= (date.today().year, date.today().month)
            rec["issues"] = "not expired yet" if pending else "futures file MISSING"
            rows.append(rec)
            continue
        df = r2.read(f"{PARTS['futures']['prefix']}/{found}.parquet")
        days = pd.to_datetime(df["trade_date"]).dt.date
        start = (prev or found - timedelta(days=35))
        want = [d for d in trading if start < d <= found]
        per_day = df.assign(d=days).groupby("d").size()
        issues = hygiene(df, short_days) if len(df) else ["0 rows"]
        if df["instrument_key"].nunique() != 1:
            issues.append(f"{df['instrument_key'].nunique()} contracts in file")
        miss = [str(d) for d in want if d not in set(days)]
        if miss:
            issues.append(f"{len(miss)} trading days with no bars: {miss[:6]}")
        thin = per_day[(per_day < MIN_ATM_BARS) & ~per_day.index.isin(short_days)]
        if len(thin):
            issues.append(f"{len(thin)} day(s) under {MIN_ATM_BARS} bars: {[f'{d}={n}' for d, n in thin.head(4).items()]}")
        rec.update(rows=len(df), days=int(days.nunique()), issues="; ".join(issues))
        rows.append(rec)
        prev = found

    t = pd.DataFrame(rows)
    opt, fut = t[t["part"] == "options"], t[t["part"] == "futures"]
    clean_o = opt[opt["issues"] == ""]
    clean_f = fut[fut["issues"] == ""]
    lines += [
        f"short sessions (Muhurat etc., not flagged): {', '.join(map(str, sorted(short_days & set(trading[-600:]))))}",
        f"OPTIONS  {len(clean_o)} of {len(opt)} expiries clean",
        f"   band 1m   : {int(opt['band_rows'].fillna(0).sum()):,} rows, "
        f"{int(opt['band_contracts'].fillna(0).sum()):,} contracts, files {len(files['band'])}",
        f"   rest 30m  : {int(opt['rest_rows'].fillna(0).sum()):,} rows, "
        f"{int(opt['rest_contracts'].fillna(0).sum()):,} contracts, files {len(files['rest'])}",
        f"FUTURES  {len(clean_f)} of {len(fut)} months clean, files {len(files['futures'])}",
        "", "ISSUES (expiry: what)",
    ]
    for r in t[t["issues"] != ""].itertuples():
        lines.append(f"   {r.part:<8} {r.expiry}: {r.issues}")
    if (t["issues"] == "").all():
        lines.append("   none")
    return lines, t


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    try:
        lines, table = run()
    except Exception:
        logger.exception("Audit failed")
        return 1
    table.to_csv(LOG_DIR / "audit_by_expiry.csv", index=False)
    text = "\n".join(lines)
    (LOG_DIR / "audit.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
