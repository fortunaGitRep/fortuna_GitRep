"""
Unit tests for ema_break_snapshot.py (no R2 needed: a fake reader serves candles).

Run on their own (writes logs/ema_break_test_logs/ema_break_snapshot_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.test_ema_break_snapshot
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.ema_break_snapshot import (
    build_ema_break_snapshot,
    context_view,
    live_view,
    summary_line,
)

FREQ = {"1d": "B", "1w": "W-MON", "1mo": "MS", "60m": "60min", "15m": "15min", "5m": "5min"}


def _candles(n=1500, seed=4, freq="5min", start="2026-01-01 09:15"):
    rng = np.random.default_rng(seed)
    close = 22000 + np.cumsum(rng.normal(0, 12, n))
    o = np.r_[close[0], close[:-1]]
    t = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({"time": t, "trade_date": t.date, "open": o,
                         "high": np.maximum(o, close) + rng.uniform(0, 8, n),
                         "low": np.minimum(o, close) - rng.uniform(0, 8, n), "close": close})


def fake_reader(key, domain, tf):
    n = 400 if tf in ("1d", "1w", "1mo") else 1500
    return SimpleNamespace(ok=True, df=_candles(n, freq=FREQ[tf]).rename(columns={"time": "ts"}), error=None)


def test_live_view_has_three_emas():
    v = live_view(_candles(), "5m")
    assert [s["period"] for s in v["lines"]] == [50, 100, 200]
    assert v["timeframe"] == "5m" and v["close"] is not None


def test_live_view_quiet_when_far_from_emas():
    # steady climb: price stays far above EMA 50/100/200 (they lag behind), candles move ~5 pts
    n = 600
    close = 20000 + 5.0 * np.arange(n) + np.where(np.arange(n) % 2, 1.0, -1.0)
    o = np.r_[close[0], close[:-1]]
    c = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=n, freq="15min"), "open": o,
                      "high": np.maximum(o, close) + 1, "low": np.minimum(o, close) - 1, "close": close})
    v = live_view(c, "15m")
    assert all(not s["near"] and s["break"] is None for s in v["lines"])
    assert v["texts"] == [] and v["alerts"] == []


def test_context_line_sides_and_percent():
    c = _candles(400, freq="B", start="2025-01-01")
    v = context_view(c, "1d")
    assert v["texts"][0].startswith("1D (")
    for lv in v["levels"]:
        assert lv["side"] in ("above", "below", "at")
        assert ("+" if lv["side"] == "above" else "") in v["texts"][0]


def test_context_line_ema_not_ready():
    v = context_view(_candles(120, freq="MS", start="2016-01-01"), "1mo")
    assert "EMA 200 n/a" in v["texts"][0] and v["levels"][2]["ema"] is None


def test_summary_line_words():
    live = {
        "60m": {"lines": [{"period": 50, "near": False, "break": None}]},
        "15m": {"lines": [{"period": 200, "near": True,
                           "break": {"direction": "below", "tier": "tall"}}]},
        "5m": {"lines": [{"period": 50, "near": True, "break": None},
                         {"period": 100, "near": False,
                          "break": {"direction": "above", "tier": "small"}}]},
    }
    assert summary_line(live) == ("EMA break watch: 60m quiet · 15m ⚡ broke below EMA 200 (tall) · "
                                  "5m near EMA 50, broke above EMA 100 (small)")


def test_build_all_views_json_safe():
    snap = build_ema_break_snapshot(reader=fake_reader)
    assert snap["ok"] and not snap["errors"]
    assert set(snap["live"]) == {"60m", "15m", "5m"} and set(snap["context"]) == {"1mo", "1w", "1d"}
    assert snap["texts"][0] == "Nifty 50 · EMA break watch (EMA 50 / 100 / 200)"
    assert snap["texts"][1] == snap["summary"]
    json.dumps(snap)   # must not raise (no default=)


def test_alerts_collected_from_live_views():
    snap = build_ema_break_snapshot(reader=fake_reader)
    expected = [a for tf in ("60m", "15m", "5m") for a in snap["live"][tf]["alerts"]]
    assert snap["alerts"] == expected


def test_never_raises_when_reader_raises():
    def broken(key, domain, tf):
        raise RuntimeError("R2 down")
    snap = build_ema_break_snapshot(reader=broken)
    assert snap["ok"] is False and len(snap["errors"]) == 6


def test_failed_timeframe_reported_others_built():
    def no_15m(key, domain, tf):
        if tf == "15m":
            return SimpleNamespace(ok=False, df=None, error="no 15m file")
        return fake_reader(key, domain, tf)
    snap = build_ema_break_snapshot(reader=no_15m)
    assert snap["errors"] == {"15m": "no 15m file"} and "5m" in snap["live"]
    assert "15m n/a" in snap["summary"]


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    results, failed = [], 0
    for t in TESTS:
        try:
            t()
            results.append(f"PASSED  {t.__name__}")
        except Exception:
            failed += 1
            results.append(f"FAILED  {t.__name__}\n{traceback.format_exc()}")
    summary = f"summary: {len(TESTS) - failed} passed, {failed} failed"
    text = "\n".join([f"ema_break snapshot unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
                     + results + ["", summary, f"exit status: {1 if failed else 0}"])
    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "ema_break_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ema_break_snapshot_unit_tests.log").write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(1 if failed else 0)
