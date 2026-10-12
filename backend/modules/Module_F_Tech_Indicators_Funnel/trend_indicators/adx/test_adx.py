"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx/test_adx.py

Unit tests for adx.compute_adx (part 1). Pure maths -- no R2, no network.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx -v
(results also written to logs/adx_test_logs/test_adx.log by conftest.py)

Covers: Wilder's rma hand-worked, a plain-loop Pine reference of the whole DMI,
the +DM/-DM rule (incl. ties), true range using the previous close, where each
line starts, DX from Ash's chart numbers, flat prices (no division errors),
ADXR lookback, short history, input safety and validation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx import adx as A


def _ohlc(high, low, close) -> pd.DataFrame:
    n = len(close)
    ts = pd.date_range("2026-01-01", periods=n, freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "open": np.asarray(close, float), "high": np.asarray(high, float),
                         "low": np.asarray(low, float), "close": np.asarray(close, float)})


@pytest.fixture
def walk() -> pd.DataFrame:
    """200 candles: a random walk with a trend phase and a choppy phase."""
    rng = np.random.default_rng(7)
    steps = np.concatenate([rng.normal(8, 30, 100), rng.normal(0, 30, 100)])
    close = 22000 + np.cumsum(steps)
    spread = np.abs(rng.normal(40, 15, 200))
    high = close + spread * rng.uniform(0.2, 1, 200)
    low = close - spread * rng.uniform(0.2, 1, 200)
    return _ohlc(high, low, close)


# --- Reference: Pine's DMI written as a plain loop ------------------------------

def _pine_rma(values, n):
    out, prev, window = [], None, []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(math.nan)
            continue
        if prev is None:
            window.append(v)
            if len(window) < n:
                out.append(math.nan)
                continue
            prev = sum(window) / n
        else:
            prev = (v + (n - 1) * prev) / n
        out.append(prev)
    return out


def _pine_dmi(h, l, c, n=14, m=14, lookback=13):
    pdm, mdm, tr = [math.nan], [math.nan], [math.nan]
    for i in range(1, len(c)):
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if (up > down and up > 0) else 0.0)
        mdm.append(down if (down > up and down > 0) else 0.0)
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    trs, ps, ms = _pine_rma(tr, n), _pine_rma(pdm, n), _pine_rma(mdm, n)
    plus, minus, lp, lm = [], [], math.nan, math.nan
    for t, p, mm in zip(trs, ps, ms):
        if not math.isnan(t) and t != 0:
            lp, lm = 100 * p / t, 100 * mm / t
        plus.append(lp)
        minus.append(lm)
    dx = [math.nan if math.isnan(a) else 100 * abs(a - b) / ((a + b) or 1)
          for a, b in zip(plus, minus)]
    adx = _pine_rma(dx, m)
    adxr = [math.nan if i < lookback else (adx[i] + adx[i - lookback]) / 2
            for i in range(len(adx))]
    return plus, minus, dx, adx, adxr


def test_matches_plain_pine_reference(walk):
    a = A.compute_adx(walk)
    ref = _pine_dmi(list(walk["high"]), list(walk["low"]), list(walk["close"]))
    for col, r in zip(A.ADX_COLS, ref):
        np.testing.assert_allclose(a[col], r, equal_nan=True, rtol=0, atol=1e-9, err_msg=col)


# --- Wilder's rma ------------------------------------------------------------------

def test_rma_hand_worked():
    # rma(3) of 1,2,3,4,5: blank, blank, avg(1,2,3)=2, (2*2+4)/3=2.6667, (2.6667*2+5)/3=3.4444
    r = A.rma_tradingview(pd.Series([1.0, 2, 3, 4, 5]), 3)
    assert r.iloc[:2].isna().all()
    assert list(r.iloc[2:].round(4)) == [2.0, 2.6667, 3.4444]


def test_rma_with_leading_blank_seeds_from_first_value():
    r = A.rma_tradingview(pd.Series([np.nan, 1.0, 2, 3, 4]), 3)
    assert r.iloc[:3].isna().all() and r.iloc[3] == pytest.approx(2.0)


# --- Directional movement and true range ------------------------------------------

