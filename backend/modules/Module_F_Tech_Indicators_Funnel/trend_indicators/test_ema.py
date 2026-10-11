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
    cross_above,
    cross_below,
    default_cross_checks,
    detect_crosses,
    ema_tradingview,
    stack_stage,
    check_states,
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


# --- Part 2: crosses (TradingView ta.crossover / ta.crossunder) -------------

def _s(values):
    return pd.Series(values, dtype="float64")


def test_cross_above_fires_once_on_the_cross_bar():
    a = _s([1, 2, 3, 4, 5])
    b = _s([3, 3, 3, 3, 3])
    # a: below, below, equal, above, above -> cross on bar 3 only (prev equal counts)
    assert cross_above(a, b).tolist() == [False, False, False, True, False]


def test_equal_today_is_not_a_cross():
    a = _s([1, 3])
    b = _s([3, 3])
    assert cross_above(a, b).tolist() == [False, False]


def test_cross_below_mirror():
    a = _s([5, 4, 3, 2, 1])
    b = _s([3, 3, 3, 3, 3])
    assert cross_below(a, b).tolist() == [False, False, False, True, False]


def test_blank_on_either_bar_is_no_cross():
    a = _s([1, 5, 1, 5])
    b = _s([math.nan, 3, 3, math.nan])
    assert cross_above(a, b).tolist() == [False, False, False, False]
    assert cross_below(a, b).tolist() == [False, False, True, False]


def test_default_checks_are_the_agreed_12():
    checks = default_cross_checks()
    assert len(checks) == 12
    assert ("close", "ema_5") in checks and ("close", "ema_200") in checks
    for a, b in [(5, 13), (13, 26), (26, 50), (50, 100), (100, 200), (50, 200)]:
        assert (f"ema_{a}", f"ema_{b}") in checks


def test_detect_crosses_adds_24_columns_and_keeps_input():
    rng = np.random.default_rng(7)
    closes = (20000 + rng.normal(0, 150, 600).cumsum()).tolist()
    emas = compute_emas(_bars(closes))
    before = emas.copy()
    out = detect_crosses(emas)
    new = [c for c in out.columns if c.startswith("cross_")]
    assert len(new) == 24
    assert "cross_above_ema_50_ema_200" in new and "cross_below_ema_50_ema_200" in new
    assert emas.equals(before)
    assert out[new].dtypes.eq(bool).all()


def test_detect_crosses_matches_plain_loop():
    rng = np.random.default_rng(11)
    closes = (20000 + rng.normal(0, 150, 800).cumsum()).tolist()
    out = detect_crosses(compute_emas(_bars(closes)))
    a, b = out["ema_13"].tolist(), out["ema_26"].tolist()
    for t in range(1, len(a)):
        ok = not any(math.isnan(x) for x in (a[t], b[t], a[t - 1], b[t - 1]))
        exp_up = ok and a[t] > b[t] and a[t - 1] <= b[t - 1]
        exp_dn = ok and a[t] < b[t] and a[t - 1] >= b[t - 1]
        assert out["cross_above_ema_13_ema_26"].iloc[t] == exp_up
        assert out["cross_below_ema_13_ema_26"].iloc[t] == exp_dn


def test_golden_cross_on_known_bar():
    # Hand-built EMA columns: 50 below 200, then above from bar 2.
    df = pd.DataFrame({"close": [1.0, 1.0, 1.0],
                       "ema_50": [10.0, 10.0, 12.0],
                       "ema_200": [11.0, 11.0, 11.0]})
    out = detect_crosses(df, checks=[("ema_50", "ema_200")])
    assert out["cross_above_ema_50_ema_200"].tolist() == [False, False, True]
    assert not out["cross_below_ema_50_ema_200"].any()


def test_detect_crosses_without_emas_raises():
    with pytest.raises(ValueError):
        detect_crosses(_bars([1.0, 2.0, 3.0]))


def test_detect_crosses_unsorted_raises():
    emas = compute_emas(_bars([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]), periods=(2, 3))
    with pytest.raises(ValueError):
        detect_crosses(emas.iloc[::-1].reset_index(drop=True),
                       checks=[("ema_2", "ema_3")])


# --- Part 3: stage and states ----------------------------------------------

def _stack_row(e5, e13, e26, e50, e100, e200):
    return {"ema_5": e5, "ema_13": e13, "ema_26": e26, "ema_50": e50,
            "ema_100": e100, "ema_200": e200}


