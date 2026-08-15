#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FORTUNA - Foundation List - Direction Funnel - Track A - v0.9
Corrections layer on top of v0.8, driven by the Perplexity v2 corrections doc
and the 12-Aug-2026 live backtest.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, HRFlowable, PageBreak, NextPageTemplate
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

# ---------- palette (kept close to the v0.8 report feel: dark teal + amber) ----------
INK = colors.HexColor("#1a1c20")
SOFT = colors.HexColor("#41454c")
MUTE = colors.HexColor("#787d86")
HAIRLINE = colors.HexColor("#d3d6db")
TEAL = colors.HexColor("#0f3d3e")
TEAL_LIGHT = colors.HexColor("#e4eeee")
AMBER = colors.HexColor("#b3791c")
AMBER_LIGHT = colors.HexColor("#fbf1de")
GREY_HEAD = colors.HexColor("#eef0f2")
WHITE = colors.white
RED_FLAG = colors.HexColor("#8a2b1f")
RED_LIGHT = colors.HexColor("#f7e6e2")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

# ---------- styles ----------
styles = {}
styles["DocTitle"] = ParagraphStyle("DocTitle", fontName="Helvetica-Bold", fontSize=26,
                                     leading=30, textColor=TEAL, spaceAfter=4)
styles["DocSub"] = ParagraphStyle("DocSub", fontName="Helvetica", fontSize=12.5,
                                   leading=16, textColor=SOFT, spaceAfter=2)
styles["DocMeta"] = ParagraphStyle("DocMeta", fontName="Helvetica-Bold", fontSize=10,
                                    leading=13, textColor=AMBER, spaceAfter=2)
styles["H1"] = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, leading=19,
                               textColor=TEAL, spaceBefore=4, spaceAfter=8)
styles["H2"] = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=12, leading=15,
                               textColor=INK, spaceBefore=10, spaceAfter=5)
styles["StageKicker"] = ParagraphStyle("StageKicker", fontName="Helvetica-Bold", fontSize=9.5,
                                        leading=12, textColor=WHITE, spaceBefore=0, spaceAfter=0)
styles["Body"] = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.3, leading=12.6,
                                 textColor=INK, alignment=TA_JUSTIFY, spaceAfter=5)
styles["BodySmall"] = ParagraphStyle("BodySmall", fontName="Helvetica", fontSize=8.4,
                                      leading=11.4, textColor=SOFT, alignment=TA_JUSTIFY)
styles["Cell"] = ParagraphStyle("Cell", fontName="Helvetica", fontSize=8.0, leading=10.4,
                                 textColor=INK, alignment=TA_LEFT)
styles["CellBold"] = ParagraphStyle("CellBold", fontName="Helvetica-Bold", fontSize=8.2,
                                     leading=10.6, textColor=INK, alignment=TA_LEFT)
styles["CellHead"] = ParagraphStyle("CellHead", fontName="Helvetica-Bold", fontSize=7.6,
                                     leading=9.4, textColor=WHITE, alignment=TA_LEFT)
styles["CellWeight"] = ParagraphStyle("CellWeight", fontName="Helvetica-Bold", fontSize=8.4,
                                       leading=10.6, textColor=TEAL, alignment=TA_CENTER)
styles["CellFix"] = ParagraphStyle("CellFix", fontName="Helvetica", fontSize=8.0, leading=10.6,
                                    textColor=INK, alignment=TA_LEFT)
styles["NoteLabel"] = ParagraphStyle("NoteLabel", fontName="Helvetica-Bold", fontSize=8.6,
                                      leading=11, textColor=AMBER)
styles["FlagLabel"] = ParagraphStyle("FlagLabel", fontName="Helvetica-Bold", fontSize=8.6,
                                      leading=11, textColor=RED_FLAG)
styles["Small"] = ParagraphStyle("Small", fontName="Helvetica-Oblique", fontSize=8.2,
                                  leading=11, textColor=MUTE)
styles["Bullet"] = ParagraphStyle("Bullet", fontName="Helvetica", fontSize=9.2, leading=12.6,
                                   textColor=INK, leftIndent=10, spaceAfter=4)

DOC_TITLE = "FORTUNA \u2014 Foundation List \u2014 Direction Funnel \u2014 Track A \u2014 v0.9"

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(HAIRLINE)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 16 * mm, PAGE_W - MARGIN, 16 * mm)
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTE)
    canvas.drawString(MARGIN, 11 * mm, "FORTUNA \u00b7 Foundation List \u00b7 Direction Funnel \u00b7 Track A \u00b7 v0.9 \u00b7 Corrections Layer on v0.8")
    canvas.drawRightString(PAGE_W - MARGIN, 11 * mm, f"Page {doc.page}   \u00b7   Confidential \u2014 Internal Use Only")
    canvas.restoreState()

