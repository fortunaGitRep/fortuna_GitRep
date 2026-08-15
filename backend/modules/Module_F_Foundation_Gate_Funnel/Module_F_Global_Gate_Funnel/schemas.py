"""
Fortuna — Module_F_Global_Gate_Funnel — schemas.py

Pydantic models for Stage 1-4 of the Direction Funnel (MAC-1..3, NAT-1,
FLO-1..2, PRE-1..5). Mirrors the `ModuleOutput` / partial `Verdict` structs
in Fortuna_Funnel_Pseudocode_v3_with_Nifty.md.

This module does NOT include Stage 5 (ENG-1..11) — that's
Module_F_Tech_Indicators_Funnel. The two get combined later in
Module_F_Foundation_Gate_Funnel.
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


class ModuleOutput(BaseModel):
    """Standard output shape for every MAC/NAT/FLO/PRE module."""
    module_id: str  # e.g. "MAC-1", "PRE-2"
    signal: str
    direction_weight: float = Field(ge=0.0, le=1.0)
    context_weight: float = Field(ge=0.0, le=1.0)
    confidence_mult: float = Field(ge=0.0)
    bias: Direction = Direction.UNKNOWN  # which way direction_weight leans, if any
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# AI Gateway output shapes (Claude + web_search)
# ---------------------------------------------------------------------------

class USCloseData(BaseModel):
    dow_pct: Optional[float] = None
    sp500_pct: Optional[float] = None
    nasdaq_pct: Optional[float] = None
    direction: Direction = Direction.UNKNOWN


class AsiaStatus(BaseModel):
    direction: Direction = Direction.UNKNOWN
    notes: Optional[str] = None


class GiftNiftyData(BaseModel):
    raw_level: Optional[float] = None
    as_of_ist: Optional[str] = None
    notes: Optional[str] = None


class FiiDiiData(BaseModel):
    as_of_date: Optional[str] = None
    fii_net_cr: Optional[float] = None  # crores, +ve = net buy
    dii_net_cr: Optional[float] = None
    source_note: Optional[str] = None


class MacroLevels(BaseModel):
    dxy: Optional[float] = None
    us10y: Optional[float] = None
    crude_brent: Optional[float] = None
    gold: Optional[float] = None


class Stage1To4Extraction(BaseModel):
    """Raw data Claude fetched via web_search for today's pre-market snapshot."""
    run_date: date
    us_close: USCloseData
    asia_status: AsiaStatus
    gift_nifty: GiftNiftyData
    fii_dii: FiiDiiData
    macro_levels: MacroLevels
    extraction_confidence_note: Optional[str] = None
    sources: list[str] = Field(default_factory=list)


class Stage1To4Judgment(BaseModel):
    """Qualitative judgment calls — the parts a formula can't make."""
    mac1_shock_detected: bool = False
    mac1_shock_description: Optional[str] = None
    mac1_live_overhang_active: bool = False
    mac1_overhang_description: Optional[str] = None

    nat1_event_today: bool = False
    nat1_event_name: Optional[str] = None
    nat1_surprise_flag: bool = False
    nat1_surprise_description: Optional[str] = None

    pre3_news_flag: bool = False  # feeds PRE-3's runaway-gap precondition


class AIGatewayResponse(BaseModel):
    """Full parsed response from the single daily Claude call."""
    extraction: Stage1To4Extraction
    judgment: Stage1To4Judgment
    raw_model_response: Optional[str] = None  # kept for audit trail / debugging


# ---------------------------------------------------------------------------
# Deterministic (Dhan-sourced) inputs
# ---------------------------------------------------------------------------

class ViXSnapshot(BaseModel):
    level: float
    percentile: Optional[float] = None  # rolling percentile, computed separately


class NiftyOHLC(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    prev_close: float


# ---------------------------------------------------------------------------
# Stage 1-4 aggregate output (partial — no Stage 5 yet)
# ---------------------------------------------------------------------------

class Stage1To4Result(BaseModel):
    """
    Output of Module_F_Global_Gate_Funnel for one trading day.
    This is NOT a final Verdict — direction/conviction here only reflect
    Stages 1-4. Module_F_Foundation_Gate_Funnel merges this with Stage 5
    (ENG-1..11) to produce the final Verdict object.
    """
    run_date: date
    run_timestamp_ist: datetime

    module_outputs: dict[str, ModuleOutput]  # keyed by module_id, e.g. "MAC-1"

    # Stage 1-4 partial direction read (pre-Stage-5)
    dir_score_up_partial: float
    dir_score_down_partial: float
    direction_lean_partial: Direction

    # Rolls up into Stage 5 stage's confidence multiplier chain
    confidence_mult_product_partial: float

    # Early tradeable gate (VIX turbulent / Tue expiry PM pin) — Stage 5
    # can only tighten this, never loosen it
    tradeable_gate_partial: str  # "GO" | "NO_GO"

    trap_risk_partial: str  # "low" | "moderate" | "high"

    extraction: Stage1To4Extraction
    judgment: Stage1To4Judgment

    open_items: list[str] = Field(default_factory=list)  # flags for review