@pytest.mark.parametrize("row, expected", [
    (_stack_row(6, 5, 4, 3, 2, 1), 5),                 # full bullish stack
    (_stack_row(1, 2, 3, 4, 5, 6), -5),                # full bearish stack
    (_stack_row(5, 4, 6, 7, 8, 9), 1),                 # only 5 above 13 (weakest uptrend)
    (_stack_row(6, 5, 4, 7, 8, 9), 2),                 # 5>13>26, 26 below 50
    (_stack_row(4, 5, 3, 2, 1, 0.5), -1),              # pullback: 5<13, but 13>26 stops the count
    (_stack_row(5, 5, 4, 3, 2, 1), 0),                 # 5 == 13
    (_stack_row(6, 5, 4, 3, 2, math.nan), 4),          # 200 blank: max +4
    (_stack_row(6, math.nan, 4, 3, 2, 1), math.nan),   # 13 blank: no stage
])
def test_stack_stage(row, expected):
    got = stack_stage(pd.DataFrame([row])).iloc[0]
    if math.isnan(expected):
        assert math.isnan(got)
    else:
        assert got == expected


def test_stage_missing_columns_raise():
    with pytest.raises(ValueError):
        stack_stage(pd.DataFrame({"ema_5": [1.0]}))


def _state_frame():
    # close vs ema_5 on 6 days: below, below, above, above, above, below
    return pd.DataFrame({
        "trade_date": ["d1", "d2", "d3", "d4", "d5", "d6"],
        "close":  [9.0, 9.0, 11.0, 12.0, 13.0, 9.0],
        "high":   [9.5, 9.5, 11.5, 12.5, 13.5, 10.5],
        "low":    [8.5, 8.5,  9.5, 10.5, 12.5, 8.5],
        "ema_5":  [10.0] * 6,
    })


def test_side_held_since():
    out = check_states(_state_frame(), checks=[("close", "ema_5")])
    assert out["side_close_ema_5"].tolist() == [-1, -1, 1, 1, 1, -1]
    assert out["held_close_ema_5"].tolist() == [1, 2, 1, 2, 3, 1]
    assert out["since_close_ema_5"].tolist() == ["d1", "d1", "d3", "d3", "d3", "d6"]


def test_margin_points_and_percent():
    out = check_states(_state_frame(), checks=[("close", "ema_5")])
    assert out["margin_pts_close_ema_5"].iloc[3] == pytest.approx(2.0)
    assert out["margin_pct_close_ema_5"].iloc[3] == pytest.approx(20.0)


def test_whole_candle_clear():
    out = check_states(_state_frame(), checks=[("close", "ema_5")])
    # d3: above but low 9.5 < 10 -> not clear; d4: low 10.5 > 10 -> clear;
    # d1: below, high 9.5 < 10 -> clear; d6: below but high 10.5 > 10 -> not clear
    assert out["candle_clear_close_ema_5"].tolist() == [True, True, False, True, True, False]


def test_ema_pairs_have_no_candle_flag():
    df = pd.DataFrame({"ema_5": [1.0, 3.0], "ema_13": [2.0, 2.0],
                       "high": [5.0, 5.0], "low": [0.5, 0.5]})
    out = check_states(df, checks=[("ema_5", "ema_13")])
    assert "candle_clear_ema_5_ema_13" not in out.columns
    assert out["held_ema_5_ema_13"].tolist() == [1, 1]


def test_blank_values_give_blank_state_and_restart_count():
    df = pd.DataFrame({"trade_date": ["d1", "d2", "d3", "d4"],
                       "close": [11.0, 11.0, 11.0, 11.0],
                       "ema_5": [math.nan, 10.0, 10.0, 10.0]})
    out = check_states(df, checks=[("close", "ema_5")])
    assert math.isnan(out["side_close_ema_5"].iloc[0])
    assert math.isnan(out["held_close_ema_5"].iloc[0])
    assert out["held_close_ema_5"].tolist()[1:] == [1, 2, 3]
    assert out["since_close_ema_5"].iloc[3] == "d2"


def test_states_keep_input_and_full_default_run():
    rng = np.random.default_rng(5)
    closes = (20000 + rng.normal(0, 150, 400).cumsum())
    bars = _bars(closes.tolist())
    bars["high"], bars["low"] = closes + 50, closes - 50
    emas = compute_emas(bars)
    before = emas.copy()
    out = check_states(emas)
    assert emas.equals(before)
    assert len([c for c in out.columns if c.startswith("held_")]) == 12
    assert len([c for c in out.columns if c.startswith("candle_clear_")]) == 6


def test_held_matches_plain_loop():
    rng = np.random.default_rng(9)
    closes = (20000 + rng.normal(0, 150, 500).cumsum()).tolist()
    out = check_states(compute_emas(_bars(closes)), checks=[("ema_5", "ema_13")])
    side = out["side_ema_5_ema_13"].tolist()
    held = out["held_ema_5_ema_13"].tolist()
    count, prev = 0, None
    for s, h in zip(side, held):
        if math.isnan(s):
            assert math.isnan(h)
            count, prev = 0, None
            continue
        count = count + 1 if s == prev else 1
        prev = s
        assert h == count
