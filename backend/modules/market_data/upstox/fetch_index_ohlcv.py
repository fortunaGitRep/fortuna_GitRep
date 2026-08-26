"""
modules/market_data/upstox/fetch_index_ohlcv.py

Bulk OHLCV backfill for the INDEX domain (Domains 2 + 3). Thin caller over the shared
_ohlcv_backfill_runner — all orchestration lives there; this file only specifies WHICH
domain (indices) and WHICH catalogue table (f_all_nse_index_instruments).

(Refactored 2026-08-24: the orchestration that was here moved into
_ohlcv_backfill_runner so the universe caller can share it. Behaviour is unchanged from
the proven 135-index run — verify with `--limit 1` after deploying.)

Run:
  verify-first:  python -m modules.market_data.upstox.fetch_index_ohlcv --limit 3
  full run:      python -m modules.market_data.upstox.fetch_index_ohlcv [--quiet]
"""

from __future__ import annotations

from modules.market_data.upstox._ohlcv_backfill_runner import DomainConfig, cli_main

INDEX_CONFIG = DomainConfig(
    domain="indices",
    catalogue_table="f_all_nse_index_instruments",
)


if __name__ == "__main__":
    cli_main(INDEX_CONFIG)
