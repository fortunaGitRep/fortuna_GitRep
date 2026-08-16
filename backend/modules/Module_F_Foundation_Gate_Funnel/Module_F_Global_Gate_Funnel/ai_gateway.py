"""
Fortuna — Module_F_Global_Gate_Funnel — ai_gateway.py

The ONE place in this module that talks to Claude. Does two jobs in a
single daily call:

  1. DATA EXTRACTION (via web_search) — GIFT Nifty raw level, US close %,
     Asia market status, FII/DII net flows, DXY/US10Y/crude/gold. None of
     these are available from Dhan (GIFT Nifty trades on a different
     exchange — NSE IFSC, not NSE proper; FII/DII are NSE/NSDL end-of-day
     reports, not a broker feed).

  2. QUALITATIVE JUDGMENT — MAC-1 shock classification, MAC-1 overhang
     detection, NAT-1 surprise classification. These are genuinely
     language/context judgment calls that a formula can't make well.

Everything downstream of this call — every number that goes into
direction_weight/context_weight math — happens in deterministic_modules.py,
in plain Python. This call NEVER does arithmetic on GIFT levels, VIX, or
anything else. That's the direct lesson from the 12-Aug-2026 Corrections
Log: keep the math out of the model's hands.

Requires: F_ANTHROPIC_API_KEY in environment.
"""

from __future__ import annotations
import json
import logging
import os
import re
from datetime import date, datetime, timezone, timedelta

from anthropic import Anthropic

from .schemas import (
    Stage1To4Extraction, Stage1To4Judgment, AIGatewayResponse,
)

# Adjust to whatever current Claude model your account has access to —
# verify against docs.claude.com/en/docs/about-claude/models before relying
# on this string long-term.
MODEL = "claude-sonnet-4-5"

IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a data-extraction and classification assistant for a \
pre-market trading pipeline (Fortuna, NSE Nifty 50 cash/options). You do NOT \
give trading advice, predictions, or recommendations. You do two things only:

1. EXTRACT current pre-market data points using web search: \
   yesterday's US market close (Dow/S&P/Nasdaq % change), today's Asian \
   market session status/direction, yesterday's FII and DII net cash \
   flows in crores (from NSE provisional data or NSDL), and current \
   DXY/US10Y yield/Brent crude/gold levels if readily available. \
   (Do NOT fetch GIFT Nifty or India VIX — those come from the broker \
   data feed, not you.)

   Every field you cannot verify from a real source must be null. Do not \
   estimate, infer, or fill gaps with plausible-sounding numbers. Include \
   the source URLs you actually used.

2. CLASSIFY, using only the definitions below — do not use your own \
   judgment of "importance", use exactly these definitions:

   - mac1_shock_detected: true ONLY if there is a genuinely NEW \
     Fed/geopolitical/commodity shock that broke in roughly the last \
     24-48 hours. A long-running, already-priced-in situation (e.g. an \
     ongoing geopolitical standoff with no fresh escalation) is NOT a \
     shock — set this false and instead set mac1_live_overhang_active.
   - mac1_live_overhang_active: true if there is an unresolved, ongoing \
     macro/geopolitical situation still weighing on sentiment, even if \
     it's not fresh news today.
   - nat1_event_today: true if there is a scheduled India-specific event \
     today (RBI policy, Union Budget, major election result, etc).
   - nat1_surprise_flag: true ONLY if a scheduled event's OUTCOME today \
     was a genuine consensus surprise (not just "this event exists").
   - pre3_news_flag: true if there is a specific, identifiable news \
     catalyst for today's session (distinct from a generic overhang).

Respond with ONLY a single JSON object matching the schema you're given \
in the user message. No prose, no markdown fences, no commentary."""

JSON_SCHEMA_INSTRUCTIONS = """
Return exactly this JSON shape (use null for anything unverified):

{
  "extraction": {
    "run_date": "YYYY-MM-DD",
    "us_close": {"dow_pct": float|null, "sp500_pct": float|null, "nasdaq_pct": float|null, "direction": "up"|"down"|"flat"|"unknown"},
    "asia_status": {"direction": "up"|"down"|"flat"|"unknown", "notes": string|null},
    "fii_dii": {"as_of_date": string|null, "fii_net_cr": float|null, "dii_net_cr": float|null, "source_note": string|null},
    "macro_levels": {"dxy": float|null, "us10y": float|null, "crude_brent": float|null, "gold": float|null},
    "extraction_confidence_note": string|null,
    "sources": [string, ...]
  },
  "judgment": {
    "mac1_shock_detected": bool,
    "mac1_shock_description": string|null,
    "mac1_live_overhang_active": bool,
    "mac1_overhang_description": string|null,
    "nat1_event_today": bool,
    "nat1_event_name": string|null,
    "nat1_surprise_flag": bool,
    "nat1_surprise_description": string|null,
    "pre3_news_flag": bool
  }
}
"""


def _extract_json_block(text: str) -> dict:
    """
    Extract the JSON object from Claude's response. Claude is instructed to
    return raw JSON, but in practice (especially with web_search) it often
    prepends reasoning prose and/or wraps the JSON in a ```json fenced block.
    This handles all three cases:
      1. a ```json ... ``` (or ``` ... ```) fenced block anywhere in the text
      2. a bare JSON object embedded after prose (first '{' to matching last '}')
      3. clean JSON (no wrapping)
    Fails loud with a clear error (including a preview) if no JSON is found,
    rather than a bare JSONDecodeError.
    """
    if not text or not text.strip():
        raise ValueError("AI gateway returned an empty response; no JSON to parse.")

    candidate = None

    # Case 1: a fenced code block anywhere in the text.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        # Case 2/3: take the first '{' through the matching last '}'.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]

    if candidate is None:
        preview = text[:300]
        raise ValueError(
            f"AI gateway response contained no JSON object. Response preview: {preview!r}"
        )

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        preview = candidate[:300]
        raise ValueError(
            f"AI gateway response JSON failed to parse: {exc}. Candidate preview: {preview!r}"
        ) from exc


def fetch_stage1to4_snapshot(run_date: date | None = None) -> AIGatewayResponse:
    """
    Single daily call. Intended to run once, pre-market (e.g. ~08:45-09:00
    IST) before Gift Nifty's directional relevance decays. The resulting
    values are then fed into deterministic_modules.py functions, which
    handle the ~10:00 decay via time_of_day parameters — this function is
    NOT re-called through the morning.
    """
    run_date = run_date or datetime.now(IST).date()
    client = Anthropic(api_key=os.environ["F_ANTHROPIC_API_KEY"])

    user_message = (
        f"Today's date (IST) is {run_date.isoformat()}. "
        f"Fetch the pre-market snapshot for NSE Nifty 50.\n\n{JSON_SCHEMA_INSTRUCTIONS}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_message}],
    )

    # Concatenate all text blocks (web_search responses interleave tool_use blocks)
    text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    full_text = "\n".join(text_parts)

    # Diagnostic (silent unless debug logging enabled): block types + text length.
    # Claude often returns reasoning prose + a ```json fenced block rather than
    # clean JSON; _extract_json_block handles that.
    logger.debug(
        "ai_gateway response: stop_reason=%s, blocks=%d, text_len=%d",
        getattr(response, "stop_reason", "n/a"), len(response.content), len(full_text),
    )

    parsed = _extract_json_block(full_text)

    extraction = Stage1To4Extraction(**parsed["extraction"])
    judgment = Stage1To4Judgment(**parsed["judgment"])

    return AIGatewayResponse(
        extraction=extraction,
        judgment=judgment,
        raw_model_response=full_text,
    )