def title_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTE)
    canvas.drawCentredString(PAGE_W / 2, 12 * mm, "Confidential \u2014 Internal Use Only")
    canvas.restoreState()

doc = BaseDocTemplate(
    "/home/claude/Fortuna_TrackA_Foundation_Funnel_v0_9.pdf",
    pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN, topMargin=18 * mm, bottomMargin=22 * mm,
    title="Fortuna Foundation List - Direction Funnel - Track A - v0.9",
)
frame_normal = Frame(MARGIN, 22 * mm, PAGE_W - 2 * MARGIN, PAGE_H - 18 * mm - 22 * mm, id="normal")
frame_title = Frame(MARGIN, 18 * mm, PAGE_W - 2 * MARGIN, PAGE_H - 18 * mm - 18 * mm, id="title")
doc.addPageTemplates([
    PageTemplate(id="Title", frames=[frame_title], onPage=title_footer),
    PageTemplate(id="Normal", frames=[frame_normal], onPage=footer),
])

story = []

def stage_bar(text, color=TEAL):
    t = Table([[Paragraph(text, styles["StageKicker"])]], colWidths=[PAGE_W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t

def note_box(label_style, label, body_text, bg, border):
    inner = Table([[Paragraph(f"{label}", label_style)],
                    [Paragraph(body_text, styles["BodySmall"])]],
                   colWidths=[PAGE_W - 2 * MARGIN - 16])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.75, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    return inner

# =========================================================================
# PAGE 1 - TITLE
# =========================================================================
story.append(Spacer(1, 55 * mm))
story.append(Paragraph("FORTUNA", ParagraphStyle("Big", fontName="Helvetica-Bold", fontSize=34,
                                                   leading=40, textColor=TEAL, spaceAfter=14)))
story.append(Paragraph("Foundation List \u2014 Direction Funnel", styles["DocSub"]))
story.append(Spacer(1, 4))
story.append(Paragraph("Corrections Layer \u00b7 Track A \u00b7 v0.9 \u00b7 12 Aug 2026", styles["DocMeta"]))
story.append(Spacer(1, 14))
story.append(HRFlowable(width="35%", thickness=1.2, color=AMBER, spaceAfter=14, hAlign="LEFT"))
story.append(Paragraph(
    "This revision layers the Perplexity v2 corrections (\u201cFortuna Direction Funnel \u2013 Corrections & "
    "Usage Guidelines v2, Aug 2026\u201d) on top of v0.8, plus lessons from the 12-Aug-2026 live backtest. "
    "It does not replace v0.8 \u2014 the proof, mechanism, and per-timeframe-weight sections for every item "
    "stay as written there. v0.9 adds a formal <b>direction_weight / context_weight / confidence_multiplier</b> "
    "field to all 22 trunk items, corrects three items where v0.8's language allowed an unintended directional "
    "read, and appends a Corrections Log documenting exactly how the funnel produced a wrong verdict on 12 Aug "
    "2026 and what changes prevent a repeat.",
    styles["Body"]
))
story.append(Spacer(1, 90 * mm))
story.append(HRFlowable(width="100%", thickness=0.6, color=HAIRLINE, spaceAfter=6))
story.append(Paragraph("FORTUNA \u00b7 Foundation List \u00b7 Direction Funnel \u00b7 Track A \u00b7 v0.9 \u00b7 Confidential \u2014 Internal Use Only",
                        styles["Small"]))

story.append(NextPageTemplate("Normal"))
story.append(PageBreak())

# =========================================================================
# REVISION NOTE
# =========================================================================
story.append(Paragraph("Revision Note", styles["H1"]))
story.append(Paragraph(
    "v0.8 (13 Jul 2026) completed the 22-item Foundation List trunk. This v0.9 (12 Aug 2026) does three things:",
    styles["Body"]))
for b in [
    "<b>Formalizes weights.</b> Every item's Signal Strength discussion in v0.8 described direction and "
    "volatility qualitatively (HIGH/MED/LOW, Gate, Infra). v0.9 converts this into explicit "
    "<b>direction_weight</b>, <b>context_weight</b>, and a <b>confidence_multiplier</b> per item, per the v2 "
    "corrections spec \u2014 so the System Score can be coded, not just read.",
    "<b>Corrects three items</b> (FLO-1, FLO-2, PRE-4) where v0.8's wording left room for an item to be read "
    "as directional when it should structurally carry direction_weight = 0. This exact gap produced a wrong "
    "\u201cUptrend\u201d call on 12 Aug 2026 \u2014 see the Corrections Log at the end of this document.",
    "<b>Appends a Corrections Log</b> \u2014 a real case study (12 Aug 2026) of the funnel being run end-to-end "
    "against live data, what it got right, what it got wrong, and the operational safeguards now in place "
    "to prevent the same mistake.",
]:
    story.append(Paragraph(f"\u2022 {b}", styles["Bullet"]))
story.append(Spacer(1, 6))
story.append(note_box(styles["NoteLabel"], "Scope note",
    "This document assumes v0.8 open alongside it. Where an item is unchanged in substance, v0.9 says so "
    "explicitly and points back to the v0.8 page rather than repeating the proof/mechanism text.",
    AMBER_LIGHT, AMBER))

story.append(Spacer(1, 14))
story.append(Paragraph("The Verdict Object, Formalized", styles["H1"]))
story.append(Paragraph(
    "v0.8 (page 2) defined the funnel's output as a verdict object rather than a single directional number: "
    "<font face='Helvetica-Bold'>verdict = { tradeable \u00b7 day_type \u00b7 direction \u00b7 conviction \u00b7 "
    "volatility_character \u00b7 size \u00b7 trap_risk \u00b7 stop }</font>. v0.9 adds the machinery that fills "
    "the <i>direction</i> and <i>conviction</i> fields specifically:", styles["Body"]))

field_rows = [
    [Paragraph("Field", styles["CellHead"]), Paragraph("Definition", styles["CellHead"]),
     Paragraph("Rule", styles["CellHead"])],
    [Paragraph("direction_weight", styles["CellBold"]),
     Paragraph("How much this item may move the <i>direction</i> field, 0\u20131.", styles["Cell"]),
     Paragraph("Hard-coded to 0 for any item v0.8 already called a pure gate (PRE-1, PRE-5, ENG-1, ENG-6, "
               "ENG-8, ENG-9, ENG-11) or a same-day-EOD item (FLO-1, FLO-2, NAT-1, MAC-1 on non-event days).", styles["Cell"])],
    [Paragraph("context_weight", styles["CellBold"]),
     Paragraph("How much this item may move tradeable / day_type / conviction / size / trap_risk.", styles["Cell"]),
     Paragraph("Non-zero for every item, including the direction_weight=0 ones \u2014 this is where PRE-1, "
               "PRE-5, ENG-1 etc. do their real work.", styles["Cell"])],
    [Paragraph("confidence_multiplier", styles["CellBold"]),
     Paragraph("Scales the whole cascade's trust level up or down (roughly 0.8\u20131.2).", styles["Cell"]),
     Paragraph("Driven mainly by PRE-1 (VIX regime) and ENG-1 (trend/chop gate). Never treat a backtest "
               "percentage (GIFT 75\u201385%, Supertrend follow-through, VIX\u2013Nifty corr., FII/DII R<super>2</super>) as "
               "an absolute law \u2014 use it only to modulate this multiplier and GO/NO-GO calls (v2, \u00a78).", styles["Cell"])],
]
t = Table(field_rows, colWidths=[35*mm, 65*mm, None])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), TEAL),
    ("GRID", (0, 0), (-1, -1), 0.5, HAIRLINE),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREY_HEAD]),
]))
story.append(t)
story.append(PageBreak())

