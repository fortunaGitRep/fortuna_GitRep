"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/test_stoch_rsi_snapshot.py

Unit tests for stoch_rsi_snapshot.py (no R2). Run from backend/:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi -v
Results also go to logs/stoch_rsi_test_logs/test_stoch_rsi.log (conftest.py).

Events are tested by cutting a candle history right after an event: every Stoch RSI
value uses only that candle and earlier ones, so the event is then on the latest candle.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import report_date
from modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi import stoch_rsi_snapshot as snapmod
from modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi import (
    compute_stoch_rsi,
    fmt2,
    kd_cross_text,
    srsi_all,
    zone_change_text,
)
from modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi_snapshot import (
    snapshot_from_bars,
    summary_line,
)

_FREQ = {"1mo": "MS", "1w": "W-MON", "1d": "B", "60m": "h", "15m": "15min", "5m": "5min"}


def _bars(n=400, seed=7, tf="1d"):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2024-01-01", periods=n, freq=_FREQ[tf], tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "close": 22000 + np.cumsum(rng.normal(0, 40, n))})


def _cut_at(col, seed=7, n=400):
    """Bars ending on the last candle where `col` is True (event on the latest candle)."""
    bars = _bars(n, seed)
    a = srsi_all(bars)
    hits = a.index[a[col].astype(bool)]
    assert len(hits), f"no {col} in the test series"
    i = hits[-1]
    return bars.iloc[: i + 1].reset_index(drop=True), a.loc[i]


# --- header and numbers ------------------------------------------------------------

@pytest.mark.parametrize("tf, tail", [("1d", ""), ("1w", " (week to date)"),
                                      ("1mo", " (month to date)"), ("60m", "")])
def test_header_per_timeframe(tf, tail):
    bars = _bars(200, tf=tf)
    s = snapshot_from_bars(bars, "Nifty 50", tf)
    name = {"1d": "1D", "1w": "1W", "1mo": "1M", "60m": "60m"}[tf]
    expected = (f"Nifty 50 · {name} Stoch RSI — {report_date(bars['ts'].iloc[-1], tf)}{tail}: "
                f"close {bars['close'].iloc[-1]:,.2f}")
    assert s["texts"][0] == expected
    assert s["partial"] == (tf in ("1w", "1mo"))


def test_numbers_line_shows_tradingview_k_and_d_today_and_previous():
    bars = _bars()
    c = compute_stoch_rsi(bars)
    s = snapshot_from_bars(bars, "Nifty 50", "1d")
    t, y = c.iloc[-1], c.iloc[-2]
    assert s["texts"][1] == (f"%K {fmt2(t['srsi_k'])} · %D {fmt2(t['srsi_d'])} "
                             f"[yesterday: %K {fmt2(y['srsi_k'])} · %D {fmt2(y['srsi_d'])}]")
    assert s["values"]["today"] == {"k": t["srsi_k"], "d": t["srsi_d"]}


def test_state_line_has_zone_slope_and_kd_side():
    bars = _bars()
    a = srsi_all(bars)
    t = a.iloc[-1]
    line = snapshot_from_bars(bars, "Nifty 50", "1d")["texts"][2]
    assert line.startswith(t["srsi_label"] + " — ")
    word = {1: "%K above %D", -1: "%K below %D", 0: "%K equal to %D"}[int(t["srsi_kd_side"])]
    assert word + " since " + report_date(t["srsi_kd_since"], "1d") in line
    assert {1: "rising", -1: "falling", 0: "flat"}[int(t["srsi_slope"])] in line


# --- events and alerts (both directions, no filter) --------------------------------

def test_zone_change_text_and_alert():
    bars, ev = _cut_at("srsi_zone_change")
    s = snapshot_from_bars(bars, "Nifty 50", "1d")
    text = zone_change_text(ev["srsi_k"], ev["srsi_zone_from"], ev["srsi_zone"])
    assert f"{report_date(ev['ts'], '1d')}: {text}" in s["texts"]
    z = [a for a in s["alerts"] if a["type"] == "zone_change"]
    assert len(z) == 1 and z[0]["text"] == text and z[0]["timeframe"] == "1d"
    assert z[0]["direction"] == ("up" if ev["srsi_zone_change_up"] else "down")


