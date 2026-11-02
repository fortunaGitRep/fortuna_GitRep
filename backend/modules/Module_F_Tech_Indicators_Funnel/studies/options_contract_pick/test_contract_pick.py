"""Unit tests for contract_pick.py -- hand-made data, no R2."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from modules.Module_F_Tech_Indicators_Funnel.studies.options_contract_pick.contract_pick import (
    atm_strike, build, contract_stats, ladder, reading_notes, session_vwap, to_5m, write_outputs,
)

DAY = "2025-01-02"


def _bars(prices, start="09:15", day=DAY, lows=None, highs=None, volume=750, oi=7500):
    """1m bars; open = previous close (first open = first price)."""
    ts = pd.date_range(f"{day} {start}", periods=len(prices), freq="1min", tz="Asia/Kolkata")
    opens = [prices[0]] + prices[:-1]
    return pd.DataFrame({
        "ts": ts, "open": opens, "close": prices,
        "high": highs or [max(o, c) for o, c in zip(opens, prices)],
        "low": lows or [min(o, c) for o, c in zip(opens, prices)],
        "volume": volume, "oi": oi,
    })


def _day_prices(at_0930=100.0):
    """09:15..15:29 (375 bars): flat to 09:30, dips to 90 by 09:40, rallies to 200 at 13:00, 150 after."""
    p = [at_0930] * 15                                   # 09:15..09:29 close at 100
    p += list(np.linspace(at_0930, 90, 11))[1:]          # 09:30..09:39 -> 90
    p += list(np.linspace(90, 200, 201))[1:]             # 09:40..12:59 -> 200
    p += [150.0] * (375 - len(p))
    return [float(x) for x in p]


def test_atm_and_ladder_ce_pe():
    assert atm_strike(23_812.4) == 23_800
    assert atm_strike(23_826) == 23_850
    ce = ladder(23_800, "CE")
    assert ce[0] == ("ITM 4", 23_600) and ce[4] == ("ATM", 23_800) and ce[-1] == ("OTM 4", 24_000)
    pe = ladder(23_800, "PE")
    assert pe[0] == ("ITM 4", 24_000) and pe[-1] == ("OTM 4", 23_600)
    assert len(ce) == len(pe) == 9


def test_entry_high_dip_and_exit_prices():
    s = contract_stats(_bars(_day_prices()), lot_size=75, capital=100_000)
    assert s["entry_0930"] == pytest.approx(100.0)       # open of the 09:30 bar
    assert s["entry_time"] == "09:30"
    assert s["high"] == pytest.approx(200.0) and s["high_time"] == "12:59"
    assert s["move_pts"] == pytest.approx(100.0) and s["move_pct"] == pytest.approx(100.0)
    assert s["dip_pts"] == pytest.approx(10.0) and s["dip_pct"] == pytest.approx(10.0)
    assert s["p_1130"] == pytest.approx(_day_prices()[134])   # close of the 11:29 bar
    assert s["p_1510"] == pytest.approx(150.0)


def test_lots_cash_and_profit_with_one_lakh():
    s = contract_stats(_bars(_day_prices()), lot_size=75, capital=100_000)
    assert s["lot_cost"] == pytest.approx(7_500)          # 100 x 75
    assert s["lots"] == 13 and s["cash_left"] == pytest.approx(2_500)
    assert s["profit_high"] == pytest.approx(13 * 75 * 100)
    assert s["profit_1510"] == pytest.approx(13 * 75 * 50)
    assert s["volume_0930_lots"] == pytest.approx(10) and s["oi_0930_lots"] == pytest.approx(100)


def test_high_after_exit_is_ignored_and_no_dip_when_never_below_entry():
    p = [100.0] * 15 + [100 + i for i in range(1, 341)] + [999.0] * 20     # 09:15 + 355 bars = 15:10 spike
    s = contract_stats(_bars(p), lot_size=75)
    assert s["high"] == pytest.approx(440.0) and s["high_time"] == "15:09"
    assert s["dip_pts"] == 0.0


def test_missing_0930_bar_uses_next_bar_and_no_lot_size_leaves_rupees_blank():
    b = _bars(_day_prices())
    b = b[b["ts"].dt.strftime("%H:%M") != "09:30"]
    s = contract_stats(b, lot_size=None)
    assert s["entry_time"] == "09:31"
    assert np.isnan(s["lot_cost"]) and np.isnan(s["profit_high"])


def test_empty_contract_gives_blanks():
    s = contract_stats(_bars([100.0]).iloc[0:0], lot_size=75)
    assert np.isnan(s["entry_0930"]) and s["high_time"] == ""


def test_reading_notes():
    assert "Expiry day" in reading_notes(date(2025, 1, 2), date(2025, 1, 2))[0]
    assert "weekend" in reading_notes(date(2025, 3, 7), date(2025, 3, 13))[0]     # Friday
    assert reading_notes(date(2025, 3, 11), date(2025, 3, 13)) == []               # Tuesday


def test_build_end_to_end(tmp_path):
    rows = []
    for strike in range(23_550, 24_101, 50):
        b = _bars(_day_prices(max(5.0, 23_800 - strike + 100)))
        rows.append(b.assign(strike=float(strike), option_type="CE", trade_date=date(2025, 1, 2),
                             trading_symbol=f"NIFTY {strike} CE", lot_size=75))
    band = pd.concat(rows, ignore_index=True)
    greeks = band[["ts", "trade_date", "strike", "option_type"]].assign(delta=0.5, theta=-10.0, iv=15.0)
    n5 = pd.DataFrame({"ts": pd.date_range(f"{DAY} 09:15", periods=75, freq="5min", tz="Asia/Kolkata"),
                       "trade_date": date(2025, 1, 2), "open": 23_810.0, "high": 23_820.0,
                       "low": 23_800.0, "close": 23_815.0})
    table, meta = build(date(2025, 1, 2), "CE", 100_000, band, greeks, n5, date(2025, 1, 2))
    assert meta["atm"] == 23_800
    assert table["strike"].tolist() == [float(k) for k in range(23_600, 24_001, 50)]
    assert table.loc[table["position"] == "ATM", "entry_0930"].iloc[0] == pytest.approx(100.0)
    assert table["iv_0930"].tolist() == [15.0] * 9
    assert len(meta["legs"][0]["b1"]) == 375 and len(meta["legs"][0]["b5"]) == 75
    assert meta["legs"][0]["b5"][0][7] is not None                # VWAP on the first 5m bar
    csv_path, html_path = write_outputs(table, meta, tmp_path)
    assert csv_path.exists() and "Expiry day" in html_path.read_text(encoding="utf-8")


def test_session_vwap_hlc3_and_5m_bars():
    b = pd.DataFrame({"ts": pd.date_range(f"{DAY} 09:15", periods=6, freq="1min", tz="Asia/Kolkata"),
                      "open": [10, 11, 12, 13, 14, 15.0], "high": [12, 13, 14, 15, 16, 17.0],
                      "low": [9, 10, 11, 12, 13, 14.0], "close": [11, 12, 13, 14, 15, 16.0],
                      "volume": [100, 0, 300, 200, 100, 50], "oi": [1, 2, 3, 4, 5, 6]})
    v = session_vwap(b)
    tp = (b["high"] + b["low"] + b["close"]) / 3                  # 10.667, 11.667, 12.667, ...
    assert v.iloc[0] == pytest.approx(tp.iloc[0])
    assert v.iloc[1] == pytest.approx(tp.iloc[0])                 # zero-volume bar keeps the VWAP
    assert v.iloc[2] == pytest.approx((tp.iloc[0] * 100 + tp.iloc[2] * 300) / 400)
    f = to_5m(b)
    assert len(f) == 2 and f["ts"].dt.strftime("%H:%M").tolist() == ["09:15", "09:20"]
    r = f.iloc[0]
    assert (r["open"], r["high"], r["low"], r["close"], r["volume"], r["oi"]) == (10, 16, 9, 15, 700, 5)
    v5 = session_vwap(f)                                          # TradingView: VWAP of the 5m bars
    assert v5.iloc[0] == pytest.approx((16 + 9 + 15) / 3)


def test_session_vwap_no_volume_yet_is_blank():
    b = pd.DataFrame({"ts": pd.date_range(f"{DAY} 09:15", periods=2, freq="1min", tz="Asia/Kolkata"),
                      "high": [2.0, 3.0], "low": [1.0, 1.0], "close": [1.5, 2.0], "volume": [0, 10]})
    v = session_vwap(b)
    assert np.isnan(v.iloc[0]) and v.iloc[1] == pytest.approx(2.0)
