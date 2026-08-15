"""
Fortuna — Module_F_Global_Gate_Funnel — deterministic_modules.py

Pure functions, no AI, no network calls. Ported directly from
Fortuna_Funnel_Pseudocode_v3_with_Nifty.md Sections 1-4 (MAC-1..3, NAT-1,
FLO-1..2, PRE-1..5), aligned with the v3 corrections doc and the v0.9
Corrections Log.

Every threshold below is a named constant at the top so they're easy to
tune later against your own backtests — none of them are hard-coded inline.

IMPORTANT (per the 12-Aug-2026 Corrections Log): PRE-2's implied gap must
be basis-adjusted. Never diff GIFT's raw quoted level against the cash
close directly.
"""

from __future__ import annotations
from datetime import date, time, datetime
from typing import Optional

from .schemas import ModuleOutput, Direction

# ---------------------------------------------------------------------------
# Tunable thresholds — review these against real backtests before trusting them
# ---------------------------------------------------------------------------

VIX_LOW_PCTL = 25.0
VIX_HIGH_PCTL = 75.0
VIX_TURBULENT_PCTL = 90.0

GIFT_GAP_NOISE_PCT = 0.002    # <0.2%
GIFT_GAP_LARGE_PCT = 0.005    # >0.5%
GIFT_DECAY_CUTOFF = time(10, 0)

# Standing GIFT-to-cash carry premium (interest-rate differential).
# TODO(open item): this is currently a static estimate. The v0.9/v3 docs
# call for netting out "the standing GIFT-to-cash carry premium (interest-rate
# differential, routinely 50-100+ points)" but don't specify a formula.
# Replace with a computed value (e.g. from GIFT futures vs spot cost-of-carry)
# once available — flagging as an open item rather than guessing further.
GIFT_CARRY_PREMIUM_POINTS_DEFAULT = 75.0

CPR_NARROW_THRESHOLD_PTS = 35.0
CPR_WIDE_THRESHOLD_PTS = 60.0

TINY_GAP_THRESHOLD_PCT = 0.001  # <0.1% treated as effectively no gap

ADX_TREND_MIN = 25.0
CHOP_TREND_MAX = 38.2
CHOP_REGIME_MIN = 61.8
ADX_CHOP_MIN = 20.0


# ---------------------------------------------------------------------------
# Stage 1 · Macro Scan
# ---------------------------------------------------------------------------

def MAC_1(shock_detected: bool, shock_description: Optional[str] = None) -> ModuleOutput:
    """Global Macro News. shock_detected comes from the AI judgment layer —
    a GENUINE new Fed/geopolitical/commodity shock, not a stale overhang."""
    if shock_detected:
        return ModuleOutput(
            module_id="MAC-1", signal="event_shock",
            direction_weight=0.4, context_weight=0.6, confidence_mult=0.8,
            bias=Direction.UNKNOWN,  # direction sign must come from the AI description, not assumed
            notes=shock_description,
        )
    return ModuleOutput(
        module_id="MAC-1", signal="neutral",
        direction_weight=0.0, context_weight=0.3, confidence_mult=1.0,
        bias=Direction.UNKNOWN,
    )


def MAC_2(
    us_close_direction: Direction,
    asia_direction: Direction,
    gift_gap_direction: Direction,
    gift_gap_pct: float,
    vix_in_normal_band: bool,
    time_of_day_ist: time,
) -> ModuleOutput:
    """US/Asia correlation + GIFT cue. Open-window only, decays to 0 by ~10:00."""
    aligned_cues = (us_close_direction == asia_direction == gift_gap_direction
                     and us_close_direction != Direction.UNKNOWN)
    before_decay = time_of_day_ist < GIFT_DECAY_CUTOFF

    if before_decay and aligned_cues and vix_in_normal_band and abs(gift_gap_pct) >= GIFT_GAP_NOISE_PCT:
        return ModuleOutput(
            module_id="MAC-2", signal="aligned_open_bias",
            direction_weight=0.5, context_weight=0.6, confidence_mult=1.1,
            bias=us_close_direction,
        )
    return ModuleOutput(
        module_id="MAC-2", signal="decayed_or_contradictory",
        direction_weight=0.0, context_weight=0.3, confidence_mult=1.0,
        bias=Direction.UNKNOWN,
    )


