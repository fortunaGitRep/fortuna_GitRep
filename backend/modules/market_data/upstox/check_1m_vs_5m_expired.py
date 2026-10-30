"""
Read-only check: does 5m built from Upstox's 1m candles match Upstox's own 5m candles
for expired Nifty options? Decides whether the archive can store 1m only.

For the oldest, middle and newest expiry, three contracts each:
  ATM CE, far OTM CE (ATM + 9 strikes), far OTM PE (ATM - 9 strikes)
ATM = strike nearest the middle of that week's Nifty range. Window = the expiry week.
Each contract: fetch 1minute and 5minute, apply the same rules as the fetcher (drop
bars at/after 15:30 and non-positive prices), build 5m from 1m, compare bar by bar:
  open = first, high = max, low = min, close = last, volume = sum, oi = last (at bar close)
~22 calls. Stores nothing.

Run from backend/:
  python -m modules.market_data.upstox.check_1m_vs_5m_expired
Output: logs/expired_contracts_probe_logs/check_1m_vs_5m.log (also on screen)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from modules.market_data.upstox.fetch_expired_nifty_options import (
    NIFTY_KEY,
    STRIKE_STEP,
    STRIKES_EACH_SIDE,
    _paced,
    candles_frame,
    week_windows,
)
from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.market_data.upstox.probe_expired_contracts import (
    ProbeError,
    get_candles,
    get_contracts,
    get_expiries,
)

LOG_DIR = Path("logs") / "expired_contracts_probe_logs"
PRICE_TOL = 0.001
FIELDS = ("open", "high", "low", "close", "volume", "oi")
SHOW = 5
logger = logging.getLogger(__name__)


def build_5m(one: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1m bars to 5m buckets labelled by start time (09:15 = 09:15-09:20)."""
    if one.empty:
        return one
    g = one.assign(bucket=one["ts"].dt.floor("5min")).groupby("bucket", sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum(), "oi": g["oi"].last()})
    return out.rename_axis("ts").reset_index()


def compare(five: pd.DataFrame, built: pd.DataFrame) -> dict:
    m = five[["ts", *FIELDS]].merge(built, on="ts", how="outer", suffixes=("_5m", "_1m"), indicator=True)
    both = m[m["_merge"] == "both"]
    res = {"bars_5m": len(five), "bars_built": len(built),
           "only_5m": m.loc[m["_merge"] == "left_only", "ts"].tolist(),
           "only_1m": m.loc[m["_merge"] == "right_only", "ts"].tolist(), "diffs": {}}
    for f in FIELDS:
        a, b = both[f + "_5m"].astype(float), both[f + "_1m"].astype(float)
        tol = PRICE_TOL if f in ("open", "high", "low", "close") else 0
        bad = both[((a - b).abs() > tol) & ~(a.isna() & b.isna())]
        if len(bad):
            res["diffs"][f] = [(r.ts, getattr(r, f + "_5m"), getattr(r, f + "_1m")) for r in bad.head(SHOW).itertuples()]
            res["diffs"][f].insert(0, len(bad))
    return res


def pick(contracts: list[dict], mid: float) -> list[tuple[str, dict]]:
    atm = round(mid / STRIKE_STEP) * STRIKE_STEP
    want = [("ATM CE", atm, "CE"), (f"ATM+{STRIKES_EACH_SIDE} CE", atm + STRIKES_EACH_SIDE * STRIKE_STEP, "CE"),
            (f"ATM-{STRIKES_EACH_SIDE} PE", atm - STRIKES_EACH_SIDE * STRIKE_STEP, "PE")]
    out = []
    for label, strike, typ in want:
        c = next((c for c in contracts if float(c.get("strike_price", 0)) == strike
                  and c.get("instrument_type") == typ), None)
        if c:
            out.append((label, c))
    return out


def run() -> list[str]:
    n5 = read_for_indicators(NIFTY_KEY, "universe_intraday", "5m")
    if not n5.ok:
        raise RuntimeError(f"Nifty 5m read failed: {n5.error}")
    nifty = n5.df.assign(trade_date=pd.to_datetime(n5.df["trade_date"]).dt.date)
    weeks = week_windows(_paced(get_expiries))
    chosen = [weeks[0], weeks[len(weeks) // 2], weeks[-1]]
    lines = ["=" * 78, "CHECK: 5m built from 1m vs Upstox 5m -- expired Nifty options", "=" * 78]
    totals = {"contracts": 0, "clean": 0}
    for start, expiry in chosen:
        wk = nifty[(nifty["trade_date"] >= start) & (nifty["trade_date"] <= expiry)]
        lines.append(f"--- expiry {expiry} ({expiry:%a}), window {start} .. {expiry}")
        if wk.empty:
            lines += ["   no Nifty 5m data for this week -- skipped", ""]
            continue
        mid = (float(wk["low"].min()) + float(wk["high"].max())) / 2
        try:
            contracts = _paced(get_contracts, expiry)
        except ProbeError as exc:
            lines += [f"   contracts FAILED: {exc}", ""]
            continue
        for label, c in pick(contracts, mid):
            sym = c.get("trading_symbol", c["instrument_key"])
            try:
                one = candles_frame(_paced(get_candles, c["instrument_key"], "1minute", expiry, start), c, expiry, start)
                five = candles_frame(_paced(get_candles, c["instrument_key"], "5minute", expiry, start), c, expiry, start)
            except ProbeError as exc:
                lines.append(f"   {label:<10} {sym}: FAILED -- {exc}")
                continue
            totals["contracts"] += 1
            r = compare(five, build_5m(one))
            clean = not (r["only_5m"] or r["only_1m"] or r["diffs"])
            totals["clean"] += clean
            lines.append(f"   {label:<10} {sym}: 1m bars {len(one)}, 5m bars {r['bars_5m']}, built {r['bars_built']}"
                         f"  -> {'MATCH' if clean else 'DIFFERENT'}")
            if r["only_5m"]:
                lines.append(f"      5m bars with no 1m data: {len(r['only_5m'])}, e.g. {[str(t) for t in r['only_5m'][:SHOW]]}")
            if r["only_1m"]:
                lines.append(f"      built bars missing from 5m: {len(r['only_1m'])}, e.g. {[str(t) for t in r['only_1m'][:SHOW]]}")
            for f, d in r["diffs"].items():
                lines.append(f"      {f}: {d[0]} bars differ; (time, 5m, built): {[(str(t), a, b) for t, a, b in d[1:]]}")
        lines.append("")
    lines.append(f"RESULT: {totals['clean']} of {totals['contracts']} contracts match exactly")
    return lines


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    try:
        lines = run()
    except Exception:
        logger.exception("Check failed")
        return 1
    text = "\n".join(lines)
    (LOG_DIR / "check_1m_vs_5m.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
