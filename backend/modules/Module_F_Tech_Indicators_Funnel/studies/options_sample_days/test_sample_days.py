"""Unit tests for sample_days.py -- hand-made data, no R2."""

from datetime import date

import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.studies.options_sample_days.sample_days import (
    build_day_table, daily_labels, expiry_calendar, intraday_profile, phase_by_day,
    coverage_report, pick_candidates,
)


def _daily(rows):
    return pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close"])


# ---- TC-SEL-01 / 02 / TC-NB-04
def test_strong_boundary_and_colour():
    d = daily_labels(_daily([
        ("2025-09-01", 100, 110, 100, 106),      # body 6/10 = 0.60 -> strong green
        ("2025-09-02", 106, 116, 106, 111.99),   # 5.99/10 -> not strong
        ("2025-09-03", 112, 112, 112, 112),      # zero range -> not strong, no error
        ("2025-09-04", 112, 120, 100, 100.5),    # red, 11.5/20 -> not strong
        ("2025-09-05", 100, 101, 90, 91),        # red 9/11 -> strong
    ]))
    assert d["strong"].tolist() == [True, False, False, False, True]
    assert d["colour"].tolist() == ["green", "green", "doji", "red", "red"]


def test_gap_types():
    d = daily_labels(_daily([
        ("2025-09-01", 100, 105, 95, 100),
        ("2025-09-02", 106, 107, 104, 105),      # open above prev high -> full_up
        ("2025-09-03", 105.2, 106, 104, 105),    # +0.19% -> up
        ("2025-09-04", 105.05, 106, 104, 105),   # +0.05% -> none
        ("2025-09-05", 104.5, 105, 103, 104),    # -0.48%, inside prev range -> down
        ("2025-09-08", 102, 103, 101, 102),      # below prev low -> full_down
    ]))
    assert pd.isna(d["gap_type"].iloc[0])                      # no previous close
    assert d["gap_type"].tolist()[1:] == ["full_up", "up", "none", "down", "full_down"]


# ---- TC-DATA-02
def test_expiry_thursday_era_and_changeover():
    days = pd.bdate_range("2025-08-20", "2025-09-16")
    e = expiry_calendar(days, start=date(2025, 8, 20)).set_index("trade_date")
    assert e.loc[date(2025, 8, 22), "expiry_date"] == date(2025, 8, 28)   # Fri -> Thu 28 Aug
    assert e.loc[date(2025, 8, 22), "dte"] == 4                          # Fri, Mon, Tue, Wed, Thu
    assert e.loc[date(2025, 8, 28), "era"] == "thu"
    assert e.loc[date(2025, 8, 29), "expiry_date"] == date(2025, 9, 2)   # changeover week
    assert e.loc[date(2025, 9, 2), "dte"] == 0
    assert e.loc[date(2025, 9, 2), "era"] == "tue"
    assert not e["holiday_shifted"].any()


def test_expiry_first_tuesday_week():
    days = pd.bdate_range("2025-09-01", "2025-09-16")
    e = expiry_calendar(days, start=date(2025, 9, 3)).set_index("trade_date")
    assert e.index.min() == date(2025, 9, 3)                              # before start ignored
    assert e.loc[date(2025, 9, 3), "expiry_date"] == date(2025, 9, 9)
    assert e.loc[date(2025, 9, 3), "dte"] == 4                # Wed 3, Thu, Fri, Mon, Tue 9
    assert e.loc[date(2025, 9, 9), "dte"] == 0
    assert e.loc[date(2025, 9, 10), "expiry_date"] == date(2025, 9, 16)


def test_expiry_full_week_wed_is_5():
    days = pd.bdate_range("2025-09-10", "2025-09-16")       # Wed 10 .. Tue 16
    e = expiry_calendar(days, start=date(2025, 9, 10)).set_index("trade_date")
    assert e["dte"].tolist() == [4, 3, 2, 1, 0]


def test_expiry_holiday_tuesday_moves_to_monday():
    days = [d for d in pd.bdate_range("2026-10-14", "2026-10-21") if d.date() != date(2026, 10, 20)]
    e = expiry_calendar(days, start=date(2026, 10, 14)).set_index("trade_date")
    assert e.loc[date(2026, 10, 19), "expiry_date"] == date(2026, 10, 19)
    assert e.loc[date(2026, 10, 19), "dte"] == 0
    assert bool(e.loc[date(2026, 10, 19), "holiday_shifted"])
    assert e.loc[date(2026, 10, 21), "expiry_date"] == date(2026, 10, 27)