def MAC_3(dxy_risk_off: bool, us10y_risk_off: bool) -> ModuleOutput:
    """Macro levels (DXY/US10Y/crude/gold). Swing-horizon only; intraday must
    ignore this direction_weight entirely (enforced by the aggregator, not here)."""
    if dxy_risk_off or us10y_risk_off:
        return ModuleOutput(
            module_id="MAC-3", signal="risk_off_swing_bias",
            direction_weight=0.4, context_weight=0.5, confidence_mult=0.9,
            bias=Direction.DOWN,
        )
    return ModuleOutput(
        module_id="MAC-3", signal="neutral_swing_background",
        direction_weight=0.1, context_weight=0.4, confidence_mult=1.0,
        bias=Direction.UNKNOWN,
    )


# ---------------------------------------------------------------------------
# Stage 2 · National News
# ---------------------------------------------------------------------------

def NAT_1(event_today: bool, surprise_flag: bool, surprise_description: Optional[str] = None) -> ModuleOutput:
    if event_today:
        if surprise_flag:
            return ModuleOutput(
                module_id="NAT-1", signal="event_surprise",
                direction_weight=0.3, context_weight=0.8, confidence_mult=0.7,
                bias=Direction.UNKNOWN, notes=surprise_description,
            )
        return ModuleOutput(
            module_id="NAT-1", signal="scheduled_event",
            direction_weight=0.0, context_weight=0.9, confidence_mult=0.6,
            bias=Direction.UNKNOWN,
        )
    return ModuleOutput(
        module_id="NAT-1", signal="no_event",
        direction_weight=0.0, context_weight=0.2, confidence_mult=1.0,
        bias=Direction.UNKNOWN,
    )


# ---------------------------------------------------------------------------
# Stage 3 · Institutional Flows
# ---------------------------------------------------------------------------

def FLO_1(fii_net_cr: float, dii_net_cr: float, rolling_trend_strong: bool) -> ModuleOutput:
    """FII/DII cash flow. Always net(FII+DII) — never FII alone.
    direction_weight is hard-zero for same-day use per the v0.9 correction;
    the non-zero direction_weight here represents next-day/swing bias only,
    and must never be applied to an intraday call."""
    total_net = fii_net_cr + dii_net_cr

    if rolling_trend_strong and total_net > 0:
        return ModuleOutput(
            module_id="FLO-1", signal="supportive_flows",
            direction_weight=0.2, context_weight=0.5, confidence_mult=1.1,
            bias=Direction.UP, notes="next-day/swing bias only, not same-day",
        )
    if rolling_trend_strong and total_net < 0:
        return ModuleOutput(
            module_id="FLO-1", signal="pressure_flows",
            direction_weight=0.2, context_weight=0.5, confidence_mult=0.9,
            bias=Direction.DOWN, notes="next-day/swing bias only, not same-day",
        )
    return ModuleOutput(
        module_id="FLO-1", signal="noisy_or_offset_flows",
        direction_weight=0.0, context_weight=0.3, confidence_mult=1.0,
        bias=Direction.UNKNOWN,
    )


def FLO_2(retail_vs_fii_divergence: bool, flo1_signal: str) -> ModuleOutput:
    if retail_vs_fii_divergence and flo1_signal in ("supportive_flows", "pressure_flows"):
        return ModuleOutput(
            module_id="FLO-2", signal="trap_signal",
            direction_weight=0.2, context_weight=0.5, confidence_mult=1.2,
            bias=Direction.UNKNOWN, notes="confirmation only, cross-check hedge vs bet",
        )
    return ModuleOutput(
        module_id="FLO-2", signal="neutral_intent",
        direction_weight=0.0, context_weight=0.3, confidence_mult=1.0,
        bias=Direction.UNKNOWN,
    )


# ---------------------------------------------------------------------------
# Stage 4 · Pre-market Gates
# ---------------------------------------------------------------------------

def PRE_1(vix_percentile: float) -> ModuleOutput:
    if vix_percentile < VIX_LOW_PCTL:
        return ModuleOutput(module_id="PRE-1", signal="calm",
                             direction_weight=0.0, context_weight=0.8, confidence_mult=1.2)
    if vix_percentile < VIX_HIGH_PCTL:
        return ModuleOutput(module_id="PRE-1", signal="normal",
                             direction_weight=0.0, context_weight=0.8, confidence_mult=1.0)
    if vix_percentile < VIX_TURBULENT_PCTL:
        return ModuleOutput(module_id="PRE-1", signal="elevated",
                             direction_weight=0.0, context_weight=0.9, confidence_mult=0.8)
    return ModuleOutput(module_id="PRE-1", signal="turbulent",
                         direction_weight=0.0, context_weight=1.0, confidence_mult=0.5)


