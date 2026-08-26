"""
modules/market_data/upstox/fetch_universe_ohlcv.py

Bulk OHLCV backfill for the UNIVERSE domain (Domain 1 — the ~2,643 NSE equities).
Thin caller over the shared _ohlcv_backfill_runner — identical machinery to the index
backfill, differing only in domain ('universe') and catalogue table
(f_universe_instruments).

SCALE NOTE: this is the big run. ~2,643 stocks × ~5 calls ≈ 13,000 API calls, spanning
multiple of Upstox's 1000-per-30-min windows. At 0.25s/instrument throttle plus fetch
time, expect roughly 15–25 minutes. The ledger-based resumability is what makes this
safe: if it stalls (rate-limit pause) or you stop it, re-running skips done stocks and
resumes where it left off. Expect some `failed` — delisted/illiquid names, or newly
listed stocks with sparse data (handled gracefully, isolated, don't block the run).

Run:
  verify-first:  python -m modules.market_data.upstox.fetch_universe_ohlcv --limit 3
  full run:      python -m modules.market_data.upstox.fetch_universe_ohlcv --quiet
"""

from __future__ import annotations

from modules.market_data.upstox._ohlcv_backfill_runner import DomainConfig, cli_main

UNIVERSE_CONFIG = DomainConfig(
    domain="universe",
    catalogue_table="f_universe_instruments",
)


if __name__ == "__main__":
    cli_main(UNIVERSE_CONFIG)