def test_expiry_beyond_data_is_assumed():
    days = pd.bdate_range("2026-10-21", "2026-10-26")       # Wed..Mon, Tue 27 not in data
    e = expiry_calendar(days, start=date(2026, 10, 21)).set_index("trade_date")
    assert bool(e.loc[date(2026, 10, 26), "expiry_assumed"])
    assert e.loc[date(2026, 10, 26), "dte"] == 1
    assert e.loc[date(2026, 10, 21), "dte"] == 4


# ---- TC-SEL-04
def _sw(rows):
    return pd.DataFrame(rows, columns=["kind", "price", "pivot_time", "locked_time", "is_locked"])


def test_phase_markup_then_distribution_no_lookahead():
    sw = _sw([
        ("low", 100, "2025-01-01", "2025-01-05", True),
        ("high", 120, "2025-02-01", "2025-02-05", True),
        ("low", 110, "2025-03-01", "2025-03-05", True),
        ("high", 130, "2025-04-01", "2025-04-05", True),   # HH + HL -> markup from 5 Apr
        ("low", 105, "2025-05-01", "2025-05-05", True),    # HH + LL -> distribution from 5 May
        ("high", 140, "2025-06-01", "2025-06-05", False),  # not locked: ignored
    ])
    p = phase_by_day(pd.to_datetime(["2025-04-04", "2025-04-05", "2025-05-05", "2025-06-10"]),
                     sw, 0.5).set_index("trade_date")["phase"]
    assert pd.isna(p[date(2025, 4, 4)])                    # only one high locked yet
    assert p[date(2025, 4, 5)] == "markup"
    assert p[date(2025, 5, 5)] == "distribution"
    assert p[date(2025, 6, 10)] == "distribution"


def test_phase_markdown_then_accumulation_and_equal():
    sw = _sw([
        ("high", 200, "2025-01-01", "2025-01-05", True),
        ("low", 180, "2025-02-01", "2025-02-05", True),
        ("high", 190, "2025-03-01", "2025-03-05", True),
        ("low", 170, "2025-04-01", "2025-04-05", True),    # LH + LL -> markdown
        ("high", 190.5, "2025-05-01", "2025-05-05", True), # equal high (0.26%) -> range
    ])
    p = phase_by_day(pd.to_datetime(["2025-04-06", "2025-05-06"]), sw, 0.5).set_index("trade_date")
    assert p.loc[date(2025, 4, 6), "phase"] == "markdown"
    assert p.loc[date(2025, 5, 6), "phase"] == "accumulation"
    assert p.loc[date(2025, 5, 6), "phase_basis"] == "EQH+LL"


# ---- TC-NB-01 / 03
def _five(day, closes, opens=None, start="09:15"):
    ts = pd.date_range(f"{day} {start}", periods=len(closes), freq="5min", tz="Asia/Kolkata")
    opens = opens or [closes[0]] + closes[:-1]
    return pd.DataFrame({"ts": ts, "trade_date": day, "open": opens,
                         "high": [max(o, c) for o, c in zip(opens, closes)],
                         "low": [min(o, c) for o, c in zip(opens, closes)], "close": closes})


def test_timing_morning_all_day_late():
    n = 75                                    # 09:15 .. 15:25
    k = 27                                    # bars before 11:30
    morning = [100 + 0.4 * min(i, k) for i in range(n)]
    late = [100] * k + [100 + 0.3 * (i - k) for i in range(k, n)]
    even = [100 + 0.2 * i for i in range(n)]
    f = pd.concat([_five("2025-09-03", morning), _five("2025-09-04", late), _five("2025-09-05", even)])
    p = intraday_profile(f).set_index("trade_date")["move_timing"]
    assert p.tolist() == ["morning", "late", "all_day"]


def test_window_move_from_0930():
    closes = [100, 101, 102, 103, 104] + [105] * 70     # 09:30 bar is index 3
    p = intraday_profile(_five("2025-09-03", closes)).iloc[0]
    assert p["window_move_pts"] == pytest.approx(105 - 102)


