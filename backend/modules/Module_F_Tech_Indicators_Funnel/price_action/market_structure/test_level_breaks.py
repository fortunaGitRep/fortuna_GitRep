"""
Unit tests for level_breaks.py. One resistance level at 100 (or support at
100), tolerance 1% (retest zone 100-101, failure below 99).

Run from backend/ (output also saved to logs/market_structure_test_logs/level_breaks_unit_tests.log):
  python -m modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.test_level_breaks
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from level_breaks import find_level_breaks  # noqa: E402

TOL = 1.0
T0 = pd.Timestamp("2026-10-14 09:15")


def candles(ohlc):
    t = pd.date_range(T0, periods=len(ohlc), freq="5min")
    o, h, l, c = zip(*ohlc)
    return pd.DataFrame({"time": t, "open": o, "high": h, "low": l, "close": c})


def level(kind="high", price=100.0, known_bar=0):
    return pd.DataFrame({"kind": [kind], "price": [price],
                         "known_at": [T0 + pd.Timedelta(minutes=5 * known_bar)]})


def t(i):
    return T0 + pd.Timedelta(minutes=5 * i)


def test_wick_attempt_then_close_confirmed():
    c = candles([(95, 96, 94, 95),      # 0 known
                 (95, 101, 94, 99),     # 1 wick above, close below -> attempt
                 (99, 104, 98, 103),    # 2 close above -> confirmed
                 (103, 106, 102, 105)])
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["attempt_time"] == t(1)
    assert r["confirmed_time"] == t(2)
    assert not r["gap"]
    assert pd.isna(r["retest_time"]) and r["outcome"] is None   # no retest = stronger case


def test_gap_through_level():
    c = candles([(95, 96, 94, 95), (102, 105, 101.5, 104)])
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["confirmed_time"] == t(1) and bool(r["gap"])


def test_retest_then_held():
    c = candles([(95, 96, 94, 95),
                 (99, 104, 98, 103),    # 1 confirmed
                 (103, 106, 102, 105),
                 (105, 105, 100.5, 102),  # 3 back within 100-101, closes above -> retest + held
                 ])
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["retest_time"] == t(3) and r["bars_to_retest"] == 2
    assert r["outcome"] == "held" and r["outcome_time"] == t(3)


def test_failed_break_busted():
    c = candles([(95, 96, 94, 95),
                 (99, 104, 98, 103),    # 1 confirmed
                 (103, 103, 97, 98)])   # 2 closes below 99 -> failed
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["outcome"] == "failed" and r["outcome_time"] == t(2)


def test_retest_then_failed():
    c = candles([(95, 96, 94, 95),
                 (99, 104, 98, 103),        # 1 confirmed
                 (103, 106, 102, 105),      # 2 cleared (low 102 > 101)
                 (105, 105, 99.5, 99.8),    # 3 retest, close 99.8 (below level, above 99): no hold yet
                 (99.8, 100, 97, 98)])      # 4 close below 99 -> failed
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["cleared_time"] == t(2) and r["retest_time"] == t(3)
    assert r["outcome"] == "failed" and r["outcome_time"] == t(4)


def test_support_level_mirrors():
    c = candles([(105, 106, 104, 105),
                 (101, 102, 99, 101),     # 1 wick below -> attempt
                 (101, 101, 96, 97),      # 2 close below -> confirmed
                 (97, 98, 95, 96),        # 3 cleared (high 98 < 99)
                 (96, 99.5, 96, 98)])     # 4 back within 99-100, closes below -> retest + held
    r = find_level_breaks(c, level("low"), TOL).iloc[0]
    assert r["attempt_time"] == t(1) and r["confirmed_time"] == t(2)
    assert r["cleared_time"] == t(3)
    assert r["outcome"] == "held" and r["outcome_time"] == t(4)


def test_held_then_failed_later():
    # Ash's 22534.40 case: held Fri, failed Mon
    c = candles([(95, 96, 94, 95),
                 (99, 104, 98, 103),      # 1 confirmed
                 (103, 106, 102, 105),    # 2 cleared
                 (105, 105, 100.5, 102),  # 3 retest + held
                 (102, 103, 101.5, 102),
                 (102, 102, 97, 98)])     # 5 close below 99 -> failed after hold
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["held_time"] == t(3)
    assert r["outcome"] == "failed" and r["outcome_time"] == t(5)


def test_held_stays_held_without_failure():
    c = candles([(95, 96, 94, 95), (99, 104, 98, 103), (103, 106, 102, 105),
                 (105, 105, 100.5, 102), (102, 106, 101.5, 105)])
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["outcome"] == "held" and r["held_time"] == t(3) and r["outcome_time"] == t(3)


def test_next_candle_overlap_is_not_a_retest():
    # Ash's 22534.40 case: candle after the break dips into the band, no white space yet
    c = candles([(95, 96, 94, 95),
                 (99, 104, 98, 103),      # 1 confirmed
                 (103, 105, 100.5, 104),  # 2 low in band, never cleared before -> not a retest
                 (104, 106, 103, 105)])   # 3 cleared
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["cleared_time"] == t(3)
    assert pd.isna(r["retest_time"]) and r["outcome"] is None


def test_hugging_level_is_not_cleared():
    c = candles([(95, 96, 94, 95), (99, 104, 98, 103), (103, 104, 100.5, 102)])
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert not pd.isna(r["confirmed_time"])
    assert pd.isna(r["cleared_time"]) and pd.isna(r["retest_time"])


def test_gap_candle_fully_clear_counts_as_cleared():
    c = candles([(95, 96, 94, 95), (102, 105, 101.5, 104)])
    r = find_level_breaks(c, level(), TOL).iloc[0]
    assert r["cleared_time"] == t(1)


def test_rebreak_after_failure_is_new_cycle():
    # like 24571.75 support: gap break 4 Mar, failed 5 Mar, broke again 6 Mar
    c = candles([(105, 106, 104, 105),
                 (98, 99, 96, 97),        # 1 gap break below 100
                 (97, 103, 97, 102),      # 2 close above 101 -> failed
                 (102, 102, 97, 98)])     # 3 close below 100 again -> cycle 2
    r = find_level_breaks(c, level("low"), TOL)
    assert list(r["cycle"]) == [1, 2]
    assert r["outcome"].iloc[0] == "failed" and r["outcome_time"].iloc[0] == t(2)
    assert r["confirmed_time"].iloc[1] == t(3) and r["outcome"].iloc[1] is None
    assert list(r["price"]) == [100.0, 100.0]


def test_failed_without_new_attempt_stays_one_row():
    c = candles([(95, 96, 94, 95), (99, 104, 98, 103), (103, 103, 97, 98), (98, 99, 96, 97)])
    r = find_level_breaks(c, level(), TOL)
    assert len(r) == 1 and r["cycle"].iloc[0] == 1


def test_unresolved_outcome_is_none_with_many_levels():
    c = candles([(95, 96, 94, 95), (99, 104, 98, 103), (103, 106, 102, 105)])
    lv = pd.DataFrame({"kind": ["high", "high"], "price": [100.0, 200.0],
                       "known_at": [T0, T0]})
    r = find_level_breaks(c, lv, TOL)
    assert r["outcome"].iloc[0] is None and r["outcome"].iloc[1] is None


def test_timezone_aware_times():
    c = candles([(95, 96, 94, 95), (99, 104, 98, 103)])
    c["time"] = c["time"].dt.tz_localize("Asia/Kolkata")
    lv = level()
    lv["known_at"] = lv["known_at"].dt.tz_localize("Asia/Kolkata")
    r = find_level_breaks(c, lv, TOL).iloc[0]
    assert r["confirmed_time"] == t(1).tz_localize("Asia/Kolkata")


def test_candles_before_known_time_ignored():
    c = candles([(99, 104, 98, 103), (103, 104, 102, 103)])
    r = find_level_breaks(c, level(known_bar=1), TOL).iloc[0]
    assert pd.isna(r["attempt_time"]) and pd.isna(r["confirmed_time"])


def test_bad_input():
    c = candles([(95, 96, 94, 95)])
    with pytest.raises(ValueError):
        find_level_breaks(c.drop(columns="open"), level(), TOL)
    with pytest.raises(ValueError):
        find_level_breaks(c, level().drop(columns="known_at"), TOL)
    with pytest.raises(ValueError):
        find_level_breaks(c, level(), -1)


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
    log_path = log_dir / "level_breaks_unit_tests.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Level breaks unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