def compute_basis_adjusted_gap_pct(
    gift_raw_level: float,
    prev_cash_close: float,
    carry_premium_points: float = GIFT_CARRY_PREMIUM_POINTS_DEFAULT,
) -> float:
    """
    THE fix from the 12-Aug-2026 Corrections Log.
    implied_gap = (GIFT - prev_cash_close - carry_premium) / prev_cash_close
    Never subtract GIFT's raw quoted level from the prior cash close directly.
    """
    adjusted_gift = gift_raw_level - carry_premium_points
    return (adjusted_gift - prev_cash_close) / prev_cash_close


def PRE_2(gift_gap_pct: float, time_of_day_ist: time, is_domestic_event: bool) -> ModuleOutput:
    """gift_gap_pct MUST already be basis-adjusted — see compute_basis_adjusted_gap_pct()."""
    if is_domestic_event:
        return ModuleOutput(module_id="PRE-2", signal="event_morning_context_only",
                             direction_weight=0.0, context_weight=0.5, confidence_mult=1.0)

    before_decay = time_of_day_ist < GIFT_DECAY_CUTOFF
    bias = Direction.UP if gift_gap_pct > 0 else (Direction.DOWN if gift_gap_pct < 0 else Direction.FLAT)

    if abs(gift_gap_pct) < GIFT_GAP_NOISE_PCT:
        return ModuleOutput(module_id="PRE-2", signal="small_gap_noise",
                             direction_weight=0.0, context_weight=0.3, confidence_mult=1.0, bias=Direction.UNKNOWN)
    if abs(gift_gap_pct) < GIFT_GAP_LARGE_PCT:
        return ModuleOutput(module_id="PRE-2", signal="moderate_gap_bias",
                             direction_weight=0.5 if before_decay else 0.0,
                             context_weight=0.6, confidence_mult=1.1, bias=bias)
    return ModuleOutput(module_id="PRE-2", signal="large_gap_bias",
                         direction_weight=0.7 if before_decay else 0.0,
                         context_weight=0.7, confidence_mult=1.2, bias=bias)


def PRE_3(
    actual_gap_pct: float,
    atr_normalized_gap: Optional[float],
    trend_alignment: Optional[str],  # "bull" | "bear" | None — Stage-5 input, may be unavailable
    vix_signal: str,
    news_flag: bool,
    live_overhang_active: bool,
) -> ModuleOutput:
    """
    Gap Up/Down Behaviour classifier.
    NOTE: atr_normalized_gap / trend_alignment are Stage-5 (ENG) derived. If
    Module_F_Tech_Indicators_Funnel hasn't run yet, pass None — this
    function degrades gracefully to "uncertain" rather than guessing.
    A live macro overhang (per v0.9/v3) excludes a Runaway classification
    even absent a scheduled news event.
    """
    def _aligned_runaway() -> bool:
        if atr_normalized_gap is None or trend_alignment is None:
            return False
        return (atr_normalized_gap > 1.0 and trend_alignment in ("bull", "bear")
                and vix_signal in ("calm", "normal") and not news_flag and not live_overhang_active)

    def _genuine_breakaway() -> bool:
        return news_flag and not live_overhang_active

    def _exhaustion_gap() -> bool:
        if atr_normalized_gap is None:
            return False
        return atr_normalized_gap > 1.5 and vix_signal in ("elevated", "turbulent")

    if abs(actual_gap_pct) < TINY_GAP_THRESHOLD_PCT:
        return ModuleOutput(module_id="PRE-3", signal="common_tiny:sit_out_open",
                             direction_weight=0.1, context_weight=0.4, confidence_mult=1.0)
    if _aligned_runaway():
        return ModuleOutput(module_id="PRE-3", signal="runaway:trade_with_gap",
                             direction_weight=0.4, context_weight=0.6, confidence_mult=1.1)
    if _genuine_breakaway():
        return ModuleOutput(module_id="PRE-3", signal="breakaway:trade_with_gap_all_day",
                             direction_weight=0.5, context_weight=0.7, confidence_mult=1.2)
    if _exhaustion_gap():
        return ModuleOutput(module_id="PRE-3", signal="exhaustion:fade_after_rollover",
                             direction_weight=0.3, context_weight=0.7, confidence_mult=1.0)
    # live overhang during a moderate gap-up: reduced confidence, not a clean runaway (v0.9 correction)
    conf = 0.8 if live_overhang_active else 0.9
    return ModuleOutput(module_id="PRE-3", signal="uncertain:wait",
                         direction_weight=0.0, context_weight=0.5, confidence_mult=conf)


