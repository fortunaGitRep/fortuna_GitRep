"""
Map each sample-day candidate to the contracts to look at (test plan TC-DATA-05, TC-SEL-07).

Per candidate day:
  expiry       first stored weekly expiry on/after the day (real archive dates, holiday shifts included)
  week_start   day after the previous expiry (the weekly chart starts here)
  atm          strike nearest the Nifty 09:15 5m open
  strikes      CE: ITM2 = ATM-100, ATM, OTM2 = ATM+100   PE: ITM2 = ATM+100, ATM, OTM2 = ATM-100
  futures      near-month futures: first stored futures expiry on/after the day
  flags        known gaps: week not stored / empty, strike with no bars that day, no futures

Run from backend/:
  python -m modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.candidate_contracts
  ... --candidates logs/options_sample_days_logs/candidates.csv   (default)
Output: logs/options_candidate_charts/candidate_contracts.csv (+ screen)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from modules.market_data.upstox.expired_archive_reader import read_part, stored_expiries
from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

NIFTY_KEY = "NSE_INDEX|Nifty 50"
STRIKE_STEP = 50
OFFSET_STRIKES = 2
DEFAULT_CANDIDATES = Path("logs") / "options_sample_days_logs" / "candidates.csv"
OUT_DIR = Path("logs") / "options_candidate_charts"
LEGS = ("ce_itm2", "ce_atm", "ce_otm2", "pe_itm2", "pe_atm", "pe_otm2")
logger = logging.getLogger(__name__)


def leg_strikes(atm: float) -> dict[str, float]:
    k = OFFSET_STRIKES * STRIKE_STEP
    return {"ce_itm2": atm - k, "ce_atm": atm, "ce_otm2": atm + k,
            "pe_itm2": atm + k, "pe_atm": atm, "pe_otm2": atm - k}


def nifty_opens(five: pd.DataFrame) -> dict[date, float]:
    f = five.assign(trade_date=pd.to_datetime(five["trade_date"]).dt.date).sort_values("ts")
    return f.groupby("trade_date")["open"].first().to_dict()


def map_day(day: date, open_0915: float | None, all_expiries: list[date],
            band_expiries: set[date], fut_expiries: list[date]) -> dict:
    row: dict = {"trade_date": day}
    flags = []
    expiry = next((e for e in all_expiries if e >= day), None)
    if expiry is None:
        return {**row, "flags": "no expiry on/after this day in the archive"}
    prev = max((e for e in all_expiries if e < expiry), default=None)
    row.update(expiry=expiry, week_start=(prev + timedelta(days=1)) if prev else expiry - timedelta(days=7),
               dte_calendar=(expiry - day).days)
    if open_0915 is None:
        flags.append("no Nifty 5m data for this day")
    else:
        atm = float(round(open_0915 / STRIKE_STEP) * STRIKE_STEP)
        row.update(nifty_open_0915=open_0915, atm=atm, **leg_strikes(atm))
    if expiry not in band_expiries:
        flags.append("options week not stored or empty (known gap)")
    elif "atm" in row:
        band = read_part("band", expiry)
        have = band[band["trade_date"] == day].groupby(["strike", "option_type"]).size()
        for leg in LEGS:
            typ = leg[:2].upper()
            if int(have.get((row[leg], typ), 0)) == 0:
                flags.append(f"{leg} {int(row[leg])}{typ} has no bars this day")
    fut = next((e for e in fut_expiries if e >= day), None)
    row["futures_expiry"] = fut
    if fut is None:
        flags.append("no futures stored for this day (known gap)")
    row["flags"] = "; ".join(flags)
    return row


def build(candidates: pd.DataFrame) -> pd.DataFrame:
    n5 = read_for_indicators(NIFTY_KEY, "universe_intraday", "5m")
    if not n5.ok:
        raise RuntimeError(f"Nifty 5m read failed: {n5.error}")
    opens = nifty_opens(n5.df)
    band_exp = set(stored_expiries("band"))
    all_exp = sorted(band_exp | set(stored_expiries("rest")))   # rest also stores the gap week
    fut_exp = list(stored_expiries("futures"))
    cands = candidates.copy()
    cands["trade_date"] = pd.to_datetime(cands["trade_date"]).dt.date
    rows = [map_day(d, opens.get(d), all_exp, band_exp, fut_exp) for d in cands["trade_date"]]
    out = pd.DataFrame(rows)
    keep = [c for c in ("trade_date", "weekday", "era", "dte", "colour", "body_ratio", "phase", "move_timing",
                        "gap_type", "window_move_pts", "covers") if c in cands.columns]
    return cands[keep].merge(out, on="trade_date", how="left")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Map candidate days to their option and futures contracts")
    ap.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    try:
        table = build(pd.read_csv(args.candidates))
    except Exception:
        logger.exception("Mapping failed")
        return 1
    path = OUT_DIR / "candidate_contracts.csv"
    table.to_csv(path, index=False)
    flagged = table[table["flags"].fillna("") != ""]
    lines = [f"candidates mapped : {len(table)} -> {path}",
             f"expiries used     : {table['expiry'].nunique()}, futures months: {table['futures_expiry'].nunique()}",
             f"flagged           : {len(flagged)}"]
    lines += [f"   {r.trade_date}: {r.flags}" for r in flagged.itertuples()]
    text = "\n".join(lines)
    (OUT_DIR / "candidate_contracts.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