# =========================================================================
# HELPER: build one item's compact v0.9 card
# =========================================================================
def item_row(iid, was, name, v08, v09, dw, cw, conf, changed):
    label_style = styles["FlagLabel"] if changed else styles["CellBold"]
    header = f"{iid} <font color='#787d86'>(was {was})</font> \u2014 {name}"
    tag = " &nbsp; <font color='#8a2b1f' size=7>[CORRECTED IN v0.9]</font>" if changed else " &nbsp; <font color='#787d86' size=7>[unchanged \u2014 see v0.8]</font>"
    rows = [
        [Paragraph(header + tag, styles["CellBold"])],
        [Paragraph(f"<b>v0.8 verdict:</b> {v08}", styles["Cell"])],
        [Paragraph(f"<b>v0.9:</b> {v09}", styles["Cell"])],
    ]
    body_tbl = Table(rows, colWidths=[PAGE_W - 2*MARGIN - 34*mm])
    body_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    weight_rows = [
        [Paragraph("dir_wt", styles["Small"])],
        [Paragraph(dw, styles["CellWeight"])],
        [Paragraph("ctx_wt", styles["Small"])],
        [Paragraph(cw, styles["CellWeight"])],
        [Paragraph("conf.", styles["Small"])],
        [Paragraph(conf, styles["CellWeight"])],
    ]
    weight_tbl = Table(weight_rows, colWidths=[30*mm])
    weight_tbl.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 1), ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    outer = Table([[body_tbl, weight_tbl]], colWidths=[PAGE_W - 2*MARGIN - 30*mm, 30*mm])
    bg = RED_LIGHT if changed else WHITE
    outer.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.6, HAIRLINE),
        ("LINEAFTER", (0,0), (0,0), 0.6, HAIRLINE),
        ("BACKGROUND", (0,0), (0,0), bg),
        ("BACKGROUND", (1,0), (1,0), TEAL_LIGHT),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    return KeepTogether([outer, Spacer(1, 5)])

