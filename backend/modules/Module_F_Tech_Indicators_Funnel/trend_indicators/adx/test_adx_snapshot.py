"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx/test_adx_snapshot.py

Unit tests for adx_snapshot (ADX part 3). No R2: the pure core runs on a hand-made
price path; build_adx_snapshot uses a faked reader.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx -v

Covers: header per timeframe, the five TradingView numbers (today + previous), the
label line (slope, direction, "but no trend"), DI-cross text with the ADX tag,
ADX-25 cross texts, directions filter (stocks), holding line with the ADX at the
cross, bigger picture, short history, summary line, JSON safety, never-raise.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx import adx as A
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx import adx_snapshot as S


def _path(n_flat=120, n_down=80, n_up=60, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = np.concatenate([rng.normal(0, 30, n_flat), rng.normal(-25, 30, n_down),
                            rng.normal(15, 30, n_up)])
    c = 22000 + np.cumsum(steps)
    sp = np.abs(rng.normal(40, 15, len(c)))
    ts = pd.date_range("2026-01-01", periods=len(c), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str), "open": c,
                         "high": c + sp * 0.6, "low": c - sp * 0.6, "close": c})


BARS = _path()


def _first(pred, directions="both"):
    for k in range(60, len(BARS)):
        snap = S.snapshot_from_bars(BARS.iloc[:k], "Nifty 50", "1d", directions)
        if pred(snap):
            return snap, k
    raise AssertionError("no candle matched")


def _has(snap, kind, **kw):
    return any(e["type"] == kind and all(e.get(k) == v for k, v in kw.items())
               for e in snap["events_today"])


# --- header, numbers, label ----------------------------------------------------------

@pytest.mark.parametrize("tf, expected", [
    ("1d", "Nifty 50 · 1D DMI — as of "), ("1w", "(week to date): close "),
    ("1mo", "(month to date): close "), ("15m", " candle: close "),
])
def test_header(tf, expected):
    assert expected in S.snapshot_from_bars(BARS, "Nifty 50", tf)["texts"][0]


def test_numbers_line_shows_all_five_today_and_previous():
    snap = S.snapshot_from_bars(BARS, "Nifty 50", "1d")
    a = A.compute_adx(BARS)
    t, y = a.iloc[-1], a.iloc[-2]
    line = snap["texts"][1]
    assert line.startswith(f"+DI {t['plus_di']:,.2f} · -DI {t['minus_di']:,.2f} · DX {t['dx']:,.2f} · "
                           f"ADX {t['adx']:,.2f} · ADXR {t['adxr']:,.2f}")
    assert f"[yesterday: +DI {y['plus_di']:,.2f}" in line
    assert snap["values"]["today"]["adxr"] == pytest.approx(t["adxr"])


def test_label_line_has_slope_and_direction():
    snap = S.snapshot_from_bars(BARS, "Nifty 50", "1d")
    line = snap["texts"][2]
    assert line.startswith(snap["label"])
    assert f"ADX {snap['strength']['adx']:.2f} {snap['strength']['slope']} for" in line
    assert ("bulls (+DI above -DI)" in line) or ("bears (-DI above +DI)" in line)


def test_no_trend_label_says_but_no_trend():
    snap, _ = _first(lambda s: s["strength"]["band"] == "no_trend" and s["direction"]["side"] in ("bulls", "bears"))
    assert snap["texts"][2].startswith("NO TREND") and "(but no trend)" in snap["texts"][2]


# --- events -----------------------------------------------------------------------

def test_di_cross_text_carries_adx_tag():
    snap, _ = _first(lambda s: _has(s, "di_cross"))
    e = [e for e in snap["events_today"] if e["type"] == "di_cross"][0]
    line = [x for x in snap["texts"] if "+DI crossed" in x][0]
    assert f"ADX {e['adx']:.2f} — {S.BAND_WORDS[e['band']]}" in line
    assert ("bulls take over" in line) == (e["direction"] == "above")


