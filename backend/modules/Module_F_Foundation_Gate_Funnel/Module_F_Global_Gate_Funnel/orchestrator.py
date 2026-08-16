"""
Fortuna — Module_F_Global_Gate_Funnel — orchestrator.py

Entry point: run_stage1_to_4(). Wires together:
  - Store-sourced Dhan data (VIX regime, Nifty prev-day OHLC, GIFT level)
  - Claude+web_search snapshot (ai_gateway.py) -> FII/DII, US/Asia, macro, judgment
  - Hard-coded calendar (weekday/expiry)

...and rolls all 11 module outputs (MAC-1..3, NAT-1, FLO-1..2, PRE-1..5)
into a Stage1To4Result. This is a PARTIAL result — no Stage 5 yet.

DATA SOURCING (as of the live-data cleanup, Aug 2026):
  - VIX regime     -> market_data.vix_regime.evaluate_vix_decision() (store)
  - Nifty prev-day -> market_data.index_store.get_latest_bar("NIFTY_50")
  - GIFT level     -> market_data.index_store.get_latest_bar("GIFT_NIFTY")
  - FII/DII, US/Asia close, macro levels, news + judgment -> AI gateway
  The AI gateway NO LONGER fetches GIFT (it's in the store now).

PRE-MARKET AWARENESS:
  Today's Nifty OPEN doesn't exist at a pre-market (~08:45 IST) run. Gates that
  need it report "not available yet" instead of faking a verdict, and the
  rollup uses only the available verdicts:
    - PRE-3 (gap behaviour) -> fully pending (needs today's open)
    - PRE-4 location        -> pending (width still contributes)
  Everything else runs on overnight/prior-day/date data.
  Pass nifty_today_open once the market has opened to fill these in.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from .schemas import (
    Stage1To4Result, AIGatewayResponse, Direction, ModuleOutput,
)
from .deterministic_modules import (
    MAC_1, MAC_2, MAC_3, NAT_1, FLO_1, FLO_2,
    PRE_1, PRE_2, PRE_3, PRE_4, PRE_5,
    compute_basis_adjusted_gap_pct, compute_cpr, get_weekday_and_expiry_flag,
)
from .ai_gateway import fetch_stage1to4_snapshot

# Shared market-data layer (store + VIX regime)
from modules.market_data.vix_regime import evaluate_vix_decision, VolRegime
from modules.market_data.index_store import get_latest_bar

IST = timezone(timedelta(hours=5, minutes=30))


def _vix_signal_from_regime(regime: VolRegime) -> str:
    """Map vix_regime's regime enum to the string PRE-3/MAC-2 expect
    ('calm'/'normal'/'elevated'/'turbulent')."""
    return {
        VolRegime.LOW: "calm",
        VolRegime.NORMAL: "normal",
        VolRegime.HIGH: "elevated",
        VolRegime.EXTREME: "turbulent",
        VolRegime.NO_DATA: "normal",  # safe neutral if VIX data missing
    }.get(regime, "normal")


def run_stage1_to_4(
    nifty_today_open: Optional[float] = None,  # None = pre-market; supply after 9:15
    fii_dii_rolling_trend_strong: bool = False,  # TODO(open item): real rolling-window calc
    retail_vs_fii_divergence: bool = False,      # TODO(open item): real derivatives data
    is_domestic_event_morning: bool = False,
    dxy_risk_off: bool = False,
    us10y_risk_off: bool = False,
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

    # --- 1. AI snapshot (FII/DII, US/Asia, macro, judgment) --------------
    if ai_response is None:
        ai_response = fetch_stage1to4_snapshot(run_date=run_date)
    extraction = ai_response.extraction
    judgment = ai_response.judgment

    if extraction.fii_dii.fii_net_cr is None or extraction.fii_dii.dii_net_cr is None:
        open_items.append("FII/DII net flows unavailable — FLO-1 degraded to noisy_or_offset_flows")

    # --- 2. VIX regime (store, via vix_regime) ---------------------------
    vix_decision = evaluate_vix_decision()
    vix_signal = _vix_signal_from_regime(vix_decision.regime)
    vix_in_normal_band = vix_decision.regime in (VolRegime.LOW, VolRegime.NORMAL)
    if vix_decision.regime == VolRegime.NO_DATA:
        open_items.append("VIX data unavailable from store — PRE-1 degraded to NO_DATA/neutral")

    # --- 3. Nifty prev-day OHLC + GIFT level (store) ---------------------
    nifty_bar = get_latest_bar("NIFTY_50")
    gift_bar = get_latest_bar("GIFT_NIFTY")

    if nifty_bar is None:
        open_items.append("Nifty OHLC unavailable from store — CPR/gap degraded")
    if gift_bar is None:
        open_items.append("GIFT level unavailable from store — PRE-2/MAC-2 gap degraded to neutral")

    # --- 4. Basis-adjusted GIFT gap (store data) ------------------------
    if gift_bar is not None and nifty_bar is not None:
        gift_gap_pct = compute_basis_adjusted_gap_pct(
            gift_raw_level=gift_bar.close,
            prev_cash_close=nifty_bar.close,
        )
        gift_gap_direction = (Direction.UP if gift_gap_pct > 0
                               else Direction.DOWN if gift_gap_pct < 0 else Direction.FLAT)
    else:
        gift_gap_pct = 0.0
        gift_gap_direction = Direction.UNKNOWN

    # --- 5. Actual gap (today's real open vs prev close) — pre-market aware
    if nifty_today_open is not None and nifty_bar is not None:
        actual_gap_pct: Optional[float] = (nifty_today_open - nifty_bar.close) / nifty_bar.close
    else:
        actual_gap_pct = None  # pre-market: PRE-3 will report not_available_yet

    # --- 6. Calendar -----------------------------------------------------
    weekday, is_expiry_pm = get_weekday_and_expiry_flag(run_date, now_ist.time())

    # --- 7. CPR (width always; location only post-open) -----------------
    if nifty_bar is not None and nifty_bar.high is not None and nifty_bar.low is not None:
        cpr = compute_cpr(nifty_bar.high, nifty_bar.low, nifty_bar.close)
        cpr_width = cpr["width_pts"]
        if nifty_today_open is not None:
            if nifty_today_open > cpr["tc"]:
                price_vs_cpr: Optional[str] = "above_TC"
            elif nifty_today_open < cpr["bc"]:
                price_vs_cpr = "below_BC"
            else:
                price_vs_cpr = "inside"
        else:
            price_vs_cpr = None  # pre-market: location pending
    else:
        cpr_width = 0.0
        price_vs_cpr = None

    # --- 8. Run all deterministic modules -------------------------------
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

    outputs["PRE-1"] = PRE_1(vix_decision)  # thin adapter: VixDecision -> ModuleOutput
    outputs["PRE-2"] = PRE_2(gift_gap_pct, now_ist.time(), is_domestic_event_morning)
    outputs["PRE-3"] = PRE_3(
        actual_gap_pct=actual_gap_pct,  # None pre-market -> not_available_yet
        atr_normalized_gap=atr_normalized_gap,
        trend_alignment=trend_alignment,
        vix_signal=vix_signal,
        news_flag=judgment.pre3_news_flag,
        live_overhang_active=judgment.mac1_live_overhang_active,
    )
    if actual_gap_pct is None:
        open_items.append("PRE-3 pending — today's Nifty open not available (pre-market run)")
    elif atr_normalized_gap is None or trend_alignment is None:
        open_items.append("PRE-3 running without Stage-5 ATR/trend inputs — degraded to 'uncertain' unless tiny/breakaway/exhaustion")

    outputs["PRE-4"] = PRE_4(cpr_width, price_vs_cpr, ema_bias, rsi_bias, vwap_bias)
    if price_vs_cpr is None:
        open_items.append("PRE-4 location pending — today's price not available (pre-market run); width context only")
    outputs["PRE-5"] = PRE_5(weekday, is_expiry_pm)

    # --- 9. Aggregate (Stage 1-4 partial) -------------------------------
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
                             or vix_decision.go_no_go == "NO_GO"
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