# =========================================================================
# STAGE 1 - MACRO
# =========================================================================
story.append(stage_bar("STAGE 1 \u00b7 MACRO SCAN"))
story.append(Spacer(1, 8))

story.append(item_row(
    "MAC-1", "B4", "Global Macro News (Fed / Geopolitical / Commodity Shocks)",
    "Conditional event-gate / regime overlay. Neutral ~90% of days, dominant on rare event days.",
    "v2 tightens this: direction_weight = 0 on all <i>normal, non-event</i> days \u2014 including a live, "
    "grinding overhang (e.g. an unresolved geopolitical standoff) that hasn't produced a fresh acute shock. "
    "Only a genuinely new Fed/geopolitical/commodity shock may raise direction_weight above 0. A running "
    "overhang still raises trap_risk and lowers confidence_multiplier via context_weight \u2014 it just may not "
    "vote on direction by itself.",
    "0 (normal day) / event-conditional", "0.5", "1.0 baseline, \u21930.6\u20130.8 on live shocks",
    changed=True,
))
story.append(item_row(
    "MAC-2", "B6", "US / Asian Market Correlation",
    "Continuous correlation input (~0.68 30-day). Sets opening gap + first 30 min via cue alignment.",
    "No substantive change. v0.9 makes the decay explicit and numeric: direction_weight = 0.3 at/after "
    "the open, decaying to 0 by ~10:00 \u2014 formalizing v0.8's qualitative \u201cdecays by 10:00\u201d language.",
    "0.3 (open, decaying)", "0.7", "1.0",
    changed=False,
))
story.append(item_row(
    "MAC-3", "B12", "Macro Levels (DXY / US 10-Year Yield / Crude / Gold)",
    "Weekly/monthly directional input, threshold-banded. Near-zero intraday.",
    "No substantive change \u2014 v0.9 just assigns v0.8's \u201c~0 intraday\u201d language an explicit "
    "direction_weight = 0, with context_weight carrying the swing-regime backdrop.",
    "0 (intraday)", "0.4 (swing)", "1.0",
    changed=False,
))

# =========================================================================
# STAGE 2 - NATIONAL
# =========================================================================
story.append(stage_bar("STAGE 2 \u00b7 NATIONAL NEWS"))
story.append(Spacer(1, 8))
story.append(item_row(
    "NAT-1", "B5", "National News (RBI / Union Budget / Elections / Policy)",
    "Scheduled-event gate. Output is trade/no-trade + IV-crush warning, not a continuous weight.",
    "No substantive change. v0.9 hard-sets direction_weight = 0 (v0.8's sub-signal table had implied "
    "MED/LOW direction on some rows, e.g. RBI MPC \u2014 removed). NAT-1's job is entirely tradeable / size / "
    "trap_risk via context_weight; it never votes on direction, even on a genuine surprise (an election "
    "surprise raises trap_risk sharply instead).",
    "0", "0.3", "1.0, sharply reduced on event days",
    changed=False,
))

# =========================================================================
# STAGE 3 - FLOWS
# =========================================================================
story.append(stage_bar("STAGE 3 \u00b7 INSTITUTIONAL FLOWS"))
story.append(Spacer(1, 8))
story.append(item_row(
    "FLO-1", "C1", "FII/DII Daily Cash Flow",
    "Next-day/swing bias on net(FII+DII), 3\u20135 day rolling trend. ~0 same-day intraday.",
    "CORRECTED \u2014 this is the item that broke on 12 Aug 2026. v0.8 said \u201c~0 same-day intraday\u201d but "
    "left the door open for a 2\u20133 day cash-flow trend to be read as a same-day directional lean. v2 hard-sets "
    "direction_weight = 0 for <i>any</i> same-day use; FLO-1 only ever informs context_weight (next-day/swing "
    "bias) and must always use net(FII+DII), never FII alone. If FII and DII disagree sharply, flag it rather "
    "than netting silently.",
    "0 (same-day, hard)", "0.4 (next-day/swing)", "1.1 when net trend + DII absorption agree",
    changed=True,
))
story.append(item_row(
    "FLO-2", "C2", "FII Index Derivatives Positioning",
    "Next-day/multi-week signal. Confirmer via FII-vs-retail divergence, not a standalone trigger.",
    "CORRECTED alongside FLO-1 for the same reason. direction_weight = 0, always. Its only job is context: "
    "cross-check against FLO-1 to separate a directional short from a hedge before any confidence_multiplier "
    "adjustment is made \u2014 never assign it directional pull on its own, even when the hedge-vs-bet read is "
    "unambiguous.",
    "0 (hard)", "0.3", "1.0, unless FLO-1 cross-check flags a genuine bet (not hedge)",
    changed=True,
))

