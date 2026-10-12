"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd/test_macd_snapshot.py

Unit tests for macd_snapshot (MACD part 4). No R2: the pure core runs on hand-made
price paths; build_macd_snapshot uses a faked reader.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd -v

Covers: header per timeframe (day / week to date / month to date / intraday
candle), the TradingView numbers line (today + previous), label + histogram
line with "watch for" hint, each event text (signal cross with zone meaning,
zero cross, momentum turn), directions filter (stocks: bullish only), holding
and bigger-picture lines, start-of-data marker, short history (n/a), summary
line across timeframes, JSON safety, and the never-raise boundary.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd import macd as M
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd import macd_snapshot as S


def _bars(closes, freq="D", start="2026-01-01") -> pd.DataFrame:
    ts = pd.date_range(start, periods=len(closes), freq=freq, tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "close": np.asarray(closes, dtype="float64")})


_WAVE = 22000 + np.sin(np.arange(220) / 8) * 300


def _first_bar_where(pred, tf="1d", directions="both"):
    """Cut the wave at the first candle (after warm-up) whose snapshot matches pred."""
    for k in range(60, len(_WAVE)):
        snap = S.snapshot_from_bars(_bars(_WAVE[:k]), "Nifty 50", tf, directions)
        if pred(snap):
            return snap
    raise AssertionError("no candle matched")


def _has(snap, kind, **kw):
    return any(e["type"] == kind and all(e.get(k) == v for k, v in kw.items())
               for e in snap["events_today"])


# --- header and numbers ---------------------------------------------------------

@pytest.mark.parametrize("tf, freq, expected", [
    ("1d", "D", "Nifty 50 · 1D — as of "),
    ("1w", "W-MON", "(week to date): close "),
    ("1mo", "MS", "(month to date): close "),
    ("60m", "60min", " candle: close "),
])
def test_header_per_timeframe(tf, freq, expected):
    snap = S.snapshot_from_bars(_bars(_WAVE[:120], freq), "Nifty 50", tf)
    assert expected in snap["texts"][0]
    assert snap["partial"] == (tf in ("1w", "1mo"))


def test_month_and_intraday_dates():
    bars = _bars(_WAVE[:100], "MS")
    m = S.snapshot_from_bars(bars, "X", "1mo")
    assert m["texts"][0].startswith(f"X · 1M — as of {bars['ts'].iloc[-1]:%b %Y} (month to date)")
    i = S.snapshot_from_bars(_bars(_WAVE[:100], "15min", "2026-10-09 09:15"), "X", "15m")
    assert ":" in i["as_of"] and "T" in i["as_of"]           # ISO datetime for intraday
    assert i["texts"][0].endswith(f"close {_WAVE[99]:,.2f}")


def test_numbers_line_shows_tradingview_values_today_and_previous():
    bars = _bars(_WAVE[:120])
    snap = S.snapshot_from_bars(bars, "Nifty 50", "1d")
    m = M.compute_macd(bars)
    t, y = m.iloc[-1], m.iloc[-2]
    line = snap["texts"][1]
    assert line.startswith(f"MACD {t['macd']:,.2f} · Signal {t['macd_signal']:,.2f} · "
                           f"Histogram {t['macd_hist']:,.2f} ({M.HIST_COLOUR[t['macd_hist_state']]})")
    assert f"[yesterday: MACD {y['macd']:,.2f}" in line
    assert snap["values"]["today"]["histogram"] == pytest.approx(t["macd_hist"])


def test_label_line_and_watch_hint():
    snap = _first_bar_where(lambda s: s["histogram"]["state"] == "above_fading")
    assert "bullish momentum fading" in snap["texts"][2]
    assert "watch for a bearish MACD cross" in snap["texts"][2]
    assert snap["texts"][2].startswith(snap["label"])


# --- events ---------------------------------------------------------------------

def test_signal_cross_text_with_zone_meaning():
    snap = _first_bar_where(lambda s: _has(s, "signal_cross", direction="below"))
    zone = [e for e in snap["events_today"] if e["type"] == "signal_cross"][0]["zone"]
    line = [x for x in snap["texts"] if x.startswith("Today: MACD crossed below signal")][0]
    assert S._ZONE_MEANING[("below", zone)] in line and "Gap -" in line
    assert any(a["type"] == "signal_cross" for a in snap["alerts"])


def test_zero_cross_text():
    snap = _first_bar_where(lambda s: _has(s, "zero_cross", direction="above"))
    assert any(x.startswith("⚡ Today: MACD crossed above zero → 12 EMA now above 26 EMA")
               for x in snap["texts"])


def test_momentum_turn_text():
    snap = _first_bar_where(lambda s: _has(s, "momentum_turn", to="above_fading"))
    line = [x for x in snap["texts"] if x.startswith("⚡ Momentum turn")][0]
    assert "bullish momentum fading" in line and "of growing bullish momentum" in line


