"""
Unit tests for swing_labels.py. Tolerance 0.05% (100.00 vs 100.04 = equal).

Run from backend/ (output also saved to logs/market_structure_test_logs/swing_labels_unit_tests.log):
  python -m modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.test_swing_labels
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from swing_labels import add_swing_labels  # noqa: E402

TOL = 0.05


def sw(prices, first="low", locked_all_but_last=True):
    kinds = [first if i % 2 == 0 else ("high" if first == "low" else "low")
             for i in range(len(prices))]
    locked = [True] * len(prices)
    if locked_all_but_last and prices:
        locked[-1] = False
    return pd.DataFrame({"kind": kinds, "price": prices, "is_locked": locked})


def test_uptrend_labels():
    out = add_swing_labels(sw([100, 110, 104, 115, 108]), TOL)
    assert list(out["label"]) == ["L", "H", "HL", "HH", "HL"]


def test_downtrend_labels():
    out = add_swing_labels(sw([115, 100, 110, 95, 105], first="high"), TOL)
    assert list(out["label"]) == ["H", "L", "LH", "LL", "LH"]


def test_double_top_zone_and_neckline():
    # low 95, high 100.00, low 97, high 100.04 -> double top, neckline 97
    out = add_swing_labels(sw([95, 100.00, 97, 100.04]), TOL)
    assert out["label"].iloc[3] == "EQH"
    last = out.iloc[3]
    assert last["zone_touches"] == 2
    assert last["zone_low"] == 100.00 and last["zone_high"] == 100.04
    assert last["neckline"] == 97
    assert out["zone_id"].iloc[1] == out["zone_id"].iloc[3]   # first top is in the zone


def test_triple_top_neckline_is_lowest_low_between():
    out = add_swing_labels(sw([95, 100.00, 97, 100.03, 96.5, 100.02]), TOL)
    assert list(out["label"].iloc[3:]) == ["EQH", "LL", "EQH"]   # 96.5 < 97
    last = out.iloc[5]
    assert last["zone_touches"] == 3
    assert last["neckline"] == 96.5


def test_double_bottom():
    out = add_swing_labels(sw([105, 100.00, 103, 99.98], first="high"), TOL)
    assert out["label"].iloc[3] == "EQL"
    assert out["neckline"].iloc[3] == 103


def test_just_outside_tolerance_is_hh():
    out = add_swing_labels(sw([95, 100.00, 97, 100.06]), TOL)
    assert out["label"].iloc[3] == "HH"
    assert pd.isna(out["zone_id"].iloc[3])


def test_two_separate_zones_get_different_ids():
    out = add_swing_labels(sw([95, 100, 97, 100.02, 90, 92, 91, 92.01]), TOL)
    ids = out["zone_id"].dropna().unique()
    assert len(ids) == 2


def test_latest_label_can_change():
    out = add_swing_labels(sw([100, 110, 104]), TOL)
    assert list(out["label_can_change"]) == [False, False, True]


def test_bad_input():
    with pytest.raises(ValueError):
        add_swing_labels(pd.DataFrame({"kind": ["high", "high"], "price": [1.0, 2.0]}), TOL)
    with pytest.raises(ValueError):
        add_swing_labels(sw([100, 110]), -1)
    assert add_swing_labels(sw([]), TOL).empty


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
    log_path = log_dir / "swing_labels_unit_tests.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Swing labels unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
