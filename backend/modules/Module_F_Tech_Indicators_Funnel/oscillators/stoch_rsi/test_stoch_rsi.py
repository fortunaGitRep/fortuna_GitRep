"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/test_stoch_rsi.py

Unit tests for stoch_rsi.py (no R2). Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi -v
Results also go to logs/stoch_rsi_test_logs/test_stoch_rsi.log (conftest.py).

Where the expected values come from:
  - an independent plain-loop copy of Pine's ta.rsi / ta.stoch / ta.sma written only for
    these tests (no pandas rolling, no Fortuna code);
  - small series worked out by hand;
  - compute_rsi itself (proves the RSI is reused, not re-implemented);
  - part 2: hand-built %K / %D series with the zones, events and wording Ash approved
    (2026-10-13).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi import compute_rsi
from modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi import (
    LABEL_NA,
    SRSI_COLS,
    compare_cross_rules,
    compute_stoch_rsi,
    flat_windows,
    fmt2,
    kd_cross_text,
    kd_crosses,
    srsi_all,
    srsi_label,
    srsi_states,
    srsi_zone,
    stoch_from_rsi,
    zone_change_text,
)

NAN = math.nan


def _bars(closes, start="2020-01-01"):
    ts = pd.date_range(start, periods=len(closes), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "close": np.asarray(closes, dtype=float)})


def _walk(n=300, seed=7):
    rng = np.random.default_rng(seed)
    return _bars(1000 + np.cumsum(rng.normal(0, 5, n)))


# --- independent Pine reference (plain loops) -------------------------------------

