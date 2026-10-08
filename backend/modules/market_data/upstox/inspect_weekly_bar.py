"""
modules/market_data/upstox/inspect_weekly_bar.py

READ-ONLY probe (no R2 writes, no Supabase): explains why a weekly bar's high/low differs
from the daily bars inside the same week. Found by audit_ohlcv_data on the week of
2026-08-24: in 78 of 208 watchlist stocks the 1w high was ABOVE and the 1w low BELOW the
range of that week's daily bars (up to 3.4%), while intraday and daily agreed with each
other -- so the weekly bar is the odd one out.

For each stock this prints:
  - the stored 1w bar(s) around the week, with raw ts/trade_date
  - the daily bars from the previous Friday to the next Monday
  - which date-window REPRODUCES the weekly high/low (Mon-Fri only? plus prev Fri? plus next Mon?),
    and which single day each extreme came from.

Run from backend/:
    python -m modules.market_data.upstox.inspect_weekly_bar
    python -m modules.market_data.upstox.inspect_weekly_bar --keys "NSE_EQ|INE003A01024" --week-start 2026-08-24
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

# Siemens (largest gap, -3.43% low), Reliance (+0.22% high), Hindustan Unilever-size sample
DEFAULT_KEYS = ["NSE_EQ|INE003A01024", "NSE_EQ|INE002A01018", "NSE_EQ|INE019A01038"]
DEFAULT_WEEK_START = "2026-08-24"       # a Monday
TOL = 0.0005                            # 0.05% -- "reproduces" tolerance


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["td"] = pd.to_datetime(out["trade_date"]).dt.normalize()
    return out


def explain(df: pd.DataFrame, week_start: pd.Timestamp) -> list[str]:
    """Return printable lines explaining the weekly bar vs the daily bars (pure, testable)."""
    lines: list[str] = []
    d = _prep(df)
    daily = d[d["timeframe"] == "1d"].sort_values("td").drop_duplicates("td", keep="last").set_index("td")
    weekly = d[d["timeframe"] == "1w"].sort_values("td")

    near = weekly[(weekly["td"] >= week_start - pd.Timedelta(days=8)) &
                  (weekly["td"] <= week_start + pd.Timedelta(days=8))]
    lines.append("  stored 1w bars near the week:")
    for r in near.itertuples():
        lines.append(f"    ts={r.ts}  trade_date={r.trade_date}  O={r.open:.2f} H={r.high:.2f} L={r.low:.2f} C={r.close:.2f} V={r.volume:.0f}")

    wk = weekly[weekly["td"] == week_start]
    if wk.empty:
        lines.append(f"  !! no 1w bar dated {week_start:%Y-%m-%d}")
        return lines
    wh, wl = float(wk["high"].iloc[0]), float(wk["low"].iloc[0])

    wv = float(wk["volume"].iloc[0])
    dv = float(daily.loc[week_start:week_start + pd.Timedelta(days=4), "volume"].sum())
    lines.append(f"  weekly volume={wv:.0f}  sum of Mon-Fri daily volume={dv:.0f}  "
                 f"-> volume not in our daily bars: {wv - dv:.0f} ({(wv - dv) / wv:+.1%} of weekly)" if wv else "  weekly volume=0")

    lo, hi = week_start - pd.Timedelta(days=3), week_start + pd.Timedelta(days=7)
    lines.append("  daily bars (prev Fri .. next Mon):")
    for dt, r in daily.loc[lo:hi].iterrows():
        mark = ""
        if abs(r["high"] - wh) / wh <= TOL:
            mark += "  <- equals WEEKLY HIGH"
        if abs(r["low"] - wl) / wl <= TOL:
            mark += "  <- equals WEEKLY LOW"
        lines.append(f"    {dt:%a %Y-%m-%d}  H={r['high']:.2f} L={r['low']:.2f} C={r['close']:.2f} V={r['volume']:.0f}{mark}")

    windows = {
        "Mon-Fri of the week": (week_start, week_start + pd.Timedelta(days=4)),
        "prev Fri + Mon-Fri": (week_start - pd.Timedelta(days=3), week_start + pd.Timedelta(days=4)),
        "Mon-Fri + next Mon": (week_start, week_start + pd.Timedelta(days=7)),
        "prev Fri .. next Mon": (week_start - pd.Timedelta(days=3), week_start + pd.Timedelta(days=7)),
    }
    lines.append(f"  weekly H={wh:.2f} L={wl:.2f}; which daily window reproduces both?")
    found = False
    for name, (a, b) in windows.items():
        w = daily.loc[a:b]
        if w.empty:
            continue
        h, l = float(w["high"].max()), float(w["low"].min())
        ok = abs(h - wh) / wh <= TOL and abs(l - wl) / wl <= TOL
        found |= ok
        lines.append(f"    {name:<22} daily H={h:.2f} L={l:.2f}  {'MATCH' if ok else 'no'}")
    if not found:
        lines.append("    -> no window reproduces the weekly bar: the extreme is not in our daily bars at all")
    return lines


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.WARNING)
    p = argparse.ArgumentParser(description="Read-only weekly-bar probe.")
    p.add_argument("--keys", nargs="+", default=DEFAULT_KEYS)
    p.add_argument("--week-start", default=DEFAULT_WEEK_START, help="Monday of the week, YYYY-MM-DD")
    args = p.parse_args()

    from modules.market_data.upstox.ohlcv_store import read_candles
    ws = pd.Timestamp(args.week_start)
    for key in args.keys:
        print("\n" + "=" * 78)
        print(key)
        df = read_candles(key, "universe")
        if df is None:
            print("  no file in R2")
            continue
        print("\n".join(explain(df, ws)))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
