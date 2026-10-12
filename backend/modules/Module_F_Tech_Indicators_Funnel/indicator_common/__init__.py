"""
modules/Module_F_Tech_Indicators_Funnel/indicator_common/

Shared helpers for every indicator family (trend_indicators/, oscillators/, ...).
Pure code only: no I/O, nothing specific to one indicator.

  smoothing.py    ema_tradingview (Pine ta.ema), rma_tradingview (Pine ta.rma)
  crosses.py      cross_above / cross_below (Pine ta.crossover / ta.crossunder), runs
  timeframes.py   TIMEFRAMES, TF_NAME, DEFAULT_DOMAIN, time words per timeframe
  text_format.py  number / date formatting for snapshot texts (JSON-safe)

Moved here 2026-10-12 from ema.py, adx.py, macd.py, macd_snapshot.py and
adx_snapshot.py, unchanged. Those files still export the old names, so every
existing import keeps working.
"""