def _pine_rsi(close, n=14):
    """Pine ta.rsi: rma seeded with the simple average of the first n gains / losses."""
    m, a = len(close), 1.0 / n
    out = [NAN] * m
    up = dn = None
    for i in range(1, m):
        ch = close[i] - close[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if i < n:
            continue
        if i == n:
            up = sum(max(close[j] - close[j - 1], 0.0) for j in range(1, n + 1)) / n
            dn = sum(max(close[j - 1] - close[j], 0.0) for j in range(1, n + 1)) / n
        else:
            up = a * g + (1 - a) * up
            dn = a * l + (1 - a) * dn
        out[i] = 100.0 if dn == 0 else 0.0 if up == 0 else 100 - 100 / (1 + up / dn)
    return out


def _pine_sma(x, n):
    out = [NAN] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if any(math.isnan(v) for v in w):
            continue
        out[i] = sum(w) / n
    return out


def _pine_stoch(rsi, length, sk, sd):
    raw = [NAN] * len(rsi)
    for i in range(length - 1, len(rsi)):
        w = rsi[i - length + 1:i + 1]
        if any(math.isnan(v) for v in w):
            continue
        hi, lo = max(w), min(w)
        if hi - lo == 0:
            continue                       # Pine: division by zero -> na
        raw[i] = 100 * (rsi[i] - lo) / (hi - lo)
    k = _pine_sma(raw, sk)
    return raw, k, _pine_sma(k, sd)


def _close(a, b):
    return np.allclose(np.asarray(a, float), np.asarray(b, float),
                       rtol=0, atol=1e-9, equal_nan=True)


# --- formula -----------------------------------------------------------------------

def test_matches_plain_pine_reference():
    df = _walk(300)
    out = compute_stoch_rsi(df)
    rsi = _pine_rsi(df["close"].tolist(), 14)
    raw, k, d = _pine_stoch(rsi, 14, 3, 3)
    assert _close(out["srsi_rsi"], rsi)
    assert _close(out["srsi_raw"], raw)
    assert _close(out["srsi_k"], k)
    assert _close(out["srsi_d"], d)


def test_custom_lengths_match_reference():
    df = _walk(200, seed=3)
    out = compute_stoch_rsi(df, rsi_length=5, stoch_length=6, smooth_k=2, smooth_d=4)
    rsi = _pine_rsi(df["close"].tolist(), 5)
    raw, k, d = _pine_stoch(rsi, 6, 2, 4)
    assert _close(out["srsi_k"], k)
    assert _close(out["srsi_d"], d)


def test_hand_worked_window():
    # RSI 10, 20, 30, 25; window 3: candle 3 = (30-10)/(30-10) = 100; candle 4 = (25-20)/(30-20) = 50
    raw, k, d = stoch_from_rsi(pd.Series([10.0, 20, 30, 25]), 3, 1, 2)
    assert _close(raw, [NAN, NAN, 100, 50])
    assert _close(k, [NAN, NAN, 100, 50])
    assert _close(d, [NAN, NAN, NAN, 75])


def test_hand_worked_flat_window_is_blank_then_recovers():
    # window 3; the window 60, 60, 60 (candle 8) has range 0 -> raw blank (Pine na)
    rsi = pd.Series([10.0, 20, 30, 40, 50, 60, 60, 60, 70, 80, 90, 100, 90, 80])
    raw, k, d = stoch_from_rsi(rsi, 3, 3, 3)
    assert _close(raw, [NAN, NAN, 100, 100, 100, 100, 100, NAN, 100, 100, 100, 100, 0, 0])
    # %K blank for the 3 candles whose window holds the blank raw, then back
    assert _close(k, [NAN] * 4 + [100, 100, 100, NAN, NAN, NAN, 100, 100, 200 / 3, 100 / 3])
    # %D blank for 5 candles, then back: (100+100+66.67)/3, (100+66.67+33.33)/3
    assert _close(d, [NAN] * 6 + [100, NAN, NAN, NAN, NAN, NAN, 800 / 9, 200 / 3])


def test_first_values_at_candles_15_28_30_32():
    out = compute_stoch_rsi(_walk(60))
    first = {c: out[c].first_valid_index() for c in SRSI_COLS}
    assert first == {"srsi_rsi": 14, "srsi_raw": 27, "srsi_k": 29, "srsi_d": 31}


def test_rsi_column_is_compute_rsi():
    df = _walk(120)
    pd.testing.assert_series_equal(compute_stoch_rsi(df)["srsi_rsi"], compute_rsi(df)["rsi"],
                                   check_names=False)


def test_d_is_sma3_of_k():
    out = compute_stoch_rsi(_walk(200))
    assert _close(out["srsi_d"], out["srsi_k"].rolling(3, min_periods=3).mean())


def test_values_in_range():
    out = compute_stoch_rsi(_walk(500, seed=11))
    for c in ("srsi_raw", "srsi_k", "srsi_d"):
        v = out[c].dropna()
        assert len(v) and v.min() >= -1e-9 and v.max() <= 100 + 1e-9


def test_scale_free():
    df = _walk(200)
    big = df.assign(close=df["close"] * 10)
    a, b = compute_stoch_rsi(df), compute_stoch_rsi(big)
    for c in ("srsi_k", "srsi_d"):
        assert np.allclose(a[c], b[c], atol=1e-7, equal_nan=True)


# --- edges and contract ------------------------------------------------------------

def test_flat_prices_all_blank_like_pine():
    # flat close -> Pine RSI 100 on every candle -> every window has range 0 -> blank
    out = compute_stoch_rsi(_bars([100.0] * 60))
    assert (out["srsi_rsi"].dropna() == 100).all()
    for c in ("srsi_raw", "srsi_k", "srsi_d"):
        assert out[c].isna().all()


def test_short_history_all_blank_no_error():
    out = compute_stoch_rsi(_walk(25))           # RSI from candle 15, raw needs candle 28
    assert out["srsi_rsi"].notna().sum() == 11
    for c in ("srsi_raw", "srsi_k", "srsi_d"):
        assert out[c].isna().all()


def test_non_default_index():
    df = _walk(80)
    shifted = df.set_index(pd.Index(range(1000, 1080)))
    a, b = compute_stoch_rsi(df), compute_stoch_rsi(shifted)
    assert list(b.index) == list(range(1000, 1080))
    assert _close(a["srsi_k"].to_numpy(), b["srsi_k"].to_numpy())


def test_input_not_modified():
    df = _walk(80)
    before = df.copy()
    compute_stoch_rsi(df)
    pd.testing.assert_frame_equal(df, before)


def test_adds_exactly_the_srsi_columns():
    df = _walk(80)
    out = compute_stoch_rsi(df)
    assert list(out.columns) == list(df.columns) + list(SRSI_COLS)


@pytest.mark.parametrize("kwargs", [
    {"stoch_length": 0}, {"stoch_length": 2.5}, {"stoch_length": True},
    {"smooth_k": 0}, {"smooth_d": -1}, {"rsi_length": 0},
])
def test_bad_lengths_raise(kwargs):
    with pytest.raises(ValueError):
        compute_stoch_rsi(_walk(60), **kwargs)


def test_missing_price_column_raises():
    with pytest.raises(ValueError):
        compute_stoch_rsi(_walk(60).rename(columns={"close": "c"}))


def test_unsorted_raises():
    with pytest.raises(ValueError):
        compute_stoch_rsi(_walk(60).iloc[::-1].reset_index(drop=True))


def test_stoch_from_rsi_rejects_non_series():
    with pytest.raises(ValueError):
        stoch_from_rsi([10.0, 20, 30], 3, 1, 1)


# --- printing and the flat diagnostic ----------------------------------------------

@pytest.mark.parametrize("value, text", [
    (-1e-15, "0.00"), (-0.0, "0.00"), (0.004, "0.00"), (56.04, "56.04"),
    (99.999, "100.00"), (NAN, "n/a"), (None, "n/a"),
])
def test_fmt2(value, text):
    assert fmt2(value) == text


def test_flat_windows_counts():
    df = pd.DataFrame({"srsi_rsi": [10.0, 20, 30, 30, 30, 30 + 1e-10, 40]})
    fw = flat_windows(df, stoch_length=3)
    assert fw["windows"] == 5
    assert fw["exact"] == 1 and fw["exact_at"] == [4]
    assert fw["near"] == 1 and fw["near_at"] == [5]
    assert fw["smallest_at"] == 5 and 0 < fw["smallest"] < 1e-9


def test_flat_windows_none_on_walk():
    fw = flat_windows(compute_stoch_rsi(_walk(300)))
    assert fw["exact"] == 0 and fw["near"] == 0 and fw["smallest"] > 0


def test_flat_windows_needs_compute():
    with pytest.raises(ValueError):
        flat_windows(_walk(30))


# --- part 2: zones, states, events, label, wording ----------------------------------

def _kd(k, d=None):
    """A frame shaped like compute_stoch_rsi output (only what srsi_states needs)."""
    k = [NAN if v is None else float(v) for v in k]
    d = k if d is None else [NAN if v is None else float(v) for v in d]
    ts = pd.date_range("2026-01-01", periods=len(k), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "srsi_k": k, "srsi_d": d})


