"""
modules/market_data/upstox/refresh_universe_options_intraday_ohlcv.py

Thin daily-refresh caller for intraday OHLCV — options-eligible (F&O) stocks
only. Works off the ledger seeded by fetch_universe_options_intraday_ohlcv.py's
backfill (must be run first) — refresh only touches instruments already
status='done' in the 'universe_intraday' domain, same self-healing/no-op-skip
behavior as the D/W/M refresh.

Usage:
    python -m modules.market_data.upstox.refresh_universe_options_intraday_ohlcv --limit 5
    python -m modules.market_data.upstox.refresh_universe_options_intraday_ohlcv
"""

from modules.market_data.upstox._ohlcv_engine import INTRADAY_TIMEFRAMES
from modules.market_data.upstox._ohlcv_refresh_runner import cli_main

if __name__ == "__main__":
    cli_main("universe_intraday", timeframes=INTRADAY_TIMEFRAMES)
