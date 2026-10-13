"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi/test_rsi_snapshot.py

Unit tests for rsi_snapshot (RSI part 3). No R2: the pure core runs on a hand-made
price path; build_rsi_snapshot uses a faked reader.

Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi -v

Covers: header per timeframe (report dates with year, week / month to date, candle
time), the TradingView RSI number (today + previous), the label line (slope, side of
50, start of data), every zone change and every 50 cross as a text AND an alert in
both directions (Ash's wording via zone_change_text), holding and bigger-picture
lines, the hidden MA kept out of texts and package, short history, summary line,
JSON safety, never-raise.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi import rsi as R
from modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi import rsi_snapshot as S


def _bars(closes, freq="D", start="2026-01-01") -> pd.DataFrame:
    ts = pd.date_range(start, periods=len(closes), freq=freq, tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "trade_date": ts.date.astype(str),
                         "close": np.asarray(closes, dtype="float64")})


_RNG = np.random.default_rng(3)
_PATH = 22000 + np.cumsum(np.concatenate([_RNG.normal(20, 60, 120), _RNG.normal(-20, 60, 120),
                                          _RNG.normal(0, 60, 120)]))
BARS = _bars(_PATH)


def _first(pred, tf="1d", freq="D"):
    bars = _bars(_PATH, freq)
    for k in range(40, len(bars)):
        snap = S.snapshot_from_bars(bars.iloc[:k], "Nifty 50", tf)
        if pred(snap):
            return snap
    raise AssertionError("no candle matched")


def _has(snap, kind, **kw):
    return any(e["type"] == kind and all(e.get(k) == v for k, v in kw.items())
               for e in snap["events_today"])


# --- header and numbers ----------------------------------------------------------------

@pytest.mark.parametrize("tf, freq, start, expected", [
    ("1d", "D", "2026-08-11", "Nifty 50 · 1D RSI — Fri 9 Oct 2026: close "),     # 60 days end Fri 9 Oct 2026
    ("1w", "W-MON", "2025-11-03", "(week to date): close "),
    ("1mo", "MS", "2021-11-01", "(month to date): close "),
    ("15m", "15min", "2026-10-09 09:15", " 2026 "),
])
def test_header_report_dates(tf, freq, start, expected):
    bars = _bars(_PATH[:60], freq, start)
    head = S.snapshot_from_bars(bars, "Nifty 50", tf)["texts"][0]
    assert expected in head
    if tf == "15m":
        assert head.endswith(f"close {_PATH[59]:,.2f}") and ":" in head.split("—")[1]


def test_numbers_line_today_and_previous():
    snap = S.snapshot_from_bars(BARS, "Nifty 50", "1d")
    r = R.compute_rsi(BARS)
    assert snap["texts"][1] == f"RSI {r['rsi'].iloc[-1]:.2f} [yesterday: RSI {r['rsi'].iloc[-2]:.2f}]"
    assert snap["values"]["today"]["rsi"] == pytest.approx(r["rsi"].iloc[-1])


def test_label_line_has_zone_slope_and_side_of_50():
    snap = S.snapshot_from_bars(BARS, "Nifty 50", "1d")
    line = snap["texts"][2]
    assert line.startswith(snap["label"] + " — RSI ")
    assert snap["slope"]["direction"] in line
    assert ("above 50 since" in line) or ("below 50 since" in line) or ("at 50 since" in line)
    assert " 2026 (" in line or " 2027 (" in line                   # report date with year


# --- events: every one is a text AND an alert, both directions ---------------------------

@pytest.mark.parametrize("direction", ["up", "down"])
def test_zone_change_text_and_alert_both_directions(direction):
    snap = _first(lambda s: _has(s, "zone_change", direction=direction))
    e = [e for e in snap["events_today"] if e["type"] == "zone_change"][0]
    assert e["text"] == R.zone_change_text(e["rsi"], e["from"], e["to"])
    assert any(x.endswith(": " + e["text"]) for x in snap["texts"])
    assert any(a["type"] == "zone_change" and a["direction"] == direction for a in snap["alerts"])


@pytest.mark.parametrize("direction", ["above", "below"])
def test_cross_50_text_and_alert(direction):
    snap = _first(lambda s: _has(s, "cross_50", direction=direction))
    assert any(x.endswith(f"crossed {direction.upper()} 50") for x in snap["texts"])
    assert any(a["type"] == "cross_50" and a["direction"] == direction for a in snap["alerts"])


def test_event_line_starts_with_the_candle_report_date():
    snap = _first(lambda s: bool(s["events_today"]))
    t = pd.Timestamp(snap["as_of"])
    assert snap["texts"][3].startswith(f"{t:%a} {t.day} {t:%b %Y}: RSI ")