@pytest.mark.parametrize("col, above", [("srsi_kd_cross_above", True), ("srsi_kd_cross_below", False)])
def test_kd_cross_text_and_alert_both_directions(col, above):
    bars, ev = _cut_at(col)
    s = snapshot_from_bars(bars, "Nifty 50", "1d")
    text = kd_cross_text(ev["srsi_k"], ev["srsi_d"], above, ev["srsi_kd_cross_zone"])
    assert f"{report_date(ev['ts'], '1d')}: {text}" in s["texts"]
    k = [a for a in s["alerts"] if a["type"] == "kd_cross"]
    assert len(k) == 1 and k[0]["direction"] == ("above" if above else "below")
    assert k[0]["zone"] == ev["srsi_kd_cross_zone"] and k[0]["text"] == text


def test_alerts_are_exactly_the_events():
    bars, _ = _cut_at("srsi_zone_change")
    s = snapshot_from_bars(bars, "Nifty 50", "1d")
    assert [{k: v for k, v in a.items() if k != "timeframe"} for a in s["alerts"]] == s["events_today"]


def test_intraday_event_line_has_time():
    bars = _bars(400, tf="5m")
    a = srsi_all(bars)
    i = a.index[a["srsi_kd_cross_above"]][-1]
    s = snapshot_from_bars(bars.iloc[: i + 1], "Nifty 50", "5m")
    assert any(line.startswith(report_date(a.loc[i, "ts"], "5m") + ": %K crossed above %D")
               for line in s["texts"])
    assert report_date(a.loc[i, "ts"], "5m").count(":") == 1          # 'Fri 9 Oct 2026 15:25'


def test_no_event_no_alert():
    bars = _bars()
    a = srsi_all(bars)
    quiet = a.index[~(a["srsi_zone_change"] | a["srsi_kd_cross_above"] | a["srsi_kd_cross_below"])
                    & a["srsi_k"].notna()]
    s = snapshot_from_bars(bars.iloc[: quiet[-1] + 1], "Nifty 50", "1d")
    assert s["alerts"] == [] and s["events_today"] == []


# --- holding, bigger picture, pinned -------------------------------------------------

def test_holding_line_names_where_it_came_from():
    bars = _bars()
    a = srsi_all(bars)
    rows = a.index[(a["srsi_zone_held"] >= 2) & (a["srsi_zone_held"] <= 5) & (a["srsi_zone_from_start"] == False)]
    i = rows[-1]
    s = snapshot_from_bars(bars.iloc[: i + 1], "Nifty 50", "1d")
    came = a["srsi_zone_from"].iloc[i - int(a.loc[i, "srsi_zone_held"]) + 1]
    from modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi import ZONE_LABEL
    assert any(line.startswith(f"In {a.loc[i, 'srsi_label']} for ") and
               line.endswith(f"came from {ZONE_LABEL[came]}.") for line in s["texts"])


def test_bigger_picture_line():
    bars = _bars()
    a = srsi_all(bars)
    i = a.index[a["srsi_zone_held"] > 5][-1]
    s = snapshot_from_bars(bars.iloc[: i + 1], "Nifty 50", "1d")
    assert any(line.startswith(f"Bigger picture: in {a.loc[i, 'srsi_label']} since ")
               for line in s["texts"])


def test_pinned_text():
    found = None
    for seed in range(1, 60):
        bars = _bars(500, seed)
        a = srsi_all(bars)
        hits = a.index[(a["srsi_pinned"] != 0) & (a["srsi_pinned_held"] >= 2)]
        if len(hits):
            found = (bars, a, hits[-1])
            break
    assert found, "no pinned stretch in the test series"
    bars, a, i = found
    s = snapshot_from_bars(bars.iloc[: i + 1], "Nifty 50", "1d")
    at = 100 if a.loc[i, "srsi_pinned"] == 1 else 0
    assert s["pinned"] == {"at": at, "held": int(a.loc[i, "srsi_pinned_held"])}
    assert f"%K pinned at {at} for {int(a.loc[i, 'srsi_pinned_held'])} days" in s["texts"][2]


