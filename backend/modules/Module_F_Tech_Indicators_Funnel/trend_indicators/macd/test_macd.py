"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd/test_macd.py

Unit tests for macd.compute_macd (part 2). Pure maths -- no R2, no network.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd -v

Covers: where each line starts (bars 26 / 34 / 35), the signal seed (average of
the first 9 MACD values), a plain-loop reference implementation of Pine's
ta.ema / ta.macd, histogram = MACD - signal, the 4 TradingView colour states
(incl. zero and equal-to-yesterday), PPO, Ash's 9 Oct TradingView numbers
(signal recursion), short histories, non-default index, input not modified,
and input validation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema import ema_tradingview
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd import macd as M


def _bars(closes, start="2026-01-01") -> pd.DataFrame:
    ts = pd.date_range(start, periods=len(closes), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "close": np.asarray(closes, dtype="float64")})


@pytest.fixture
def wave() -> pd.DataFrame:
    """120 bars: trend + oscillation, so MACD crosses signal and zero."""
    i = np.arange(120)
    return _bars(1000 + 2 * i + 40 * np.sin(i / 6.0))


# --- Reference: Pine's ta.ema / ta.macd written as a plain loop ---------------

def _pine_ema(values, n):
    out, prev, window = [], None, []
    alpha = 2 / (n + 1)
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(math.nan)
            continue
        if prev is None:
            window.append(v)
            if len(window) < n:
                out.append(math.nan)
                continue
            prev = sum(window) / n                  # SMA seed
        else:
            prev = alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def test_matches_plain_pine_reference(wave):
    m = M.compute_macd(wave)
    closes = list(wave["close"])
    e12, e26 = _pine_ema(closes, 12), _pine_ema(closes, 26)
    ref_macd = [a - b for a, b in zip(e12, e26)]
    ref_sig = _pine_ema(ref_macd, 9)
    np.testing.assert_allclose(m["macd"], ref_macd, equal_nan=True, rtol=0, atol=1e-9)
    np.testing.assert_allclose(m["macd_signal"], ref_sig, equal_nan=True, rtol=0, atol=1e-9)


# --- Where each line starts ---------------------------------------------------

def test_first_values_at_bars_26_34_35(wave):
    m = M.compute_macd(wave)
    assert m["macd"].iloc[:25].isna().all() and pd.notna(m["macd"].iloc[25])        # bar 26
    assert m["macd_signal"].iloc[:33].isna().all() and pd.notna(m["macd_signal"].iloc[33])  # bar 34
    assert m["macd_hist"].iloc[:33].isna().all() and pd.notna(m["macd_hist"].iloc[33])
    assert m["macd_hist_state"].iloc[:34].isna().all() and m["macd_hist_state"].iloc[34] in M.HIST_STATES


def test_signal_seed_is_average_of_first_nine_macd(wave):
    m = M.compute_macd(wave)
    assert m["macd_signal"].iloc[33] == pytest.approx(m["macd"].iloc[25:34].mean(), abs=1e-9)


def test_macd_is_ema12_minus_ema26(wave):
    m = M.compute_macd(wave)
    diff = ema_tradingview(wave["close"], 12) - ema_tradingview(wave["close"], 26)
    pd.testing.assert_series_equal(m["macd"], diff, check_names=False)


def test_histogram_is_macd_minus_signal(wave):
    m = M.compute_macd(wave)
    pd.testing.assert_series_equal(m["macd_hist"], m["macd"] - m["macd_signal"], check_names=False)


# --- Ash's TradingView numbers (Nifty daily, 7-9 Oct 2026) ---------------------

def test_signal_recursion_reproduces_tradingview():
    # legend: histogram, MACD, signal
    tv = {"07": (-30.42, -344.03, -313.60), "08": (-43.97, -368.57, -324.60),
          "09": (-28.78, -360.57, -331.79)}
    for prev, cur in (("07", "08"), ("08", "09")):
        sig = 0.2 * tv[cur][1] + 0.8 * tv[prev][2]
        assert sig == pytest.approx(tv[cur][2], abs=0.01)
        assert tv[cur][1] - tv[cur][2] == pytest.approx(tv[cur][0], abs=0.011)
    # colours seen on the chart
    states = M.hist_states(pd.Series([tv["07"][0], tv["08"][0], tv["09"][0]]))
    assert list(states[1:]) == ["below_growing", "below_fading"]   # dark red, light red


# --- Histogram colour states --------------------------------------------------

def test_hist_states_all_four_and_edges():
    h = pd.Series([np.nan, 1.0, 2.0, 1.5, 1.5, 0.0, -1.0, -0.5, -0.5, 0.0])
    s = list(M.hist_states(h))
    assert s == [None, None,             # blank, no yesterday
                 "above_growing",        # 2.0 > 1.0
                 "above_fading",         # 1.5 < 2.0
                 "above_fading",         # equal -> not rising
                 "above_fading",         # 0 counts as above, falling
                 "below_growing",        # -1 < 0
                 "below_fading",         # -0.5 > -1
                 "below_growing",        # equal -> not rising
                 "above_growing"]        # back to 0 from below: above + rising