@pytest.mark.parametrize("value, zone", [
    (100, "overbought"), (80, "overbought"), (79.99, "middle"), (50, "middle"),
    (20, "middle"), (19.99, "oversold"), (0, "oversold"), (-1e-15, "oversold"),
])
def test_zone_edges(value, zone):
    assert srsi_zone(pd.Series([float(value)]))[0] == zone


def test_zone_blank():
    assert srsi_zone(pd.Series([NAN]))[0] is None


def test_zone_change_held_and_direction():
    out = srsi_states(_kd([None, 10, 25, 85, 90, 50, 15]))
    assert list(out["srsi_zone"]) == [None, "oversold", "middle", "overbought", "overbought",
                                      "middle", "oversold"]
    assert list(out["srsi_zone_change"]) == [False, False, True, True, False, True, True]
    assert list(out["srsi_zone_from"])[2:] == ["oversold", "middle", None, "overbought", "middle"]
    assert list(out["srsi_zone_change_up"])[2:] == [True, True, None, False, False]
    assert list(out["srsi_zone_held"])[1:] == [1, 1, 1, 2, 1, 1]
    assert out["srsi_zone_since"].iloc[4] == out["ts"].iloc[3]


def test_zone_can_skip_middle():
    out = srsi_states(_kd([85, 10]))
    assert bool(out["srsi_zone_change"].iloc[1])
    assert out["srsi_zone_from"].iloc[1] == "overbought" and out["srsi_zone_change_up"].iloc[1] is False