def test_not_pinned_has_no_pinned_text():
    bars = _bars()
    a = srsi_all(bars)
    i = a.index[(a["srsi_pinned"] == 0)][-1]
    s = snapshot_from_bars(bars.iloc[: i + 1], "Nifty 50", "1d")
    assert s["pinned"] == {"at": None, "held": None}
    assert "pinned" not in s["texts"][2]


# --- edges, JSON, summary, never-raise ----------------------------------------------

def test_short_history_is_na_not_error():
    s = snapshot_from_bars(_bars(20), "Nifty 50", "1d")
    assert s["texts"][2] == "%K n/a (not enough history)."
    assert s["alerts"] == [] and s["zone"]["key"] is None


def test_single_bar():
    s = snapshot_from_bars(_bars(1), "Nifty 50", "1d")
    assert s["previous"] is None and len(s["texts"]) == 3


def test_json_safe():
    for tf in ("1d", "5m"):
        json.dumps(snapshot_from_bars(_bars(300, tf=tf), "Nifty 50", tf), allow_nan=False)
    json.dumps(snapshot_from_bars(_bars(20), "Nifty 50", "1d"), allow_nan=False)


def test_summary_line_order_and_na():
    snaps = {tf: snapshot_from_bars(_bars(300, tf=tf), "Nifty 50", tf)
             for tf in ("5m", "1d", "1mo")}
    snaps["1w"] = None
    line = summary_line(snaps)
    assert line.startswith("Stoch RSI: 1M ")
    order = [line.index(w) for w in ("1M ", "1W n/a", "1D ", "5m ")]
    assert order == sorted(order)
    k = snaps["1d"]["values"]["today"]["k"]
    assert f"1D {snaps['1d']['zone']['key']} {fmt2(k)}" in line


def test_bad_inputs_raise_in_pure_core():
    with pytest.raises(ValueError):
        snapshot_from_bars(_bars(50), "Nifty 50", "2h")
    with pytest.raises(ValueError):
        snapshot_from_bars(_bars(50).iloc[0:0], "Nifty 50", "1d")


def _fake_reader(monkeypatch, fail=(), boom=()):
    import modules.market_data.upstox.indicator_ohlcv_reader as reader

    def fake(key, domain, tf):
        if tf in boom:
            raise RuntimeError("R2 down")
        if tf in fail:
            return SimpleNamespace(ok=False, df=None, error="no OHLCV file in R2", last_ts=None)
        return SimpleNamespace(ok=True, df=_bars(300, tf=tf), error=None, last_ts=None)
    monkeypatch.setattr(reader, "read_for_indicators", fake)


def test_build_all_timeframes_ok(monkeypatch):
    _fake_reader(monkeypatch)
    res = snapmod.build_stoch_rsi_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert res.ok and not res.errors and set(res.snapshots) == {"1mo", "1w", "1d", "60m", "15m", "5m"}
    assert res.summary.startswith("Stoch RSI: 1M ")


def test_build_one_timeframe_missing_others_still_built(monkeypatch):
    _fake_reader(monkeypatch, fail=("1w",), boom=("15m",))
    res = snapmod.build_stoch_rsi_snapshot("NSE_INDEX|Nifty 50", "Nifty 50")
    assert not res.ok and set(res.errors) == {"1w", "15m"}
    assert res.snapshots["1w"] is None and res.snapshots["15m"] is None
    assert res.snapshots["1d"] is not None and "1W n/a" in res.summary


def test_build_bad_timeframe_does_not_raise(monkeypatch):
    _fake_reader(monkeypatch)
    res = snapmod.build_stoch_rsi_snapshot("NSE_INDEX|Nifty 50", "Nifty 50", ("1d", "2h"))
    assert not res.ok and "2h" in res.errors and res.snapshots["1d"] is not None
