"""
modules/market_data/upstox/fetch_universe_options_intraday_ohlcv.py

Thin one-time backfill caller for intraday OHLCV — options-eligible (F&O) stocks
only, NOT the full universe. All orchestration logic lives in
_ohlcv_backfill_runner.py; this file just supplies the domain-specific config.

Scope decisions (locked 2026-09-04, see build log):
  - F&O-eligible subset only (is_fno_eligible=True on f_universe_instruments),
    not all 2,296 stocks — options trading only needs optionable names.
  - Timeframes: 5m/15m/60m (INTRADAY_TIMEFRAMES) — enough resolution for
    intraday indicator screening without 1-minute's much larger row volume.
  - Backfill bounded to 1 year back, not the engine's full since-2022 default —
    indicators need a few hundred bars of lookback, not years; storage cost is
    trivial either way (~1GB/200 stocks/4.5yr) but redundant fetch time isn't
    free, so bound it to what's actually useful.

Usage:
    python -m modules.market_data.upstox.fetch_universe_options_intraday_ohlcv --limit 5
    python -m modules.market_data.upstox.fetch_universe_options_intraday_ohlcv
"""

from datetime import date, timedelta

from modules.market_data.upstox._ohlcv_backfill_runner import DomainConfig, cli_main
from modules.market_data.upstox._ohlcv_engine import INTRADAY_TIMEFRAMES

OPTIONS_INTRADAY_CONFIG = DomainConfig(
    domain="universe_intraday",
    catalogue_table="f_universe_instruments",
    timeframes=INTRADAY_TIMEFRAMES,
    extra_filter_column="is_fno_eligible",
    extra_filter_value=True,
    backfill_from_date=date.today() - timedelta(days=365),
)

if __name__ == "__main__":
    cli_main(OPTIONS_INTRADAY_CONFIG)
