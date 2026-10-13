"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi/test_rsi.py

Unit tests for rsi.compute_rsi (part 1). Pure maths -- no R2, no network.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi -v
(results also written to logs/rsi_test_logs/test_rsi.log by conftest.py)

Covers: a hand-worked 3-RSI, a plain-loop reference of Pine's ta.rsi / ta.sma, where
each line starts (candles 15 and 28), Pine's special cases (no losses -> 100, no gains
-> 0, flat prices -> 100), the 0-100 range, scale-free values, the hidden MA = SMA of
RSI, short history, non-default index, input safety and validation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi import rsi as R


def _bars(closes, start="2026-01-01") -> pd.DataFrame:
    ts = pd.date_range(start, periods=len(closes), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "close": np.asarray(closes, dtype="float64")})


@pytest.fixture
def walk() -> pd.DataFrame:
    """300 candles: up phase, down phase, chop -- RSI visits every zone."""
    rng = np.random.default_rng(5)
    steps = np.concatenate([rng.normal(15, 40, 100), rng.normal(-15, 40, 100),
                            rng.normal(0, 40, 100)])
    return _bars(22000 + np.cumsum(steps))


# --- Reference: Pine's ta.rsi and ta.sma written as plain loops ----------------------

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


def _pine_rsi(closes, n=14, m=14):
    gains, losses = [math.nan], [math.nan]
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    up, down = _pine_rma(gains, n), _pine_rma(losses, n)
    rsi = []
    for u, d in zip(up, down):
        if math.isnan(u) or math.isnan(d):
            rsi.append(math.nan)
        elif d == 0:
            rsi.append(100.0)
        elif u == 0:
            rsi.append(0.0)
        else:
            rsi.append(100 - 100 / (1 + u / d))
    ma = [math.nan if i < m - 1 or any(math.isnan(x) for x in rsi[i - m + 1:i + 1])
          else sum(rsi[i - m + 1:i + 1]) / m for i in range(len(rsi))]
    return rsi, ma


def test_matches_plain_pine_reference(walk):
    r = R.compute_rsi(walk)
    ref_rsi, ref_ma = _pine_rsi(list(walk["close"]))
    np.testing.assert_allclose(r["rsi"], ref_rsi, equal_nan=True, rtol=0, atol=1e-9)
    np.testing.assert_allclose(r["rsi_ma"], ref_ma, equal_nan=True, rtol=0, atol=1e-9)


# --- Hand-worked -------------------------------------------------------------------

def test_hand_worked_3_rsi():
    # closes 10, 11, 12, 11, 13 -> changes +1, +1, -1, +2
    # candle 4: up = (1+1+0)/3 = 0.6667, down = (0+0+1)/3 = 0.3333 -> RS 2 -> RSI 66.6667
    # candle 5: up = (0.6667*2 + 2)/3 = 1.1111, down = (0.3333*2 + 0)/3 = 0.2222 -> RS 5 -> RSI 83.3333
    r = R.compute_rsi(_bars([10, 11, 12, 11, 13]), length=3, ma_length=2)
    assert r["rsi"].iloc[:3].isna().all()
    assert list(r["rsi"].iloc[3:].round(4)) == [66.6667, 83.3333]
    assert r["rsi_ma"].iloc[4] == pytest.approx((200 / 3 + 250 / 3) / 2)   # SMA2 of the two


# --- Where each line starts ----------------------------------------------------------

def test_first_values_at_candles_15_and_28(walk):
    r = R.compute_rsi(walk)
    assert r["rsi"].iloc[:14].isna().all() and pd.notna(r["rsi"].iloc[14])        # candle 15
    assert r["rsi_ma"].iloc[:27].isna().all() and pd.notna(r["rsi_ma"].iloc[27])   # candle 28


# --- Pine's special cases ------------------------------------------------------------

def test_only_gains_is_100_only_losses_is_0():
    assert (R.compute_rsi(_bars(np.arange(100.0, 130.0)))["rsi"].dropna() == 100).all()
    assert (R.compute_rsi(_bars(np.arange(130.0, 100.0, -1)))["rsi"].dropna() == 0).all()


def test_flat_prices_give_100_like_pine():
    # no gains and no losses: Pine checks down == 0 first -> 100
    r = R.compute_rsi(_bars([500.0] * 40))
    assert (r["rsi"].dropna() == 100).all() and r["rsi"].notna().sum() == 26


def test_values_in_range_and_scale_free(walk):
    a = R.compute_rsi(walk)
    s = a["rsi"].dropna()
    assert (s >= 0).all() and (s <= 100).all()
    scaled = walk.copy()
    scaled["close"] = scaled["close"] / 40                 # same shape, lower price
    np.testing.assert_allclose(R.compute_rsi(scaled)["rsi"], a["rsi"], equal_nan=True, atol=1e-9)


def test_rsi_ma_is_sma_of_rsi(walk):
    r = R.compute_rsi(walk)
    pd.testing.assert_series_equal(r["rsi_ma"], r["rsi"].rolling(14).mean(), check_names=False)


