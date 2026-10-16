"""
Unit tests for swing_legs.py.

Run from backend/ (output also saved to logs/zigzag_test_logs/swing_legs_unit_tests.log):
  python -m modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.test_swing_legs
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from swing_legs import add_leg_data  # noqa: E402


def setup():
    times = pd.date_range("2026-10-14 09:15", periods=20, freq="5min")
    swings = pd.DataFrame({
        "kind": ["low", "high", "low"],
        "price": [100.0, 110.0, 105.0],
        "pivot_time": [times[2], times[8], times[11]],
    })
    return swings, pd.Series(times)


def test_leg_size_and_pct():
    swings, times = setup()
    out = add_leg_data(swings, times)
    assert pd.isna(out["leg_points"].iloc[0])
    assert out["leg_points"].iloc[1] == 10.0
    assert out["leg_pct"].iloc[1] == pytest.approx(10.0)
    assert out["leg_points"].iloc[2] == -5.0
    assert out["leg_pct"].iloc[2] == pytest.approx(-5 / 110 * 100)


def test_leg_bars():
    swings, times = setup()
    out = add_leg_data(swings, times)
    assert out["leg_bars"].iloc[1] == 6
    assert out["leg_bars"].iloc[2] == 3


def test_retracement():
    swings, times = setup()
    out = add_leg_data(swings, times)
    assert pd.isna(out["retrace_pct"].iloc[1])
    assert out["retrace_pct"].iloc[2] == pytest.approx(50.0)   # gave back half


def test_empty_and_bad_input():
    _, times = setup()
    empty = pd.DataFrame(columns=["kind", "price", "pivot_time"])
    assert add_leg_data(empty, times).empty
    with pytest.raises(ValueError):
        add_leg_data(pd.DataFrame({"price": [1.0]}), times)


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

    log_dir = Path(__file__).resolve().parents[4] / "logs" / "zigzag_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "swing_legs_unit_tests.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Swing legs unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