# --- PPO ----------------------------------------------------------------------

def test_ppo_is_macd_as_percent_of_ema26(wave):
    m = M.compute_macd(wave)
    e26 = ema_tradingview(wave["close"], 26)
    pd.testing.assert_series_equal(m["ppo"], m["macd"] / e26 * 100, check_names=False)


def test_ppo_is_scale_free(wave):
    scaled = wave.copy()
    scaled["close"] = scaled["close"] / 40          # same shape, much lower price
    a, b = M.compute_macd(wave), M.compute_macd(scaled)
    np.testing.assert_allclose(a["ppo"], b["ppo"], equal_nan=True, atol=1e-9)
    assert not np.allclose(a["macd"].dropna(), b["macd"].dropna())


# --- Short history / shapes ---------------------------------------------------

def test_fewer_than_26_bars_all_blank_no_error():
    m = M.compute_macd(_bars(range(1, 21)))
    assert m["macd"].isna().all() and m["macd_signal"].isna().all()
    assert m["macd_hist_state"].isna().all()


def test_30_bars_macd_but_no_signal():
    m = M.compute_macd(_bars(np.linspace(100, 130, 30)))
    assert m["macd"].notna().sum() == 5
    assert m["macd_signal"].isna().all()


def test_constant_prices_give_zero_and_light_green():
    m = M.compute_macd(_bars([500.0] * 40))
    assert m["macd"].dropna().eq(0).all()
    assert set(m["macd_hist_state"].dropna()) == {"above_fading"}   # 0 = above, not rising


def test_non_default_index(wave):
    shifted = wave.copy()
    shifted.index = shifted.index + 1000
    a = M.compute_macd(wave)
    b = M.compute_macd(shifted)
    np.testing.assert_allclose(a["macd_signal"], b["macd_signal"], equal_nan=True)


def test_input_not_modified(wave):
    original = wave.copy()
    M.compute_macd(wave)
    pd.testing.assert_frame_equal(wave, original)


def test_adds_exactly_the_macd_columns(wave):
    m = M.compute_macd(wave)
    assert list(m.columns) == list(wave.columns) + list(M.MACD_COLS)


# --- Validation (programming errors raise) ------------------------------------

@pytest.mark.parametrize("kwargs, msg", [
    ({"price_col": "adj"}, "price column"),
    ({"fast": 0}, "positive integer"),
    ({"signal": 2.5}, "positive integer"),
    ({"fast": True}, "positive integer"),
    ({"fast": 26, "slow": 12}, "shorter than slow"),
])
def test_bad_inputs_raise(wave, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        M.compute_macd(wave, **kwargs)


def test_unsorted_bars_raise(wave):
    with pytest.raises(ValueError, match="ascending"):
        M.compute_macd(wave.iloc[::-1])


# =============================================================================
# Part 3 — trend_macd, momentum_macd, macd_label
# =============================================================================

def _frame(**cols) -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    ts = pd.date_range("2026-01-01", periods=n, freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         **{k: np.asarray(v, dtype="float64") for k, v in cols.items()}})


def _mom_frame(macd_vals, signal_vals) -> pd.DataFrame:
    df = _frame(macd=macd_vals, macd_signal=signal_vals)
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["macd_hist_state"] = M.hist_states(df["macd_hist"])
    return df


# --- trend_macd ---------------------------------------------------------------

def test_trend_side_held_since_and_zero_crosses():
    nan = np.nan
    df = _frame(macd=[nan, nan, -2, -1, 1, 2, 0, -1])
    t = M.trend_macd(df)
    assert list(t["trend_side"].fillna(9)) == [9, 9, -1, -1, 1, 1, 0, -1]
    assert list(t["trend_held"].fillna(0)) == [0, 0, 1, 2, 1, 2, 1, 1]
    assert list(t["trend_from_start"]) == [False, False, True, True, False, False, False, False]
    assert t["trend_since"].iloc[3] == df["ts"].iloc[2]
    assert t["trend_since"].iloc[5] == df["ts"].iloc[4]
    # TradingView rule: above = >0 now and <=0 before; below = <0 now and >=0 before
    assert list(t.index[t["zero_cross_above"]]) == [4]
    assert list(t.index[t["zero_cross_below"]]) == [7]       # from 0 to -1 counts (prev >= 0)


def test_trend_matches_plain_loop(wave):
    t = M.trend_macd(M.compute_macd(wave))
    held, prev, n = [], None, 0
    for v in t["macd"]:
        if pd.isna(v):
            held.append(np.nan); prev = None; n = 0; continue
        side = np.sign(v)
        n = n + 1 if side == prev else 1
        prev = side
        held.append(n)
    np.testing.assert_allclose(t["trend_held"], held, equal_nan=True)
    assert t["zero_cross_above"].sum() + t["zero_cross_below"].sum() >= 2   # wave crosses zero


