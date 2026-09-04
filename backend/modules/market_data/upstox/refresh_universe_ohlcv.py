"""
modules/market_data/upstox/refresh_universe_ohlcv.py

Thin daily-refresh caller for the universe (stocks) domain. All logic lives in
_ohlcv_refresh_runner.py — this file just supplies the domain string.

Usage:
    python -m modules.market_data.upstox.refresh_universe_ohlcv --limit 5   # verify-first
    python -m modules.market_data.upstox.refresh_universe_ohlcv             # full sweep
"""

from modules.market_data.upstox._ohlcv_refresh_runner import cli_main

if __name__ == "__main__":
    cli_main("universe")