def test_dm_rule_ties_and_true_range():
    # bar1: up 2, down -1          -> +DM 2, -DM 0 ; TR = max(12-9, |12-9|, |9-9|)  = 3
    # bar2: up 1, down 1 (a tie)   -> both 0       ; TR = max(13-8, |13-11|, |8-11|) = 5
    # bar3: up -1, down 3          -> +DM 0, -DM 3 ; TR = max(12-5, |12-10|, |5-10|) = 7
    df = _ohlc(high=[10, 12, 13, 12], low=[8, 9, 8, 5], close=[9, 11, 10, 6])
    a = A.compute_adx(df, di_len=1, adx_len=1, adxr_lookback=1)   # length 1: DI = 100*DM/TR
    assert math.isnan(a["plus_di"].iloc[0])                         # no previous candle
    assert list(a["plus_di"].iloc[1:].round(4)) == [round(200 / 3, 4), 0.0, 0.0]
    assert list(a["minus_di"].iloc[1:].round(4)) == [0.0, 0.0, round(300 / 7, 4)]
    assert a["dx"].iloc[2] == 0.0                                   # +DI + -DI = 0 -> divide by 1
    assert a["dx"].iloc[1] == pytest.approx(100.0)


# --- Where each line starts --------------------------------------------------------

def test_first_values(walk):
    a = A.compute_adx(walk)
    assert a["plus_di"].iloc[:14].isna().all() and pd.notna(a["plus_di"].iloc[14])   # candle 15
    assert a["dx"].iloc[:14].isna().all() and pd.notna(a["dx"].iloc[14])
    assert a["adx"].iloc[:27].isna().all() and pd.notna(a["adx"].iloc[27])           # candle 28
    assert a["adxr"].iloc[:40].isna().all() and pd.notna(a["adxr"].iloc[40])         # 28 + 13


def test_adxr_lookback(walk):
    a13 = A.compute_adx(walk)
    a14 = A.compute_adx(walk, adxr_lookback=14)
    i = 100
    assert a13["adxr"].iloc[i] == pytest.approx((a13["adx"].iloc[i] + a13["adx"].iloc[i - 13]) / 2)
    assert a14["adxr"].iloc[i] == pytest.approx((a14["adx"].iloc[i] + a14["adx"].iloc[i - 14]) / 2)
    pd.testing.assert_series_equal(a13["adx"], a14["adx"])        # ADX itself unaffected


# --- Ash's chart numbers ----------------------------------------------------------

@pytest.mark.parametrize("plus, minus, dx", [
    (9.9922, 38.3904, 58.6951),     # daily 9 Oct 2026
    (30.3440, 26.3330, 7.0769),     # 1h 9 Oct 2026 15:15
])
def test_dx_formula_matches_tradingview(plus, minus, dx):
    assert 100 * abs(plus - minus) / (plus + minus) == pytest.approx(dx, abs=1e-3)


# --- Edge cases --------------------------------------------------------------------

def test_flat_prices_no_errors():
    a = A.compute_adx(_ohlc([100.0] * 60, [100.0] * 60, [100.0] * 60))   # TR = 0 everywhere
    assert a["plus_di"].isna().all() and a["adx"].isna().all()           # Pine gives na, not an error


def test_values_in_range(walk):
    a = A.compute_adx(walk).dropna(subset=["adx"])
    for col in ("plus_di", "minus_di", "dx", "adx", "adxr"):
        s = a[col].dropna()
        assert (s >= 0).all() and (s <= 100).all(), col


def test_trend_phase_has_plus_di_above_minus_di(walk):
    a = A.compute_adx(walk)
    trend = a.iloc[40:100]                                   # the up-trending first half
    assert (trend["plus_di"] > trend["minus_di"]).mean() > 0.7


def test_short_history_all_blank():
    a = A.compute_adx(_ohlc([10.0, 11, 12], [9.0, 10, 11], [9.5, 10.5, 11.5]))
    assert a["adx"].isna().all() and a["plus_di"].isna().all()


def test_input_not_modified(walk):
    original = walk.copy()
    A.compute_adx(walk)
    pd.testing.assert_frame_equal(walk, original)


def test_adds_exactly_the_adx_columns(walk):
    a = A.compute_adx(walk)
    assert list(a.columns) == list(walk.columns) + list(A.ADX_COLS)


@pytest.mark.parametrize("kwargs, msg", [
    ({"di_len": 0}, "positive integer"),
    ({"adx_len": 2.5}, "positive integer"),
    ({"adxr_lookback": True}, "positive integer"),
])
def test_bad_lengths_raise(walk, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        A.compute_adx(walk, **kwargs)


def test_missing_columns_raise(walk):
    with pytest.raises(ValueError, match="high"):
        A.compute_adx(walk.drop(columns=["high"]))


def test_unsorted_bars_raise(walk):
    with pytest.raises(ValueError, match="ascending"):
        A.compute_adx(walk.iloc[::-1])


# =============================================================================
# Part 2 — strength band, slope, direction, events, label
# =============================================================================

def _states_frame(adx, plus, minus) -> pd.DataFrame:
    n = len(adx)
    ts = pd.date_range("2026-01-01", periods=n, freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "adx": np.asarray(adx, float), "plus_di": np.asarray(plus, float),
                         "minus_di": np.asarray(minus, float)})


