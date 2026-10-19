"""
Unit tests for ema_sr_study.py (no R2 needed: a fake reader serves candles).

Run on their own (writes logs/studies_logs/ema_sr_study_unit_tests.log):
    python -m modules.Module_F_Tech_Indicators_Funnel.studies.ema_sr.test_ema_sr_study
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.studies.ema_sr.ema_sr_study import (
    _clear_bucket,
    _era,
    add_lines,
    control_summary,
    daily_lines_on_intraday,
    episodes_with_conditions,
    rates,
    run_study,
    shuffled_candles,
    split_table,
)

FREQ = {"1d": "B", "1w": "W-MON", "1mo": "MS", "60m": "60min", "15m": "15min", "5m": "5min"}


def _candles(n=400, seed=3, freq="B", start="2020-01-01", tz=None):
    rng = np.random.default_rng(seed)
    c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.concatenate([[c[0]], c[:-1]])
    t = pd.date_range(start, periods=n, freq=freq, tz=tz)
    return pd.DataFrame({"time": t, "trade_date": t.date, "open": o,
                         "high": np.maximum(o, c) * 1.003, "low": np.minimum(o, c) * 0.997, "close": c})


def test_shuffle_keeps_the_same_candles():
    c = _candles(200)
    s = shuffled_candles(c, seed=1)
    real = np.sort(c["close"].to_numpy()[1:] / c["close"].to_numpy()[:-1])
    shuf = np.sort(s["close"].to_numpy()[1:] / s["close"].to_numpy()[:-1])
    assert np.allclose(real, shuf)
    assert s["close"].iloc[0] == c["close"].iloc[0]
    assert (s["high"] >= s[["open", "close"]].max(axis=1) - 1e-9).all()
    assert (s["low"] <= s[["open", "close"]].min(axis=1) + 1e-9).all()


def test_shuffle_is_repeatable_and_differs_by_seed():
    c = _candles(200)
    a, b, d = shuffled_candles(c, 1), shuffled_candles(c, 1), shuffled_candles(c, 2)
    assert a.equals(b) and not a["close"].equals(d["close"])


def test_add_lines_columns():
    out = add_lines(_candles(300))
    for p in (5, 13, 20, 26, 50, 100, 200):
        assert f"ema_{p}" in out
    assert out["stage"].dropna().between(-5, 5).all()
    assert out["above_200"].iloc[-1] == (out["close"].iloc[-1] > out["ema_200"].iloc[-1])


def test_daily_line_uses_previous_day_only():
    daily = _candles(250, freq="B", start="2025-01-01")
    intra = _candles(75 * 3, freq="5min", start="2025-12-08 09:15")
    intra["trade_date"] = np.repeat(pd.to_datetime(["2025-12-08", "2025-12-09", "2025-12-10"]).date, 75)
    out = daily_lines_on_intraday(intra, daily)
    d = add_lines(daily).assign(day=pd.to_datetime(daily["trade_date"]))
    prev_of_9 = d[d["day"] < "2025-12-09"].iloc[-1]["ema_50"]
    got = out[pd.to_datetime(out["trade_date"]) == "2025-12-09"]["d_ema_50"].unique()
    assert len(got) == 1 and got[0] == prev_of_9
    assert len(out) == len(intra) and (out["time"].to_numpy() == intra["time"].to_numpy()).all()


def test_conditions_from_candle_before_touch():
    lined = add_lines(_candles(600))
    ep = episodes_with_conditions(lined, "ema_20", "wick", "stage")
    assert not ep.empty
    for col in ("with_trend", "stage", "above_200", "era", "clear_bucket"):
        assert col in ep
    for _, e in ep.iterrows():
        i = lined.index[lined["time"] == e["start_time"]][0]
        before = lined.iloc[i - 1]
        st = before["stage"]
        assert e["stage"] == st or (pd.isna(e["stage"]) and pd.isna(st))
        if pd.isna(st) or st == 0:
            assert pd.isna(e["with_trend"])
        else:
            expected = st > 0 if e["side"] == "support" else st < 0
            assert bool(e["with_trend"]) == bool(expected)
        assert bool(e["above_200"]) == bool(before["above_200"]) or pd.isna(e["above_200"])


def test_against_trend_is_not_a_built_in_zero():
    # Old bugs: slope on the touch candle forced 0% bounce against the trend; slope on
    # the candle before made every episode "with trend". The stack stage must give both.
    lined = add_lines(_candles(6000, seed=11))
    ep = episodes_with_conditions(lined, "ema_50", "wick", "stage")
    done = ep[ep["outcome"].isin(["bounce", "break"])]
    against = done[done["with_trend"] == False]
    with_t = done[done["with_trend"] == True]
    assert len(against) > 30 and len(with_t) > 30
    assert 0 < (against["outcome"] == "bounce").mean() < 1


def test_conditions_work_with_timezone_aware_times():
    lined = add_lines(_candles(600, tz="Asia/Kolkata"))
    assert not episodes_with_conditions(lined, "ema_20", "wick", "stage").empty


def test_rates_and_split_table():
    ep = pd.DataFrame({"outcome": ["bounce", "bounce", "break", "open"], "side": ["support", "resistance", "support", "support"]})
    assert rates(ep) == {"n": 3, "bounce_pct": 66.7, "break_pct": 33.3}
    t = split_table(ep, "side").set_index("side")
    assert t.loc["support", "n"] == 2 and t.loc["support", "bounce_pct"] == 50.0


def test_control_summary_and_split_with_control():
    c = _candles(600)
    ctrl = [episodes_with_conditions(add_lines(shuffled_candles(c, s)), "ema_20", "wick", "stage")
            for s in range(3)]
    r = control_summary(ctrl)
    assert r["ctrl_min"] <= r["ctrl_bounce_pct"] <= r["ctrl_max"] and r["ctrl_n"] > 0
    real = episodes_with_conditions(add_lines(c), "ema_20", "wick", "stage")
    t = split_table(real, "side", ctrl)
    for col in ("ctrl_n_per_run", "ctrl_bounce_pct", "edge_pts"):
        assert col in t
    pooled = pd.concat(ctrl)
    sup = pooled[(pooled["side"] == "support") & pooled["outcome"].isin(["bounce", "break"])]
    expect = round(100.0 * int((sup["outcome"] == "bounce").sum()) / len(sup), 1)
    assert t.set_index("side").loc["support", "ctrl_bounce_pct"] == expect


def test_progress_messages_are_sent():
    msgs = []
    def reader(key, domain, tf):
        return SimpleNamespace(ok=True, df=_candles(300).rename(columns={"time": "ts"}), error=None)
    run_study(reader, "X", ["1d"], shuffles=1, progress=msgs.append)
    assert msgs[0].startswith("1d: read 300 candles")
    assert any("EMA 200" in m and "control 1/1 done" in m for m in msgs)
    assert msgs[-1].startswith("all done")


def test_buckets_and_eras():
    assert [_clear_bucket(n) for n in (1, 4, 5, 19, 20, 99)] == ["1-4", "1-4", "5-19", "5-19", "20+", "20+"]
    assert [_era(y) for y in (2000, 2012, 2013, 2019, 2020, 2026)] == \
        ["2000-2012", "2000-2012", "2013-2019", "2013-2019", "2020-2026", "2020-2026"]


def test_run_study_end_to_end_with_fake_reader():
    def reader(key, domain, tf):
        n = 300 if tf in ("1d", "1w", "1mo") else 600
        c = _candles(n, freq=FREQ[tf], start="2024-01-01")
        return SimpleNamespace(ok=True, df=c.rename(columns={"time": "ts"}), error=None)
    eps, lines = run_study(reader, "X", ["1d", "60m"], shuffles=2)
    assert not eps.empty
    assert set(eps["timeframe"]) == {"1d", "60m"}
    assert any(l.startswith("daily EMA") for l in eps["line"].unique())
    assert lines[0].startswith("SUMMARY")


def test_run_study_reports_failed_timeframe():
    def reader(key, domain, tf):
        if tf == "5m":
            return SimpleNamespace(ok=False, df=None, error="no 5m file")
        return SimpleNamespace(ok=True, df=_candles(300).rename(columns={"time": "ts"}), error=None)
    _, lines = run_study(reader, "X", ["1d", "5m"], shuffles=1)
    assert any("5m: NOT OK -- no 5m file" in l for l in lines)


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
    text = "\n".join([f"ema_sr_study unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
                     + results + ["", summary, f"exit status: {1 if failed else 0}"])
    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "studies_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ema_sr_study_unit_tests.log").write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(1 if failed else 0)