# --- Shapes and safety ---------------------------------------------------------------

def test_short_history_all_blank_no_error():
    r = R.compute_rsi(_bars(range(1, 15)))                 # 14 candles = 13 changes
    assert r["rsi"].isna().all() and r["rsi_ma"].isna().all()


def test_non_default_index(walk):
    shifted = walk.copy()
    shifted.index = shifted.index + 1000
    np.testing.assert_allclose(R.compute_rsi(shifted)["rsi"], R.compute_rsi(walk)["rsi"],
                               equal_nan=True)


def test_input_not_modified(walk):
    original = walk.copy()
    R.compute_rsi(walk)
    pd.testing.assert_frame_equal(walk, original)


def test_adds_exactly_the_rsi_columns(walk):
    r = R.compute_rsi(walk)
    assert list(r.columns) == list(walk.columns) + list(R.RSI_COLS)


# --- Validation (programming errors raise) -------------------------------------------

@pytest.mark.parametrize("kwargs, msg", [
    ({"price_col": "adj"}, "price column"),
    ({"length": 0}, "positive integer"),
    ({"length": 2.5}, "positive integer"),
    ({"ma_length": True}, "positive integer"),
])
def test_bad_inputs_raise(walk, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        R.compute_rsi(walk, **kwargs)


def test_unsorted_bars_raise(walk):
    with pytest.raises(ValueError, match="ascending"):
        R.compute_rsi(walk.iloc[::-1])


# =============================================================================
# Part 2 — zones, states, events, label
# =============================================================================

def _rsi_frame(rsi, ma=None) -> pd.DataFrame:
    n = len(rsi)
    ts = pd.date_range("2026-01-01", periods=n, freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "rsi": np.asarray(rsi, float),
                         "rsi_ma": np.asarray(ma if ma is not None else [np.nan] * n, float)})


@pytest.mark.parametrize("value, zone", [
    (95, "overbought"), (80, "overbought"), (79.99, "strong_bull"), (70, "strong_bull"),
    (69.99, "bullish"), (55.01, "bullish"), (55, "sr_zone"), (50, "sr_zone"), (45, "sr_zone"),
    (44.99, "bearish"), (30, "bearish"), (29.99, "strong_bear"), (20, "strong_bear"),
    (19.99, "oversold"), (0, "oversold"), (100, "overbought"),
])
def test_zone_edges(value, zone):
    # Ash 2026-10-13: 80 and 70 belong to the upper zone, 45 and 55 inside the S&R zone,
    # 30 and 20 belong to the zone above them.
    assert R.rsi_zone(pd.Series([float(value)])).iloc[0] == zone


def test_zone_blank():
    assert R.rsi_zone(pd.Series([np.nan])).iloc[0] is None


def test_zone_change_from_held_since_and_direction():
    #   RSI : 40  42  46  50  56  57  54  44
    #   zone: brs brs sr  sr  bul bul sr  brs
    s = R.rsi_states(_rsi_frame([40, 42, 46, 50, 56, 57, 54, 44]))
    assert list(s["rsi_zone"]) == ["bearish", "bearish", "sr_zone", "sr_zone", "bullish",
                                   "bullish", "sr_zone", "bearish"]
    assert list(s.index[s["zone_change"]]) == [2, 4, 6, 7]
    assert list(s["zone_from"].dropna()) == ["bearish", "sr_zone", "bullish", "sr_zone"]
    assert list(s.loc[s["zone_change"], "zone_change_up"]) == [True, True, False, False]
    assert s["zone_change_up"].iloc[0] is None
    assert list(s["rsi_zone_held"]) == [1, 2, 1, 2, 1, 2, 1, 1]
    assert s["rsi_zone_since"].iloc[3] == s["ts"].iloc[2]
    assert list(s["rsi_zone_from_start"]) == [True, True] + [False] * 6


def test_zone_change_can_skip_zones():
    s = R.rsi_states(_rsi_frame([40, 60, 85, 25]))       # bearish -> bullish -> overbought -> strong bear
    assert list(s["zone_from"].iloc[1:]) == ["bearish", "bullish", "overbought"]
    assert list(s["zone_change_up"].iloc[1:]) == [True, True, False]


def test_first_value_after_blanks_is_not_a_change():
    s = R.rsi_states(_rsi_frame([np.nan, np.nan, 60, 61]))
    assert not s["zone_change"].any()


def test_cross_50_tradingview_rule():
    #   RSI: 48 50 51 50 49.9 52
    s = R.rsi_states(_rsi_frame([48, 50, 51, 50, 49.9, 52]))
    assert list(s.index[s["rsi_cross_above_50"]]) == [2, 5]   # 50 itself is not above
    assert list(s.index[s["rsi_cross_below_50"]]) == [4]      # from 50 (>=) to 49.9
    assert list(s["rsi_side50"]) == [-1, 0, 1, 0, -1, 1]


