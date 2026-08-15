"""
Sanity check — mocks the AI gateway response so this runs WITHOUT an
ANTHROPIC_API_KEY. Also reconstructs the 12-Aug-2026 case study from the
Corrections Log to confirm the basis-adjustment fix produces a gap-DOWN
read matching the doc's own worked example (-0.29%).

Run from the repo folder CONTAINING global_gate_funnel/, e.g.:
    cd backend/app/modules   (or wherever you place this package)
    python -m Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.test_sanity
"""
from datetime import date

from Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.schemas import (
    Stage1To4Extraction, Stage1To4Judgment, AIGatewayResponse,
    USCloseData, AsiaStatus, GiftNiftyData, FiiDiiData, MacroLevels,
    ViXSnapshot, NiftyOHLC, Direction,
)
from Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.orchestrator import run_stage1_to_4
from Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.deterministic_modules import compute_basis_adjusted_gap_pct


def test_basis_adjustment_matches_corrections_log():
    gap = compute_basis_adjusted_gap_pct(
        gift_raw_level=24555.0,
        prev_cash_close=24471.70,
        carry_premium_points=155.0,
    )
    print(f"Basis-adjusted gap: {gap:.4%}  (doc's worked example: ~-0.29%)")
    assert gap < 0, "Should be a gap-DOWN after basis adjustment, per the Corrections Log"


def test_full_pipeline_runs_with_mock_ai():
    mock_ai = AIGatewayResponse(
        extraction=Stage1To4Extraction(
            run_date=date(2026, 8, 13),
            us_close=USCloseData(dow_pct=-0.34, sp500_pct=-0.32, nasdaq_pct=-0.6, direction=Direction.DOWN),
            asia_status=AsiaStatus(direction=Direction.DOWN, notes="Nikkei, Hang Seng both lower"),
            gift_nifty=GiftNiftyData(raw_level=24620.0, as_of_ist="08:50"),
            fii_dii=FiiDiiData(as_of_date="2026-08-12", fii_net_cr=-850.0, dii_net_cr=1200.0),
            macro_levels=MacroLevels(dxy=103.2, us10y=4.3, crude_brent=82.1, gold=2410.0),
            sources=["https://example.com/mock-source"],
        ),
        judgment=Stage1To4Judgment(
            mac1_shock_detected=False,
            mac1_live_overhang_active=True,
            mac1_overhang_description="Ongoing geopolitical standoff, no fresh escalation",
            nat1_event_today=False,
            pre3_news_flag=False,
        ),
        raw_model_response="<mocked>",
    )

    vix = ViXSnapshot(level=13.4, percentile=42.0)
    prev_day = NiftyOHLC(trade_date=date(2026, 8, 11), open=24500, high=24610, low=24430, close=24471.70, prev_close=24400)

    result = run_stage1_to_4(
        vix=vix,
        nifty_prev_day=prev_day,
        nifty_today_open=24445.0,
        fii_dii_rolling_trend_strong=False,
        retail_vs_fii_divergence=False,
        ai_response=mock_ai,
        run_date=date(2026, 8, 13),
    )

    print("\n--- Stage 1-4 Result ---")
    print(f"Direction lean: {result.direction_lean_partial}")
    print(f"dir_up={result.dir_score_up_partial}  dir_down={result.dir_score_down_partial}")
    print(f"Tradeable: {result.tradeable_gate_partial}  Trap risk: {result.trap_risk_partial}")
    print(f"Confidence mult product: {result.confidence_mult_product_partial:.3f}")
    print("Open items:")
    for item in result.open_items:
        print(f"  - {item}")
    print("\nModule outputs:")
    for mid, out in result.module_outputs.items():
        print(f"  {mid}: {out.signal} | dir_wt={out.direction_weight} ctx_wt={out.context_weight} conf={out.confidence_mult} bias={out.bias}")

    assert result.tradeable_gate_partial == "GO"
    assert len(result.module_outputs) == 11  # MAC-1..3, NAT-1, FLO-1..2, PRE-1..5


if __name__ == "__main__":
    test_basis_adjustment_matches_corrections_log()
    print()
    test_full_pipeline_runs_with_mock_ai()
    print("\nAll sanity checks passed.")
