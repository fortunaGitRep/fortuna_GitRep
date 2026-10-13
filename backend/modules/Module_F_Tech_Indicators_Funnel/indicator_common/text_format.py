"""
modules/Module_F_Tech_Indicators_Funnel/indicator_common/text_format.py

Number and date formatting for snapshot packages and texts (JSON-safe), shared by
every indicator snapshot.

  num(x)              float, NaN / None / not-a-number -> None
  to_int(x)           int via num, blank -> None
  iso(x, tf)          ISO date (1d/1w/1mo) or ISO datetime (intraday); blank -> None
  when(x, tf, year)   '9 Oct', '9 Oct 15:15', 'week of 5 Oct', 'Oct 2026'
                      (the year is added when it differs from `year`)
  report_date(x, tf)  full report-style date, always with the year (added 2026-10-13):
                      'Oct 2026' (1mo), 'Week of Mon 5 Oct 2026' (1w),
                      'Fri 9 Oct 2026' (1d), 'Fri 9 Oct 2026 15:25' (intraday)
  units(n, tf)        '1 day', '3 weeks', '5 candles'
  price(x)            '22,520.45' or 'n/a'
  signed(x)           '+22.85' / '-0.08' or 'n/a'

Moved unchanged 2026-10-12 from macd_snapshot.py (were _num, _int, _iso, _when,
_units, _p, _sp; adx_snapshot imported them from there). The old names are still
re-exported by macd_snapshot.py.

ema_snapshot.py keeps its own daily-only helpers (_num, _iso(x), _day, _price) --
not moved: a different, daily-only signature, and EMA was not part of this change.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    UNIT,
    is_intraday,
)


def num(x: Any) -> Optional[float]:
    """JSON-safe float: NaN/None -> None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def to_int(x: Any) -> Optional[int]:
    f = num(x)
    return None if f is None else int(f)


def iso(x: Any, tf: str) -> Optional[str]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.isoformat() if is_intraday(tf) else ts.date().isoformat()


def when(x: Any, tf: str, ref_year: int) -> str:
    """Human date for a candle: '9 Oct', '9 Oct 15:15', 'week of 5 Oct', 'Oct 2026'."""
    ts = pd.Timestamp(x)
    day = f"{ts.day} {ts:%b}" + ("" if ts.year == ref_year else f" {ts.year}")
    if tf == "1mo":
        return f"{ts:%b %Y}"
    if tf == "1w":
        return f"week of {day}"
    if is_intraday(tf):
        return f"{day} {ts:%H:%M}"
    return day


def report_date(x: Any, tf: str) -> str:
    """Report-style date of a candle, always with the year (Ash, 2026-10-13):
    'Oct 2026' (1mo), 'Week of Mon 5 Oct 2026' (1w), 'Fri 9 Oct 2026' (1d),
    'Fri 9 Oct 2026 15:25' (5m / 15m / 60m). Weekly candles are named by their
    Monday (Upstox); TradingView names them by the week's first trading day."""
    ts = pd.Timestamp(x)
    day = f"{ts:%a} {ts.day} {ts:%b %Y}"
    if tf == "1mo":
        return f"{ts:%b %Y}"
    if tf == "1w":
        return f"Week of {day}"
    if is_intraday(tf):
        return f"{day} {ts:%H:%M}"
    return day


def units(n: int, tf: str) -> str:
    unit = UNIT.get(tf, "candle")
    return f"{n} {unit}" + ("" if n == 1 else "s")


def price(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def signed(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:+,.2f}"
