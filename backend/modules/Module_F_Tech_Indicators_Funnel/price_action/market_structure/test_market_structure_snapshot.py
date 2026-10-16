"""
Unit tests for market_structure_snapshot.py (step 6: texts, alerts, package).

Run from backend/ (output also saved to logs/market_structure_test_logs/market_structure_snapshot_unit_tests.log):
  python -m modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.test_market_structure_snapshot
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure import (
    market_structure_snapshot as mss,
)

TOL = 1.0
T0 = pd.Timestamp("2026-10-05")


def t(i):
    return T0 + pd.offsets.BDay(i)


def candles(closes):
    """Daily candles: open = previous close, high/low = +-0.5 around the body."""
    rows, prev = [], closes[0]
    for c in closes:
        rows.append((prev, max(prev, c) + 0.5, min(prev, c) - 0.5, c))
        prev = c
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"time": [t(i) for i in range(len(closes))],
                         "open": o, "high": h, "low": l, "close": c})


def levels(*rows):
    """rows: (kind, price, active_bar, pivot_bar)."""
    return pd.DataFrame({"kind": [r[0] for r in rows], "price": [float(r[1]) for r in rows],
                         "active_from": [t(r[2]) for r in rows],
                         "pivot_time": [t(r[3]) for r in rows]})


def snap(c, lv, directions="both"):
    return mss._build(c, lv, "Nifty 50", "1d", "1D", "1d", TOL, directions, partial=False)


def test_choch_today_text_and_alert():
    s = snap(candles([100, 101, 102, 106]), levels(("high", 105, 0, 0)))
    assert s["trend"]["state"] == "uptrend" and s["trend"]["held"] == 1
    assert len(s["alerts"]) == 1 and s["alerts"][0]["type"] == "CHoCH"
    assert any(x.startswith("⚡ Today: CHoCH, neutral to uptrend — closed above 105.00")
               for x in s["texts"])
    assert s["texts"][0].startswith("Nifty 50 · 1D — as of Thu 8 Oct 2026: close 106.00")


def test_bos_today_has_no_flash():
    c = candles([100, 106, 104, 103, 109])
    lv = levels(("high", 105, 0, 0), ("high", 108, 3, 2))
    s = snap(c, lv)
    line = [x for x in s["texts"] if "BOS" in x and "Today" in x][0]
    assert line.startswith("Today: BOS, uptrend continues — closed above 108.00")
    assert s["alerts"][0]["type"] == "BOS"


def test_above_filters_down_events_but_keeps_state():
    s = snap(candles([105, 104, 103, 97]), levels(("low", 100, 0, 0)), directions="above")
    assert s["trend"]["state"] == "downtrend"
    assert s["alerts"] == [] and not any("Today: CHoCH" in x for x in s["texts"])
    assert len(s["events_today"]) == 1                     # recorded, just not shown


def test_flip_lines_with_distance():
    s = snap(candles([100, 101, 102]), levels(("high", 105, 0, 0), ("low", 95, 0, 0)))
    assert s["flip"]["up"]["distance_pts"] == pytest.approx(3.0)
    assert "Close above 105.00 = CHoCH, neutral to uptrend (+3.00 / +2.94% away)." in s["texts"]
    assert "Close below 95.00 = CHoCH, neutral to downtrend (-7.00 / -6.86% away)." in s["texts"]


def test_broken_target_waits_for_new_swing():
    s = snap(candles([100, 106, 107]), levels(("high", 105, 0, 0)))
    assert "Close above: no level now, waiting for a new swing high (BOS, uptrend continues on its break)." in s["texts"]


def test_failed_label_today_is_text_not_alert():
    s = snap(candles([100, 106, 106.5, 103.5]), levels(("high", 105, 0, 0)))
    assert s["alerts"] == []
    assert s["labels_today"][0]["label"] == "failed"
    assert any(x.startswith("Today: the 105.00 break (Tue 6 Oct 2026) failed.") for x in s["texts"])


def test_last_break_status_when_nothing_today():
    s = snap(candles([100, 106, 107, 108]), levels(("high", 105, 0, 0)))
    assert any(x.startswith("Last break: CHoCH, neutral to uptrend, 105.00 (Tue 6 Oct 2026):")
               for x in s["texts"])


def test_package_is_json_safe():
    s = snap(candles([100, 106, 106.5, 103.5]), levels(("high", 105, 0, 0), ("low", 95, 0, 0)))
    json.dumps(s, allow_nan=False)


def test_summary_line():
    a = {"trend": {"state": "uptrend"}}
    b = {"trend": {"state": "downtrend"}}
    line = mss.summary_line({"1mo": a, "1d": b, "5m": None}, {"60m": a, "1d": b})
    assert line == "Structure: 1M uptrend · 1D downtrend · 5m n/a · prov. 60m uptrend · prov. 1D downtrend"


def _walk(n, freq, tz=None):
    rng = np.random.default_rng(7)
    c = 22000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    ts = pd.date_range("2024-01-01 09:15", periods=n, freq=freq, tz=tz)
    return pd.DataFrame({"ts": ts, "open": c, "high": c * 1.004, "low": c * 0.996, "close": c})


def test_snapshot_from_bars_and_provisional_run_on_real_shaped_data():
    s = mss.snapshot_from_bars(_walk(600, "B"), "Nifty 50", "1d")
    assert s["view"] == "1d" and s["texts"][0].startswith("Nifty 50 · 1D — as of ")
    json.dumps(s, allow_nan=False)
    p = mss.provisional_snapshot(_walk(800, "5min", "Asia/Kolkata"), "Nifty 50", "60m")
    assert p["view"] == "provisional_60m" and "provisional 60m (from 5m)" in p["texts"][0]
    w = mss.snapshot_from_bars(_walk(300, "W-MON"), "Nifty 50", "1w")
    assert "(week to date)" in w["texts"][0] and "Week of Mon" in w["texts"][0]


def test_build_never_raises(monkeypatch):
    from modules.market_data.upstox import indicator_ohlcv_reader as reader

    class R:
        ok, df, error = False, None, "no data stored"

    monkeypatch.setattr(reader, "read_for_indicators", lambda *a, **k: R())
    res = mss.build_market_structure_snapshot("NSE_INDEX|Nifty 50", "Nifty 50", ("1d", "5m"))
    assert not res.ok and res.snapshots == {"1d": None, "5m": None}
    assert res.errors["1d"] == "no data stored" and res.provisional["60m"] is None
    assert res.summary.startswith("Structure: 1D n/a · 5m n/a")


def test_bad_input():
    with pytest.raises(ValueError):
        mss.snapshot_from_bars(_walk(50, "B"), "Nifty 50", "2d")
    with pytest.raises(ValueError):
        mss.snapshot_from_bars(_walk(50, "B"), "Nifty 50", "1d", directions="up")
    with pytest.raises(ValueError):
        mss.snapshot_from_bars(_walk(50, "B").iloc[0:0], "Nifty 50", "1d")
    with pytest.raises(ValueError):
        mss.provisional_snapshot(_walk(50, "B"), "Nifty 50", "15m")


if __name__ == "__main__":
    from datetime import datetime

    class _Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, text):
            for s in self.streams:
                s.write(text)

        def flush(self):
            for s in self.streams:
                s.flush()

        def isatty(self):
            return False

    log_dir = Path(__file__).resolve().parents[4] / "logs" / "market_structure_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "market_structure_snapshot_unit_tests.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Market structure snapshot unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