# =========================================================================
# STAGE 4 - PRE-MARKET
# =========================================================================
story.append(PageBreak())
story.append(stage_bar("STAGE 4 \u00b7 PRE-MARKET GATES"))
story.append(Spacer(1, 8))
story.append(item_row(
    "PRE-1", "G5", "India VIX Regime",
    "Master volatility gate. Zero directional weight; sets trade/no-trade, size, premium context.",
    "No substantive change \u2014 v0.9 hard-codes what v0.8 already argued: direction_weight = 0 across all "
    "horizons, structurally, not just as guidance. Its context_weight and confidence_multiplier role (cheap "
    "premium / GO when calm, size-down when elevated) is unchanged.",
    "0 (hard, all horizons)", "0.8", "1.2 when calm, <1.0 when elevated",
    changed=False,
))
story.append(item_row(
    "PRE-2", "G7", "GIFT Nifty Pre-market",
    "Most directional pre-market gate. Basis-adjusted implied gap; answers \u201cwhich way does Nifty open.\u201d",
    "CRITICAL FIX \u2014 the implied gap must be <b>basis-adjusted</b>: implied gap = (GIFT \u2212 prev cash close) "
    "minus the standing GIFT-to-cash carry premium (interest-rate differential, routinely 50\u2013100+ points). "
    "Never subtract GIFT's raw quoted level from the prior cash close directly \u2014 that ignores the structural "
    "premium and can invert the actual signal. Bucket the adjusted gap into three sizes (noise <0.2% / moderate "
    "0.2\u20130.5% / large >0.5%) before assigning direction_weight. This exact error (raw-level subtraction, no "
    "basis adjustment) produced a false gap-up call on 12 Aug 2026 \u2014 see Corrections Log.",
    "0.5 (open, decaying to 0 by ~10:00)", "0.7", "1.1 when basis-adjusted gap is moderate/large + no live overhang",
    changed=True,
))
story.append(item_row(
    "PRE-3", "E9", "Gap Up / Gap Down Behaviour",
    "Opening classifier: common / runaway / breakaway / exhaustion, via trend-alignment + ATR-size + VIX + no-news.",
    "The \u201cno-news\u201d precondition for a Runaway classification is tightened: it now excludes days with a "
    "live, unresolved macro overhang (e.g. an ongoing geopolitical/commodity standoff under MAC-1), not just "
    "scheduled calendar events (NAT-1/RBI/Budget). A moderate gap-up during a live overhang should be "
    "classified with reduced confidence, or reclassified toward \u201cprofit-booking / low-conviction\u201d rather "
    "than a clean Runaway continuation.",
    "0.4", "0.6", "1.1 in a clean Runaway; \u21930.7\u20130.9 if a live MAC-1 overhang is active",
    changed=True,
))
story.append(item_row(
    "PRE-4", "D8-11", "CPR (Central Pivot Range)",
    "Pre-market day-type forecast (narrow = trend, wide = range) + intraday S/R roadmap.",
    "CORRECTED \u2014 v0.8 bundled width and location into one discussion; v0.9 splits them explicitly. "
    "<b>Width</b> (narrow/wide) stays direction_weight = 0, context_weight only \u2014 it forecasts day-type, not "
    "side. <b>Location</b> (price relative to TC/BC/pivot at the open) gets its own small direction_weight when "
    "aligned with other cues \u2014 this was missed entirely in the 12-Aug retrospective (only width was checked).",
    "0 (width) / 0.2 (location, when aligned)", "0.6", "1.0",
    changed=True,
))
story.append(item_row(
    "PRE-5", "A7", "Calendar Day-Type / Seasonality",
    "Weekday theta/OI/gamma cycle map (post-Sep-2025 Tuesday-expiry regime). Never a direction.",
    "No substantive change \u2014 v0.9 hard-codes direction_weight = 0, explicitly. Outputs remain GO/NO-GO, "
    "day-type, and premium/theta prior only (e.g. Wednesday post-expiry \u2192 reduced size, do not force trades).",
    "0 (hard)", "0.8", "0.9 on Wednesday (post-expiry drift), 1.0 Thu/Fri, <1.0 Tue PM",
    changed=False,
))