# --- momentum_macd ------------------------------------------------------------

def test_signal_cross_and_zone():
    #        macd: -5  -4  -3  -1   2   3
    #      signal: -3  -3  -3  -2   1   4
    #        hist: -2  -1   0   1   1  -1
    m = M.momentum_macd(_mom_frame([-5, -4, -3, -1, 2, 3], [-3, -3, -3, -2, 1, 4]))
    assert list(m["mom_side"]) == [-1, -1, 0, 1, 1, -1]
    assert list(m.index[m["signal_cross_above"]]) == [3]     # prev equal (-3 = -3) counts
    assert list(m.index[m["signal_cross_below"]]) == [5]
    assert m["signal_cross_zone"].iloc[3] == "below_zero"    # MACD -1 on the cross candle
    assert m["signal_cross_zone"].iloc[5] == "above_zero"    # MACD 3
    assert m["signal_cross_zone"].drop([3, 5]).isna().all()
    assert list(m["mom_gap"]) == [-2, -1, 0, 1, 1, -1]


def test_signal_cross_at_zero_tag():
    m = M.momentum_macd(_mom_frame([-1, 0], [0.5, -0.5]))
    assert bool(m["signal_cross_above"].iloc[1]) and m["signal_cross_zone"].iloc[1] == "at_zero"


def test_momentum_turn_and_state_held():
    # hist: -5 -6 -4 -3 1 2 1.5   (macd = hist, signal = 0)
    h = [-5, -6, -4, -3, 1, 2, 1.5]
    m = M.momentum_macd(_mom_frame(h, [0] * len(h)))
    assert list(m["macd_hist_state"]) == [None, "below_growing", "below_fading", "below_fading",
                                          "above_growing", "above_growing", "above_fading"]
    assert list(m["momentum_turn"]) == [False, False, True, False, False, False, True]
    # side change (below -> above) is a signal cross, not a turn
    assert bool(m["signal_cross_above"].iloc[4]) and not m["momentum_turn"].iloc[4]
    assert list(m["hist_state_held"].fillna(0)) == [0, 1, 1, 2, 1, 2, 1]


def test_blank_breaks_run_and_from_start():
    held, since, from_start = M._runs(pd.Series([1.0, 1.0, np.nan, 1.0]),
                                      pd.Series(["a", "b", "c", "d"]))
    assert list(held.fillna(0)) == [1, 2, 0, 1]
    assert list(from_start) == [True, True, False, False]
    assert since.iloc[3] == "d"


# --- macd_label ---------------------------------------------------------------

@pytest.mark.parametrize("trend, mom, label", [
    (1, 1, "STRONG UPTREND"),
    (1, -1, "UPTREND PAUSING"),
    (-1, 1, "DOWNTREND WEAKENING"),
    (-1, -1, "STRONG DOWNTREND"),
    (0, 1, "NEUTRAL"),
    (-1, 0, "NEUTRAL"),
    (np.nan, 1, "n/a (not enough history)"),
    (1, np.nan, "n/a (not enough history)"),
])
def test_macd_label(trend, mom, label):
    df = pd.DataFrame({"trend_side": [trend], "mom_side": [mom]})
    assert M.macd_label(df).iloc[0] == label


def test_macd_all_consistent_on_wave(wave):
    m = M.macd_all(wave)
    for col in ("trend_side", "trend_held", "zero_cross_above", "mom_side", "signal_cross_zone",
                "hist_state_held", "momentum_turn", "macd_label"):
        assert col in m.columns
    ok = m.dropna(subset=["trend_side", "mom_side"])
    both_down = ok[(ok["trend_side"] < 0) & (ok["mom_side"] < 0)]
    assert (both_down["macd_label"] == "STRONG DOWNTREND").all()
    assert (m.loc[m["macd_signal"].isna(), "macd_label"] == "n/a (not enough history)").all()
    # every signal cross is tagged, nothing else is
    crosses = m["signal_cross_above"] | m["signal_cross_below"]
    assert m.loc[crosses, "signal_cross_zone"].isin(M.ZONES).all()
    assert m.loc[~crosses, "signal_cross_zone"].isna().all()


def test_part3_input_not_modified(wave):
    base = M.compute_macd(wave)
    original = base.copy()
    M.momentum_macd(M.trend_macd(base))
    pd.testing.assert_frame_equal(base, original)


def test_part3_missing_columns_raise(wave):
    with pytest.raises(ValueError, match="compute_macd"):
        M.trend_macd(wave)
    with pytest.raises(ValueError, match="compute_macd"):
        M.momentum_macd(wave)
    with pytest.raises(ValueError, match="compute_macd"):
        M.macd_label(wave)


def test_part3_unsorted_raises(wave):
    with pytest.raises(ValueError, match="ascending"):
        M.trend_macd(M.compute_macd(wave).iloc[::-1])
