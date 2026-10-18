"""
Unit tests for horizontal_sr_snapshot.py (no R2 needed: a fake reader serves candles).

Run on their own (writes logs/horizontal_sr_test_logs/horizontal_sr_snapshot_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_horizontal_sr_snapshot
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

from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr import (
    number_lines,
    swing_lines,
    pd_tags,
    merge_close_lines,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_snapshot import (
    TRADING,
    build_horizontal_sr_snapshot,
    merged_list,
    snapshot_from_lines,
    summary_line,
)

FREQ = {"1d": "B", "1w": "W-MON", "1mo": "MS", "60m": "60min", "15m": "15min", "5m": "5min"}


def fake_reader(key, domain, tf):
    n = 600
    rng = np.random.default_rng(7)
    c = 22500 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    ts = pd.date_range("2026-01-05 09:15", periods=n, freq=FREQ[tf])
    df = pd.DataFrame({"ts": ts, "open": c, "high": c * 1.003, "low": c * 0.997, "close": c,
                       "volume": 0.0, "trade_date": ts.date})
    return SimpleNamespace(ok=True, df=df, error=None)


def _numbered():
    sw = pd.DataFrame({"kind": ["high", "low", "high", "low", "high"],
                       "price": [120.0, 95.0, 110.0, 90.0, 130.0],
                       "pivot_time": pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14",
                                                     "2026-10-15", "2026-10-16"]),
                       "is_locked": [True, True, True, True, False]})
    lines = pd_tags(swing_lines(sw, "1d"), {"open": 1.0, "high": 110.0, "low": 1.0, "close": 100.0})
    return number_lines(merge_close_lines(lines, 0.0, 100.0), 100.0)


def test_view_lists_nearest_first():
    v = snapshot_from_lines(_numbered(), 100.0, pd.Timestamp("2026-10-16"), "1d", "Nifty 50")
    assert [x["label"] for x in v["resistances"]] == ["R1", "R2", "R3"]
    assert [x["price"] for x in v["resistances"]] == [110.0, 120.0, 130.0]
    assert [x["label"] for x in v["supports"]] == ["S1", "S2"]
    assert v["counts"] == {"R": 3, "AT": 0, "S": 2}


def test_view_texts_r3_to_r1_then_supports():
    v = snapshot_from_lines(_numbered(), 100.0, pd.Timestamp("2026-10-16"), "1d", "Nifty 50")
    assert v["texts"][0] == "Nifty 50 · 1d — as of Fri 16 Oct 2026: close 100.00"
    assert v["texts"][1] == "R3 130.00 (+30.00) · R2 120.00 (+20.00) · R1 110.00 PDH (+10.00)"
    assert v["texts"][2] == "S1 95.00 (-5.00) · S2 90.00 (-10.00)"


def test_line_fields():
    v = snapshot_from_lines(_numbered(), 100.0, pd.Timestamp("2026-10-16"), "1d", "Nifty 50")
    r1 = v["resistances"][0]
    assert r1["pd_tags"] == ["PDH"] and r1["timeframes"] == ["1d"] and r1["distance_pct"] == 10.0
    assert r1["pivot_text"] == "Wed 14 Oct 2026" and r1["is_locked"] is True and r1["merged"] == []


def test_no_lines_side_text():
    empty = _numbered().iloc[0:0]
    v = snapshot_from_lines(empty, 100.0, pd.Timestamp("2026-10-16"), "1d", "X")
    assert v["texts"][1] == "Above: no line." and v["texts"][2] == "Below: no line."


def test_merged_list():
    assert merged_list("") == [] and merged_list(None) == []
    assert merged_list("a; b") == ["a", "b"]


def test_summary_line():
    v = snapshot_from_lines(_numbered(), 100.0, pd.Timestamp("2026-10-16"), TRADING, "Nifty 50")
    assert summary_line(v) == "S&R: R1 110.00 PDH · S1 95.00 (trading ladder)"
    assert summary_line(None) == "S&R: trading ladder not available."


def test_build_all_views_and_json_safe():
    snap = build_horizontal_sr_snapshot(reader=fake_reader)
    assert snap["ok"] and not snap["errors"]
    assert set(snap["views"]) == {"1mo", "1w", "1d", "60m", "15m", "5m", TRADING}
    assert snap["views"][TRADING]["title"] == "Nifty 50 · Trading ladder (5m)"
    assert snap["texts"][0].startswith("Nifty 50 · Trading ladder (5m) — as of ")
    json.dumps(snap)   # must not raise


def test_build_never_raises_when_reader_raises():
    def broken(key, domain, tf):
        raise RuntimeError("R2 down")
    snap = build_horizontal_sr_snapshot(reader=broken)
    assert snap["ok"] is False and snap["errors"]


def test_build_reports_failed_timeframe_and_keeps_others():
    def no_5m(key, domain, tf):
        if tf == "5m":
            return SimpleNamespace(ok=False, df=None, error="no 5m file")
        return fake_reader(key, domain, tf)
    snap = build_horizontal_sr_snapshot(reader=no_5m)
    assert snap["errors"]["5m"] == "no 5m file"
    assert TRADING in snap["errors"] and "1d" in snap["views"]
    assert snap["summary"] == "S&R: trading ladder not available."


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
    text = "\n".join([f"horizontal_sr snapshot unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
                     + results + ["", summary, f"exit status: {1 if failed else 0}"])
    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "horizontal_sr_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "horizontal_sr_snapshot_unit_tests.log").write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(1 if failed else 0)