# =========================================================================
# STAGE 5 - ENGINE
# =========================================================================
story.append(PageBreak())
story.append(stage_bar("STAGE 5 \u00b7 DIRECTION ENGINE"))
story.append(Spacer(1, 8))

eng_items = [
    dict(iid="ENG-1", was="D8-7", name="Regime Filter (ADX + Choppiness)",
         v08="Master gate: trade or chop. 0 directional weight; multiplies every other item's confidence.",
         v09="No substantive change. Pure regime gate, direction_weight = 0, structurally. Its output "
             "(trend vs chop) directly sets confidence_multiplier for the whole cascade, and blocks/reduces "
             "confidence for fast oscillators (ENG-6, ENG-10) when chop or a wide CPR is active \u2014 see "
             "\u00a76, Direction Sequence Enforcement, below.",
         dw="0 (hard)", cw="gate (multiplies conf.)", conf="0.6\u20131.3 depending on regime"),
    dict(iid="ENG-2", was="D8-6", name="EMAs Across Timeframes",
         v08="Structural backbone. EMA stack + slope per TF defines that TF's trend; 20/50/200 = dynamic S/R.",
         v09="No substantive change, but weight is now explicitly conditional: high direction_weight only "
             "when the multi-timeframe EMA stack/slope agrees with the Stage 1\u20134 macro/flow context \u2014 not "
             "as a standalone score.",
         dw="0.5\u20130.6 when aligned with context", cw="0.7", conf="1.1 on full alignment"),
    dict(iid="ENG-3", was="D8-2", name="RSI (Cardwell Ranges)",
         v08="Regime + leading shift via Cardwell ranges (bull 40\u201380, bear 20\u201360). Stronger/more leading than MACD.",
         v09="No substantive change \u2014 v0.9 encodes the asymmetry as an explicit rule: a ceiling rejection "
             "(e.g. failure at 55\u201360) is an exit/reduce-conviction signal, never a reversal entry; a "
             "confirmed range-shift break is the leading directional signal.",
         dw="0.4", cw="0.6", conf="1.0, asymmetric per rule above"),
    dict(iid="ENG-4", was="D8-1", name="MACD Crossover",
         v08="Lagging, price-derived. Demoted from primary to confirmation, weighted by multi-TF agreement.",
         v09="No substantive change. Restricted to higher-timeframe trend filter + confirmation; a raw "
             "low-timeframe crossover (e.g. 5-minute) carries direction_weight = 0 on its own.",
         dw="0.2 (confirm-only)", cw="0.5", conf="1.0"),
    dict(iid="ENG-5", was="D8-8", name="Supertrend",
         v08="ATR-based trend filter + dynamic trailing SL. Raw flips whipsaw (45\u201360% win) \u2014 use as filter.",
         v09="No substantive change. direction_weight > 0 only when a Supertrend flip is confirmed by VWAP "
             "and/or higher-timeframe alignment; an unconfirmed raw flip stays at 0.",
         dw="0.5 (when confirmed)", cw="0.5", conf="1.1 on VWAP+HTF confluence"),
    dict(iid="ENG-6", was="D8-3", name="Stochastic RSI",
         v08="Fastest, noisiest oscillator. Pure entry-timing trigger, gated hardest.",
         v09="No substantive change. direction_weight = 0, structurally \u2014 it may only trigger entries "
             "once regime and direction are already established by earlier stages; it never sets direction "
             "itself.",
         dw="0 (hard, timing only)", cw="0.4", conf="1.0"),
    dict(iid="ENG-7", was="D8-4", name="VWAP + SL Decisions",
         v08="Intraday anchor + SL hub. Above/below VWAP = call/put bias; also the four-SL framework.",
         v09="No substantive change. direction_weight is non-zero when price is clearly above/below VWAP "
             "with supporting volume; an oscillating flat VWAP keeps it at 0.",
         dw="0.5 (when clear)", cw="0.6", conf="1.1 with volume confirmation"),
    dict(iid="ENG-8", was="D8-5", name="Volume & Liquidity",
         v08="Conviction multiplier + hard tradeability gate. Never a direction signal.",
         v09="No substantive change. direction_weight = 0, hard. Its entire role is context_weight "
             "(conviction multiplier on a cascade-confirmed move) and a binary liquidity gate.",
         dw="0 (hard)", cw="0.6", conf="0.9\u20131.1 depending on RVOL/liquidity"),
    dict(iid="ENG-9", was="D8-10", name="ATR (Average True Range)",
         v08="Volatility backbone. 0 directional weight, essential plumbing for SL/sizing.",
         v09="No substantive change. direction_weight = 0, hard \u2014 informs volatility regime, SL distance, "
             "and position size only.",
         dw="0 (hard)", cw="0.7", conf="1.0"),
    dict(iid="ENG-10", was="D8-9", name="Bollinger Bands + Squeeze",
         v08="Squeeze = volatility-expansion timer. Tells \u201cwhen,\u201d not \u201cwhich way.\u201d",
         v09="No substantive change. Squeeze ON/FIRED states answer timing only (direction_weight = 0 while "
             "ON); direction comes only from the post-fire histogram/volume, and only once fired.",
         dw="0.2 (fired + histogram aligned)", cw="0.5", conf="1.0"),
    dict(iid="ENG-11", was="E10", name="Support & Resistance + OI Walls",
         v08="The \u2018where\u2019 map. Not a direction signal \u2014 defines entry/stall/pullback locations.",
         v09="No substantive change. direction_weight = 0, hard; defines zones only. Confluence (3+ level "
             "types stacking) raises confidence_multiplier, not direction.",
         dw="0 (hard)", cw="0.7", conf="1.1 on confluence zones (3+ types)"),
]
for e in eng_items:
    story.append(item_row(e["iid"], e["was"], e["name"], e["v08"], e["v09"], e["dw"], e["cw"], e["conf"], changed=False))