def test_adx_cross_25_texts():
    up, _ = _first(lambda s: _has(s, "adx_cross_25", direction="above"))
    assert any(x.startswith("⚡ Today: ADX crossed above 25 → trend confirmed") for x in up["texts"])
    down, _ = _first(lambda s: _has(s, "adx_cross_25", direction="below"))
    assert any(x == "⚡ Today: ADX crossed below 25 → trend fading." for x in down["texts"])


def test_directions_above_hides_bearish_events():
    both, k = _first(lambda s: _has(s, "di_cross", direction="below"))
    above = S.snapshot_from_bars(BARS.iloc[:k], "X", "1d", "above")
    assert _has(above, "di_cross", direction="below")                # kept in the record
    assert not any(a["type"] == "di_cross" for a in above["alerts"])
    assert not any("crossed below -DI" in x for x in above["texts"])
    assert above["label"] == both["label"]


def test_holding_line_shows_adx_at_the_cross():
    snap, k = _first(lambda s: s["direction"]["held"] == 3 and not s["direction"]["from_start"])
    a = A.adx_all(BARS.iloc[:k])
    cross_adx = a["adx"].iloc[k - 3]
    line = [x for x in snap["texts"] if " holding for 3 days" in x][0]
    assert f"crossed with ADX {cross_adx:.2f}" in line


def test_bigger_picture_for_long_states():
    snap = S.snapshot_from_bars(BARS.iloc[:200], "X", "1d")      # end of the long down leg
    big = [x for x in snap["texts"] if x.startswith("Bigger picture: ")]
    assert big and ("ADX above 25 since" in big[0] or "since" in big[0])


# --- short history, summary, JSON, never-raise ------------------------------------

def test_short_history_na():
    snap = S.snapshot_from_bars(BARS.iloc[:20], "New", "1d")
    assert snap["label"] == A.LABEL_NA and snap["texts"][2] == f"ADX {A.LABEL_NA}."
    json.dumps(snap, allow_nan=False)


def test_json_safe_full():
    json.dumps(S.snapshot_from_bars(BARS, "X", "1d"), allow_nan=False)


def test_summary_line():
    snaps = {tf: S.snapshot_from_bars(BARS, "X", tf) for tf in S.TIMEFRAMES}
    snaps["5m"] = None
    line = S.summary_line(snaps)
    assert line.startswith("ADX: 1M ") and line.endswith("5m n/a")
    assert "(rising)" in line or "(falling)" in line or "(flat)" in line


def test_bad_inputs_raise_in_pure_core():
    with pytest.raises(ValueError, match="timeframe"):
        S.snapshot_from_bars(BARS, "X", "4h")
    with pytest.raises(ValueError, match="directions"):
        S.snapshot_from_bars(BARS, "X", "1d", "sideways")
    with pytest.raises(ValueError, match="no bars"):
        S.snapshot_from_bars(BARS.iloc[:0], "X", "1d")


def _fake_reader(monkeypatch, by_tf):
    from modules.market_data.upstox import indicator_ohlcv_reader as rd

    def fake(key, domain, tf):
        assert domain == A._DEFAULT_DOMAIN[tf]
        return by_tf[tf]
    monkeypatch.setattr(rd, "read_for_indicators", fake)


def test_build_all_ok_and_one_missing(monkeypatch):
    ok = SimpleNamespace(ok=True, df=BARS, error=None)
    miss = SimpleNamespace(ok=False, df=None, error="no OHLCV file in R2")
    _fake_reader(monkeypatch, {**{tf: ok for tf in S.TIMEFRAMES}, "5m": miss})
    res = S.build_adx_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert not res.ok and res.errors == {"5m": "no OHLCV file in R2"}
    assert res.snapshots["1d"] is not None and res.summary.endswith("5m n/a")


def test_build_bad_input_does_not_raise(monkeypatch):
    ok = SimpleNamespace(ok=True, df=BARS, error=None)
    _fake_reader(monkeypatch, {tf: ok for tf in S.TIMEFRAMES})
    res = S.build_adx_snapshot("K", "X", ("1d", "4h"))
    assert not res.ok and "4h" in res.errors and res.snapshots["1d"] is not None