@pytest.mark.parametrize("value, band", [
    (5, "no_trend"), (19.99, "no_trend"), (20, "forming"), (24.99, "forming"),
    (25, "trending"), (39.99, "trending"), (40, "strong"), (49.99, "strong"),
    (50, "very_strong"), (80, "very_strong"),
])
def test_strength_band_edges(value, band):
    assert A.strength_band(pd.Series([float(value)])).iloc[0] == band


def test_strength_band_blank():
    assert A.strength_band(pd.Series([np.nan])).iloc[0] is None


def test_slope_and_held():
    #   ADX: 20, 21, 22, 22, 21, 20
    s = A.adx_states(_states_frame([20, 21, 22, 22, 21, 20], [30] * 6, [20] * 6))
    assert list(s["adx_slope"].fillna(9)) == [9, 1, 1, 0, -1, -1]
    assert list(s["adx_slope_held"].fillna(0)) == [0, 1, 2, 1, 1, 2]


def test_di_side_cross_held_since():
    #   +DI: 20 20 25 30 18     -DI: 25 20 20 20 22
    s = A.adx_states(_states_frame([30] * 5, [20, 20, 25, 30, 18], [25, 20, 20, 20, 22]))
    assert list(s["di_side"]) == [-1, 0, 1, 1, -1]
    assert list(s.index[s["di_cross_above"]]) == [2]       # prev equal counts (TradingView rule)
    assert list(s.index[s["di_cross_below"]]) == [4]
    assert list(s["di_held"]) == [1, 1, 1, 2, 1]
    assert s["di_since"].iloc[3] == s["ts"].iloc[2]
    assert list(s["di_from_start"]) == [True, False, False, False, False]


def test_adx_cross_25():
    #   ADX: 23 25 26 25 24.9 26
    s = A.adx_states(_states_frame([23, 25, 26, 25, 24.9, 26], [30] * 6, [20] * 6))
    assert list(s.index[s["adx_cross_above_25"]]) == [2, 5]    # 25 itself is not above
    assert list(s.index[s["adx_cross_below_25"]]) == [4]        # from 25 (>=) to 24.9


@pytest.mark.parametrize("adx, plus, minus, label", [
    (43.8, 10.0, 38.4, "STRONG TREND DOWN"),        # Nifty daily 9 Oct 2026
    (20.0, 30.3, 26.3, "TREND FORMING UP"),         # Nifty 1h 9 Oct 2026 15:15
    (30.0, 30.0, 10.0, "TRENDING UP"),
    (55.0, 5.0, 40.0, "VERY STRONG TREND DOWN"),
    (15.0, 30.0, 10.0, "NO TREND"),                 # no direction when there is no trend
    (30.0, 20.0, 20.0, "TRENDING (no direction)"),
    (np.nan, 20.0, 10.0, A.LABEL_NA),
])
def test_adx_label(adx, plus, minus, label):
    s = A.adx_states(_states_frame([adx], [plus], [minus]))
    assert A.adx_label(s).iloc[0] == label


def test_adx_all_on_walk(walk):
    a = A.adx_all(walk)
    for col in ("adx_band", "adx_slope", "di_side", "di_cross_above", "adx_cross_above_25",
                "adx_label"):
        assert col in a.columns
    assert (a.loc[a["adx"].isna(), "adx_label"] == A.LABEL_NA).all()
    crosses = a["di_cross_above"] | a["di_cross_below"]
    # every DI cross flips the side
    assert (a.loc[crosses, "di_side"] != a["di_side"].shift(1)[crosses]).all()


def test_part2_input_not_modified(walk):
    base = A.compute_adx(walk)
    original = base.copy()
    A.adx_states(base)
    pd.testing.assert_frame_equal(base, original)


def test_part2_missing_columns_and_unsorted_raise(walk):
    with pytest.raises(ValueError, match="compute_adx"):
        A.adx_states(walk)
    with pytest.raises(ValueError, match="adx_states"):
        A.adx_label(A.compute_adx(walk))
    with pytest.raises(ValueError, match="ascending"):
        A.adx_states(A.compute_adx(walk).iloc[::-1])
