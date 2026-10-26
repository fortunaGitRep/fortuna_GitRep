"""
Unit tests for hsr_zones.py (no R2 needed).

Run on their own (writes logs/horizontal_sr_test_logs/hsr_zones_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_hsr_zones
or with pytest:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/price_action/horizontal_sr -v
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.hsr_zones import (
    depth_limits, hsr_zones, merge_zones, number_zones, same_turns, swing_zones, zone_breaks)


def _candles(rows, start="2026-01-01", freq="1D"):
    """rows: (open, high, low, close)"""
    t = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame({"time": t, "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows]})


def _swings(rows):
    """rows: (kind, price, time)"""
    return pd.DataFrame({"kind": [r[0] for r in rows], "price": [r[1] for r in rows],
                         "pivot_time": pd.to_datetime([r[2] for r in rows]), "is_locked": True})


# 6 daily candles moving 10 a day: gamma 10, true range 20 -> half ATR 10
FLAT = [(100, 110, 90, 100), (100, 110, 90, 110), (110, 120, 100, 100),
        (100, 110, 90, 110), (110, 120, 100, 100), (100, 110, 90, 110)]


def test_depth_limits_use_only_past_candles():
    c = depth_limits(_candles(FLAT))
    assert c["gamma"].iloc[0] != c["gamma"].iloc[0] or c["gamma"].iloc[0] >= 0   # first: NaN or 0
    assert c["gamma"].iloc[5] == pytest.approx(10.0)
    # changing a later candle must not change an earlier value
    later = [list(r) for r in FLAT]
    later[5] = [100, 500, 10, 400]
    c2 = depth_limits(_candles(later))
    assert c2["gamma"].iloc[4] == c["gamma"].iloc[4]
    assert c2["atr_half"].iloc[4] == c["atr_half"].iloc[4]


def test_swing_high_zone_is_wick_to_body_top():
    rows = [list(r) for r in FLAT]
    rows[4] = [104, 120, 100, 106]                 # body top 106, wick 120 -> depth 14 > half ATR 10
    c = _candles(rows)
    z = swing_zones(_swings([("high", 120, "2026-01-05")]), c, "1d", since=pd.Timestamp("2000-01-01"))
    half_atr = depth_limits(c)["atr_half"].iloc[4]
    assert z["hi"].iloc[0] == 120
    assert z["lo"].iloc[0] == pytest.approx(120 - min(14, half_atr))


def test_swing_low_zone_is_wick_to_body_bottom():
    rows = [list(r) for r in FLAT]
    rows[4] = [104, 110, 100, 106]                 # body bottom 104, wick 100 -> depth 4
    c = _candles(rows)
    z = swing_zones(_swings([("low", 100, "2026-01-05")]), c, "1d", since=pd.Timestamp("2000-01-01"))
    gamma = depth_limits(c)["gamma"].iloc[4]
    assert z["lo"].iloc[0] == 100
    assert z["hi"].iloc[0] == pytest.approx(100 + max(4, gamma))   # at least gamma deep


def test_depth_never_more_than_half_atr():
    rows = [list(r) for r in FLAT]
    rows[4] = [101, 120, 100, 101]                 # body bottom 101 -> 19 below the high
    c = _candles(rows)
    z = swing_zones(_swings([("high", 120, "2026-01-05")]), c, "1d", since=pd.Timestamp("2000-01-01"))
    assert 120 - z["lo"].iloc[0] <= depth_limits(c)["atr_half"].iloc[4] + 1e-9


def test_missing_candle_at_swing_is_an_error():
    with pytest.raises(ValueError):
        swing_zones(_swings([("high", 120, "2030-01-01")]), _candles(FLAT), "1d",
                    since=pd.Timestamp("2000-01-01"))


def test_unknown_timeframe_is_an_error():
    with pytest.raises(ValueError):
        swing_zones(_swings([("high", 120, "2026-01-01")]), _candles(FLAT), "4h")


def _z(tf, kind, price, lo, hi, t):
    return {"timeframe": tf, "kind": kind, "price": price, "lo": lo, "hi": hi,
            "pivot_time": pd.Timestamp(t), "is_locked": True}


def test_same_turn_on_two_timeframes_is_one_swing_with_the_smaller_zone():
    daily = pd.DataFrame([_z("1d", "low", 100.0, 100.0, 140.0, "2026-01-05")])
    five = pd.DataFrame([_z("5m", "low", 100.0, 100.0, 103.0, "2026-01-05 13:15")])
    t = same_turns([daily, five])
    assert len(t) == 1
    assert t["timeframes"].iloc[0] == "1d 5m"
    assert t["hi"].iloc[0] == 103.0               # the 5m (finest) zone


def test_same_price_on_different_days_is_two_swings():
    a = pd.DataFrame([_z("5m", "low", 100.0, 100.0, 103.0, "2026-01-05 13:15")])
    b = pd.DataFrame([_z("5m", "low", 100.0, 100.0, 103.0, "2026-01-07 10:00")])
    assert len(same_turns([a, b])) == 2


def test_overlapping_zones_merge_and_count_touches():
    t = pd.DataFrame([_z("5m", "low", 100.0, 100.0, 105.0, "2026-01-05"),
                      _z("15m", "high", 108.0, 103.0, 108.0, "2026-01-06"),
                      _z("5m", "low", 120.0, 120.0, 124.0, "2026-01-07")])
    t["timeframes"] = t["timeframe"]
    z = merge_zones(t)
    assert len(z) == 2
    first = z.iloc[0]
    assert (first["lo"], first["hi"], first["touches"], first["highs"], first["lows"]) == (100.0, 108.0, 2, 1, 1)
    assert first["timeframes"] == "15m 5m" and first["top_tf"] == "15m"


def test_touching_edges_merge_but_a_gap_does_not():
    t = pd.DataFrame([_z("5m", "low", 100.0, 100.0, 105.0, "2026-01-05"),
                      _z("5m", "low", 105.0, 105.0, 108.0, "2026-01-06"),
                      _z("5m", "low", 108.01, 108.01, 110.0, "2026-01-07")])
    t["timeframes"] = t["timeframe"]
    assert list(merge_zones(t)["touches"]) == [2, 1]


def test_wick_beyond_the_far_edge_breaks_the_zone():
    zones = pd.DataFrame([{"lo": 100.0, "hi": 105.0, "last_touch": pd.Timestamp("2026-01-01")}])
    c = _candles([(110, 112, 104, 111), (111, 112, 101, 103), (103, 104, 99.5, 101)], start="2026-01-02")
    z = zone_breaks(zones, c)                     # price above the zone (close 111)
    assert z["broken_at"].iloc[0] == pd.Timestamp("2026-01-04")     # low 99.5 < 100; 101 inside is no break
    assert z["broken_dir"].iloc[0] == "down"


def test_highs_above_a_support_zone_are_not_a_break():
    zones = pd.DataFrame([{"lo": 100.0, "hi": 105.0, "last_touch": pd.Timestamp("2026-01-01")}])
    c = _candles([(110, 130, 106, 120), (120, 140, 108, 135)], start="2026-01-02")
    z = zone_breaks(zones, c)
    assert pd.isna(z["broken_at"].iloc[0]) and z["broken_dir"].iloc[0] == ""


def test_side_from_the_close_decides_the_direction():
    # a resistance zone (price below it): a low below the zone is NOT a break, a high above it is
    zones = pd.DataFrame([{"lo": 100.0, "hi": 105.0, "last_touch": pd.Timestamp("2026-01-01"), "side": "R"}])
    c = _candles([(102, 104, 95, 96), (96, 106, 95, 104)], start="2026-01-02")
    z = zone_breaks(zones, c)
    assert z["broken_dir"].iloc[0] == "up" and z["broken_at"].iloc[0] == pd.Timestamp("2026-01-03")


def test_resistance_breaks_up_on_a_wick():
    zones = pd.DataFrame([{"lo": 100.0, "hi": 105.0, "last_touch": pd.Timestamp("2026-01-01")}])
    c = _candles([(95, 99, 90, 94), (94, 105.5, 93, 97)], start="2026-01-02")
    z = zone_breaks(zones, c)
    assert z["broken_dir"].iloc[0] == "up" and z["broken_at"].iloc[0] == pd.Timestamp("2026-01-03")


def test_numbering_from_close():
    zones = pd.DataFrame({"lo": [90.0, 98.0, 110.0, 130.0], "hi": [95.0, 102.0, 115.0, 135.0]})
    z = number_zones(zones, 100.0)
    assert list(z["label"]) == ["R2", "R1", "AT", "S1"]


def test_bad_close_is_an_error():
    with pytest.raises(ValueError):
        number_zones(pd.DataFrame({"lo": [1.0], "hi": [2.0]}), 0)


def test_end_to_end_and_input_not_modified():
    rows = [list(r) for r in FLAT]
    rows[2] = [110, 125, 100, 104]
    c = _candles(rows)
    sw = _swings([("low", 90, "2026-01-01"), ("high", 125, "2026-01-03"), ("low", 90, "2026-01-04")])
    before_c, before_s = c.copy(), sw.copy()
    z = hsr_zones({"1d": (sw, c)}, close=110.0, break_candles=c)
    pd.testing.assert_frame_equal(c, before_c)
    pd.testing.assert_frame_equal(sw, before_s)
    assert set(z["label"]) == {"R1", "S1"}
    s1 = z[z["label"] == "S1"].iloc[0]
    assert s1["touches"] == 2 and s1["lows"] == 2                  # two separate lows at 90


def test_empty_input():
    z = hsr_zones({}, close=100.0)
    assert z.empty


# --- run on their own with a log ------------------------------------------------------

def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    out = ["python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_hsr_zones",
           f"hsr_zones unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}"]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            out.append(f"PASS {name}")
        except Exception:                               # noqa: BLE001 - report every failure
            failed += 1
            out.append(f"FAIL {name}\n{traceback.format_exc()}")
    out.append(f"{len(tests) - failed} passed, {failed} failed")
    log_dir = Path(__file__).resolve().parents[4] / "logs" / "horizontal_sr_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "hsr_zones_unit_tests.log").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