def test_kd_cross_tradingview_rule_and_zone_tag():
    # side -1, 0, +1, 0, -1: equal is not a cross; the candle after equal is
    out = srsi_states(_kd([10, 20, 30, 30, 25], [20, 20, 25, 30, 30]))
    assert list(out["srsi_kd_side"]) == [-1, 0, 1, 0, -1]
    assert list(out["srsi_kd_cross_above"]) == [False, False, True, False, False]
    assert list(out["srsi_kd_cross_below"]) == [False, False, False, False, True]
    assert list(out["srsi_kd_cross_zone"]) == [None, None, "middle", None, "middle"]


def test_kd_cross_in_overbought_and_oversold():
    ob = srsi_states(_kd([92, 91.2], [91, 93.05]))
    assert bool(ob["srsi_kd_cross_below"].iloc[1]) and ob["srsi_kd_cross_zone"].iloc[1] == "overbought"
    os_ = srsi_states(_kd([4, 9], [5, 6]))
    assert bool(os_["srsi_kd_cross_above"].iloc[1]) and os_["srsi_kd_cross_zone"].iloc[1] == "oversold"


def test_kd_side_held_and_since():
    out = srsi_states(_kd([10, 30, 40, 50, 20], [20, 20, 20, 20, 30]))
    assert list(out["srsi_kd_held"]) == [1, 1, 2, 3, 1]
    assert out["srsi_kd_since"].iloc[3] == out["ts"].iloc[1]


def test_float_leftovers_raw_rule_vs_tolerance():
    # %K and %D both "100" but a few 1e-12 apart: the raw (TradingView) rule makes a
    # cross below then above; with tolerance 1e-9 they are equal and only the real
    # separation at the end is a cross.
    k = [100, 100 - 1e-12, 100, 100, 95]
    d = [100, 100, 100 - 1e-12, 100, 98]
    ra, rb = kd_crosses(pd.Series(k), pd.Series(d), 0.0)
    ta, tb = kd_crosses(pd.Series(k), pd.Series(d), 1e-9)
    assert list(ra) == [False, False, True, False, False]
    assert list(rb) == [False, True, False, False, True]
    assert list(ta) == [False] * 5
    assert list(tb) == [False, False, False, False, True]
    cc = compare_cross_rules(_kd(k, d), 1e-9)
    assert (cc["raw_above"], cc["raw_below"], cc["tol_above"], cc["tol_below"]) == (1, 2, 0, 1)
    assert cc["only_raw"] == [1, 2] and cc["only_tol"] == []


def test_default_equal_lines_no_cross_until_they_separate():
    # Ash, 2026-10-13: equal = say equal, no cross; cross on the candle they separate.
    # Like 1D 5 / 6 / 7 Jul 2023: 100.00 / 99.27, 100.00 / 100.00, 85.87 / 95.29
    out = srsi_states(_kd([100, 100 - 1e-12, 85.87], [99.27, 100, 95.29]))
    assert list(out["srsi_kd_side"]) == [1, 0, -1]
    assert list(out["srsi_kd_cross_below"]) == [False, False, True]
    assert not out["srsi_kd_cross_above"].any()


def test_slope_ignores_float_leftovers():
    out = srsi_states(_kd([90, 100, 100 - 1e-12, 100, 60]))
    assert list(out["srsi_slope"])[1:] == [1, 0, 0, -1]
    assert list(out["srsi_slope_held"])[2:4] == [1, 2]


def test_pinned_at_100_and_0():
    out = srsi_states(_kd([100, 100 - 1e-12, 100, 50, 0, 1e-13, -1e-15, 30]))
    assert list(out["srsi_pinned"]) == [1, 1, 1, 0, -1, -1, -1, 0]
    assert list(out["srsi_pinned_held"])[:3] == [1, 2, 3]
    assert list(out["srsi_pinned_held"])[4:7] == [1, 2, 3]


def test_blank_k_gives_blank_states():
    out = srsi_states(_kd([None, None, 50]))
    assert out["srsi_zone"].iloc[0] is None
    assert pd.isna(out["srsi_kd_side"].iloc[0]) and pd.isna(out["srsi_pinned"].iloc[0])
    assert not out["srsi_kd_cross_above"].iloc[:2].any()
    assert not out["srsi_zone_change"].any()


