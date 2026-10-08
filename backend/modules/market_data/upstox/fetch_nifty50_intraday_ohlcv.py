"""
modules/market_data/upstox/fetch_nifty50_intraday_ohlcv.py

Thin one-time backfill caller for Nifty 50 INTRADAY OHLCV (5m/15m/60m, full history
since Jan 2022).
All orchestration lives in _ohlcv_backfill_runner.py; this file only supplies the
config. Nifty 50 rides the existing 'universe_intraday' ledger domain, so:
  - the daily refresh needs NO new script: refresh_universe_options_intraday_ohlcv
    already refreshes every instrument whose intraday ledger status is 'done';
  - the Parquet lands in upstox/nse_indexes_intraday/Nifty_50.parquet (ohlcv_store
    routes NSE_INDEX keys there);
  - the log is logs/ohlcv_backfill_Nifty_50_intraday.log.

Verified 2026-10-08 (read-only spike): Upstox serves 5m/15m/60m for NSE_INDEX keys on
the free Analytics Token, back to 2022-01-03, volume always 0.0 (an index has no volume).

To add another index later: copy the config below with its own instrument_key and
log_name (e.g. 'Nifty_Bank_intraday'). No other change needed.

Usage:
    python -m modules.market_data.upstox.fetch_nifty50_intraday_ohlcv --limit 1
    python -m modules.market_data.upstox.fetch_nifty50_intraday_ohlcv
"""

from modules.market_data.upstox._ohlcv_backfill_runner import DomainConfig, cli_main
from modules.market_data.upstox._ohlcv_engine import INTRADAY_TIMEFRAMES

# backfill_from_date=None -> the engine's own history-start for minute data (2022-01-01,
# Upstox's documented floor). Verified 2026-10-08: Nifty 50 5m/15m/60m really start
# 2022-01-03 (~126K rows, ~3 MB). Unlike the F&O stocks (bounded to 1 year), the full
# range is cheap for a single index, so we take everything available.
NIFTY50_INTRADAY_CONFIG = DomainConfig(
    domain="universe_intraday",
    catalogue_table="f_all_nse_index_instruments",
    timeframes=INTRADAY_TIMEFRAMES,
    extra_filter_column="instrument_key",
    extra_filter_value="NSE_INDEX|Nifty 50",
    backfill_from_date=None,
    log_name="Nifty_50_intraday",
)

if __name__ == "__main__":
    cli_main(NIFTY50_INTRADAY_CONFIG)
