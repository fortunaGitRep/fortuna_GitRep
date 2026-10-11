"""
Unit tests for trend_indicators/ema.py. Pure math: no R2, no network, no DB.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/test_ema.py -v

Covers: the hand-worked TradingView example, blanks before n bars, too-short
history, period 1, agreement with an independent plain-loop implementation,
default columns, input not modified, and input validation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema import (
    DEFAULT_PERIODS,
    compute_emas,
    ema_tradingview,
)


def _bars(closes) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=len(closes), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "close": closes})


def _reference_ema(closes, n):
    """Independent plain loop of the TradingView method, for cross-checking."""
    out = [math.nan] * len(closes)
    if len(closes) < n:
        return out
    alpha = 2 / (n + 1)
    prev = sum(closes[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(closes)):
        prev = alpha * closes[i] + (1 - alpha) * prev
        out[i] = prev
    return out


# --- The method itself ------------------------------------------------------

def test_hand_worked_3_ema():
    # 3-EMA on 100, 110, 120, 100: blank, blank, avg(100,110,120)=110, 0.5*100+0.5*110=105
    got = ema_tradingview(pd.Series([100.0, 110.0, 120.0, 100.0]), 3).tolist()
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert got[2] == pytest.approx(110.0)
    assert got[3] == pytest.approx(105.0)


def test_blank_before_n_bars_then_value():
    got = ema_tradingview(pd.Series(np.arange(1.0, 11.0)), 5)
    assert got.iloc[:4].isna().all()
    assert got.iloc[4:].notna().all()
    assert got.iloc[4] == pytest.approx(3.0)        # average of 1..5


def test_fewer_bars_than_period_is_all_blank():
    got = ema_tradingview(pd.Series([100.0, 101.0, 102.0]), 200)
    assert got.isna().all()
    assert len(got) == 3


def test_period_one_equals_close():
    closes = pd.Series([5.0, 7.0, 6.0, 9.0])
    assert ema_tradingview(closes, 1).tolist() == pytest.approx(closes.tolist())


def test_matches_independent_loop_for_all_default_periods():
    rng = np.random.default_rng(42)
    closes = (20000 + rng.normal(0, 150, 1500).cumsum()).tolist()
    df = compute_emas(_bars(closes))
    for n in DEFAULT_PERIODS:
        ref = _reference_ema(closes, n)
        got = df[f"ema_{n}"].tolist()
        for g, r in zip(got, ref):
            if math.isnan(r):
                assert math.isnan(g)
            else:
                assert g == pytest.approx(r, rel=1e-12)


def test_keeps_index_alignment():
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=[10, 11, 12, 13])
    assert list(ema_tradingview(s, 2).index) == [10, 11, 12, 13]


# --- compute_emas wrapper ---------------------------------------------------

def test_default_columns_added():
    df = compute_emas(_bars(list(np.linspace(100, 300, 250))))
    for n in DEFAULT_PERIODS:
        assert f"ema_{n}" in df.columns
    assert df["ema_200"].iloc[199] == pytest.approx(np.linspace(100, 300, 250)[:200].mean())


def test_input_not_modified():
    src = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    before = src.copy()
    compute_emas(src, periods=(3,))
    assert src.equals(before)


def test_custom_price_column():
    df = pd.DataFrame({"hl2": [10.0, 20.0, 30.0]})
    out = compute_emas(df, periods=(2,), price_col="hl2")
    assert out["ema_2"].iloc[1] == pytest.approx(15.0)


# --- Validation -------------------------------------------------------------

@pytest.mark.parametrize("periods", [(0,), (-5,), (5.5,), (True,), ()])
def test_bad_periods_raise(periods):
    with pytest.raises(ValueError):
        compute_emas(_bars([1.0, 2.0, 3.0]), periods=periods)


def test_duplicate_periods_raise():
    with pytest.raises(ValueError):
        compute_emas(_bars([1.0, 2.0, 3.0]), periods=(5, 5))


def test_missing_price_column_raises():
    with pytest.raises(ValueError):
        compute_emas(pd.DataFrame({"open": [1.0, 2.0]}))


def test_unsorted_bars_raise():
    df = _bars([1.0, 2.0, 3.0]).iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError):
        compute_emas(df)
