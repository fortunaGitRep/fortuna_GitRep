"""
Unit tests for provisional_swings.py. Hand-made swing lists, threshold 1%.

Run from backend/ (output also saved to logs/zigzag_test_logs/provisional_unit_tests.log):
  python -m modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.test_provisional_swings
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provisional_swings import current_direction, provisional_swings  # noqa: E402


def swings(rows):
    """rows: (kind, price, locked) -> lower-timeframe swing list, 5 min apart."""
    t0 = pd.Timestamp("2026-10-14 09:15")
    data = []
    for i, (kind, price, locked) in enumerate(rows):
        pivot = t0 + pd.Timedelta(minutes=5 * i)
        data.append({
            "kind": kind, "price": price, "pivot_time": pivot,
            "detected_time": pivot + pd.Timedelta(minutes=25),
            "locked_time": pivot + pd.Timedelta(minutes=30) if locked else pd.NaT,
            "is_locked": locked,
        })
    return pd.DataFrame(data)


def test_small_wiggles_ignored_big_move_kept():
    # low 100 -> high 100.5 (+0.5%, ignored) -> low 100.2 -> high 102 (+2% from 100, kept)
    s = swings([("low", 100, True), ("high", 100.5, True),
                ("low", 100.2, True), ("high", 102, True), ("low", 101.5, False)])
    p = provisional_swings(s, deviation_pct=1.0)

    assert list(p["kind"]) == ["low", "high"]
    assert list(p["price"]) == [100.0, 102.0]
    assert p["known_at"].iloc[1] == s["locked_time"].iloc[3]


def test_lower_low_replaces_and_updates_known_at():
    s = swings([("low", 100, True), ("high", 100.4, True), ("low", 99.5, True)])
    p = provisional_swings(s, deviation_pct=1.0)

    assert len(p) == 1
    assert p["price"].iloc[0] == 99.5
    assert p["known_at"].iloc[0] == s["locked_time"].iloc[2]


def test_confirmed_when_next_opposite_added():
    s = swings([("low", 100, True), ("high", 102, True), ("low", 100.5, True)])
    p = provisional_swings(s, deviation_pct=1.0)

    assert list(p["price"]) == [100.0, 102.0, 100.5]
    assert bool(p["is_confirmed"].iloc[0]) and bool(p["is_confirmed"].iloc[1])
    assert p["confirmed_at"].iloc[0] == s["locked_time"].iloc[1]
    assert not bool(p["is_confirmed"].iloc[2])


def test_unlocked_lower_swings_not_used():
    s = swings([("low", 100, True), ("high", 105, False)])
    p = provisional_swings(s, deviation_pct=1.0)
    assert list(p["price"]) == [100.0]


def test_direction():
    s = swings([("low", 100, True), ("high", 102, True)])
    d = current_direction(provisional_swings(s, deviation_pct=1.0), deviation_pct=1.0)
    assert d["direction"] == "up"
    assert d["from_price"] == 100.0 and d["extreme"] == 102.0
    assert d["reverses_at"] == pytest.approx(102.0 * 0.99)

    s2 = swings([("low", 100, True), ("high", 102, True), ("low", 100.5, True)])
    d2 = current_direction(provisional_swings(s2, deviation_pct=1.0), deviation_pct=1.0)
    assert d2["direction"] == "down" and d2["extreme"] == 100.5
    assert d2["reverses_at"] == pytest.approx(100.5 * 1.01)

    empty = pd.DataFrame(columns=["kind", "price", "pivot_time", "locked_time", "is_locked"])
    empty["is_locked"] = empty["is_locked"].astype(bool)
    assert current_direction(provisional_swings(empty, 1.0), 1.0)["direction"] == "unknown"


def test_bad_input_rejected():
    with pytest.raises(ValueError):
        provisional_swings(pd.DataFrame({"kind": []}), 1.0)
    with pytest.raises(ValueError):
        provisional_swings(swings([("low", 100, True)]), 0)


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
    log_path = log_dir / "provisional_unit_tests.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Provisional swings unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