def test_intraday_event_line_has_time():
    snap = _first(lambda s: bool(s["events_today"]), tf="5m", freq="5min")
    t = pd.Timestamp(snap["as_of"])
    assert snap["texts"][3].startswith(f"{t:%a} {t.day} {t:%b %Y} {t:%H:%M}: RSI ")


def test_alerts_equal_events_no_filter():
    snap = _first(lambda s: len(s["events_today"]) >= 1)
    assert len(snap["alerts"]) == len(snap["events_today"])
    assert all(a["timeframe"] == "1d" for a in snap["alerts"])


# --- holding / bigger picture --------------------------------------------------------------

def test_holding_line_names_where_it_came_from():
    snap = _first(lambda s: s["zone"]["held"] == 3 and not s["zone"]["from_start"])
    line = [x for x in snap["texts"] if x.startswith("In ")][0]
    assert f"In {snap['label']} for 3 days (since " in line and ", came from " in line


def test_bigger_picture_after_five_candles():
    snap = _first(lambda s: (s["zone"]["held"] or 0) > 5)
    assert any(x.startswith(f"Bigger picture: in {snap['label']} since ") for x in snap["texts"])


# --- hidden MA, short history, summary, JSON ------------------------------------------------

def test_hidden_ma_not_in_texts_or_package():
    snap = S.snapshot_from_bars(BARS, "X", "1d")
    blob = json.dumps(snap, ensure_ascii=False)
    assert "rsi_ma" not in blob and " MA" not in " ".join(snap["texts"])


def test_short_history_na():
    snap = S.snapshot_from_bars(BARS.iloc[:10], "New", "1d")
    assert snap["label"] == R.LABEL_NA and snap["texts"][2] == f"RSI {R.LABEL_NA}."
    assert snap["values"]["today"]["rsi"] is None
    json.dumps(snap, allow_nan=False)


def test_single_bar():
    snap = S.snapshot_from_bars(BARS.iloc[:1], "X", "1d")
    assert snap["previous"] is None and snap["values"]["previous"] is None


def test_json_safe():
    for k in (10, 20, 100, len(BARS)):
        json.dumps(S.snapshot_from_bars(BARS.iloc[:k], "X", "1d"), allow_nan=False)


def test_summary_line():
    snaps = {tf: S.snapshot_from_bars(BARS, "X", tf) for tf in S.TIMEFRAMES}
    snaps["5m"] = None
    line = S.summary_line(snaps)
    assert line.startswith("RSI: 1M ") and line.endswith("5m n/a")
    order = [line.index(f" {S.TF_NAME[tf]} ") for tf in S.TIMEFRAMES]
    assert order == sorted(order)


def test_bad_inputs_raise_in_pure_core():
    with pytest.raises(ValueError, match="timeframe"):
        S.snapshot_from_bars(BARS, "X", "4h")
    with pytest.raises(ValueError, match="no bars"):
        S.snapshot_from_bars(BARS.iloc[:0], "X", "1d")


# --- never-raise boundary ------------------------------------------------------------------

def _fake_reader(monkeypatch, by_tf):
    from modules.market_data.upstox import indicator_ohlcv_reader as rd

    def fake(key, domain, tf):
        assert domain == S.DEFAULT_DOMAIN[tf]
        return by_tf[tf]
    monkeypatch.setattr(rd, "read_for_indicators", fake)


def test_build_all_ok_and_one_missing(monkeypatch):
    ok = SimpleNamespace(ok=True, df=BARS, error=None)
    miss = SimpleNamespace(ok=False, df=None, error="no OHLCV file in R2")
    _fake_reader(monkeypatch, {tf: ok for tf in S.TIMEFRAMES})
    res = S.build_rsi_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert res.ok and list(res.snapshots) == list(S.TIMEFRAMES)
    _fake_reader(monkeypatch, {**{tf: ok for tf in S.TIMEFRAMES}, "5m": miss})
    res = S.build_rsi_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert not res.ok and res.errors == {"5m": "no OHLCV file in R2"}
    assert res.snapshots["1d"] is not None and res.summary.endswith("5m n/a")


def test_build_bad_input_does_not_raise(monkeypatch):
    _fake_reader(monkeypatch, {tf: SimpleNamespace(ok=True, df=BARS, error=None) for tf in S.TIMEFRAMES})
    res = S.build_rsi_snapshot("K", "X", ("1d", "4h"))
    assert not res.ok and "4h" in res.errors and res.snapshots["1d"] is not None
