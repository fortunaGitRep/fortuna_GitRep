"""
modules/market_data/upstox/test_indicator_ohlcv_reader.py

Unit tests for indicator_ohlcv_reader.read_for_indicators(). Runs WITHOUT R2:
ohlcv_store.read_candles is replaced by a fake via monkeypatch, so these tests
never touch the network, Supabase or the ledger.

Run from backend/:
    python -m pytest modules/market_data/upstox/test_indicator_ohlcv_reader.py -v

Covers: normal read + reader rule 1, sort order, missing file, no bars for the
timeframe, R2/network failure, missing R2 config, missing column, every bar
invalid, unsupported timeframe refused, repeat runs, the log line written per
outcome, and (intraday) reader rule 2: after-close bars dropped, Muhurat
evening session kept, naive timestamps, wrong-domain hint.
"""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from modules.market_data.upstox import indicator_ohlcv_reader as reader

KEY = "NSE_INDEX|Nifty 50"
DOMAIN = "indices"
_COLS = ["timeframe", "ts", "trade_date", "open", "high", "low", "close",
         "volume", "open_interest"]


def _bar(day: str, o: float, h: float, l: float, c: float) -> list:
    return ["1d", pd.Timestamp(day, tz="Asia/Kolkata"), day, o, h, l, c, 0, 0]


@pytest.fixture
def bars() -> pd.DataFrame:
    """Three daily bars, stored newest-first, one with zero prices."""
    return pd.DataFrame([
        _bar("2026-10-07", 10, 11, 9, 10.5),
        _bar("2026-10-06", 9, 10, 8, 9.5),
        _bar("2026-10-05", 0, 0, 0, 0),
    ], columns=_COLS)


def _fake_store(monkeypatch, result=None, raises: Exception | None = None):
    def fake_read_candles(instrument_key, domain, timeframe=None):
        if raises is not None:
            raise raises
        return result
    monkeypatch.setattr(reader, "read_candles", fake_read_candles)


# --- Success path -----------------------------------------------------------

def test_normal_read_drops_zero_bar_and_sorts(monkeypatch, bars):
    _fake_store(monkeypatch, result=bars)
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert res.ok
    assert res.rows_read == 3
    assert res.rows_dropped == 1
    assert list(res.df["trade_date"]) == ["2026-10-06", "2026-10-07"]
    assert list(res.df.columns) == ["ts", "trade_date", "open", "high", "low",
                                    "close", "volume"]
    assert res.last_trade_date == "2026-10-07"
    assert res.error is None


def test_repeat_runs_give_same_result(monkeypatch, bars):
    _fake_store(monkeypatch, result=bars)
    results = [reader.read_for_indicators(KEY, DOMAIN) for _ in range(5)]
    assert all(r.ok for r in results)
    assert all(r.df.equals(results[0].df) for r in results)


def test_input_frame_not_modified(monkeypatch, bars):
    original = bars.copy()
    _fake_store(monkeypatch, result=bars)
    reader.read_for_indicators(KEY, DOMAIN)
    assert bars.equals(original)


# --- Expected misses: ok=False, never raises --------------------------------

def test_file_missing(monkeypatch):
    _fake_store(monkeypatch, result=None)
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert not res.ok
    assert "no OHLCV file in R2" in res.error


def test_no_bars_for_timeframe(monkeypatch, bars):
    _fake_store(monkeypatch, result=bars.iloc[0:0])
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert not res.ok
    assert "no '1d' bars" in res.error


def test_missing_column(monkeypatch, bars):
    _fake_store(monkeypatch, result=bars.drop(columns=["volume"]))
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert not res.ok
    assert "volume" in res.error


def test_every_bar_invalid(monkeypatch, bars):
    _fake_store(monkeypatch, result=bars.iloc[[2]])
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert not res.ok
    assert "nothing usable" in res.error
    assert res.rows_read == 1


def test_unsupported_timeframe_refused_without_reading(monkeypatch):
    _fake_store(monkeypatch, raises=AssertionError("store must not be called"))
    res = reader.read_for_indicators(KEY, DOMAIN, timeframe="4h")
    assert not res.ok
    assert "not supported" in res.error


# --- Unexpected failures: still ok=False, never raises ----------------------

def test_r2_or_network_failure(monkeypatch):
    _fake_store(monkeypatch, raises=ConnectionError("endpoint unreachable"))
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert not res.ok
    assert "ConnectionError" in res.error


def test_missing_r2_config(monkeypatch):
    _fake_store(monkeypatch,
                raises=RuntimeError("Missing required R2 env var(s): R2_BUCKET"))
    res = reader.read_for_indicators(KEY, DOMAIN)
    assert not res.ok
    assert "R2_BUCKET" in res.error


# --- Logging: one line per outcome, right level -----------------------------

def _reader_records(caplog):
    return [r for r in caplog.records if r.name == reader.__name__]


def test_log_success_is_one_info_line(monkeypatch, bars, caplog):
    _fake_store(monkeypatch, result=bars.iloc[:2])   # no bad bars
    with caplog.at_level(logging.DEBUG, logger=reader.__name__):
        reader.read_for_indicators(KEY, DOMAIN)
    recs = _reader_records(caplog)
    assert [r.levelname for r in recs] == ["INFO"]
    assert "read ok" in recs[0].getMessage()