# ---- TC-SEL-03 / 05 / 06
def test_candidates_cover_each_cell_with_strongest():
    days = pd.DataFrame({
        "trade_date": [date(2025, 9, d) for d in (3, 4, 5, 8)],
        "month": ["2025-09"] * 4, "phase": ["markup", "markup", "markdown", "markdown"],
        "dte": [4, 3, 2, 1], "era": ["tue"] * 4, "colour": ["green", "green", "red", "red"],
        "strong": [True, True, True, False], "body_ratio": [0.7, 0.9, 0.65, 0.4],
    })
    c = pick_candidates(days)
    assert list(c["trade_date"]) == [date(2025, 9, 3), date(2025, 9, 4), date(2025, 9, 5)]
    assert "month=2025-09/green" in c.loc[c["trade_date"] == date(2025, 9, 4), "covers"].iloc[0]


def test_build_day_table_runs_end_to_end():
    daily = _daily([(f"2025-09-{d:02d}", 100, 110, 100, 107) for d in (1, 2, 3, 4)])
    five = pd.concat([_five(f"2025-09-{d:02d}", [100 + i * 0.1 for i in range(75)]) for d in (3, 4)])
    sw = _sw([("low", 90, "2025-01-01", "2025-01-02", True)])
    t = build_day_table(daily, five, sw, 0.5, start=date(2025, 9, 3))
    assert list(t["trade_date"]) == [date(2025, 9, 3), date(2025, 9, 4)]
    assert t["event"].isna().all()


def test_dte_coverage_uses_tuesday_era_only():
    days = pd.DataFrame({
        "trade_date": [date(2024, 5, 2), date(2025, 9, 4)],
        "month": ["2024-05", "2025-09"], "phase": ["markup", "markup"],
        "dte": [0, 3], "era": ["thu", "tue"], "colour": ["green", "green"],
        "strong": [True, True], "body_ratio": [0.95, 0.7],
    })
    c = pick_candidates(days).set_index("trade_date")["covers"]
    assert "dte" not in c[date(2024, 5, 2)]               # Thursday-era day: month/phase only
    assert "dte=3/green" in c[date(2025, 9, 4)]
    lines = coverage_report(days, pick_candidates(days))
    dte_rows = [l for l in lines if l.strip().split(" ")[0] in ("0", "3")]
    assert [l.strip()[0] for l in dte_rows] == ["3"]       # dte 0 (Thursday era) not listed


def test_phase_memory_uses_history_before_start():
    daily = _daily([("2025-01-02", 100, 101, 99, 100)] + [(f"2025-09-{d:02d}", 100, 110, 100, 107) for d in (3, 4)])
    sw = _sw([
        ("high", 200, "2024-01-01", "2024-01-05", True), ("low", 180, "2024-02-01", "2024-02-05", True),
        ("high", 190, "2024-03-01", "2024-03-05", True), ("low", 170, "2024-04-01", "2024-04-05", True),
        ("high", 195, "2025-08-01", "2025-08-05", True),     # LH -> HH? 195 > 190: HH + LL -> range
    ])
    five = _five("2025-09-03", [100 + i * 0.1 for i in range(75)])
    t = build_day_table(daily, five, sw, 0.5, start=date(2025, 9, 3))
    assert t["phase"].tolist() == ["accumulation", "accumulation"]   # markdown remembered from 2024


def test_extra_picks_expiry_days_and_window_against_colour():
    days = pd.DataFrame({
        "trade_date": [date(2026, 6, d) for d in (2, 9, 10, 11, 12)],
        "month": ["2026-06"] * 5, "phase": ["markdown"] * 5,
        "dte": [0, 0, 4, 3, 2], "era": ["tue"] * 5,
        "colour": ["red", "red", "green", "red", "green"],
        "strong": [True, True, True, True, False],
        "body_ratio": [0.9, 0.7, 0.8, 0.75, 0.9],
        "window_move_pts": [-50, -20, 30, 40, -10],
    })
    c = pick_candidates(days).set_index("trade_date")["covers"]
    assert "TC-CB-06 expiry day" in c[date(2026, 6, 9)]        # second expiry day kept too
    assert "TC-CB-04 window against colour" in c[date(2026, 6, 11)]   # red day, window up
    assert date(2026, 6, 12) not in c.index                    # not strong
    assert "TC-CB-04" not in c[date(2026, 6, 10)]              # green day, window up