story.append(Spacer(1, 4))
story.append(Paragraph(
    "None of the 11 Stage-5 items required a substantive verdict change \u2014 v0.8's engine design already "
    "matched the v2 direction_weight/context_weight framework closely. What changed is that they must now "
    "actually be <b>run</b>: the 12-Aug-2026 retrospective issued a direction verdict from Stages 1\u20134 alone, "
    "with no Stage-5 pass at all (see Corrections Log, item 3).",
    styles["Body"]
))

# =========================================================================
# DIRECTION SEQUENCE ENFORCEMENT (updated)
# =========================================================================
story.append(PageBreak())
story.append(Paragraph("Direction Sequence Enforcement \u2014 Updated (v2, \u00a76\u20138)", styles["H1"]))
story.append(Paragraph(
    "v0.8 (page 34) already specified the gate-first, top-down pipeline: regime \u2192 higher-TF bias \u2192 "
    "direction confirm \u2192 location \u2192 timing \u2192 conviction \u2192 stop. v0.9 makes three additions explicit:",
    styles["Body"]))
for b in [
    "<b>Regime gate blocks fast oscillators, not just \u2018reduces confidence.\u2019</b> If ENG-1 shows chop or "
    "PRE-4 shows a wide CPR, ENG-6 (StochRSI) and ENG-10 (squeeze) must be blocked or have their weight sharply "
    "cut \u2014 not just noted as lower-conviction.",
    "<b>Higher-TF disagreement forces an explicit WAIT state.</b> If ENG-2/ENG-3 (higher-timeframe EMA/RSI) "
    "disagree with the intraday read, low-timeframe triggers (ENG-6, ENG-7, ENG-10) cannot override that "
    "disagreement to force a trade \u2014 the system must output WAIT, not a low-conviction directional call.",
    "<b>Backtest statistics modulate, never dictate.</b> Every sharp percentage cited anywhere in this document "
    "\u2014 GIFT's 75\u201385% opening-direction claim, Supertrend's ~65% filtered follow-through, the VIX\u2013Nifty "
    "\u22120.41 correlation, FII/DII's ~16.5% single-day R<super>2</super> \u2014 is a soft prior, not an absolute law. Use these "
    "only to modulate confidence_multiplier and GO/NO-GO decisions; never hard-wire a trade off one.",
]:
    story.append(Paragraph(f"\u2022 {b}", styles["Bullet"]))

story.append(Spacer(1, 6))
story.append(Paragraph("Expiry & Weekday Map \u2014 Hard-Coded (v2, \u00a77)", styles["H2"]))
story.append(Paragraph(
    "No change from v0.8's Weekday Day-Type Map (page 21): Nifty weekly options expire Tuesday, monthlies the "
    "last Tuesday; Sensex expires Thursday. v0.9's only addition is operational \u2014 hard-code this calendar "
    "in the build (rather than deriving it) and use it strictly to shape theta/gamma context (day-type, volume "
    "expectation, theta pressure, premium posture), never direction. Re-check the NSE circular for holiday "
    "shifts every week rather than assuming the weekday.",
    styles["Body"]))

