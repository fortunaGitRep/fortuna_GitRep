"""archive_greeks on a synthetic band priced with known IV and a moving forward (no R2).
Run from backend/:  python -m pytest modules/Module_F_Tech_Indicators_Funnel/options_indicators -q"""

from datetime import date

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks import archive_greeks as ag
from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks import black76 as b

EXPIRY = date(2026, 11, 3)
IV = 0.13


def synthetic_band(drop_minute=None):
    rows = []
    for d in ("2026-11-02", "2026-11-03"):
        ts = pd.date_range(f"{d} 09:15", f"{d} 15:39", freq="1min", tz="Asia/Kolkata")
        F = 22900 + 60 * np.sin(np.arange(len(ts)) / 40)
        T = ag.minutes_to_expiry(pd.Series(ts), EXPIRY) / b.MINUTES_PER_YEAR
        for k in range(22450, 23351, 50):
            for typ in ("CE", "PE"):
                px = b.price(F, k, T, ag.REPO_RATE, IV, typ == "CE")
                px = np.where(np.isnan(px), np.maximum((F - k) if typ == "CE" else (k - F), 0.05), px)  # last bar
                df = pd.DataFrame({"ts": ts, "close": np.round(px, 2), "strike": float(k), "option_type": typ,
                                   "instrument_key": f"{k}{typ}", "volume": 10,
                                   "oi": 1000 + np.arange(len(ts)) + (0 if d == "2026-11-02" else 5000)})
                rows.append(df[df["close"] > 0.05])
    band = pd.concat(rows, ignore_index=True)
    band["trade_date"] = band["ts"].dt.date
    band["expiry"] = EXPIRY
    if drop_minute is not None:
        band = band[band["ts"] != drop_minute]
    return band, F


def test_recovers_known_iv_and_forward():
    band, _ = synthetic_band()
    g = ag.compute_expiry(band, EXPIRY)
    early = g[(g["trade_date"] == date(2026, 11, 2)) & (g["otm_steps"].abs() <= 3)]
    assert early["iv"].notna().mean() > 0.99
    assert (early["iv"] - IV * 100).abs().median() < 0.2          # rounding of prices to 0.05
    q = ag.quality(g)
    assert q["iv_cover"] > 0.95 and q["ce_pe_gap"] < 0.2


def test_forward_matches_truth_and_otm_steps_sign():
    band, _ = synthetic_band()
    g = ag.compute_expiry(band, EXPIRY)
    row = g[(g["strike"] == 23000) & (g["option_type"] == "CE")].iloc[0]
    assert abs(row["forward"] - 22900) < 1.0                       # first minute: sin(0) = 0
    pe = g[(g["strike"] == 23000) & (g["option_type"] == "PE")].iloc[0]
    assert row["otm_steps"] > 1.9 and pe["otm_steps"] < -1.9


def test_final_minute_blank_and_oi_changes():
    band, _ = synthetic_band()
    g = ag.compute_expiry(band, EXPIRY)
    last = g[g["ts"] == g["ts"].max()]
    assert last["t_minutes"].eq(0).all() and last["iv"].isna().all()
    c = g[g["instrument_key"] == "22900CE"].sort_values("ts")
    assert c["oi_chg_1m"].iloc[1] == 1
    day2 = c[c["trade_date"] == date(2026, 11, 3)].iloc[0]
    assert day2["oi_chg_day"] == 1000 + 5000 - (1000 + len(c[c["trade_date"] == date(2026, 11, 2)]) - 1)


def test_missing_minute_carries_forward():
    gone = pd.Timestamp("2026-11-02 10:00", tz="Asia/Kolkata")
    band, _ = synthetic_band()
    keep = band[(band["ts"] != gone) | (band["strike"] == 22900)]   # only one strike trades at 10:00
    keep = keep[~((keep["ts"] == gone) & (keep["option_type"] == "PE"))]
    g = ag.compute_expiry(keep, EXPIRY)
    assert g.loc[g["ts"] == gone, "forward"].notna().all()           # carried from 09:59
