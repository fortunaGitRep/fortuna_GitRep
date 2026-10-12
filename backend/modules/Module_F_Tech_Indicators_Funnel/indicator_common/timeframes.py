"""
modules/Module_F_Tech_Indicators_Funnel/indicator_common/timeframes.py

The six indicator timeframes and the words that go with them, shared by every
indicator and snapshot.

  TIMEFRAMES      ("1mo", "1w", "1d", "60m", "15m", "5m") -- longest first
  TF_NAME         display names: 1M, 1W, 1D, 60m, 15m, 5m
  DEFAULT_DOMAIN  where each timeframe's candles live in R2 (for Nifty):
                  1d/1w/1mo -> 'indices', 5m/15m/60m -> 'universe_intraday'
  UNIT / NOW / PREV   day/week/month, Today/This week/This month,
                      yesterday/last week/last month (intraday: candle / On this
                      candle / previous candle -- the callers' .get() default)
  is_intraday(tf)

Moved unchanged 2026-10-12: TIMEFRAMES, TF_NAME, _UNIT, _NOW, _PREV from
macd_snapshot.py (the same three word maps were repeated in adx_snapshot.py);
_DEFAULT_DOMAIN from macd.py (repeated in adx.py); _intraday from macd_snapshot.py.
The old names are still re-exported there.

Note: DEFAULT_DOMAIN serves Nifty; stocks read 1d/1w/1mo from 'universe' (open
item: a domain option for the snapshots, with the watchlist work).
"""

from __future__ import annotations

TIMEFRAMES = ("1mo", "1w", "1d", "60m", "15m", "5m")      # longest first
TF_NAME = {"1mo": "1M", "1w": "1W", "1d": "1D", "60m": "60m", "15m": "15m", "5m": "5m"}
INTRADAY = ("5m", "15m", "60m")

DEFAULT_DOMAIN = {"1d": "indices", "1w": "indices", "1mo": "indices",
                  "5m": "universe_intraday", "15m": "universe_intraday",
                  "60m": "universe_intraday"}

UNIT = {"1mo": "month", "1w": "week", "1d": "day"}        # intraday -> "candle"
NOW = {"1mo": "This month", "1w": "This week", "1d": "Today"}
PREV = {"1mo": "last month", "1w": "last week", "1d": "yesterday"}


def is_intraday(tf: str) -> bool:
    return tf in INTRADAY