def compute_cpr(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Standard CPR: Pivot, BC, TC. Returns points + width."""
    pivot = (prev_high + prev_low + prev_close) / 3.0
    bc = (prev_high + prev_low) / 2.0
    tc = (pivot - bc) + pivot
    width = abs(tc - bc)
    return {"pivot": pivot, "bc": min(bc, tc), "tc": max(bc, tc), "width_pts": width}


def PRE_4(
    cpr_width_points: float,
    price_vs_cpr: str,  # "above_TC" | "below_BC" | "inside"
    ema_bias: Optional[str],
    rsi_bias: Optional[str],
    vwap_bias: Optional[str],
) -> ModuleOutput:
    if cpr_width_points < CPR_NARROW_THRESHOLD_PTS:
        width_signal, width_ctx = "narrow_trend_possible", 0.7
    elif cpr_width_points > CPR_WIDE_THRESHOLD_PTS:
        width_signal, width_ctx = "wide_range_day", 0.7
    else:
        width_signal, width_ctx = "normal", 0.5

    aligned_bull = ema_bias == rsi_bias == vwap_bias == "bull"
    aligned_bear = ema_bias == rsi_bias == vwap_bias == "bear"

    if price_vs_cpr == "above_TC" and aligned_bull:
        loc_dw, loc_signal, bias = 0.2, "bull_bias_zone", Direction.UP
    elif price_vs_cpr == "below_BC" and aligned_bear:
        loc_dw, loc_signal, bias = 0.2, "bear_bias_zone", Direction.DOWN
    else:
        loc_dw, loc_signal, bias = 0.0, "indecision_zone", Direction.UNKNOWN

    return ModuleOutput(
        module_id="PRE-4", signal=f"{width_signal} | {loc_signal}",
        direction_weight=loc_dw, context_weight=width_ctx, confidence_mult=1.0, bias=bias,
    )


def PRE_5(weekday: str, is_expiry_pm: bool) -> ModuleOutput:
    table = {
        "Mon": ("pressure_cooker_mon", 0.8, 0.9),
        "Wed": ("Wed_post_expiry_drift", 0.7, 0.9),
        "Thu": ("Thu_Sensex_expiry_spill", 0.7, 1.0),
        "Fri": ("Fri_pre_weekend_theta", 0.7, 1.0),
    }
    if weekday == "Tue":
        if is_expiry_pm:
            return ModuleOutput(module_id="PRE-5", signal="Tue_expiry_PM_pin",
                                 direction_weight=0.0, context_weight=0.9, confidence_mult=0.8)
        return ModuleOutput(module_id="PRE-5", signal="Tue_expiry_AM_tradeable",
                             direction_weight=0.0, context_weight=0.8, confidence_mult=1.1)
    if weekday in table:
        signal, ctx, conf = table[weekday]
        return ModuleOutput(module_id="PRE-5", signal=signal,
                             direction_weight=0.0, context_weight=ctx, confidence_mult=conf)
    # Weekend / unknown — should not be called, but fail safe rather than crash
    return ModuleOutput(module_id="PRE-5", signal="non_trading_day",
                         direction_weight=0.0, context_weight=0.0, confidence_mult=0.0)


# ---------------------------------------------------------------------------
# Calendar helper — hard-coded per v3 §7. TODO(open item): re-check NSE
# circular for holiday shifts weekly rather than trusting this blindly.
# ---------------------------------------------------------------------------

NIFTY_WEEKLY_EXPIRY_WEEKDAY = "Tue"


def get_weekday_and_expiry_flag(run_date: date, now_ist: time) -> tuple[str, bool]:
    weekday = run_date.strftime("%a")[:3]  # "Mon", "Tue", ...
    is_expiry_day = weekday == NIFTY_WEEKLY_EXPIRY_WEEKDAY
    # "PM pin" defined as post-noon on expiry day
    is_expiry_pm = is_expiry_day and now_ist >= time(12, 0)
    return weekday, is_expiry_pm