def test_slope_and_held():
    s = R.rsi_states(_rsi_frame([40, 42, 44, 44, 41, 39]))
    assert list(s["rsi_slope"].fillna(9)) == [9, 1, 1, 0, -1, -1]
    assert list(s["rsi_slope_held"].fillna(0)) == [0, 1, 2, 1, 1, 2]


def test_hidden_ma_cross_recorded():
    s = R.rsi_states(_rsi_frame([40, 45, 50, 48], ma=[44, 45, 46, 49]))
    assert list(s["rsi_ma_side"]) == [-1, 0, 1, -1]
    assert list(s.index[s["rsi_ma_cross_above"]]) == [2]
    assert list(s.index[s["rsi_ma_cross_below"]]) == [3]


@pytest.mark.parametrize("value, label", [
    (85, "OVERBOUGHT (>80)"), (75, "STRONG BULL (70–80)"), (60, "BULLISH (55–70)"),
    (50, "RSI S&R ZONE (45–55)"), (36.50, "BEARISH (30–45)"),      # Nifty daily 9 Oct 2026
    (25, "STRONG BEAR (20–30)"), (10, "OVERSOLD (<20)"), (np.nan, R.LABEL_NA),
])
def test_rsi_label(value, label):
    assert R.rsi_label(R.rsi_states(_rsi_frame([value]))).iloc[0] == label


def test_rsi_all_on_walk(walk):
    a = R.rsi_all(walk)
    assert (a.loc[a["rsi"].isna(), "rsi_label"] == R.LABEL_NA).all()
    assert set(a["rsi_zone"].dropna()) == set(R.ZONES)           # the walk visits every zone
    ch = a["zone_change"]
    assert (a.loc[ch, "rsi_zone"] != a.loc[ch, "zone_from"]).all()
    assert (a.loc[ch, "zone_from"] == a["rsi_zone"].shift(1)[ch]).all()
    assert a.loc[~ch, "zone_from"].isna().all()


def test_part2_input_not_modified(walk):
    base = R.compute_rsi(walk)
    original = base.copy()
    R.rsi_states(base)
    pd.testing.assert_frame_equal(base, original)


def test_part2_missing_columns_and_unsorted_raise(walk):
    with pytest.raises(ValueError, match="compute_rsi"):
        R.rsi_states(walk)
    with pytest.raises(ValueError, match="rsi_states"):
        R.rsi_label(R.compute_rsi(walk))
    with pytest.raises(ValueError, match="ascending"):
        R.rsi_states(R.compute_rsi(walk).iloc[::-1])


# --- Zone-change wording (Ash, 2026-10-13) --------------------------------------------

@pytest.mark.parametrize("value, z_from, z_to, text", [
    # the table Ash approved: real Nifty values where we have them
    (57.68, "sr_zone", "bullish", "RSI 57.68 RSI S&R ZONE (45–55) rising strong up into BULLISH (55–70)"),
    (70.16, "bullish", "strong_bull", "RSI 70.16 BULLISH (55–70) rising strong up into STRONG BULL (70–80)"),
    (22.10, "oversold", "strong_bear", "RSI 22.10 OVERSOLD (<20) rising up into STRONG BEAR (20–30)"),
    (33.66, "strong_bear", "bearish", "RSI 33.66 STRONG BEAR (20–30) rising up into BEARISH (30–45)"),
    (46.20, "bearish", "sr_zone", "RSI 46.20 BEARISH (30–45) rising up into RSI S&R ZONE (45–55)"),
    (44.95, "sr_zone", "bearish", "RSI 44.95 RSI S&R ZONE (55–45) falling strong down into BEARISH (45–30)"),
    (26.44, "bearish", "strong_bear", "RSI 26.44 BEARISH (45–30) falling strong down into STRONG BEAR (30–20)"),
    (67.83, "strong_bull", "bullish", "RSI 67.83 STRONG BULL (80–70) falling down into BULLISH (70–55)"),
    (54.81, "bullish", "sr_zone", "RSI 54.81 BULLISH (70–55) falling down into RSI S&R ZONE (55–45)"),
    # extremes and a skip
    (85.00, "strong_bull", "overbought", "RSI 85.00 STRONG BULL (70–80) rising strong up into OVERBOUGHT (>80)"),
    (18.40, "strong_bear", "oversold", "RSI 18.40 STRONG BEAR (30–20) falling strong down into OVERSOLD (<20)"),
    (60.00, "bearish", "bullish", "RSI 60.00 BEARISH (30–45) rising strong up into BULLISH (55–70)"),
])
def test_zone_change_text(value, z_from, z_to, text):
    assert R.zone_change_text(value, z_from, z_to) == text


def test_zone_change_text_rejects_non_changes():
    with pytest.raises(ValueError, match="not a zone change"):
        R.zone_change_text(50, "sr_zone", "sr_zone")
    with pytest.raises(ValueError, match="unknown zone"):
        R.zone_change_text(50, "strong_up", "bullish")
