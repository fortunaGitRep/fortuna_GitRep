"""
modules/market_data/upstox/test_index_intraday.py

READ-ONLY spike: can Upstox's V3 historical-candle API serve 5m/15m/60m for NSE
INDEX keys on the free Analytics Token? No R2 writes, no ledger/Supabase access.

Run from backend/:
    python -m modules.market_data.upstox.test_index_intraday
    python -m modules.market_data.upstox.test_index_intraday --keys "NSE_INDEX|Nifty 50" "NSE_INDEX|Nifty Bank"
    python -m modules.market_data.upstox.test_index_intraday --days 30      # quick smoke first

What it reports per (index, timeframe):
  - OK/FAIL and the first error (e.g. UDAPI1148 range, 401, empty window)
  - candle count, first/last timestamp, distinct trading days
  - bars per full day (expect ~75 for 5m, ~25 for 15m, ~7 for 60m on NSE)
  - volume: how many candles have volume non-null / > 0 (indices often report 0 or null)
  - one sample candle from each end
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date, timedelta

from dotenv import load_dotenv

from modules.market_data.upstox._ohlcv_engine import fetch_full_history

# Defined locally so this test doesn't depend on the engine's INTRADAY_TIMEFRAMES name.
TEST_TIMEFRAMES = (("minutes", "5"), ("minutes", "15"), ("minutes", "60"))
DEFAULT_KEYS = ["NSE_INDEX|Nifty 50"]


def _report(key: str, unit: str, interval: str, from_d: date, to_d: date) -> bool:
    label = f"{interval}m"
    res = fetch_full_history(key, unit, interval, from_date=from_d, to_date=to_d)
    print("-" * 72)
    if not res.ok:
        print(f"  {label:<4} FAIL  {res.error}")
        return False

    c = res.candles
    days = Counter(x.trade_date for x in c)
    # Bars on a typical full session = the most common per-day count.
    typical = Counter(days.values()).most_common(1)[0][0]
    vol_non_null = sum(1 for x in c if x.volume is not None)
    vol_positive = sum(1 for x in c if x.volume and x.volume > 0)

    print(f"  {label:<4} OK    {len(c):>7,} candles over {len(days)} trading days")
    print(f"        range : {c[0].ts.isoformat()}  ..  {c[-1].ts.isoformat()}")
    print(f"        bars/day (typical): {typical}")
    print(f"        volume: non-null {vol_non_null:,}/{len(c):,}   >0 {vol_positive:,}/{len(c):,}")
    print(f"        oldest: O={c[0].open:.2f} H={c[0].high:.2f} L={c[0].low:.2f} C={c[0].close:.2f} V={c[0].volume}")
    print(f"        newest: O={c[-1].open:.2f} H={c[-1].high:.2f} L={c[-1].low:.2f} C={c[-1].close:.2f} V={c[-1].volume}")
    return True


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Index intraday availability spike (read-only).")
    p.add_argument("--keys", nargs="+", default=DEFAULT_KEYS, help="instrument keys to test")
    p.add_argument("--days", type=int, default=365, help="lookback in days (default 365)")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    to_d = date.today()
    from_d = to_d - timedelta(days=args.days)

    print("\n" + "=" * 72)
    print("INDEX INTRADAY SPIKE  (read-only: no R2, no Supabase)")
    print(f"window: {from_d} .. {to_d}  ({args.days} days)")
    print("=" * 72)

    all_ok = True
    for key in args.keys:
        print(f"\n{key}")
        for unit, interval in TEST_TIMEFRAMES:
            all_ok &= _report(key, unit, interval, from_d, to_d)

    print("\n" + "=" * 72)
    print("RESULT:", "ALL TIMEFRAMES OK" if all_ok else "SOME TIMEFRAMES FAILED - see above")
    print("=" * 72 + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
