"""
Unit tests for zigzag_swings.py, one per ported TradingView rule.
Candles are hand-made so every expected swing can be checked by eye.

Run (PowerShell, from this folder), output also saved to the logs folder:
  python -m pytest test_zigzag_swings.py -v 2>&1 | Tee-Object -FilePath <repo>\\logs\\zigzag_test_logs\\unit_tests.log
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zigzag_settings import get_zigzag_settings  # noqa: E402
from zigzag_swings import bars_each_side, find_zigzag_swings  # noqa: E402


def make_candles(highs, lows=None):
    """One candle per minute. If lows is None, low == high (a plain line)."""
    lows = highs if lows is None else lows
    times = pd.date_range("2026-10-14 09:15", periods=len(highs), freq="1min")
    return pd.DataFrame({"time": times, "high": highs, "low": lows})


def t(candles, bar):
    return candles["time"].iloc[bar]


# Rule 1: depth is halved, minimum 2
@pytest.mark.parametrize("depth, expected", [(10, 5), (20, 10), (5, 2), (4, 2), (1, 2)])
def test_depth_is_halved_with_minimum_two(depth, expected):
    assert bars_each_side(depth) == expected


# Rules 2 and 4: one high, one low, and confirmation d bars later
def test_simple_high_then_low():
    c = make_candles([100, 101, 102, 110, 102, 101, 100, 90, 100, 101, 102])
    s = find_zigzag_swings(c, deviation_pct=5.0, depth=4)  # d = 2

    assert list(s["kind"]) == ["high", "low"]
    assert list(s["price"]) == [110.0, 90.0]
    assert s["pivot_time"].iloc[0] == t(c, 3)
    assert s["detected_time"].iloc[0] == t(c, 5)   # 2 bars after the high
    assert s["pivot_time"].iloc[1] == t(c, 7)
    assert s["detected_time"].iloc[1] == t(c, 9)


# Locking: a swing locks when the next opposite swing is added
def test_locked_time_set_by_next_opposite_swing():
    c = make_candles([100, 101, 102, 110, 102, 101, 100, 90, 100, 101, 102])
    s = find_zigzag_swings(c, deviation_pct=5.0, depth=4)

    assert bool(s["is_locked"].iloc[0]) is True
    assert s["locked_time"].iloc[0] == t(c, 9)
    assert bool(s["is_locked"].iloc[1]) is False
    assert pd.isna(s["locked_time"].iloc[1])


# Rule 4: a reversal smaller than the deviation is ignored;
# a later, higher high replaces the earlier high
def test_small_reversal_ignored_and_higher_high_replaces():
    c = make_candles([100, 101, 102, 110, 108, 107, 108, 109, 111, 120, 111, 110, 109])
    s = find_zigzag_swings(c, deviation_pct=5.0, depth=4)

    assert len(s) == 1
    assert s["kind"].iloc[0] == "high"
    assert s["price"].iloc[0] == 120.0
    assert s["pivot_time"].iloc[0] == t(c, 9)
    assert s["detected_time"].iloc[0] == t(c, 11)
    assert bool(s["is_locked"].iloc[0]) is False


# Rule 2 tie-break: with two equal highs, the FIRST one is the pivot
def test_equal_highs_first_one_wins():
    c = make_candles([100, 101, 105, 105, 101, 100])
    s = find_zigzag_swings(c, deviation_pct=5.0, depth=4)

    assert len(s) == 1
    assert s["price"].iloc[0] == 105.0
    assert s["pivot_time"].iloc[0] == t(c, 2)


# Pivot highs use the high column, pivot lows use the low column
def test_uses_wicks_not_closes():
    highs = [100, 101, 102, 112, 102, 101, 100, 96, 100, 101, 102]
    lows = [99, 100, 101, 108, 101, 100, 99, 88, 99, 100, 101]
    c = make_candles(highs, lows)
    s = find_zigzag_swings(c, deviation_pct=5.0, depth=4)

    assert list(s["price"]) == [112.0, 88.0]


# Settings table
def test_settings_lookup():
    assert get_zigzag_settings("5m") == (0.2, 10)
    assert get_zigzag_settings("1d") == (5.0, 10)
    with pytest.raises(ValueError):
        get_zigzag_settings("2h")


# Input checks
@pytest.mark.parametrize(
    "bad",
    [
        pd.DataFrame({"time": [1, 2], "high": [1.0, 2.0]}),                      # no low
        pd.DataFrame({"time": [2, 1], "high": [1.0, 2.0], "low": [1.0, 2.0]}),  # unsorted
        pd.DataFrame({"time": [1, 2], "high": [0.0, 2.0], "low": [0.0, 2.0]}),  # zero price
    ],
)
def test_bad_candles_rejected(bad):
    with pytest.raises(ValueError):
        find_zigzag_swings(bad, deviation_pct=5.0, depth=10)


@pytest.mark.parametrize("deviation, depth", [(0, 10), (-1, 10), (5.0, 0)])
def test_bad_settings_rejected(deviation, depth):
    c = make_candles([100, 101, 102])
    with pytest.raises(ValueError):
        find_zigzag_swings(c, deviation_pct=deviation, depth=depth)


# Too few bars: no swings, no error
def test_too_few_bars_returns_empty():
    s = find_zigzag_swings(make_candles([100, 101, 102]), deviation_pct=5.0, depth=10)
    assert s.empty


# Run directly: output goes to the terminal AND backend/logs/zigzag_test_logs/unit_tests.log
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

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "zigzag_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "unit_tests.log"

    with open(log_path, "w", encoding="utf-8") as log_file:  # overwritten each run
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Zig Zag unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