def test_log_expected_miss_is_one_warning(monkeypatch, caplog):
    _fake_store(monkeypatch, result=None)
    with caplog.at_level(logging.DEBUG, logger=reader.__name__):
        reader.read_for_indicators(KEY, DOMAIN)
    assert [r.levelname for r in _reader_records(caplog)] == ["WARNING"]


def test_log_failure_is_one_error_with_traceback(monkeypatch, caplog):
    _fake_store(monkeypatch, raises=ConnectionError("endpoint unreachable"))
    with caplog.at_level(logging.DEBUG, logger=reader.__name__):
        reader.read_for_indicators(KEY, DOMAIN)
    recs = _reader_records(caplog)
    assert [r.levelname for r in recs] == ["ERROR"]
    assert recs[0].exc_info is not None


# --- Intraday + reader rule 2 ------------------------------------------------

IDOMAIN = "universe_intraday"


def _ibar(stamp: str, c: float, tf: str = "5m", tz: str | None = "Asia/Kolkata") -> list:
    ts = pd.Timestamp(stamp, tz=tz) if tz else pd.Timestamp(stamp)
    return [tf, ts, stamp[:10], c, c, c, c, 0, 0]


@pytest.fixture
def intraday() -> pd.DataFrame:
    """Two regular days (one with bad after-close bars) and a Muhurat evening."""
    return pd.DataFrame([
        _ibar("2024-03-28 15:25", 101),
        _ibar("2024-03-28 15:30", 999),     # rule 2: drop
        _ibar("2024-03-28 15:35", 999),     # rule 2: drop
        _ibar("2024-03-28 09:15", 100),
        _ibar("2024-11-01 18:00", 200),     # Muhurat: evening-only day, keep
        _ibar("2024-11-01 18:05", 201),     # keep
        _ibar("2026-10-09 15:25", 300),
        _ibar("2026-10-09 15:20", 299),
    ], columns=_COLS)


def test_rule2_drops_after_close_bars_and_keeps_muhurat(monkeypatch, intraday):
    _fake_store(monkeypatch, result=intraday)
    res = reader.read_for_indicators(KEY, IDOMAIN, timeframe="5m")
    assert res.ok
    assert res.rows_read == 8
    assert res.rows_dropped == 0
    assert res.rows_dropped_after_close == 2
    assert res.days_after_close == 1
    assert 999 not in set(res.df["close"])
    assert list(res.df["close"]) == [100, 101, 200, 201, 299, 300]   # sorted by ts
    assert res.last_trade_date == "2026-10-09"
    assert res.last_ts.startswith("2026-10-09 15:25")


def test_rule2_handles_fixed_offset_and_naive_timestamps(monkeypatch):
    fixed = pd.DataFrame([
        ["15m", pd.Timestamp("2024-03-28 15:15+05:30"), "2024-03-28", 1, 1, 1, 1, 0, 0],
        ["15m", pd.Timestamp("2024-03-28 15:30+05:30"), "2024-03-28", 2, 2, 2, 2, 0, 0],
    ], columns=_COLS)
    _fake_store(monkeypatch, result=fixed)
    assert reader.read_for_indicators(KEY, IDOMAIN, "15m").rows_dropped_after_close == 1

    naive = pd.DataFrame([_ibar("2024-03-28 15:15", 1, "60m", tz=None),
                          _ibar("2024-03-28 15:30", 2, "60m", tz=None)], columns=_COLS)
    _fake_store(monkeypatch, result=naive)
    res = reader.read_for_indicators(KEY, IDOMAIN, "60m")
    assert res.ok and res.rows_dropped_after_close == 1


def test_rule2_not_applied_to_daily(monkeypatch):
    daily = pd.DataFrame([_ibar("2024-03-28 15:30", 5, "1d")], columns=_COLS)
    _fake_store(monkeypatch, result=daily)
    res = reader.read_for_indicators(KEY, DOMAIN, "1d")
    assert res.ok and res.rows_dropped_after_close == 0 and len(res.df) == 1


def test_intraday_wrong_domain_gives_hint(monkeypatch):
    _fake_store(monkeypatch, result=None)
    res = reader.read_for_indicators(KEY, "indices", "5m")
    assert not res.ok
    assert "universe_intraday" in res.error


def test_rule2_bad_timestamps_not_ok_never_raises(monkeypatch, intraday):
    bad = intraday.copy()
    bad["ts"] = "not a time"
    _fake_store(monkeypatch, result=bad)
    res = reader.read_for_indicators(KEY, IDOMAIN, "5m")
    assert not res.ok
    assert "bar times" in res.error


def test_log_rule2_success(monkeypatch, intraday, caplog):
    _fake_store(monkeypatch, result=intraday)
    with caplog.at_level(logging.DEBUG, logger=reader.__name__):
        reader.read_for_indicators(KEY, IDOMAIN, "5m")
    recs = _reader_records(caplog)
    assert [r.levelname for r in recs] == ["INFO", "INFO"]
    assert "Reader rule 2" in recs[0].getMessage()
    assert "read ok" in recs[1].getMessage()
