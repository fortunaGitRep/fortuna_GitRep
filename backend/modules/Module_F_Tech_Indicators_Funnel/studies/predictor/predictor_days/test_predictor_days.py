"""Unit tests for predictor_days.py and the runner's pure parts -- hand-made data, no R2."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.predictor_days import (
    build_predictor_days, day_intraday, futures_volume, intraday_measures, narrow_range_prev,
    near_month, ordered, prior_average, to_5m,
)
from modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.futures_parity_check import (
    compare, report, show_lines,
)
from modules.Module_F_Tech_Indicators_Funnel.studies.predictor.predictor_days.predictor_days_run import (
    parity_lines, summary, viewer_data,
)

DAY = "2026-02-24"


def _five(day, closes, start="09:15", spread=1.0):
    ts = pd.date_range(f"{day} {start}", periods=len(closes), freq="5min", tz="Asia/Kolkata")
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame({"ts": ts, "trade_date": day, "open": opens, "close": closes,
                         "high": [max(o, c) + spread for o, c in zip(opens, closes)],
                         "low": [min(o, c) - spread for o, c in zip(opens, closes)]})


def _t(df):
    d = df.copy()
    d["t"] = pd.to_datetime(d["ts"]).dt.time
    return d


def test_first_hour_extension_and_first_break():
    closes = [100.0] * 12 + [100, 104, 108, 112] + [112] * 59          # IB = 09:15..10:10, flat at 100
    r = day_intraday(_t(_five(DAY, closes)), prev_close=90.0)
    assert (r["ib_high"], r["ib_low"], r["ib_width"]) == (101.0, 99.0, 2.0)
    assert r["first_break"] == "up" and r["first_break_time"] == "10:20"   # 10:15 bar closes 100 (high 101 = not above)
    assert r["ext_up_pts"] == pytest.approx(113 - 101) and r["ext_down_pts"] == 0.0
    assert r["first30_pts"] == pytest.approx(100 - 90)                      # close of the 09:40 bar vs prev close


def test_hour_blocks_and_no_break():
    closes = [100 + i * 0.01 for i in range(75)]
    b = _t(_five(DAY, closes))
    b.loc[0, "high"], b.loc[0, "low"] = 200.0, 0.0                          # first-hour range holds the whole day
    r = day_intraday(b, prev_close=None)
    assert r["first_break"] == "none" and r["ext_up_pts"] == 0.0
    assert r["h1_0915"] == pytest.approx(closes[11] - closes[0])            # first bar open = closes[0]
    assert r["h2_1015"] == pytest.approx(closes[23] - closes[11])           # 10:15 bar opens at previous close
    assert r["h6_1415"] == pytest.approx(closes[-1] - closes[59])
    assert np.isnan(r["first30_pts"])


def test_evening_only_session_is_blank():
    r = day_intraday(_t(_five("2024-11-01", [100.0] * 12, start="18:00")), prev_close=99.0)
    assert np.isnan(r["ib_width"]) and r["first_break"] == ""


def test_intraday_measures_progress_and_columns():
    seen = []
    f = pd.concat([_five("2026-02-23", [100.0] * 75), _five(DAY, [101.0] * 75)])
    out = intraday_measures(f, {date(2026, 2, 24): 100.0}, lambda i, n, d: seen.append((i, n)))
    assert list(out["trade_date"]) == [date(2026, 2, 23), date(2026, 2, 24)]
    assert seen == [(1, 2), (2, 2)]
    assert out.loc[1, "first30_pts"] == pytest.approx(1.0)


def test_prior_average_excludes_today():
    s = pd.Series([float(i) for i in range(25)])
    a = prior_average(s, 20)
    assert a.iloc[:20].isna().all()
    assert a.iloc[20] == pytest.approx(np.mean(range(20)))                  # days 0..19, not day 20


def test_prior_average_skips_blank_days():
    s = pd.Series([1.0] * 20 + [np.nan] + [3.0] * 5)
    a = prior_average(s, 20)
    assert np.isnan(a.iloc[20])                                              # the blank day itself
    assert a.iloc[21] == pytest.approx(1.0)                                  # previous 20 valid days, blank skipped
    assert a.iloc[22] == pytest.approx((19 * 1 + 3) / 20)                    # window slides over valid days only


def test_narrow_range_previous_day():
    d = pd.DataFrame({"high": [110, 108, 106, 103, 120, 110], "low": [100, 100, 100, 100, 100, 100]})
    nr4 = narrow_range_prev(d, 4)
    assert nr4.tolist() == [False, False, False, False, True, False]        # day 3 (range 3) narrowest of 4 -> flag on day 4


def test_near_month_and_futures_volume_first_hour():
    assert near_month(date(2026, 2, 24), [date(2026, 3, 30), date(2026, 2, 24)]) == date(2026, 2, 24)
    assert near_month(date(2026, 2, 25), [date(2026, 2, 24), date(2026, 3, 30)]) == date(2026, 3, 30)
    ts = pd.date_range(f"{DAY} 09:15", periods=375, freq="1min", tz="Asia/Kolkata")
    near = pd.DataFrame({"expiry": date(2026, 2, 24), "ts": ts, "trade_date": DAY, "volume": 10.0, "lot_size": 65})
    nxt = near.assign(expiry=date(2026, 3, 30), volume=99.0)
    v = futures_volume(pd.concat([near, nxt]), [date(2026, 2, 24), date(2026, 3, 30)])
    r = v.iloc[0]
    assert r["fut_expiry"] == date(2026, 2, 24)                             # near month only
    assert r["fut_vol_day"] == 3750 and r["fut_vol_ib"] == 600               # 60 one-minute bars before 10:15


def _small_world():
    days = [d.date() for d in pd.bdate_range("2026-01-01", periods=25)]
    daily = pd.DataFrame({"trade_date": days, "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0})
    table = daily.assign(prev_close=daily["close"].shift(1), colour="green", weekday="Mon", day_move_pts=5.0)
    intra = pd.DataFrame({"trade_date": days, "ib_high": 104.0, "ib_low": 100.0, "ib_width": [4.0] * 24 + [8.0],
                          "ext_up_pts": 6.0, "ext_down_pts": 0.0, "first_break": "up", "first_break_time": "10:30",
                          "first30_pts": 2.1, **{h: 1.0 for h in ["h1_0915", "h2_1015", "h3_1115", "h4_1215",
                                                                  "h5_1315", "h6_1415"]}})
    fut = pd.DataFrame({"trade_date": days, "fut_expiry": date(2026, 2, 24), "fut_lot_size": 65.0,
                        "fut_vol_day": [6500.0] * 24 + [13000.0], "fut_vol_ib": 650.0})
    return days, daily, table, intra, fut


def test_build_predictor_days_ratios_and_order():
    days, daily, table, intra, fut = _small_world()
    t = ordered(build_predictor_days(table, daily, intra, fut, start=days[0]))
    last = t.iloc[-1]
    assert last["ib_width_x"] == pytest.approx(2.0) and last["ext_up_x"] == pytest.approx(6 / 8)
    assert last["fut_vol_day_lots"] == pytest.approx(200) and last["fut_vol_day_x"] == pytest.approx(2.0)
    assert np.isnan(t.iloc[5]["ib_width_x"])                                 # not 20 days of history yet
    assert last["first30_pct"] == pytest.approx(100 * 2.1 / 105)
    assert list(t.columns[:3]) == ["trade_date", "weekday", "colour"]


def test_runner_viewer_summary_and_parity():
    days, daily, table, intra, fut = _small_world()
    t = ordered(build_predictor_days(table, daily, intra, fut, start=days[0]))
    five = pd.concat([_five(str(d), [100.0] * 75) for d in days[-2:]])
    ts = pd.date_range("2026-02-24 09:15", periods=30, freq="1min", tz="Asia/Kolkata")
    fut1 = pd.DataFrame({"expiry": date(2026, 2, 24), "ts": ts, "trade_date": "2026-02-24", "open": 1.0,
                         "high": 2.0, "low": 0.5, "close": 1.5, "volume": 130.0, "lot_size": 65,
                         "trading_symbol": "NIFTY FUT 24 FEB 26"})
    v = viewer_data(t, five, fut1, [date(2026, 2, 24)], days[0])
    assert len(v["days"]) == 25 and len(v["days"][-1]["bars"]) == 75
    assert v["days"][-1]["row"]["ib_width_x"] == 2.0
    lines = summary(t)
    assert any(l.startswith("days") and "25" in l for l in lines)
    p = parity_lines(fut1, [date(2026, 2, 24)])
    assert any("Tue 24 Feb 2026 09:30" in l and "volume 650 units = 10 lots" in l for l in p)
    assert any("no bars stored" in l for l in p)                             # 11:40 not in the 30 bars


def _one_min(day="2026-08-26", n=10):
    ts = pd.date_range(f"{day} 09:15", periods=n, freq="1min", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts, "open": [float(i) for i in range(n)], "high": [i + 0.5 for i in range(n)],
                         "low": [i - 0.5 for i in range(n)], "close": [i + 0.2 for i in range(n)],
                         "volume": [100.0] * n})


def test_to_5m_aggregates_like_upstox():
    f = to_5m(_one_min())
    assert f["ts"].dt.strftime("%H:%M").tolist() == ["09:15", "09:20"]
    r = f.iloc[1]
    assert (r["open"], r["high"], r["low"], r["close"], r["volume"]) == (5.0, 9.5, 4.5, 9.2, 500.0)
    assert f["trade_date"].iloc[0] == date(2026, 8, 26)


def test_parity_compare_report_and_chart_lines():
    ours = to_5m(_one_min())
    upstox = ours.copy()
    upstox.loc[1, "volume"] = 480.0                                          # one mismatch
    upstox = pd.concat([upstox, upstox.iloc[[0]].assign(ts=upstox["ts"].iloc[0] + pd.Timedelta(minutes=10))])
    m = compare(ours, upstox)
    lines = report(m)
    assert lines[0].startswith("candles: 2 in both, 0 only ours, 1 only Upstox")
    assert any(l.strip().startswith("volume  exact 1 / 2") and "largest gap 20.00" in l for l in lines)
    assert any(l.strip().startswith("close   exact 2 / 2") for l in lines)
    s = show_lines(m)
    assert any("Wed 26 Aug 2026 09:15" in l and "Vol 500" in l for l in s)
    assert any("not in the data" in l for l in s)
