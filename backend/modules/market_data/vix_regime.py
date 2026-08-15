"""
modules/market_data/vix_regime.py

VIX percentile + volatility-regime decision logic. This feeds PRE-1's
DECISION role only (regime / trade-no-trade / size / confidence) -- it does
NOT produce a direction. Direction from VIX (as a confirmation-only input
alongside price) belongs to Stage 5, built separately.

Design, fact-checked against the Perplexity VIX brief and Fortuna v0.9/v3:
  - Percentile is computed over TWO windows: 252-day (primary regime) and
    63-day (recent-change / shock detection). This is the standard and the
    brief's recommendation.
  - "Exclude today" is handled correctly: today's VIX is ranked against the
    N closes that came BEFORE it, never against a set that includes itself
    (the pseudocode's "prior observations only" rule).
  - Mid-rank tie handling: (count_below + 0.5*count_equal)/N -- the standard
    mean-rank percentile convention.
  - Graceful under-window handling: we backfilled ~250 days, so the 252
    window may have slightly fewer than 252 priors early on. The calc ranks
    against whatever priors exist and reports the actual count used, rather
    than assuming a full window.
  - Regime bands are on the 252 PERCENTILE, not raw VIX level -- percentile
    self-calibrates to India VIX's own history, avoiding US-VIX absolute
    thresholds (<12/>20) that don't transfer.
  - VIX is a GATE here: direction_weight is structurally 0 (v0.9/v3 PRE-1
    rule). Output is regime, GO/NO-GO, size guidance, confidence multiplier.

Standards applied: single responsibility (VIX decision only, no direction),
pure functions (percentile calc is testable in isolation), defensive
(handles empty/short history), typed result, no hidden magic numbers
(thresholds are named constants).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Optional

from .index_store import get_recent_closes

logger = logging.getLogger(__name__)

VIX_INDEX_KEY = "INDIA_VIX"

# Percentile windows (trading days). 252 = ~1yr primary regime; 63 = recent
# shock detection. Per the VIX brief and standard practice.
WINDOW_PRIMARY = 252
WINDOW_RECENT = 63

# Regime bands on the 252-day percentile (NOT raw VIX). Per the brief:
# >=90 extreme, >=75 high/elevated, <=25 calm, else normal.
PCTL_EXTREME = 90.0
PCTL_HIGH = 75.0
PCTL_LOW = 25.0

# Recent-acceleration warning: 63-day percentile unusually hot AND meaningfully
# above the 252 (volatility rising fast relative to the year).
RECENT_WARN_PCTL = 80.0
RECENT_WARN_GAP = 10.0

# Minimum priors required to produce a trustworthy percentile. Below this we
# flag low confidence rather than emit a confident regime off thin history.
MIN_PRIORS_FOR_CONFIDENCE = 40


class VolRegime(str, Enum):
    LOW = "low"          # calm
    NORMAL = "normal"
    HIGH = "high"        # elevated
    EXTREME = "extreme"  # stress/panic
    UNKNOWN = "unknown"  # insufficient history


@dataclass
class VixDecision:
    """PRE-1's individual DECISION verdict (no direction).

    `latest_close_vix` is the most recent COMPLETED daily VIX close (i.e. the
    prior session's close at a pre-market ~08:45 IST run) -- NOT a live
    intraday value. Fortuna evaluates the regime it's about to trade into from
    the last settled close; intraday live-VIX mode was deliberately dropped
    (other gates handle in-session decisions; live VIX would add noise, not
    decision quality).
    """
    latest_close_vix: Optional[float]
    percentile_252: Optional[float]
    percentile_63: Optional[float]
    priors_252_used: int
    priors_63_used: int
    regime: VolRegime
    recent_volatility_stress: bool     # 63d hot vs 252d -- current value unusual recently vs annually
                                       # (cross-sectional, NOT a time-change; see note in evaluate)
    go_no_go: str                      # "GO" | "NO_GO"
    size_guidance: str                 # e.g. "normal", "50-75% of normal"
    confidence_mult: float             # PRE-1's contribution to cascade confidence
    direction_weight: float = 0.0      # structurally 0 -- VIX never votes direction here
    notes: list[str] = field(default_factory=list)


def calculate_percentile(current_value: float, prior_values: list[float]) -> Optional[float]:
    """
    Percentile of `current_value` within `prior_values` (which must exclude
    the current observation). Mid-rank tie handling. Returns 0-100, or None if
    there are no priors to rank against.
    """
    n = len(prior_values)
    if n == 0:
        return None
    count_below = sum(1 for v in prior_values if v < current_value)
    count_equal = sum(1 for v in prior_values if v == current_value)
    return ((count_below + 0.5 * count_equal) / n) * 100.0


def _regime_from_percentile(pctl_252: Optional[float]) -> VolRegime:
    if pctl_252 is None:
        return VolRegime.UNKNOWN
    if pctl_252 >= PCTL_EXTREME:
        return VolRegime.EXTREME
    if pctl_252 >= PCTL_HIGH:
        return VolRegime.HIGH
    if pctl_252 <= PCTL_LOW:
        return VolRegime.LOW
    return VolRegime.NORMAL


def _size_and_confidence(regime: VolRegime) -> tuple[str, float]:
    """Map regime to position-size guidance + PRE-1's confidence multiplier.
    Mirrors v0.9 PRE-1: 1.2 when calm, <1.0 when elevated."""
    return {
        VolRegime.LOW:     ("normal", 1.2),
        VolRegime.NORMAL:  ("normal", 1.0),
        VolRegime.HIGH:    ("50-75% of normal", 0.8),
        VolRegime.EXTREME: ("25-50% of normal", 0.5),
        VolRegime.UNKNOWN: ("reduced (insufficient VIX history)", 0.8),
    }[regime]


def evaluate_vix_decision() -> VixDecision:
    """
    Full PRE-1 decision pass, pre-market mode. Reads stored India VIX closes,
    ranks the latest COMPLETED close against prior completed closes over both
    windows, classifies the regime, and emits a decision verdict (GO/NO-GO,
    size, confidence). No direction.

    "Latest completed close" = the prior session's VIX close at an ~08:45 IST
    pre-market run. This is the regime we're about to trade into.
    """
    notes: list[str] = []

    def _no_data(msg: str, size_msg: str) -> VixDecision:
        return VixDecision(
            latest_close_vix=None, percentile_252=None, percentile_63=None,
            priors_252_used=0, priors_63_used=0, regime=VolRegime.UNKNOWN,
            recent_volatility_stress=False, go_no_go="NO_GO",
            size_guidance=size_msg, confidence_mult=0.5, notes=[msg],
        )

    # Pull the larger window PLUS one (the latest close to rank + its priors).
    raw = get_recent_closes(VIX_INDEX_KEY, WINDOW_PRIMARY + 1)
    if not raw:
        logger.error("evaluate_vix_decision: no VIX closes stored.")
        return _no_data("No VIX history available; cannot assess regime.",
                        "no trade -- no VIX data")

    # Validate: drop anything non-finite / non-positive. VIX is always > 0.
    closes = [float(v) for v in raw
              if v is not None and isfinite(float(v)) and float(v) > 0]
    if not closes:
        logger.error("evaluate_vix_decision: no VALID VIX closes after filtering.")
        return _no_data("No valid VIX observations available.",
                        "no trade -- invalid VIX data")
    if len(closes) < len(raw):
        notes.append(f"Dropped {len(raw) - len(closes)} invalid VIX value(s) before ranking.")

    # get_recent_closes contracts oldest-first; last element is the latest close.
    latest_close = closes[-1]
    priors_all = closes[:-1]

    priors_252 = priors_all[-WINDOW_PRIMARY:]
    priors_63 = priors_all[-WINDOW_RECENT:]

    pctl_252 = calculate_percentile(latest_close, priors_252)
    pctl_63 = calculate_percentile(latest_close, priors_63)

    # Thin-history guard: below the minimum, a percentile off few priors is
    # unreliable -- do NOT emit a confident regime. Set UNKNOWN.
    if len(priors_252) < MIN_PRIORS_FOR_CONFIDENCE:
        regime = VolRegime.UNKNOWN
        notes.append(
            f"Only {len(priors_252)} prior VIX observations "
            f"(<{MIN_PRIORS_FOR_CONFIDENCE}); regime set to UNKNOWN until more history accumulates."
        )
    else:
        regime = _regime_from_percentile(pctl_252)

    # recent_volatility_stress: the latest value ranks hot on the 63d window AND
    # well above its 252d rank. NOTE: this is CROSS-SECTIONAL (same value vs two
    # windows), not a time-change -- it flags "unusual recently vs annually",
    # not "VIX rising over N days". A true acceleration flag (multi-day % change)
    # is a future enhancement.
    recent_volatility_stress = (
        pctl_63 is not None and pctl_252 is not None
        and pctl_63 >= RECENT_WARN_PCTL
        and pctl_63 > pctl_252 + RECENT_WARN_GAP
    )
    if recent_volatility_stress:
        notes.append(
            f"Recent volatility stress: 63d pctl {pctl_63:.0f} vs 252d {pctl_252:.0f}."
        )

    size_guidance, confidence_mult = _size_and_confidence(regime)

    # GO/NO-GO: EXTREME or UNKNOWN -> PRE-1 votes caution/NO-GO. LOW/NORMAL/HIGH -> GO.
    if regime in (VolRegime.EXTREME, VolRegime.UNKNOWN):
        go_no_go = "NO_GO"
        reason = "Extreme volatility" if regime == VolRegime.EXTREME else "Regime unknown (thin history)"
        notes.append(f"{reason}: PRE-1 votes NO-GO / minimal size.")
    else:
        go_no_go = "GO"

    return VixDecision(
        latest_close_vix=latest_close,
        percentile_252=pctl_252,
        percentile_63=pctl_63,
        priors_252_used=len(priors_252),
        priors_63_used=len(priors_63),
        regime=regime,
        recent_volatility_stress=recent_volatility_stress,
        go_no_go=go_no_go,
        size_guidance=size_guidance,
        confidence_mult=confidence_mult,
        direction_weight=0.0,  # structural: VIX never votes direction (v0.9/v3 PRE-1)
        notes=notes,
    )
