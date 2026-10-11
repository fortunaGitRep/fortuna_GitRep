"""
Unit tests for trend_indicators/ema/ema_snapshot.py. No R2: bars are built in memory and
the reader is faked for build_ema_snapshot().

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema/test_ema_snapshot.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema import ema_snapshot as snapmod
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema_snapshot import (
    snapshot_from_bars,
    stage_label,
)


def _bars(closes, start="2026-01-01") -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    days = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({
        "ts": days.tz_localize("Asia/Kolkata"),
        "trade_date": [d.date() for d in days],
        "open": closes, "high": closes + 5, "low": closes - 5, "close": closes,
        "volume": 0.0,
    })


def _downtrend_then(last_closes, n=260):
    """Steady fall (full bearish stack), then the given closing prices."""
    return _bars(list(np.linspace(30000, 20000, n)) + list(last_closes))


# --- labels -----------------------------------------------------------------

@pytest.mark.parametrize("stage, text", [
    (5, "STRONG UPTREND (+5 of 5)"),
    (-5, "STRONG DOWNTREND (-5 of 5)"),
    (1, "EARLY UPTREND (+1 of 5, weakest)"),
    (-3, "DOWNTREND (stage -3 of 5)"),
    (0, "NEUTRAL (0)"),
    (None, "STAGE n/a (not enough history)"),
])
def test_stage_label(stage, text):
    assert stage_label(stage, 5) == text


# --- structure ----------------------------------------------------------------

def test_snapshot_values_and_json_safe():
    snap = snapshot_from_bars(_downtrend_then([]), "Nifty 50")
    assert snap["stage"]["today"] == -5
    assert len(snap["emas"]) == 6 and len(snap["checks"]) == 12
    assert snap["as_of"] > snap["previous"]
    json.dumps(snap, allow_nan=False, ensure_ascii=False)     # no NaN, all serialisable


def test_header_and_ema_line():
    snap = snapshot_from_bars(_downtrend_then([]), "Nifty 50")
    assert snap["texts"][0].startswith("Nifty 50 — as of ")
    assert "STRONG DOWNTREND (-5 of 5): 5 < 13 < 26 < 50 < 100 < 200" in snap["texts"][1]
    assert any(t.startswith("EMAs today (yesterday): 5: ") for t in snap["texts"])


def test_cross_today_text_and_alert():
    bars = _downtrend_then([20500])                 # jump above the 5 EMA on the last day
    snap = snapshot_from_bars(bars, "Nifty 50")
    lines = [t for t in snap["texts"] if t.startswith("Today: close crossed above the 5 EMA")]
    assert len(lines) == 1
    assert "(yesterday " in lines[0] and "Whole candle clear:" in lines[0]
    assert {"a": "close", "b": "ema_5", "direction": "above",
            "golden_cross": False, "death_cross": False} in snap["alerts"]


def test_holding_line_after_cross():
    bars = _downtrend_then([20500, 20600, 20700])   # crossed 3 bars ago and stayed above
    snap = snapshot_from_bars(bars, "Nifty 50")
    hold = [t for t in snap["texts"] if t.startswith("Close holding above the 5 EMA")]
    assert len(hold) == 1 and "for 3 days" in hold[0]
    assert not any(t.startswith("Today: close crossed above the 5 EMA") for t in snap["texts"])


def test_directions_above_filters_cross_below():
    bars = _bars(list(np.linspace(20000, 30000, 260)) + [29000])   # uptrend, then a drop
    both = snapshot_from_bars(bars, "X", "both")
    above = snapshot_from_bars(bars, "X", "above")
    assert any(a["direction"] == "below" for a in both["alerts"])
    assert all(a["direction"] == "above" for a in above["alerts"])
    assert not any("crossed below" in t for t in above["texts"])
    assert len(above["checks"]) == 12                # states always complete


def test_stage_change_line():
    changed = snapshot_from_bars(_downtrend_then([21000]), "Nifty 50")   # -5 -> +1
    assert (changed["stage"]["yesterday"], changed["stage"]["today"]) == (-5, 1)
    assert "Stage moved from -5 to +1 today." in changed["texts"]
    assert changed["stage"]["label"] == "EARLY UPTREND (+1 of 5, weakest)"
    same = snapshot_from_bars(_downtrend_then([20500]), "Nifty 50")      # stays -5
    assert not any(t.startswith("Stage moved from") for t in same["texts"])


def test_bigger_trend_line():
    snap = snapshot_from_bars(_downtrend_then([]), "Nifty 50")
    line = [t for t in snap["texts"] if t.startswith("Bigger trend: ")]
    assert len(line) == 1
    for part in ("5 below 13 since", "100 below 200 since", "death cross (50 below 200) since"):
        assert part in line[0]
    assert "(start of data)" in line[0]     # this test series begins already falling


def test_golden_cross_text():
    # Long fall, then a long rise: the 50 EMA eventually crosses above the 200 EMA.
    closes = list(np.linspace(30000, 20000, 300)) + list(np.linspace(20000, 32000, 300))
    full = snapshot_from_bars(_bars(closes), "X")      # warm-up
    bars = _bars(closes)
    from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema import (
        compute_emas, detect_crosses)
    hits = detect_crosses(compute_emas(bars))["cross_above_ema_50_ema_200"]
    cross_at = int(np.flatnonzero(hits.to_numpy())[0])
    snap = snapshot_from_bars(bars.iloc[:cross_at + 1].reset_index(drop=True), "X")
    assert any(t.startswith("⚡ GOLDEN CROSS today: 50 EMA crossed above the 200 EMA")
               for t in snap["texts"])
    assert any(a["golden_cross"] for a in snap["alerts"])
    assert full["stage"]["today"] is not None


def test_short_history_blank_200():
    snap = snapshot_from_bars(_bars(np.linspace(100, 200, 150)), "New stock")
    ema200 = [e for e in snap["emas"] if e["period"] == 200][0]
    assert ema200["today"] is None
    assert snap["stage"]["today"] == 4               # can't reach 5 without the 200 EMA
    assert "200: n/a (n/a)" in [t for t in snap["texts"] if t.startswith("EMAs")][0]
    json.dumps(snap, allow_nan=False)


def test_single_bar():
    snap = snapshot_from_bars(_bars([100.0]), "X")
    assert snap["previous"] is None and snap["close"]["yesterday"] is None
    assert snap["stage"]["today"] is None
    json.dumps(snap, allow_nan=False)


def test_bad_inputs_raise_in_pure_core():
    with pytest.raises(ValueError):
        snapshot_from_bars(_bars([1.0, 2.0]), "X", directions="sideways")
    with pytest.raises(ValueError):
        snapshot_from_bars(_bars([1.0]).iloc[0:0], "X")


# --- build_ema_snapshot never raises -----------------------------------------------

def _fake_reader(monkeypatch, result=None, raises=None):
    import modules.market_data.upstox.indicator_ohlcv_reader as rd

    def fake(key, domain, timeframe):
        if raises:
            raise raises
        return result
    monkeypatch.setattr(rd, "read_for_indicators", fake)


def test_build_ok(monkeypatch):
    bars = _downtrend_then([])
    _fake_reader(monkeypatch, SimpleNamespace(ok=True, df=bars, error=None))
    res = snapmod.build_ema_snapshot("NSE_INDEX|Nifty 50", "indices", "Nifty 50")
    assert res.ok and res.snapshot["stage"]["today"] == -5


def test_build_reader_not_ok(monkeypatch):
    _fake_reader(monkeypatch, SimpleNamespace(ok=False, df=None, error="no OHLCV file in R2"))
    res = snapmod.build_ema_snapshot("NSE_INDEX|Nifty 50", "indices", "Nifty 50")
    assert not res.ok and "no OHLCV file" in res.error


def test_build_bad_directions_does_not_raise(monkeypatch):
    _fake_reader(monkeypatch, SimpleNamespace(ok=True, df=_downtrend_then([]), error=None))
    res = snapmod.build_ema_snapshot("NSE_INDEX|Nifty 50", "indices", "Nifty 50", "sideways")
    assert not res.ok and "directions" in res.error
