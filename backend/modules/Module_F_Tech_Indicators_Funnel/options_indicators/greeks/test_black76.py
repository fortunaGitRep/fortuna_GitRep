"""Tests for black76 and the live check's comparison logic (no Upstox calls).
Run from backend/:  python -m pytest modules/Module_F_Tech_Indicators_Funnel/options_indicators/greeks -q"""

from datetime import date, datetime

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks import black76 as b
from modules.Module_F_Tech_Indicators_Funnel.options_indicators.greeks import live_greeks_check as lc

F, T, R = 25000.0, 3 / 365, 0.055
K = np.arange(24500, 25501, 50, dtype=float)


def test_put_call_parity():
    c = b.price(F, K, T, R, 0.14, True)
    p = b.price(F, K, T, R, 0.14, False)
    assert np.allclose(c - p, np.exp(-R * T) * (F - K), atol=1e-8)


def test_iv_round_trip_calls_and_puts():
    sig = np.linspace(0.08, 0.6, len(K))
    for call in (True, False):
        px = b.price(F, K, T, R, sig, call)
        assert np.allclose(b.implied_vol(px, F, K, T, R, call), sig, atol=1e-6)


def test_iv_nan_outside_no_arbitrage_and_at_expiry():
    df = np.exp(-R * T)
    assert np.isnan(b.implied_vol(df * 100 - 1, F, F - 100, T, R, True))     # below intrinsic
    assert np.isnan(b.implied_vol(50, F, F, 0.0, R, True))                    # expired
    assert np.isnan(b.implied_vol(0, F, F, T, R, True))


def test_greeks_match_finite_differences():
    sig, is_call = 0.15, np.array([True, False])
    k = np.array([25100.0, 24900.0])
    g = b.greeks(F, k, T, R, sig, is_call)
    S = F * np.exp(-R * T)
    pf = lambda s, sg=sig, t=T: b.price(s * np.exp(R * t), k, t, R, sg, is_call)   # noqa: E731
    h = 0.5
    assert np.allclose(g["delta"], (pf(S + h) - pf(S - h)) / (2 * h), atol=1e-5)
    assert np.allclose(g["gamma"], (pf(S + h) - 2 * pf(S) + pf(S - h)) / h ** 2, rtol=1e-3)
    assert np.allclose(g["vega"], (pf(S, sig + 5e-5) - pf(S, sig - 5e-5)) / 1e-4 / 100, rtol=1e-4)
    dt = 1 / 365 / 24
    pF = lambda t: b.price(F, k, t, R, sig, is_call)                                 # noqa: E731
    assert np.allclose(g["theta"], (pF(T - dt) - pF(T + dt)) / (2 * dt) / 365, rtol=1e-3)   # forward held
    assert 0 < g["delta"][0] < 1 and -1 < g["delta"][1] < 0
    atm = b.greeks(F, F, T, R, sig, np.array([True, False]))["theta"]
    assert abs(atm[0] - atm[1]) < 1e-9                                              # CE = PE at F


def test_forward_from_parity_recovers_forward():
    c, p = b.price(F, K, T, R, 0.13, True), b.price(F, K, T, R, 0.13, False)
    assert abs(b.forward_from_parity(K, c, p, 24990, T, R) - F) < 1e-6


def _fake_chain(at, expiry, spot, sigma):
    Tm = lc.years_to_expiry(at, expiry, "close")
    fwd = spot * np.exp(lc.REPO_RATE * Tm)
    rows = []
    for k in np.arange(spot - 600, spot + 601, 50).round(-1):
        for typ in ("CE", "PE"):
            px = float(b.price(fwd, k, Tm, lc.REPO_RATE, sigma, typ == "CE"))
            g = b.greeks(fwd, k, Tm, lc.REPO_RATE, sigma, typ == "CE")
            rows.append({"snapshot_at": at, "expiry": expiry.isoformat(), "spot": spot, "strike": k,
                         "option_type": typ, "instrument_key": f"{k}{typ}", "ltp": px, "bid": px - 0.05,
                         "ask": px + 0.05, "volume": 100, "oi": 1000, "prev_oi": 900, "u_iv": sigma * 100,
                         "u_delta": float(g["delta"]), "u_gamma": float(g["gamma"]), "u_theta": float(g["theta"]),
                         "u_vega": float(g["vega"]), "u_pop": 50})
    return pd.DataFrame(rows)


def test_live_check_recovers_upstox_when_conventions_match():
    at = datetime(2026, 10, 29, 13, 50, tzinfo=lc.IST)
    df = _fake_chain(at, date(2026, 11, 3), 25012.0, 0.14)
    rows, table = lc.check_snapshot(df, at)
    best = table.sort_values("iv_pts").iloc[0]
    assert best["iv_pts"] < 0.01 and best["delta"] < 1e-3
    assert abs(best["gamma_x"] - 1) < 1e-3 and abs(best["theta_x"] - 1) < 1e-3
    chosen = table[(table.underlying == "parity") & (table.expiry_time == "close") & (table.premium == "ltp")].iloc[0]
    assert chosen["iv_pts"] < 0.01                     # parity forward = spot carried at r here
    assert rows["in_scope"].sum() > 30
    assert (table["rows"] > 0).all()
    assert table.loc[table.expiry_time == "1530", "iv_pts"].min() > 0.001  # 10 min less T shows up
