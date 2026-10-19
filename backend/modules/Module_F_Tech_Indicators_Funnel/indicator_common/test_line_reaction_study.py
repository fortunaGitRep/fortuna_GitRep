"""
Unit tests for line_reaction_study.py (no R2 needed; hand-built candles, line at 100, X = 2).

Run on their own (writes logs/indicator_common_test_logs/line_reaction_study_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.indicator_common.test_line_reaction_study
"""

from __future__ import annotations

import math
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.line_reaction_study import (
    average_move,
    find_episodes,
    touch_table,
)


def _c(rows):
    """rows: (open, high, low, close) per candle, one day apart."""
    return pd.DataFrame({"time": pd.date_range("2026-01-01", periods=len(rows), freq="D"),
                         "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows]})


def _run(rows, mode="wick", line=100.0, x=2.0, x_window=20):
    c = _c(rows)
    ln = pd.Series([line] * len(c)) if not isinstance(line, list) else pd.Series(line, dtype=float)
    return find_episodes(c, ln, mode, x=pd.Series([x] * len(c)), x_window=x_window)


CLEAR_ABOVE = (105, 106, 104, 105)
CLEAR_BELOW = (95, 96, 94, 95)


def test_single_touch_bounce():
    ep = _run([CLEAR_ABOVE, (101, 103.5, 99.5, 103)])
    assert len(ep) == 1
    e = ep.iloc[0]
    assert (e["side"], e["touches"], e["candles"], e["outcome"]) == ("support", 1, 1, "bounce")
    assert e["candles_clear_before"] == 1


def test_three_touches_then_bounce():
    ep = _run([CLEAR_ABOVE,
               (101, 101.5, 99.8, 101),     # touch 1, unresolved
               (101, 101.5, 100.5, 101),    # no touch, still near
               (101, 101.2, 99.9, 100.5),   # touch 2
               (100.5, 101.5, 99, 101),     # touch 3
               (101, 103.2, 100.8, 103)])   # bounce (no touch)
    e = ep.iloc[0]
    assert (e["touches"], e["candles"], e["outcome"]) == (3, 5, "bounce")


def test_break_after_two_touches_and_reclaim():
    ep = _run([CLEAR_ABOVE,
               (101, 101.5, 99.5, 100.5),   # touch 1
               (100.5, 100.8, 99, 99.5),    # touch 2, close below = break
               (99.5, 101.5, 99.5, 101)])   # first close back above
    e = ep.iloc[0]
    assert (e["touches"], e["outcome"], e["reclaimed_after"]) == (2, "break", 1.0)


def test_break_never_reclaimed_is_nan():
    ep = _run([CLEAR_ABOVE, (101, 101, 98, 98.5), CLEAR_BELOW])
    assert ep.iloc[0]["outcome"] == "break" and math.isnan(ep.iloc[0]["reclaimed_after"])


def test_side_flips_after_break():
    ep = _run([CLEAR_ABOVE, (101, 101, 98, 98.5), CLEAR_BELOW, (96, 100.3, 96, 97.5)])
    assert list(ep["side"]) == ["support", "resistance"]
    assert list(ep["outcome"]) == ["break", "bounce"]


def test_gap_through_line_is_a_one_touch_break():
    # candle opens and stays below the support line: wick touch + close below on the same candle
    ep = _run([CLEAR_ABOVE, CLEAR_BELOW])
    e = ep.iloc[0]
    assert (e["side"], e["touches"], e["candles"], e["outcome"]) == ("support", 1, 1, "break")


def test_resistance_bounce():
    ep = _run([CLEAR_BELOW, (97, 100.2, 96.5, 97.5)])
    e = ep.iloc[0]
    assert (e["side"], e["touches"], e["outcome"]) == ("resistance", 1, "bounce")


def test_needs_a_clear_candle_first():
    straddle = (100, 101, 99, 100.5)
    assert _run([straddle] * 5).empty


def test_next_episode_needs_clear_candle_again():
    # bounce, then straddling candles without a clear candle: no second episode
    ep = _run([CLEAR_ABOVE, (101, 103.5, 99.5, 103), (101, 101, 99.5, 100.5), (100.5, 101, 99.5, 100.2)])
    assert len(ep) == 1


def test_open_at_end_of_data():
    ep = _run([CLEAR_ABOVE, (101, 101.5, 99.6, 101)])
    assert ep.iloc[0]["outcome"] == "open" and pd.isna(ep.iloc[0]["end_time"])


def test_nan_line_is_skipped():
    ep = _run([CLEAR_ABOVE, CLEAR_ABOVE, (101, 103.5, 99.5, 103)], line=[math.nan, 100.0, 100.0])
    assert len(ep) == 1 and ep.iloc[0]["outcome"] == "bounce"


def test_close_mode_counts_a_near_close_without_wick():
    rows = [CLEAR_ABOVE, (102, 102.5, 100.5, 101.5), (101.5, 103.5, 101, 103)]
    assert _run(rows, "wick").empty
    ep = _run(rows, "close")
    assert (ep.iloc[0]["touches"], ep.iloc[0]["outcome"]) == (1, "bounce")


def test_candle_strength_of_deciding_candle():
    ep = _run([CLEAR_ABOVE, (100.5, 104, 99.5, 103.5)], x_window=2)
    e = ep.iloc[0]
    assert round(e["body_pct"], 2) == 66.67
    assert round(e["close_pos"], 3) == 0.889
    assert round(e["range_vs_avg"], 3) == round(4.5 / ((2 + 4.5) / 2), 3)


def test_average_move_rolling_no_future():
    x = average_move(pd.Series([100.0, 102.0, 101.0, 105.0]), window=2)
    assert x.isna().tolist()[:2] == [True, True]
    assert x.tolist()[2:] == [1.5, 2.5]


def test_touch_table():
    ep = pd.DataFrame({"touches": [1, 1, 2, 3, 6, 2],
                       "outcome": ["bounce", "break", "bounce", "break", "bounce", "open"]})
    t = touch_table(ep, max_k=5).set_index("touches")
    assert t.loc["1", ["reached", "bounce", "break", "more_touches"]].tolist() == [5, 1, 1, 3]
    assert t.loc["2", ["reached", "bounce", "break", "more_touches"]].tolist() == [3, 1, 0, 2]
    assert t.loc["3", ["reached", "bounce", "break", "more_touches"]].tolist() == [2, 0, 1, 1]
    assert t.loc["5+", ["reached", "bounce", "break", "more_touches"]].tolist() == [1, 1, 0, 0]


def test_input_not_modified():
    c = _c([CLEAR_ABOVE, (101, 103.5, 99.5, 103)])
    before = c.copy()
    find_episodes(c, pd.Series([100.0, 100.0]), x=pd.Series([2.0, 2.0]))
    pd.testing.assert_frame_equal(c, before)


def test_validation():
    c = _c([CLEAR_ABOVE])
    for call in (lambda: find_episodes(c, pd.Series([1.0, 2.0])),
                 lambda: find_episodes(c, pd.Series([1.0]), touch_mode="body"),
                 lambda: find_episodes(c.drop(columns=["open"]), pd.Series([1.0])),
                 lambda: average_move(pd.Series([1.0]), window=0)):
        try:
            call()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


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
    text = "\n".join([f"line_reaction_study unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
                     + results + ["", summary, f"exit status: {1 if failed else 0}"])
    backend_dir = Path(__file__).resolve().parents[3]
    log_dir = backend_dir / "logs" / "indicator_common_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "line_reaction_study_unit_tests.log").write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(1 if failed else 0)