@pytest.mark.parametrize("k, label", [
    (85, "OVERBOUGHT (>80)"), (50, "MIDDLE (20–80)"), (5, "OVERSOLD (<20)"), (None, LABEL_NA),
    (56.04, "MIDDLE (20–80)"),          # Nifty 1D Fri 9 Oct 2026
    (96.77, "OVERBOUGHT (>80)"),        # Nifty 60m Fri 9 Oct 2026 15:15
])
def test_srsi_label(k, label):
    out = srsi_states(_kd([k]))
    assert srsi_label(out).iloc[0] == label


@pytest.mark.parametrize("k, z_from, z_to, text", [
    (83.12, "middle", "overbought", "%K 83.12 MIDDLE (20–80) rising into OVERBOUGHT (>80)"),
    (18.40, "middle", "oversold", "%K 18.40 MIDDLE (80–20) falling into OVERSOLD (<20)"),
    (79.10, "overbought", "middle", "%K 79.10 OVERBOUGHT (>80) falling into MIDDLE (80–20)"),
    (21.50, "oversold", "middle", "%K 21.50 OVERSOLD (<20) rising into MIDDLE (20–80)"),
    (12.00, "overbought", "oversold", "%K 12.00 OVERBOUGHT (>80) falling into OVERSOLD (<20)"),
])
def test_zone_change_text(k, z_from, z_to, text):
    assert zone_change_text(k, z_from, z_to) == text


def test_zone_change_text_rejects_non_changes():
    with pytest.raises(ValueError):
        zone_change_text(50, "middle", "middle")
    with pytest.raises(ValueError):
        zone_change_text(50, "middle", "bullish")


def test_kd_cross_text():
    assert (kd_cross_text(91.2, 93.05, False, "overbought")
            == "%K crossed below %D in OVERBOUGHT (%K 91.20, %D 93.05)")
    assert (kd_cross_text(-1e-15, 0.0, True, "oversold")
            == "%K crossed above %D in OVERSOLD (%K 0.00, %D 0.00)")
    with pytest.raises(ValueError):
        kd_cross_text(50, 50, True, "nowhere")


def test_srsi_all_on_walk_is_consistent():
    a = srsi_all(_walk(600, seed=5))
    assert set(a["srsi_zone"].dropna()) == {"overbought", "middle", "oversold"}
    ch = a.loc[a["srsi_zone_change"]]
    assert len(ch) and (ch["srsi_zone"] != ch["srsi_zone_from"]).all()
    cross = a["srsi_kd_cross_above"] | a["srsi_kd_cross_below"]
    assert cross.any() and not (a["srsi_kd_cross_above"] & a["srsi_kd_cross_below"]).any()
    assert a.loc[cross, "srsi_kd_cross_zone"].notna().all()
    assert a.loc[~cross, "srsi_kd_cross_zone"].isna().all()
    assert (a.loc[a["srsi_kd_cross_above"], "srsi_kd_side"] == 1).all()
    assert (a.loc[a["srsi_kd_cross_below"], "srsi_kd_side"] == -1).all()
    assert (a["srsi_label"] == srsi_label(a)).all()


def test_states_input_not_modified():
    df = _kd([10, 30, 85])
    before = df.copy()
    srsi_states(df)
    pd.testing.assert_frame_equal(df, before)


def test_states_missing_columns_raise():
    with pytest.raises(ValueError):
        srsi_states(_walk(40))
    with pytest.raises(ValueError):
        compare_cross_rules(_walk(40))
    with pytest.raises(ValueError):
        srsi_label(_kd([50]))


def test_states_unsorted_raise():
    with pytest.raises(ValueError):
        srsi_states(_kd([10, 30, 85]).iloc[::-1].reset_index(drop=True))


@pytest.mark.parametrize("tol", [-1e-9, NAN, True, "0"])
def test_bad_cross_tol_raises(tol):
    with pytest.raises(ValueError):
        srsi_states(_kd([10, 30, 85]), cross_tol=tol)
