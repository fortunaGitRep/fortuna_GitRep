"""
Unit tests for ema_break.py (no R2 needed; hand-built candles, the EMA passed in as a line).

Run on their own (writes logs/ema_break_test_logs/ema_break_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.test_ema_break
"""

from __future__ import annotations

import math
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.ema_break import (
    analyze_line,
    history_odds,
    line_texts,
    size_tier,
)


def _candles(last_rows, n_base=25, base=105.0):
    """n_base calm candles above 100 (close alternates base/base+1, range 2), then last_rows."""
    rows = []
    for i in range(n_base):
        c = base + (i % 2)
        rows.append((c, c + 1, c - 1, c))
    rows += last_rows
    return pd.DataFrame({"time": pd.date_range("2026-10-01 09:15", periods=len(rows), freq="5min"),
                         "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows]})


def _line(c, value=100.0):
    return pd.Series([value] * len(c), dtype=float)


def test_size_tiers():
    assert [size_tier(v) for v in (2.0, 3.5, 1.99, 1.0, 0.99, 0.2)] == \
        ["tall", "tall", "normal", "normal", "small", "small"]
    assert size_tier(float("nan")) is None and size_tier(None) is None


def test_tall_break_on_latest_candle():
    c = _candles([(104, 104.5, 98, 98.5)])          # range 6.5 vs avg ~2.2 -> tall, close below 100
    s = analyze_line(c, _line(c), 50, "5m")
    b = s["break"]
    assert b["direction"] == "below" and b["tier"] == "tall" and b["range_vs_avg"] >= 2
    texts, alerts = line_texts(s)
    assert alerts and alerts[0].startswith("⚡ 5m: closed below EMA 50 (100.00) on a TALL candle")


def test_small_break_is_text_only():
    c = _candles([(100.4, 100.6, 99.4, 99.6)])      # range 1.2 vs avg ~1.96 -> small
    s = analyze_line(c, _line(c), 200, "15m")
    assert s["break"]["tier"] == "small"
    texts, alerts = line_texts(s)
    assert texts and not alerts and "on a small candle" in texts[0]


def test_break_above_resistance():
    rows = []
    for i in range(25):
        c = 95.0 - (i % 2)
        rows.append((c, c + 1, c - 1, c))
    rows.append((96, 102.5, 95.8, 102))             # closes above 100, range 6.7 -> tall
    c = pd.DataFrame({"time": pd.date_range("2026-10-01", periods=len(rows), freq="15min"),
                      "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                      "low": [r[2] for r in rows], "close": [r[3] for r in rows]})
    s = analyze_line(c, _line(c), 100, "15m")
    assert s["break"]["direction"] == "above" and s["break"]["tier"] == "tall"


def test_near_new_fires_once():
    c = _candles([(101, 101.2, 100.2, 100.6)])      # close 0.6 above, X = 1 -> near, new
    s = analyze_line(c, _line(c), 50, "5m")
    assert s["near"] and s["near_new"] and s["break"] is None
    texts, alerts = line_texts(s)
    assert len(alerts) == 1 and "near" in alerts[0]
    c2 = _candles([(101, 101.2, 100.2, 100.6), (100.6, 101.0, 100.3, 100.8)])
    s2 = analyze_line(c2, _line(c2), 50, "5m")
    assert s2["near"] and not s2["near_new"]
    t2, a2 = line_texts(s2)
    assert t2 and not a2


def test_far_from_ema_says_nothing():
    c = _candles([])
    s = analyze_line(c, _line(c), 50, "5m")
    assert not s["near"] and s["break"] is None
    assert line_texts(s) == ([], [])


def test_no_ema_yet_returns_none():
    c = _candles([])
    ema = _line(c)
    ema.iloc[-1] = np.nan
    assert analyze_line(c, ema, 200, "5m") is None


def test_history_odds_and_recent_breaks_excluded():
    times = pd.Series(pd.date_range("2026-01-01", periods=100, freq="D"))
    ep = pd.DataFrame({
        "outcome": ["break", "break", "break", "break", "bounce", "break"],
        "end_time": [times[10], times[20], times[30], times[40], times[50], times[95]],
        "range_vs_avg": [2.5, 2.2, 1.5, 0.5, 1.0, 3.0],
        "reclaimed_after": [np.nan, 2.0, 12.0, 1.0, np.nan, np.nan],
    })
    o = history_odds(ep, times)
    assert o["touches"] == 6 and o["touch_break_pct"] == round(100 * 5 / 6, 1)
    assert o["tall"] == {"n": 2, "held_pct": 50.0, "failed_pct": 50.0}   # 95 excluded (only 4 candles after)
    assert o["normal"] == {"n": 1, "held_pct": 100.0, "failed_pct": 0.0}
    assert o["small"] == {"n": 1, "held_pct": 0.0, "failed_pct": 100.0}
    assert o["all"]["n"] == 4


def test_odds_attached_to_break_match_history():
    rng = np.random.default_rng(5)
    n = 3000
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    o = np.r_[close[0], close[:-1]]
    c = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=n, freq="5min"), "open": o,
                      "high": np.maximum(o, close) + rng.uniform(0, 1, n),
                      "low": np.minimum(o, close) - rng.uniform(0, 1, n), "close": close})
    ema = c["close"].ewm(span=50, adjust=False).mean()
    s = analyze_line(c, ema, 50, "5m")
    assert s["history"]["touches"] > 50
    if s["break"] and s["break"]["tier"]:
        assert s["break"]["odds"] == s["history"][s["break"]["tier"]]


def test_input_not_modified():
    c = _candles([(104, 104.5, 98, 98.5)])
    before = c.copy()
    analyze_line(c, _line(c), 50, "5m")
    pd.testing.assert_frame_equal(c, before)


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
    text = "\n".join([f"ema_break unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
                     + results + ["", summary, f"exit status: {1 if failed else 0}"])
    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "ema_break_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ema_break_unit_tests.log").write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(1 if failed else 0)