# =========================================================================
# CORRECTIONS LOG
# =========================================================================
story.append(PageBreak())
story.append(stage_bar("APPENDIX \u00b7 CORRECTIONS LOG", color=RED_FLAG))
story.append(Spacer(1, 8))
story.append(Paragraph("Case Study: 12 August 2026", styles["H1"]))
story.append(Paragraph(
    "A pre-market run of Stages 1\u20134 (v0.8 logic, before this revision) produced a verdict of "
    "<b>Uptrend (mild)</b> for the 12 Aug 2026 NSE session. The actual session closed at 24,435.95, "
    "down 35.75 (-0.15%) from the prior close of 24,471.70, after an intraday reversal of roughly 300 points. "
    "The verdict was wrong on direction. This section documents why, and what changed as a result.",
    styles["Body"]))

story.append(note_box(styles["FlagLabel"], "Root cause",
    "PRE-2 (GIFT Nifty) was read by subtracting GIFT's raw quoted level (~24,547\u201324,564) from the prior "
    "cash close (24,471.70), producing a false <b>+0.3 to +0.4% gap-up</b> call. The correct, basis-adjusted "
    "read (netting out GIFT's standing carry premium over cash) was a <b>\u22120.29% gap-down</b>. Every "
    "downstream call \u2014 PRE-3's Runaway classification, the direction field of the verdict object, and the "
    "overall Uptrend call \u2014 inherited this single bad input. Fixed in this revision: PRE-2's entry above now "
    "mandates basis-adjustment and forbids raw-level subtraction.",
    RED_LIGHT, RED_FLAG))
story.append(Spacer(1, 6))

for label, body in [
    ("Secondary error \u2014 PRE-4 location skipped",
     "Only CPR width was computed (day-type context); the price-vs-pivot location \u2014 a legitimate small "
     "direction signal per the doc \u2014 was never checked. Fixed: PRE-4 above now splits width (context "
     "only) from location (small direction_weight when aligned)."),
    ("Secondary error \u2014 FLO-1/FLO-2 given directional pull they shouldn't have",
     "Both were informally classified \u201cUptrend\u201d in the retrospective sheet, despite v0.8 already saying "
     "same-day direction should be ~0. Fixed: both hard-set to direction_weight = 0 above, with no exceptions."),
    ("Secondary error \u2014 Stage 5 never run",
     "The verdict was issued from Stages 1\u20134 alone. A parallel run using ENG-2 (EMA), ENG-5 (Supertrend), "
     "and ENG-7 (VWAP) found all three leaning bearish intraday \u2014 confirmation that was available and unused. "
     "Fixed: no direction verdict should be issued without at least a partial Stage-5 pass when the underlying "
     "OHLC is available."),
    ("Secondary error \u2014 MAC-2 under-weighted",
     "A soft, risk-off overnight US close (Dow -0.34%, S&P -0.32%, Nasdaq -0.6%) was read as fully Neutral. "
     "Per the corrected MAC-2 weighting above (0.3 direction_weight at the open), it should have contributed a "
     "mild bearish lean rather than none."),
]:
    story.append(Paragraph(label, styles["NoteLabel"]))
    story.append(Paragraph(body, styles["BodySmall"]))
    story.append(Spacer(1, 6))

story.append(Spacer(1, 4))
story.append(Paragraph("Operational Safeguards (in force from v0.9 onward)", styles["H2"]))
for b in [
    "Never diff GIFT's raw quoted level against the cash close. Only use an explicitly stated basis-adjusted "
    "implied-gap figure, or a like-for-like futures-to-futures comparison.",
    "Treat any single-source pre-market gap read as unverified until cross-checked against a second source "
    "that states direction explicitly.",
    "Always compute PRE-4 location (price vs TC/BC/pivot), not width alone.",
    "Hold FLO-1, FLO-2, PRE-1, PRE-4 (width), PRE-5, ENG-1, ENG-6, ENG-8, ENG-9, ENG-11 at direction_weight = 0 "
    "structurally \u2014 this is a build rule, not a per-run judgment call.",
    "Never issue a direction verdict without at least a partial Stage-5 pass (ENG-2, ENG-5, ENG-7 at minimum) "
    "when intraday OHLC is available.",
    "Flag low-confidence or single-source inputs explicitly in the output rather than silently treating them "
    "as facts \u2014 applies to CPR OHLC, GIFT reads, and any scraped/estimated figure alike.",
]:
    story.append(Paragraph(f"\u2022 {b}", styles["Bullet"]))

doc.build(story)
print("built v0.9 PDF")
