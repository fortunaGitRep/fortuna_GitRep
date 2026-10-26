"""
Unit tests for horizontal_sr.py (no R2 needed).

Run on their own (writes logs/horizontal_sr_test_logs/horizontal_sr_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_horizontal_sr
or with pytest:
    python -m pytest modules/Module_F_Tech_Indicators_Funnel/price_action/horizontal_sr -v
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr import (
    horizontal_sr,
    keep_recent,
    merge_close_lines,
    number_lines,
    pd_tags,
    recent_since,
    swing_lines,
    timeframe_lines,
    trading_ladder,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import (
    find_zigzag_swings,
)


def _swings(rows):
    """rows: (kind, price, 'YYYY-MM-DD', is_locked)"""
    return pd.DataFrame({
        "kind": [r[0] for r in rows],
        "price": [r[1] for r in rows],
        "pivot_time": pd.to_datetime([r[2] for r in rows]),
        "detected_time": pd.to_datetime([r[2] for r in rows]),
        "locked_time": pd.NaT,
        "is_locked": [r[3] for r in rows],
    })


SW = _swings([
    ("low", 100.00, "2026-01-01", True),
    ("high", 120.00, "2026-01-10", True),
    ("low", 105.00, "2026-01-20", True),
    ("high", 130.00, "2026-02-01", True),
    ("low", 110.00, "2026-02-10", False),
])


def test_every_swing_is_one_line():
    lines = swing_lines(SW, "1d")
    assert len(lines) == len(SW)
    assert list(lines["price"]) == [100.0, 120.0, 105.0, 130.0, 110.0]
    assert set(lines["timeframe"]) == {"1d"}


def test_numbering_outward_from_close():
    out = number_lines(swing_lines(SW, "1d"), close=115.0)
    got = dict(zip(out["label"], out["price"]))
    assert got == {"R1": 120.0, "R2": 130.0, "S1": 110.0, "S2": 105.0, "S3": 100.0}


def test_order_top_of_chart_first():
    out = number_lines(swing_lines(SW, "1d"), close=115.0)
    assert list(out["label"]) == ["R2", "R1", "S1", "S2", "S3"]
    assert list(out["price"]) == sorted(out["price"], reverse=True)


def test_line_at_close_is_AT_and_not_numbered():
    out = number_lines(swing_lines(SW, "1d"), close=110.0)
    at = out[out["label"] == "AT"]
    assert len(at) == 1 and at["price"].iloc[0] == 110.0 and at["rank"].iloc[0] is None
    assert dict(zip(out["label"], out["price"]))["S1"] == 105.0
    assert list(out["label"]) == ["R2", "R1", "AT", "S1", "S2"]


def test_at_compared_at_two_decimals():
    out = number_lines(swing_lines(SW, "1d"), close=110.004)
    assert "AT" in set(out["label"])


def test_close_above_all_lines_gives_only_supports():
    out = number_lines(swing_lines(SW, "1d"), close=200.0)
    assert set(out["side"]) == {"S"}
    assert out.iloc[0]["label"] == "S1" and out.iloc[0]["price"] == 130.0


def test_equal_prices_stay_two_lines_newer_first():
    sw = _swings([("high", 120.0, "2026-01-01", True), ("low", 90.0, "2026-01-05", True),
                  ("high", 120.0, "2026-01-10", False)])
    out = number_lines(swing_lines(sw, "1d"), close=100.0)
    r = out[out["side"] == "R"].sort_values("rank")
    assert list(r["label"]) == ["R1", "R2"]
    assert r.iloc[0]["pivot_time"] == pd.Timestamp("2026-01-10")


def test_pd_tags_exact_match():
    prev = {"open": 108.0, "high": 130.0, "low": 105.0, "close": 105.0}
    out = pd_tags(swing_lines(SW, "1d"), prev)
    tags = dict(zip(out["price"], out["pd_tags"]))
    assert tags[130.0] == "PDH"
    assert tags[105.0] == "PDL PDC"
    assert tags[100.0] == "" and tags[110.0] == ""


def test_pd_tags_none_prev_day():
    out = pd_tags(swing_lines(SW, "1d"), None)
    assert set(out["pd_tags"]) == {""}


def test_pd_tags_missing_field_raises():
    try:
        pd_tags(swing_lines(SW, "1d"), {"open": 1.0, "high": 2.0, "low": 0.5})
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_locked_flag_kept():
    out = horizontal_sr(SW, "1d", 115.0)
    assert out.loc[out["price"] == 110.0, "is_locked"].iloc[0] is False or \
        not bool(out.loc[out["price"] == 110.0, "is_locked"].iloc[0])
    assert bool(out.loc[out["price"] == 130.0, "is_locked"].iloc[0])


def test_input_not_modified():
    before = SW.copy()
    horizontal_sr(SW, "1d", 115.0, {"open": 1.0, "high": 130.0, "low": 1.0, "close": 1.0})
    pd.testing.assert_frame_equal(SW, before)


def test_bad_close_raises():
    for bad in (0, -5, float("nan"), None):
        try:
            number_lines(swing_lines(SW, "1d"), bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"expected an error for close={bad!r}")


def test_missing_columns_raises():
    try:
        swing_lines(SW.drop(columns=["is_locked"]), "1d")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_empty_swings():
    empty = _swings([])
    out = horizontal_sr(empty, "5m", 100.0)
    assert out.empty


def test_lines_equal_zigzag_swing_prices_on_candles():
    # Real path: candles -> find_zigzag_swings -> lines. Swing high = candle high, low = candle low.
    n = 60
    times = pd.date_range("2026-01-01", periods=n, freq="D")
    base = [100 + 15 * ((i // 10) % 2) * (i % 10) / 9 - 15 * (1 - (i // 10) % 2) * (i % 10) / 9
            for i in range(n)]
    candles = pd.DataFrame({"time": times,
                            "high": [b + 1 for b in base],
                            "low": [b - 1 for b in base]})
    swings = find_zigzag_swings(candles, 5.0, 10)
    lines = swing_lines(swings, "1d")
    assert len(lines) == len(swings) > 0
    highs = set(candles["high"].round(6))
    lows = set(candles["low"].round(6))
    for _, r in lines.iterrows():
        pool = highs if r["kind"] == "high" else lows
        assert round(r["price"], 6) in pool


# --- recency, merge (rule A), trading ladder (added 2026-10-18) ---------------

def _lines(rows, tf="1d"):
    return pd_tags(swing_lines(_swings(rows), tf), None)


def test_recent_since_counts_trading_days():
    times = pd.Series(pd.to_datetime(["2026-10-13 09:15", "2026-10-13 15:25", "2026-10-14 09:15",
                                      "2026-10-15 09:15", "2026-10-16 09:15", "2026-10-16 15:25"]))
    assert recent_since(times, 3) == pd.Timestamp("2026-10-14")
    assert recent_since(times, 99) == pd.Timestamp("2026-10-13")
    assert recent_since(times, None) is None


def test_keep_recent_drops_old_pivots():
    lines = _lines([("low", 100.0, "2026-10-10", True), ("high", 120.0, "2026-10-14", True),
                    ("low", 110.0, "2026-10-16", False)], "5m")
    kept = keep_recent(lines, pd.Timestamp("2026-10-14"))
    assert list(kept["price"]) == [120.0, 110.0]
    assert len(keep_recent(lines, None)) == 3


def test_merge_all_highs_keeps_highest():
    # Ash: 26,277.35 (Sep 2024) / 26,325.80 (Dec 2025) / 26,373.20 (Jan 2026) -> 26,373.20
    lines = _lines([("high", 26277.35, "2024-09-27", True), ("high", 26325.80, "2025-12-01", True),
                    ("high", 26373.20, "2026-01-05", True)])
    out = merge_close_lines(lines, 0.50)
    assert list(out["price"]) == [26373.20]
    assert out.iloc[0]["merged_count"] == 3
    assert "26,277.35" in out.iloc[0]["merged_from"] and "26,325.80" in out.iloc[0]["merged_from"]


def test_merge_all_lows_keeps_lowest():
    # Ash: 22,182.55 (Thu 2 Apr 2026) / 22,179.90 (Thu 8 Oct 2026) -> 22,179.90
    lines = _lines([("low", 22182.55, "2026-04-02", True), ("low", 22179.90, "2026-10-08", False)])
    out = merge_close_lines(lines, 0.50)
    assert list(out["price"]) == [22179.90]


def test_merge_mixed_keeps_earliest():
    # Ash: high 23,056.40 (Thu 15 Oct 13:30) / low 23,059.45 (Fri 16 Oct 11:10) -> 23,056.40
    lines = _lines([("high", 23056.40, "2026-10-15 13:30", True),
                    ("low", 23059.45, "2026-10-16 11:10", True)], "5m")
    out = merge_close_lines(lines, 0.05)
    assert list(out["price"]) == [23056.40]


def test_merge_keeps_lines_outside_tolerance():
    lines = _lines([("low", 100.0, "2026-01-01", True), ("high", 100.4, "2026-01-02", True),
                    ("low", 101.0, "2026-01-03", True)])
    out = merge_close_lines(lines, 0.50)
    assert list(out["price"]) == [100.0, 101.0]      # 100.4 within 0.5% of 100 -> mixed -> earliest 100.0


def test_merge_group_width_is_bounded():
    # 100, 100.4, 100.8: 100.8 is more than 0.5% above the group's lowest -> its own group
    lines = _lines([("high", 100.0, "2026-01-01", True), ("high", 100.4, "2026-01-02", True),
                    ("high", 100.8, "2026-01-03", True)])
    out = merge_close_lines(lines, 0.50)
    assert list(out["price"]) == [100.4, 100.8]


def test_merge_tolerance_zero_only_identical():
    lines = _lines([("low", 100.0, "2026-01-01", True), ("low", 100.0, "2026-01-05", True),
                    ("low", 100.01, "2026-01-09", True)])
    out = merge_close_lines(lines, 0.0)
    assert list(out["price"]) == [100.0, 100.01]
    assert out.iloc[0]["pivot_time"] == pd.Timestamp("2026-01-01")


def test_pd_line_never_merged_with_other_price():
    # 23,149.85 is PDH; 23,149.00 within 0.05% must not absorb it or take its tag
    lines = pd_tags(swing_lines(_swings([("high", 23149.85, "2026-10-16 10:35", True),
                                         ("high", 23149.00, "2026-10-14 10:00", True)]), "5m"),
                    {"open": 1.0, "high": 23149.85, "low": 1.0, "close": 1.0})
    out = merge_close_lines(lines, 0.05)
    got = dict(zip(out["price"], out["pd_tags"]))
    assert got == {23149.00: "", 23149.85: "PDH"}


def test_pd_lines_same_price_combine_across_timeframes():
    prev = {"open": 1.0, "high": 23149.85, "low": 1.0, "close": 1.0}
    m60 = pd_tags(swing_lines(_swings([("high", 23149.85, "2026-10-16 10:15", False)]), "60m"), prev)
    m5 = pd_tags(swing_lines(_swings([("high", 23149.85, "2026-10-16 10:35", True)]), "5m"), prev)
    out = trading_ladder([merge_close_lines(m60, 0.2), merge_close_lines(m5, 0.05)], 23146.15, 0.05)
    assert len(out) == 1 and out.iloc[0]["timeframes"] == "60m 5m" and out.iloc[0]["pd_tags"] == "PDH"


def test_lines_on_opposite_sides_of_price_never_merge():
    # Real 60m case 16 Oct 2026: high 23,149.85 above the close 23,146.15, low 23,116.10 below
    lines = _lines([("low", 23116.10, "2026-09-16 09:15", True),
                    ("high", 23149.85, "2026-10-16 10:15", False)], "60m")
    out = number_lines(merge_close_lines(lines, 0.20, close=23146.15), 23146.15)
    got = dict(zip(out["label"], out["price"]))
    assert got == {"R1": 23149.85, "S1": 23116.10}


def test_line_at_price_not_merged():
    lines = _lines([("low", 100.0, "2026-01-01", True), ("high", 100.2, "2026-01-02", True)])
    out = merge_close_lines(lines, 0.5, close=100.0)
    assert sorted(out["price"]) == [100.0, 100.2]


def test_timeframe_lines_applies_recency_for_5m():
    sw = _swings([("low", 100.0, "2026-10-01 10:00", True), ("high", 105.0, "2026-10-15 10:00", True),
                  ("low", 101.0, "2026-10-16 10:00", False)])
    times = pd.Series(pd.date_range("2026-10-01 09:15", "2026-10-16 15:25", freq="D"))
    out = timeframe_lines(sw, "5m", times, 0.05)
    assert sorted(out["price"]) == [101.0, 105.0]


def test_timeframe_lines_daily_keeps_all_history():
    times = pd.Series(pd.date_range("2026-01-01", "2026-02-15", freq="D"))
    out = timeframe_lines(SW, "1d", times, 0.0)
    assert len(out) == len(SW)


def test_trading_ladder_merges_timeframes_and_lists_them():
    d = merge_close_lines(_lines([("low", 23070.15, "2026-06-08", True)], "1d"), 0.5)
    m60 = merge_close_lines(_lines([("low", 23070.15, "2026-06-08 09:15", True),
                                    ("high", 23149.85, "2026-10-16 10:15", False)], "60m"), 0.2)
    m5 = merge_close_lines(_lines([("high", 23149.85, "2026-10-16 10:35", True),
                                   ("high", 23162.70, "2026-09-25 14:00", True)], "5m"), 0.05)
    out = trading_ladder([d, m60, m5], 23146.15, 0.05)
    got = {r["label"]: (r["price"], r["timeframes"]) for _, r in out.iterrows()}
    assert got["R1"] == (23149.85, "60m 5m")
    assert got["R2"] == (23162.70, "5m")
    assert got["S1"] == (23070.15, "1d 60m")


def test_trading_ladder_mixes_naive_and_tz_aware_times():
    d = merge_close_lines(_lines([("low", 100.0, "2026-06-08", True)], "1d"), 0.5)
    sw = _swings([("low", 100.0, "2026-06-08 09:15", True)])
    sw["pivot_time"] = sw["pivot_time"].dt.tz_localize("Asia/Kolkata")
    m5 = merge_close_lines(pd_tags(swing_lines(sw, "5m"), None), 0.05)
    out = trading_ladder([d, m5], 110.0, 0.05)
    assert len(out) == 1 and out.iloc[0]["timeframes"] == "1d 5m"


def test_trading_ladder_empty():
    assert trading_ladder([], 100.0, 0.05).empty


# --- rule A by side of price (Ash, 2026-10-23) --------------------------------

def test_merge_mixed_below_price_keeps_lowest_low():
    # Ash: support at 11:20 on 19 Oct is 23,059.45 (Fri 16 Oct 11:10 low), not the
    # older 23,056.40 high (Thu 15 Oct 13:35) — below price, the lowest LOW
    lines = _lines([("high", 23056.40, "2026-10-15 13:35", True),
                    ("low", 23059.45, "2026-10-16 11:10", True)], "5m")
    out = merge_close_lines(lines, 0.05, close=23062.25)
    assert list(out["price"]) == [23059.45]
    assert "23,056.40" in out.iloc[0]["merged_from"]


def test_merge_mixed_above_price_keeps_highest_high():
    # 19 Oct 15:25 close 22,888.95: 22,894.15 low (Thu) / 22,900.65 high (Mon 14:55) -> 22,900.65
    lines = _lines([("low", 22894.15, "2026-10-15 11:15", True),
                    ("high", 22900.65, "2026-10-19 14:55", True)], "5m")
    out = merge_close_lines(lines, 0.05, close=22888.95)
    assert list(out["price"]) == [22900.65]


def test_merge_mixed_side_uses_matching_kind_not_extreme_price():
    # below price: a high lower than the low is not chosen; the lowest LOW is
    lines = _lines([("low", 100.30, "2026-01-01", True), ("high", 100.10, "2026-01-02", True),
                    ("low", 100.20, "2026-01-03", True)])
    out = merge_close_lines(lines, 0.5, close=110.0)
    assert list(out["price"]) == [100.20]


def test_merge_mixed_without_close_still_earliest():
    lines = _lines([("high", 23056.40, "2026-10-15 13:35", True),
                    ("low", 23059.45, "2026-10-16 11:10", True)], "5m")
    assert list(merge_close_lines(lines, 0.05)["price"]) == [23056.40]


def test_trading_ladder_applies_side_rule():
    m5 = merge_close_lines(_lines([("high", 23056.40, "2026-10-15 13:35", True)], "5m"), 0.05)
    m15 = merge_close_lines(_lines([("low", 23059.45, "2026-10-16 11:10", True)], "15m"), 0.10)
    out = trading_ladder([m5, m15], 23062.25, 0.05)
    s1 = out[out["label"] == "S1"].iloc[0]
    assert s1["price"] == 23059.45 and s1["timeframes"] == "15m 5m"


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
    text = "\n".join([f"horizontal_sr unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
                     + results + ["", summary, f"exit status: {1 if failed else 0}"])
    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "horizontal_sr_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "horizontal_sr_unit_tests.log").write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(1 if failed else 0)