def test_directions_above_hides_bearish_events():
    both = _first_bar_where(lambda s: _has(s, "signal_cross", direction="below"))
    cut = pd.Timestamp(both["as_of"])
    bars = _bars(_WAVE)
    bars = bars[bars["ts"].dt.date <= cut.date()]
    above = S.snapshot_from_bars(bars, "X", "1d", "above")
    assert _has(above, "signal_cross", direction="below")          # still in the record
    assert not any(a["type"] == "signal_cross" for a in above["alerts"])
    assert not any("crossed below signal" in x for x in above["texts"])
    assert above["label"] == both["label"]                          # states always shown


def test_holding_line_after_signal_cross():
    snap = _first_bar_where(lambda s: s["momentum"]["held"] == 3 and not s["momentum"]["from_start"])
    assert any(x.startswith(f"MACD holding {snap['momentum']['side']} signal for 3 days")
               for x in snap["texts"])


def test_bigger_picture_and_start_of_data():
    snap = S.snapshot_from_bars(_bars(np.linspace(20000, 23000, 80)), "X", "1d")  # steady rise
    big = [x for x in snap["texts"] if x.startswith("Bigger picture: ")]
    assert len(big) == 1 and "MACD above zero since" in big[0]
    assert "(start of data)" in big[0]                     # never crossed zero in this history


# --- short history, summary, JSON ---------------------------------------------------

def test_short_history_is_na_not_error():
    snap = S.snapshot_from_bars(_bars(_WAVE[:20]), "New", "1d")
    assert snap["label"] == M.LABEL_NA
    assert snap["texts"][2] == f"MACD {M.LABEL_NA}."
    assert snap["values"]["today"]["macd"] is None


def test_single_bar():
    snap = S.snapshot_from_bars(_bars([100.0]), "X", "1d")
    assert snap["previous"] is None and snap["values"]["previous"] is None


def test_summary_line_order_and_fading():
    snaps = {tf: S.snapshot_from_bars(_bars(_WAVE[:120]), "X", tf) for tf in S.TIMEFRAMES}
    snaps["5m"] = None
    line = S.summary_line(snaps)
    assert line.startswith("MACD: 1M ")
    order = [line.index(f" {S.TF_NAME[tf]} ") for tf in S.TIMEFRAMES]
    assert order == sorted(order)
    assert line.endswith("5m n/a")
    fading = S.snapshot_from_bars(_bars(_WAVE[:120]), "X", "1d")
    if fading["histogram"]["state"].endswith("fading"):
        assert "(fading)" in S.summary_line({"1d": fading})


def test_json_safe():
    for k in (20, 40, 120):
        snap = S.snapshot_from_bars(_bars(_WAVE[:k]), "X", "1d")
        json.dumps(snap, allow_nan=False)


def test_bad_inputs_raise_in_pure_core():
    with pytest.raises(ValueError, match="timeframe"):
        S.snapshot_from_bars(_bars(_WAVE[:50]), "X", "4h")
    with pytest.raises(ValueError, match="directions"):
        S.snapshot_from_bars(_bars(_WAVE[:50]), "X", "1d", "sideways")
    with pytest.raises(ValueError, match="no bars"):
        S.snapshot_from_bars(_bars([])[:0], "X", "1d")


# --- never-raise boundary --------------------------------------------------------

def _fake_reader(monkeypatch, by_tf):
    from modules.market_data.upstox import indicator_ohlcv_reader as rd

    def fake(key, domain, tf):
        assert domain == M._DEFAULT_DOMAIN[tf]
        return by_tf[tf]
    monkeypatch.setattr(rd, "read_for_indicators", fake)


def test_build_all_timeframes_ok(monkeypatch):
    ok = SimpleNamespace(ok=True, df=_bars(_WAVE[:150]), error=None)
    _fake_reader(monkeypatch, {tf: ok for tf in S.TIMEFRAMES})
    res = S.build_macd_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert res.ok and not res.errors
    assert list(res.snapshots) == list(S.TIMEFRAMES)
    assert res.summary.startswith("MACD: 1M ")


def test_build_one_timeframe_missing_others_still_built(monkeypatch):
    ok = SimpleNamespace(ok=True, df=_bars(_WAVE[:150]), error=None)
    miss = SimpleNamespace(ok=False, df=None, error="no OHLCV file in R2")
    _fake_reader(monkeypatch, {**{tf: ok for tf in S.TIMEFRAMES}, "5m": miss})
    res = S.build_macd_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert not res.ok and res.errors == {"5m": "no OHLCV file in R2"}
    assert res.snapshots["5m"] is None and res.snapshots["1d"] is not None
    assert res.summary.endswith("5m n/a")


def test_build_bad_input_does_not_raise(monkeypatch):
    ok = SimpleNamespace(ok=True, df=_bars(_WAVE[:150]), error=None)
    _fake_reader(monkeypatch, {tf: ok for tf in S.TIMEFRAMES})
    res = S.build_macd_snapshot("NSE_INDEX|Nifty 50", "Nifty 50", ("1d", "4h"), "both")
    assert not res.ok and "4h" in res.errors and res.snapshots["1d"] is not None
    res2 = S.build_macd_snapshot("NSE_INDEX|Nifty 50", "Nifty 50", ("1d",), "sideways")
    assert not res2.ok and "directions" in res2.errors["1d"]
