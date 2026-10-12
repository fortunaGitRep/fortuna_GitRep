"""
modules/Module_F_Tech_Indicators_Funnel/indicator_common/test_indicator_common.py

Unit tests for the shared indicator helpers. Pure -- no R2, no network.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/indicator_common -v
(results also written to logs/indicator_common_test_logs/test_indicator_common.log)

Two groups:
  1. The move is a pure move: every old name in ema.py / macd.py / macd_snapshot.py /
     adx.py / adx_snapshot.py is the SAME object as the shared one (`is`), so nothing
     can have drifted. (The 190 existing EMA / MACD / ADX tests still run through the
     old names and prove the behaviour.)
  2. Each shared helper on its own, on hand-worked values, so RSI / Stochastic RSI can
     rely on them directly.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.indicator_common import crosses as C
from modules.Module_F_Tech_Indicators_Funnel.indicator_common import smoothing as SM
from modules.Module_F_Tech_Indicators_Funnel.indicator_common import text_format as TX
from modules.Module_F_Tech_Indicators_Funnel.indicator_common import timeframes as TF
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx import adx as A
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx import adx_snapshot as AS
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema import ema as E
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd import macd as M
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd import macd_snapshot as MS


# =============================================================================
# 1. Pure move: old names are the shared objects
# =============================================================================

@pytest.mark.parametrize("old, new", [
    (E.ema_tradingview, SM.ema_tradingview),
    (E.cross_above, C.cross_above),
    (E.cross_below, C.cross_below),
    (M.ema_tradingview, SM.ema_tradingview),
    (M.cross_above, C.cross_above),
    (M.cross_below, C.cross_below),
    (M._runs, C.runs),
    (M._labels, C.bar_labels),
    (M._DEFAULT_DOMAIN, TF.DEFAULT_DOMAIN),
    (MS.TIMEFRAMES, TF.TIMEFRAMES),
    (MS.TF_NAME, TF.TF_NAME),
    (MS._UNIT, TF.UNIT),
    (MS._NOW, TF.NOW),
    (MS._PREV, TF.PREV),
    (MS._intraday, TF.is_intraday),
    (MS._num, TX.num),
    (MS._int, TX.to_int),
    (MS._iso, TX.iso),
    (MS._when, TX.when),
    (MS._units, TX.units),
    (MS._p, TX.price),
    (MS._sp, TX.signed),
    (A.rma_tradingview, SM.rma_tradingview),
    (A.cross_above, C.cross_above),
    (A._runs, C.runs),
    (A._labels, C.bar_labels),
    (A._DEFAULT_DOMAIN, TF.DEFAULT_DOMAIN),
    (AS._runs, C.runs),
    (AS.TIMEFRAMES, TF.TIMEFRAMES),
    (AS._NOW, TF.NOW),
    (AS._PREV, TF.PREV),
    (AS._UNIT, TF.UNIT),
    (AS._when, TX.when),
])
def test_old_name_is_the_shared_object(old, new):
    assert old is new


# =============================================================================
# 2. The helpers on their own
# =============================================================================

# --- smoothing --------------------------------------------------------------------

def test_ema_hand_worked():
    # 3-EMA of 100, 110, 120, 100: blank, blank, avg = 110, 0.5*100 + 0.5*110 = 105
    got = SM.ema_tradingview(pd.Series([100.0, 110, 120, 100]), 3)
    assert got.iloc[:2].isna().all()
    assert list(got.iloc[2:]) == pytest.approx([110.0, 105.0])


def test_ema_short_history_all_blank():
    assert SM.ema_tradingview(pd.Series([1.0, 2.0]), 5).isna().all()


def test_rma_hand_worked():
    # rma(3) of 1..5: blank, blank, avg(1,2,3) = 2, (2*2 + 4)/3 = 2.6667, (2.6667*2 + 5)/3 = 3.4444
    r = SM.rma_tradingview(pd.Series([1.0, 2, 3, 4, 5]), 3)
    assert r.iloc[:2].isna().all()
    assert list(r.iloc[2:].round(4)) == [2.0, 2.6667, 3.4444]


def test_rma_seeds_from_first_non_blank_value():
    r = SM.rma_tradingview(pd.Series([np.nan, np.nan, 1.0, 2, 3, 4]), 3)
    assert r.iloc[:4].isna().all() and r.iloc[4] == pytest.approx(2.0)


def test_rma_matches_plain_loop():
    rng = np.random.default_rng(3)
    vals = rng.normal(0, 10, 300)
    got = SM.rma_tradingview(pd.Series(vals), 14)
    ref, prev = [], None
    for i, v in enumerate(vals):
        if i < 13:
            ref.append(math.nan)
            continue
        prev = vals[:14].mean() if prev is None else (v + 13 * prev) / 14
        ref.append(prev)
    np.testing.assert_allclose(got, ref, equal_nan=True, rtol=0, atol=1e-9)


def test_smoothing_keeps_index_and_input():
    s = pd.Series([1.0, 2, 3, 4], index=[10, 11, 12, 13])
    before = s.copy()
    assert list(SM.ema_tradingview(s, 2).index) == [10, 11, 12, 13]
    assert list(SM.rma_tradingview(s, 2).index) == [10, 11, 12, 13]
    pd.testing.assert_series_equal(s, before)


# --- crosses and runs --------------------------------------------------------------

def test_cross_above_and_below_tradingview_rule():
    a = pd.Series([1.0, 2, 3, 4, 3, 2])
    b = pd.Series([3.0] * 6)
    # equal on bar 2 then above on bar 3 -> cross on bar 3 (previous equal counts)
    assert C.cross_above(a, b).tolist() == [False, False, False, True, False, False]
    assert C.cross_below(a, b).tolist() == [False, False, False, False, False, True]


def test_cross_blank_is_no_cross():
    a = pd.Series([1.0, 5, 1])
    b = pd.Series([np.nan, 3, 3])
    assert not C.cross_above(a, b).any()
    assert C.cross_below(a, b).tolist() == [False, False, True]


def test_runs_held_since_from_start_and_blank_break():
    held, since, from_start = C.runs(pd.Series([1.0, 1, -1, -1, np.nan, -1]),
                                     pd.Series(list("abcdef")))
    assert list(held.fillna(0)) == [1, 2, 1, 2, 0, 1]
    assert list(since.drop(4)) == ["a", "a", "c", "c", "f"] and pd.isna(since.iloc[4])
    assert list(from_start) == [True, True, False, False, False, False]


def test_bar_labels_preference():
    ts = pd.date_range("2026-01-01", periods=2, freq="D")
    assert C.bar_labels(pd.DataFrame({"ts": ts, "trade_date": ["x", "y"]})).equals(
        pd.Series(ts, name="ts"))
    assert list(C.bar_labels(pd.DataFrame({"trade_date": ["x", "y"]}))) == ["x", "y"]
    assert list(C.bar_labels(pd.DataFrame({"close": [1, 2]}, index=[5, 6]))) == [5, 6]


# --- timeframes ---------------------------------------------------------------------

def test_timeframes_and_domains():
    assert TF.TIMEFRAMES == ("1mo", "1w", "1d", "60m", "15m", "5m")
    assert set(TF.DEFAULT_DOMAIN) == set(TF.TIMEFRAMES)
    assert {TF.DEFAULT_DOMAIN[t] for t in ("1d", "1w", "1mo")} == {"indices"}
    assert {TF.DEFAULT_DOMAIN[t] for t in ("5m", "15m", "60m")} == {"universe_intraday"}
    assert [TF.is_intraday(t) for t in TF.TIMEFRAMES] == [False, False, False, True, True, True]


# --- text_format --------------------------------------------------------------------

def test_num_and_to_int_are_json_safe():
    assert TX.num(np.nan) is None and TX.num(None) is None and TX.num("x") is None
    assert TX.num(np.float64(1.5)) == 1.5 and TX.to_int(2.9) == 2 and TX.to_int(np.nan) is None
    json.dumps([TX.num(np.nan), TX.num(np.float64(3.0))], allow_nan=False)


@pytest.mark.parametrize("tf, expected", [
    ("1d", "9 Oct"), ("1w", "week of 9 Oct"), ("1mo", "Oct 2026"), ("15m", "9 Oct 15:15"),
])
def test_when_per_timeframe(tf, expected):
    assert TX.when(pd.Timestamp("2026-10-09 15:15"), tf, 2026) == expected


def test_when_adds_year_when_different():
    assert TX.when(pd.Timestamp("2025-03-04"), "1d", 2026) == "4 Mar 2025"


def test_iso_daily_vs_intraday():
    ts = pd.Timestamp("2026-10-09 15:15", tz="Asia/Kolkata")
    assert TX.iso(ts, "1d") == "2026-10-09"
    assert TX.iso(ts, "15m") == "2026-10-09T15:15:00+05:30"
    assert TX.iso(None, "1d") is None


def test_units_price_signed():
    assert TX.units(1, "1d") == "1 day" and TX.units(3, "1w") == "3 weeks"
    assert TX.units(5, "5m") == "5 candles"
    assert TX.price(22520.449) == "22,520.45" and TX.price(None) == "n/a"
    assert TX.signed(22.85) == "+22.85" and TX.signed(-0.08) == "-0.08"
