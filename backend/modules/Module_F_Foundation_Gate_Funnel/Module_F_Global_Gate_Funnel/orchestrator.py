"""
Fortuna — Module_F_Global_Gate_Funnel — orchestrator.py

Entry point: run_stage1_to_4(). Wires together:
  - Dhan-sourced data (VIX, Nifty OHLC)         -> deterministic math
  - Claude+web_search snapshot (ai_gateway.py)  -> deterministic math
  - Hard-coded calendar (weekday/expiry)        -> deterministic math

...and rolls all 9 module outputs (MAC-1..3, NAT-1, FLO-1..2, PRE-1..5)
into a Stage1To4Result. This is a PARTIAL result — no Stage 5 yet.
Module_F_Foundation_Gate_Funnel combines this with
Module_F_Tech_Indicators_Funnel's ENG-1..11 output to produce the final
Verdict.

Dhan's Data API subscription is not yet active (per Fortuna-Build-Log.md
open items), so VIX and Nifty OHLC are accepted as injected parameters
here rather than fetched internally — swap in real dhan_client calls once
that's live. Keeping this as dependency injection rather than a hard
import means this module is fully testable today with mock data.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from .schemas import (
    Stage1To4Result, ViXSnapshot, NiftyOHLC, AIGatewayResponse, Direction,
    ModuleOutput,
)
from .deterministic_modules import (
    MAC_1, MAC_2, MAC_3, NAT_1, FLO_1, FLO_2,
    PRE_1, PRE_2, PRE_3, PRE_4, PRE_5,
    compute_basis_adjusted_gap_pct, compute_cpr, get_weekday_and_expiry_flag,
)
from .ai_gateway import fetch_stage1to4_snapshot

IST = timezone(timedelta(hours=5, minutes=30))


def _vix_signal_bucket(percentile: float) -> str:
    if percentile < 25.0:
        return "calm"
    if percentile < 75.0:
        return "normal"
    if percentile < 90.0:
        return "elevated"
    return "turbulent"


def run_stage1_to_4(
    vix: ViXSnapshot,
    nifty_prev_day: NiftyOHLC,        # yesterday's OHLC, for CPR
    nifty_today_open: float,          # today's actual open, for the real gap
    fii_dii_rolling_trend_strong: bool,  # TODO(open item): needs a real rolling-window calc, see README
    retail_vs_fii_divergence: bool,      # TODO(open item): needs real derivatives data, see README
    is_domestic_event_morning: bool = False,
    dxy_risk_off: bool = False,
    us10y_risk_off: bool = False,
    price_vs_cpr_override: Optional[str] = None,  # "above_TC"|"below_BC"|"inside"
    ema_bias: Optional[str] = None,   # Stage-5 input, None until that module exists
    rsi_bias: Optional[str] = None,
    vwap_bias: Optional[str] = None,
    atr_normalized_gap: Optional[float] = None,  # Stage-5 input
    trend_alignment: Optional[str] = None,        # Stage-5 input
    ai_response: Optional[AIGatewayResponse] = None,  # pass in to skip re-fetching
    run_date: Optional[date] = None,
) -> Stage1To4Result:

    now_ist = datetime.now(IST)
    run_date = run_date or now_ist.date()
    open_items: list[str] = []

    # --- 1. AI snapshot (data extraction + judgment) --------------------
    if ai_response is None:
        ai_response = fetch_stage1to4_snapshot(run_date=run_date)
    extraction = ai_response.extraction
    judgment = ai_response.judgment

    if extraction.gift_nifty.raw_level is None:
        open_items.append("GIFT Nifty level unavailable from AI extraction — PRE-2/MAC-2 degraded to neutral")
    if extraction.fii_dii.fii_net_cr is None or extraction.fii_dii.dii_net_cr is None:
        open_items.append("FII/DII net flows unavailable — FLO-1 degraded to noisy_or_offset_flows")

    # --- 2. VIX-derived values -------------------------------------------
    vix_pctl = vix.percentile if vix.percentile is not None else 50.0
    vix_signal = _vix_signal_bucket(vix_pctl)
    vix_in_normal_band = vix_signal in ("calm", "normal")

    # --- 3. Basis-adjusted GIFT gap --------------------------------------
    if extraction.gift_nifty.raw_level is not None:
        gift_gap_pct = compute_basis_adjusted_gap_pct(
            gift_raw_level=extraction.gift_nifty.raw_level,
            prev_cash_close=nifty_prev_day.close,
        )
        gift_gap_direction = (Direction.UP if gift_gap_pct > 0
                               else Direction.DOWN if gift_gap_pct < 0 else Direction.FLAT)
    else:
        gift_gap_pct = 0.0
        gift_gap_direction = Direction.UNKNOWN

    # --- 4. Actual gap (today's real open vs prev close) ----------------
    actual_gap_pct = (nifty_today_open - nifty_prev_day.close) / nifty_prev_day.close

    # --- 5. Calendar -------------------------------------------------------
    weekday, is_expiry_pm = get_weekday_and_expiry_flag(run_date, now_ist.time())

    # --- 6. CPR --------------------------------------------------------
    cpr = compute_cpr(nifty_prev_day.high, nifty_prev_day.low, nifty_prev_day.close)
    if price_vs_cpr_override is not None:
        price_vs_cpr = price_vs_cpr_override
    else:
        if nifty_today_open > cpr["tc"]:
            price_vs_cpr = "above_TC"
        elif nifty_today_open < cpr["bc"]:
            price_vs_cpr = "below_BC"
        else:
            price_vs_cpr = "inside"

    # --- 7. Run all 9 deterministic modules ------------------------------
    outputs: dict[str, ModuleOutput] = {}

    outputs["MAC-1"] = MAC_1(judgment.mac1_shock_detected, judgment.mac1_shock_description)
    outputs["MAC-2"] = MAC_2(
        us_close_direction=extraction.us_close.direction,
        asia_direction=extraction.asia_status.direction,
        gift_gap_direction=gift_gap_direction,
        gift_gap_pct=gift_gap_pct,
        vix_in_normal_band=vix_in_normal_band,
        time_of_day_ist=now_ist.time(),
    )
    outputs["MAC-3"] = MAC_3(dxy_risk_off=dxy_risk_off, us10y_risk_off=us10y_risk_off)

    outputs["NAT-1"] = NAT_1(
        judgment.nat1_event_today, judgment.nat1_surprise_flag, judgment.nat1_surprise_description,
    )

    fii_net = extraction.fii_dii.fii_net_cr or 0.0
    dii_net = extraction.fii_dii.dii_net_cr or 0.0
    outputs["FLO-1"] = FLO_1(fii_net, dii_net, fii_dii_rolling_trend_strong)
    outputs["FLO-2"] = FLO_2(retail_vs_fii_divergence, outputs["FLO-1"].signal)

    outputs["PRE-1"] = PRE_1(vix_pctl)
    outputs["PRE-2"] = PRE_2(gift_gap_pct, now_ist.time(), is_domestic_event_morning)
    outputs["PRE-3"] = PRE_3(
        actual_gap_pct=actual_gap_pct,
        atr_normalized_gap=atr_normalized_gap,
        trend_alignment=trend_alignment,
        vix_signal=vix_signal,
        news_flag=judgment.pre3_news_flag,
        live_overhang_active=judgment.mac1_live_overhang_active,
    )
    if atr_normalized_gap is None or trend_alignment is None:
        open_items.append("PRE-3 running without Stage-5 ATR/trend inputs — degraded to 'uncertain' unless tiny/breakaway/exhaustion")

    outputs["PRE-4"] = PRE_4(cpr["width_pts"], price_vs_cpr, ema_bias, rsi_bias, vwap_bias)
    outputs["PRE-5"] = PRE_5(weekday, is_expiry_pm)

    # --- 8. Aggregate (Stage 1-4 partial) ---------------------------------
    dir_up = sum(o.direction_weight for o in outputs.values() if o.bias == Direction.UP)
    dir_down = sum(o.direction_weight for o in outputs.values() if o.bias == Direction.DOWN)

    if dir_up > dir_down * 1.1:
        lean = Direction.UP
    elif dir_down > dir_up * 1.1:
        lean = Direction.DOWN
    else:
        lean = Direction.FLAT

    conf_product = 1.0
    for o in outputs.values():
        conf_product *= o.confidence_mult

    tradeable = "NO_GO" if (outputs["PRE-1"].signal == "turbulent"
                             or outputs["PRE-5"].signal == "Tue_expiry_PM_pin") else "GO"

    trap_risk = "low"
    if judgment.mac1_live_overhang_active or outputs["PRE-1"].signal == "elevated":
        trap_risk = "moderate"
    if outputs["PRE-1"].signal == "turbulent" or (judgment.nat1_event_today and judgment.nat1_surprise_flag):
        trap_risk = "high"

    return Stage1To4Result(
        run_date=run_date,
        run_timestamp_ist=now_ist,
        module_outputs=outputs,
        dir_score_up_partial=dir_up,
        dir_score_down_partial=dir_down,
        direction_lean_partial=lean,
        confidence_mult_product_partial=conf_product,
        tradeable_gate_partial=tradeable,
        trap_risk_partial=trap_risk,
        extraction=extraction,
        judgment=judgment,
        open_items=open_items,
    )
