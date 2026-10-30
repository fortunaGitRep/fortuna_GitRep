"""
Option pricing, implied volatility and Greeks for Nifty index options (European), vectorised.

Model: Black-76 on the forward F of the option's own expiry. Written in spot form with
S = F * exp(-r*T) and no dividend, so prices equal Black-76 and the Greeks are the usual
trader's (spot) Greeks:
  delta  per 1 point of underlying          (call 0..1, put -1..0)
  gamma  delta change per 1 point
  theta  premium change per calendar day with the FORWARD held still (Black-76 theta,
         Upstox's convention: pure time decay, near-equal for CE and PE at the same strike;
         negative for a long option)
  vega   premium change per 1 vol point     (IV 15% -> 16%)
  iv     annualised, as a fraction          (0.15 = 15%)

Inputs are numpy arrays or scalars (broadcast). T is in years (calendar time, /365).
Rows the model cannot price are NaN: T <= 0, price outside the no-arbitrage range
(below intrinsic value or above the forward / strike bound), non-positive inputs.

Forward: forward_from_parity() -- put-call parity at the strikes nearest the underlying
(F = K + (C - P) * exp(r*T)); avoids dividend guesses and the weekly-vs-futures expiry mismatch.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr

MINUTES_PER_YEAR = 365 * 24 * 60
IV_LOW, IV_HIGH = 1e-4, 5.0            # 0.01% .. 500% search range
IV_ITERATIONS = 60                     # bisection: (5 / 2^60) -> far below a paisa
_SQRT_2PI = np.sqrt(2 * np.pi)


def _pdf(x):
    return np.exp(-0.5 * x * x) / _SQRT_2PI


def _arr(*xs):
    return [np.asarray(x, dtype=float) for x in xs]


def _d1d2(S, K, T, r, sigma):
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sq
    return d1, d1 - sq


def price(F, K, T, r, sigma, is_call):
    """Black-76 premium. is_call: bool array/scalar."""
    F, K, T, r, sigma = _arr(F, K, T, r, sigma)
    is_call = np.asarray(is_call, dtype=bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        S = F * np.exp(-r * T)
        d1, d2 = _d1d2(S, K, T, r, sigma)
        df = np.exp(-r * T)
        call = S * ndtr(d1) - K * df * ndtr(d2)
        put = K * df * ndtr(-d2) - S * ndtr(-d1)
    out = np.where(is_call, call, put)
    return np.where((T > 0) & (sigma > 0) & (F > 0) & (K > 0), out, np.nan)


def implied_vol(premium, F, K, T, r, is_call):
    """IV (fraction) from the premium by bisection; NaN outside the no-arbitrage range."""
    premium, F, K, T, r = _arr(premium, F, K, T, r)
    is_call = np.asarray(is_call, dtype=bool)
    shape = np.broadcast(premium, F, K, T, r, is_call).shape
    premium, F, K, T, r, is_call = (np.broadcast_to(x, shape) for x in (premium, F, K, T, r, is_call))
    df = np.exp(-r * T)
    intrinsic = df * np.where(is_call, np.maximum(F - K, 0), np.maximum(K - F, 0))
    upper = df * np.where(is_call, F, K)
    ok = (T > 0) & (F > 0) & (K > 0) & (premium > intrinsic) & (premium < upper)
    lo = np.full(shape, IV_LOW)
    hi = np.full(shape, IV_HIGH)
    ok &= price(F, K, T, r, hi, is_call) > premium            # IV above 500%: give up
    for _ in range(IV_ITERATIONS):
        mid = 0.5 * (lo + hi)
        above = price(F, K, T, r, mid, is_call) > premium
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return np.where(ok, 0.5 * (lo + hi), np.nan)


def greeks(F, K, T, r, sigma, is_call) -> dict[str, np.ndarray]:
    """delta, gamma, theta (per calendar day), vega (per 1 vol point)."""
    F, K, T, r, sigma = _arr(F, K, T, r, sigma)
    is_call = np.asarray(is_call, dtype=bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        S = F * np.exp(-r * T)
        d1, d2 = _d1d2(S, K, T, r, sigma)
        df = np.exp(-r * T)
        sq = sigma * np.sqrt(T)
        pdf1 = _pdf(d1)
        delta = np.where(is_call, ndtr(d1), ndtr(d1) - 1.0)
        gamma = pdf1 / (S * sq)
        decay = -S * pdf1 * sigma / (2 * np.sqrt(T))
        prem = np.where(is_call, S * ndtr(d1) - K * df * ndtr(d2), K * df * ndtr(-d2) - S * ndtr(-d1))
        theta_y = decay + r * prem                        # d(premium)/dt at fixed F (Black-76)
        vega = S * pdf1 * np.sqrt(T) / 100.0
    bad = ~((T > 0) & (sigma > 0) & np.isfinite(sigma) & (F > 0) & (K > 0))
    out = {"delta": delta, "gamma": gamma, "theta": theta_y / 365.0, "vega": vega}
    return {k: np.where(bad, np.nan, v) for k, v in out.items()}


def forward_from_parity(strikes, call_prices, put_prices, underlying, T, r, n_nearest: int = 3) -> float:
    """Median of K + (C - P) * exp(rT) over the n strikes nearest the underlying that have both
    prices. NaN if none."""
    K, C, P = _arr(strikes, call_prices, put_prices)
    ok = np.isfinite(C) & np.isfinite(P) & (C > 0) & (P > 0)
    if not ok.any():
        return float("nan")
    K, C, P = K[ok], C[ok], P[ok]
    pick = np.argsort(np.abs(K - underlying))[:n_nearest]
    return float(np.median(K[pick] + (C[pick] - P[pick]) * np.exp(r * T)))
