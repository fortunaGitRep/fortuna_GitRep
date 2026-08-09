#!/usr/bin/env python3
# FORTUNA · F_capital · Calculate Capital · v01
# Reuses the Branch A / v0.8 scaffold verbatim (palette, styles, helpers).

import fortuna_scaffold as fs
from fortuna_scaffold import *
from reportlab.platypus import NextPageTemplate

fs.FOOTER_LEFT = "FORTUNA · F_capital · Calculate Capital · v01"

story = []

cst     = mk("cst",     fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=AMBER)
cintro  = mk("cintro",  fontName="Helvetica", fontSize=10, leading=15, textColor=TEAL_L)
cintro2 = mk("cintro2", fontName="Helvetica", fontSize=9,  leading=14,
             textColor=colors.HexColor("#9fc9c9"))
PEND = colors.HexColor("#b07a12")

codeS = mk("codeS", fontName="Courier", fontSize=8.2, leading=11.6, textColor=INK)


def pend_stamp(text):
    return callout("<b>STATUS - PENDING.</b> " + text,
                   bg=colors.HexColor("#fbf0d8"), bar=PEND, tcolor=INK)


def code_block(lines, label=None):
    """Monospace config block — this document is written to be translated to code."""
    rows = []
    if label:
        rows.append([Paragraph(label, mk("cl", fontName="Helvetica-Bold", fontSize=7.6,
                                         leading=10, textColor=TEAL_DK))])
    for ln in lines:
        rows.append([Paragraph(ln.replace(" ", "&nbsp;"), codeS)])
    t = Table(rows, colWidths=[CONTENT_W])
    st = [
        ("BACKGROUND", (0, 0), (-1, -1), GREY_L),
        ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
    ]
    st.append(("TOPPADDING", (0, 0), (0, 0), 7))
    st.append(("BOTTOMPADDING", (0, len(rows) - 1), (0, len(rows) - 1), 7))
    t.setStyle(TableStyle(st))
    return t


class AllocatorTree(Flowable):
    """Single input -> phase+split engine -> three sleeves -> consuming documents."""

    def __init__(self, w=CONTENT_W):
        super().__init__()
        self.w = w
        self.h = 205

    def wrap(self, aw, ah):
        return (self.w, self.h)

    def draw(self):
        c = self.canv
        W = self.w
        cx = W / 2
        top = self.h - 6

        def box(cxp, cy, w, h, fill, txt, sub=None, tcol=WHITE, tsize=8.8, ssize=6.6):
            c.setFillColor(fill)
            c.roundRect(cxp - w / 2, cy - h, w, h, 3, fill=1, stroke=0)
            c.setFillColor(tcol)
            c.setFont("Helvetica-Bold", tsize)
            if sub:
                c.drawCentredString(cxp, cy - h / 2 + 2.5, txt)
                c.setFont("Helvetica", ssize)
                c.drawCentredString(cxp, cy - h / 2 - 7.5, sub)
            else:
                c.drawCentredString(cxp, cy - h / 2 - 1, txt)

        def vline(x, y1, y2):
            c.setStrokeColor(GREY)
            c.setLineWidth(1)
            c.line(x, y1, x, y2)

        def hline(x1, x2, y):
            c.setStrokeColor(GREY)
            c.setLineWidth(1)
            c.line(x1, y, x2, y)

        # input
        y = top
        box(cx, y, W * 0.56, 30, INK, "TOTAL FORTUNA CAPITAL",
            "the single input  -  any amount", tsize=9.2)
        vline(cx, y - 30, y - 46)

        # engine
        y2 = y - 46
        box(cx, y2, W * 0.72, 32, TEAL_XdK, "F_capital  .  phase ladder  +  split engine",
            "phase decides which sleeves are live  |  split decides the ratio", tsize=9)
        vline(cx, y2 - 32, y2 - 48)

        # three sleeves
        y3 = y2 - 48
        hline(W * 0.17, W * 0.83, y3)
        sw = W * 0.29
        xs = [W * 0.17, W * 0.50, W * 0.83]
        labels = [("LONG-TERM", "60%", TEAL_DK),
                  ("SWING", "30%", TEAL),
                  ("OPTIONS", "10%  ring-fenced", AMBER)]
        for x, (nm, pc, col) in zip(xs, labels):
            vline(x, y3, y3 - 12)
            box(x, y3 - 12, sw, 30, col, nm, pc, tsize=8.6, ssize=6.8)

        # consumers
        y4 = y3 - 12 - 30 - 16
        cons = ["F_cash_long_term", "F_cash_swing  .  Section 1", "Fortuna-Index  .  sizing"]
        for x, nm in zip(xs, cons):
            vline(x, y3 - 42, y4)
            c.setFillColor(GREY_L)
            c.roundRect(x - sw / 2, y4 - 22, sw, 22, 3, fill=1, stroke=0)
            c.setStrokeColor(LINE)
            c.setLineWidth(0.6)
            c.roundRect(x - sw / 2, y4 - 22, sw, 22, 3, fill=0, stroke=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7.2)
            c.drawCentredString(x, y4 - 14, nm)

        c.setFillColor(GREY)
        c.setFont("Helvetica-Oblique", 6.8)
        c.drawCentredString(cx, 6,
                            "F_capital is not a branch. It is a shared utility - both branches "
                            "consume it, neither owns it.")


# ======================= COVER =======================
story += [
    NextPageTemplate("body"),
    Spacer(1, 30 * mm),
    Paragraph("FORTUNA", titleBig),
    Spacer(1, 3),
    Paragraph("Calculate Capital", cst),
    Spacer(1, 10),
    Paragraph("F_capital &nbsp;|&nbsp; shared utility &nbsp;|&nbsp; CAP- &nbsp;|&nbsp; v01 "
              "&nbsp;|&nbsp; allocator", titleSub),
    Spacer(1, 16 * mm),
    Paragraph("The tool that converts one input &mdash; total capital committed to Fortuna &mdash; "
              "into the rupee allocation every other Fortuna document consumes. It is "
              "<b>not a branch</b>. It sits beside the trunk and feeds both: Section 1 of "
              "<b>F_cash_swing</b> (deployable cash, buckets, position sizing) and the sizing "
              "layer of <b>Fortuna-Index</b> (Branch A). Allocation is expressed in "
              "<b>percentages, never rupees</b>, so it scales with whatever capital exists.", cintro),
    Spacer(1, 8),
    Paragraph("v01 fixes the <b>phase ladder</b> and the <b>two splits</b>. The structural rules "
              "&mdash; ring-fencing, no top-up, sleeve-relative risk, percent-based allocation "
              "&mdash; are LOCKED. The actual percentages are PROVISIONAL and get re-finalised "
              "per-strategy once each trading document has a measured risk profile. Personal "
              "internal framework, not investment advice.", cintro2),
    PageBreak(),
]

# ======================= WHERE IT SITS =======================
story += [
    Paragraph("Where F_capital Sits", h1),
    HBar(color=AMBER, thick=1.4), sp(4),
    Paragraph("Every other Fortuna document asks the same question in a different costume: "
              "<i>how much money do I put on this?</i> Answering it separately in each document "
              "guarantees the answers drift apart and quietly overlap. F_capital answers it once, "
              "upstream, and the branches inherit the number rather than deriving it.", lead),
    sp(4),
    AllocatorTree(),
    PageBreak(),
]

# ======================= THE TWO SPLITS =======================
story += [
    Paragraph("The Two Splits", h1),
    HBar(color=TEAL, thick=1.4), sp(4),
    Paragraph("There are two independent splits, and collapsing them into one is the error this "
              "document exists to prevent. <b>Split 1</b> divides total capital across the three "
              "sleeves. <b>Split 2</b> governs behaviour <i>inside</i> a sleeve. They use the same "
              "word &mdash; percent &mdash; but of different denominators.", body),
    sp(5),

    Paragraph("Split 1 &mdash; total capital into sleeves", h3),
    code_block([
        "SLEEVE_LONG_TERM   = 0.60      # compounding base",
        "SLEEVE_SWING       = 0.30      # positive-expectancy middle",
        "SLEEVE_OPTIONS     = 0.10      # ring-fenced, never topped up",
        "",
        "assert sum(SLEEVES) == 1.00",
    ], label="SPLIT 1"),
    sp(6),

    Paragraph("Split 2 &mdash; inside the swing sleeve", h3),
    code_block([
        "SWING_MAX_DEPLOYED   = 0.75    # of SWING sleeve, not of total",
        "SWING_MIN_RESERVE    = 0.25",
        "SWING_MAX_POSITIONS  = 6       # range 5-8",
        "SWING_RISK_PER_TRADE = 0.01    # of SWING sleeve, not of total",
        "",
        "position_size = (SWING_SLEEVE * SWING_RISK_PER_TRADE)",
        "                / stop_distance_pct",
    ], label="SPLIT 2"),
    sp(7),

    Paragraph("Correction carried into v01", h3),
    callout("<b>Risk is measured against the sleeve, not against total capital.</b> An earlier "
            "working note said &lsquo;risk 1-2% of total capital per trade&rsquo;. That is wrong "
            "once sleeves exist. If swing is 30% of total, then 1.5% of total is <b>5% of the "
            "swing sleeve</b> per trade &mdash; six open positions would put 30% of the sleeve at "
            "risk simultaneously. At 1% of <i>sleeve</i>, six positions risk 6% of the sleeve, "
            "which is 1.8% of total capital. That is the sane version and the one this document "
            "carries.", bg=RED_L, bar=RED),
    sp(6),
    callout("<b>Why percent and not rupees.</b> The rupee figure changes every time income is "
            "routed in (post-Midas) or a sleeve compounds. A percentage survives all of that, so "
            "F_capital never needs re-deciding &mdash; only re-running.", bg=TEAL_L, bar=TEAL,
            tcolor=INK),
    PageBreak(),
]

# ======================= PHASE LADDER =======================
story += [
    Paragraph("The Phase Ladder", h1),
    HBar(color=AMBER, thick=1.4), sp(4),
    Paragraph("Capital starts at zero and all three sleeves do not switch on together. The ladder "
              "below is the activation order: prove the index engine on a small fixed amount, add "
              "swing once Fortuna itself is built, and only reach the 60/30/10 steady state once "
              "there is enough capital for the percentages to be executable at all.", lead),
    sp(4),
    generic_table(
        ["Phase", "Live sleeves", "Split rule", "Exit condition"],
        [
            ["CAP-P1<br/>Prove",
             "OPTIONS only",
             "fixed &#8377; test amount<br/><i>deliberately not a %</i>",
             "index strategy proven &mdash; threshold PENDING"],
            ["CAP-P2<br/>Add swing",
             "SWING + OPTIONS",
             "SWING : OPTIONS = 75 : 25",
             "total capital &ge; ~&#8377;10L <i>and</i> Midas live"],
            ["CAP-P3<br/>Steady",
             "all three",
             "60 / 30 / 10",
             "&mdash; (terminal state)"],
        ],
        [CONTENT_W * 0.15, CONTENT_W * 0.19, CONTENT_W * 0.28, CONTENT_W * 0.38]),
    sp(7),

    Paragraph("CAP-P1 &mdash; why options first, and why a fixed rupee amount", h3),
    Paragraph("The index engine is the piece being built first, so it is the piece that gets "
              "tested first. Expressing this sleeve as a percentage at this stage would be "
              "arithmetic theatre &mdash; 10% of a small test pot is not enough to buy a lot. It "
              "is therefore a <b>fixed rupee amount chosen for what it can lose</b>, not a share "
              "of anything. The percentage only becomes meaningful in CAP-P3.", body),
    sp(2),
    Paragraph("CAP-P2 &mdash; why swing joins second", h3),
    Paragraph("Swing needs Fortuna-Cash to exist (Layer 1 universe, S1/S2, triggers, rank) before "
              "it can be traded systematically rather than by feel. It also needs a routed income "
              "stream to grow, which is a Midas dependency. Until both exist, adding a swing "
              "sleeve adds exposure without adding process. The 75:25 ratio keeps options "
              "proportionally small while the total pot is still building.", body),
    sp(2),
    Paragraph("CAP-P3 &mdash; why long-term is last, not first", h3),
    Paragraph("This is deliberately counter-intuitive. The long-term sleeve is the largest and "
              "does the actual wealth work, so instinct says fund it first. But the sequencing "
              "constraint here is <i>tooling</i>, not returns: Fortuna must reach a state of "
              "producing verifiable trading income before capital is committed at scale. Funding "
              "the 60% early would be sound investing but would not test anything, and the whole "
              "point of the ladder is that each rung has to be earned.", body),
    PageBreak(),
]

# ======================= EXECUTABILITY FLOOR =======================
story += [
    Paragraph("Why the Ladder Exists &mdash; the Executability Floor", h1),
    HBar(color=TEAL, thick=1.4), sp(4),
    Paragraph("A percentage split is only a plan if the resulting rupee amount can actually be "
              "traded. Below a certain total capital, 60/30/10 is arithmetic that produces "
              "unexecutable positions. The floor is set by the option lot, which is a hard "
              "regulatory unit and not negotiable.", body),
    sp(4),

    Paragraph("The atomic unit", h3),
    Paragraph("SEBI targets an index contract value of &#8377;15-20 lakh. The Nifty lot size moved "
              "25 &rarr; 75 (Nov 2024) &rarr; <b>65</b> (effective 31 Dec 2025 / Jan 2026, NSE "
              "circular FAOP70616) as index levels rose. At a &#8377;150-200 premium that is "
              "roughly <b>&#8377;10,000-13,000 of premium at risk per lot</b>. A sleeve that "
              "cannot absorb a run of consecutive losses at that unit size is not a sleeve &mdash; "
              "call it ten lots of buffer as the minimum, so <b>&#8377;1-1.5 lakh</b>.", body),
    sp(2),
    callout("<b>Read the lot size at runtime.</b> It has been revised twice in ~14 months and is "
            "revised whenever index levels drift the contract value out of the &#8377;15-20L band. "
            "Fortuna must pull it from the broker / NSE, never hardcode it. One low-quality source "
            "claims 50 &mdash; the 65 figure carries the circular reference. Verify on Dhan before "
            "lock-in.", bg=AMBER_L, bar=AMBER),
    sp(7),

    Paragraph("Options sleeve at 10% &mdash; executability by capital", h3),
    generic_table(
        ["Total capital", "Options sleeve", "Lots of buffer", "Verdict"],
        [
            ["&#8377;1 L", "&#8377;10,000", "0 - 1", "not executable"],
            ["&#8377;3 L", "&#8377;30,000", "~3", "fragile"],
            ["&#8377;5 L", "&#8377;50,000", "~5", "fragile"],
            ["&#8377;10 L", "&#8377;1.0 L", "~9", "minimum viable"],
            ["&#8377;15 L", "&#8377;1.5 L", "~14", "comfortable"],
        ],
        [CONTENT_W * 0.22, CONTENT_W * 0.24, CONTENT_W * 0.22, CONTENT_W * 0.32],
        center_cols=(1, 2, 3)),
    sp(6),

    Paragraph("Swing sleeve at 30% &mdash; per-position size by capital", h3),
    generic_table(
        ["Total capital", "Swing sleeve", "Deployed (75%)", "Per position (6)", "Verdict"],
        [
            ["&#8377;5 L", "&#8377;1.50 L", "&#8377;1.12 L", "~&#8377;18,700", "friction-heavy"],
            ["&#8377;10 L", "&#8377;3.00 L", "&#8377;2.25 L", "~&#8377;37,500", "workable"],
            ["&#8377;15 L", "&#8377;4.50 L", "&#8377;3.37 L", "~&#8377;56,000", "comfortable"],
        ],
        [CONTENT_W * 0.19, CONTENT_W * 0.19, CONTENT_W * 0.20, CONTENT_W * 0.21,
         CONTENT_W * 0.21],
        center_cols=(1, 2, 3, 4)),
    sp(6),
    callout("<b>Conclusion.</b> The 60/30/10 split becomes executable at roughly "
            "<b>&#8377;10-15 lakh total</b>. Below that, sleeves run <i>sequentially</i> (the "
            "phase ladder) rather than simultaneously. This is the entire justification for "
            "phasing &mdash; it is a constraint, not a preference.", bg=TEAL_L, bar=TEAL,
            tcolor=INK),
    PageBreak(),
]

# ======================= RULES: PROS AND COSTS =======================
story += [
    Paragraph("The Structural Rules &mdash; What Each Buys, What Each Costs", h1),
    HBar(color=AMBER, thick=1.4), sp(4),
    Paragraph("These six rules are LOCKED. They are structural, so they hold regardless of what "
              "the percentages eventually settle at. Each is stated with its cost, because a rule "
              "presented without its downside is a rule nobody stress-tests.", lead),
    sp(4),
    generic_table(
        ["Rule", "What it buys", "What it costs"],
        [
            ["CAP-R1<br/>Options sleeve ring-fenced,<br/>never topped up",
             "Caps total lifetime loss from the highest-variance activity at a known number. A "
             "losing sleeve cannot quietly eat the portfolio, which is the single most common way "
             "retail options accounts die.",
             "If the strategy is genuinely good, a drawdown followed by no refill means "
             "under-participating in the recovery. Refill only from realised options profit or a "
             "scheduled annual re-fund."],
            ["CAP-R2<br/>Risk measured against<br/>the sleeve, not total",
             "Keeps concurrent-position risk bounded. Six positions at 1% of sleeve = 6% of "
             "sleeve = 1.8% of total. The total-capital version silently runs 3-5x hotter.",
             "Per-trade rupee risk is smaller at low capital, so fixed costs (brokerage, STT, "
             "slippage) become a larger share of the risked amount."],
            ["CAP-R3<br/>Reserve floor inside swing<br/>(25%)",
             "Dry powder for adding to winners and for the setups that only appear after a "
             "market-wide flush, which is exactly when a fully-deployed account is paralysed.",
             "Structural cash drag. In a strong trending market the reserve is the part of the "
             "sleeve that earned nothing."],
            ["CAP-R4<br/>Long-term sleeve<br/>is not raidable",
             "Keeps the compounding base actually compounding, and preserves the LTCG treatment "
             "that a churned position forfeits. Prevents swing conviction from cannibalising "
             "the base.",
             "Occasionally the best available opportunity will be in swing while the capital "
             "sits in long-term. The rule means that opportunity is declined."],
            ["CAP-R5<br/>Allocation in percent,<br/>never rupees",
             "Survives every capital change. F_capital is re-run, never re-decided. Directly "
             "code-translatable as a config constant.",
             "Percentages are meaningless below the executability floor, which is why CAP-R6 "
             "has to exist alongside it."],
            ["CAP-R6<br/>Phased activation,<br/>not day-one 60/30/10",
             "Each sleeve is earned by evidence rather than assumed. Limits damage from a "
             "strategy that looked good on paper and is not.",
             "Slower ramp; the long-term sleeve stays under-funded for longer than a pure "
             "investing view would recommend."],
        ],
        [CONTENT_W * 0.20, CONTENT_W * 0.40, CONTENT_W * 0.40]),
    PageBreak(),
]

# ======================= PARAMETER REGISTER =======================
story += [
    Paragraph("Parameter Register", h1),
    HBar(color=TEAL, thick=1.4), sp(4),
    Paragraph("The code-facing surface of this document. Every row becomes a named constant. "
              "<b>LOCKED</b> = structural, will not move. <b>PROVISIONAL</b> = a working number "
              "that will be re-finalised when the owning strategy document is drilled. "
              "<b>PENDING</b> = no value yet.", lead),
    sp(4),
    generic_table(
        ["Parameter", "Value", "Denominator", "Status"],
        [
            ["SLEEVE_LONG_TERM", "0.60", "total capital", "PROVISIONAL"],
            ["SLEEVE_SWING", "0.30", "total capital", "PROVISIONAL"],
            ["SLEEVE_OPTIONS", "0.10", "total capital", "PROVISIONAL"],
            ["OPTIONS_TOPUP_ALLOWED", "False", "&mdash;", "LOCKED"],
            ["LONG_TERM_RAIDABLE", "False", "&mdash;", "LOCKED"],
            ["ALLOCATION_MODE", "percent", "&mdash;", "LOCKED"],
            ["SWING_MAX_DEPLOYED", "0.75", "swing sleeve", "PROVISIONAL"],
            ["SWING_MIN_RESERVE", "0.25", "swing sleeve", "PROVISIONAL"],
            ["SWING_MAX_POSITIONS", "6", "count", "PROVISIONAL"],
            ["SWING_RISK_PER_TRADE", "0.01", "swing sleeve", "PROVISIONAL"],
            ["P1_TEST_AMOUNT", "&mdash;", "fixed &#8377;", "PENDING"],
            ["P1_EXIT_THRESHOLD", "&mdash;", "trades / months / expectancy", "PENDING"],
            ["P2_EXIT_CAPITAL", "~&#8377;10 L", "total capital", "PROVISIONAL"],
            ["NIFTY_LOT_SIZE", "65", "units &mdash; read at runtime", "EXTERNAL"],
            ["OPT_MAX_LOTS_PER_TRADE", "&mdash;", "count", "PENDING &rarr; Branch A"],
            ["OPT_DAILY_LOSS_CAP", "&mdash;", "options sleeve", "PENDING &rarr; Branch A"],
        ],
        [CONTENT_W * 0.30, CONTENT_W * 0.16, CONTENT_W * 0.32, CONTENT_W * 0.22],
        center_cols=(1, 3)),
    sp(6),
    pend_stamp("Six parameters have no value. Four of them (P1_TEST_AMOUNT, P1_EXIT_THRESHOLD, "
               "OPT_MAX_LOTS_PER_TRADE, OPT_DAILY_LOSS_CAP) block CAP-P1 from actually starting. "
               "The two OPT_ parameters belong to Fortuna-Index, not here &mdash; F_capital only "
               "reserves the slot."),
    PageBreak(),
]

# ======================= TRACKER + OPEN QUESTIONS =======================
story += [
    Paragraph("F_capital . Tracker", h1),
    HBar(color=AMBER, thick=1.4), sp(4),
    generic_table(
        ["Area", "Decided", "Status"],
        [
            ["Document role", "Shared utility, not a branch; prefix CAP-", "LOCKED"],
            ["Split model", "Two splits: sleeves, then inside-sleeve", "LOCKED"],
            ["Risk denominator", "Sleeve, never total capital", "LOCKED"],
            ["Options top-up", "Never; realised profit or annual re-fund only", "LOCKED"],
            ["Long-term raiding", "Not permitted", "LOCKED"],
            ["Allocation unit", "Percent, not rupees", "LOCKED"],
            ["Phase ladder", "P1 options &rarr; P2 +swing &rarr; P3 all three", "LOCKED"],
            ["Sleeve percentages", "60 / 30 / 10", "PROVISIONAL"],
            ["Swing internals", "75/25, 6 positions, 1% risk", "PROVISIONAL"],
            ["Phase-1 exit test", "Definition of &lsquo;proven&rsquo;", "PENDING"],
            ["Options internals", "Lots per trade, daily loss cap", "PENDING (Branch A)"],
            ["Phase-2 idle long-term", "What the unfunded 60% does meanwhile", "PENDING"],
        ],
        [CONTENT_W * 0.24, CONTENT_W * 0.50, CONTENT_W * 0.26]),
    sp(8),

    Paragraph("Open Questions", h2),
    HBar(color=TEAL, thick=1.0), sp(4),
    generic_table(
        ["#", "Question", "Why it blocks"],
        [
            ["CAP-Q1",
             "What defines &lsquo;index strategy proven&rsquo;? Suggested: minimum 100 trades "
             "<i>and</i> 3 months, judged on net-of-cost expectancy rather than win rate.",
             "Without a number the phase ladder is a vibe, not a gate. Blocks P1 &rarr; P2."],
            ["CAP-Q2",
             "Is swing risk-per-trade really 1%? At 1% of a &#8377;3L sleeve that is &#8377;3,000 "
             "risked &mdash; friction is a meaningful share of it. Case for 1.5% until the sleeve "
             "grows.",
             "Sets position size in F_cash_swing Section 1."],
            ["CAP-Q3",
             "SWING_MAX_POSITIONS fixed at 6, or scaled by capital (5 below &#8377;5L, 8 above "
             "&#8377;15L)?",
             "Changes bucket count and therefore per-position size."],
            ["CAP-Q4",
             "What is P1_TEST_AMOUNT in rupees, and can it lose 100% without affecting anything "
             "else?",
             "CAP-P1 cannot start without it."],
            ["CAP-Q5",
             "During CAP-P2 the long-term 60% is unfunded. Should surplus route to index funds so "
             "it is not cash-drag for a year, or stay uncommitted?",
             "Affects real return during the whole ramp."],
            ["CAP-Q6",
             "Do the sleeve percentages themselves shift by phase, or is 60/30/10 only ever the "
             "terminal state?",
             "Determines whether F_capital needs per-phase ratio tables."],
        ],
        [CONTENT_W * 0.10, CONTENT_W * 0.52, CONTENT_W * 0.38]),
    sp(8),
    callout("<b>Next active step.</b> Answer CAP-Q1 and CAP-Q4 &mdash; they are the only two that "
            "block CAP-P1 from starting. Everything else can wait until the owning strategy "
            "document is drilled. Percentages are revisited after each of F_cash_swing Section 3 "
            "and Branch A sizing produce a measured risk profile.", bg=AMBER_L, bar=AMBER),
    sp(10),
    Paragraph("DOCUMENT ENDS HERE", mk("end", fontName="Helvetica-Bold", fontSize=8,
                                       leading=11, textColor=GREY)),
    Paragraph("FORTUNA &mdash; F_capital . Calculate Capital . v01 . Confidential — Internal Use "
              "Only", tiny),
]

doc = Doc("/home/claude/Fortuna_Calculate_Capital_v01.pdf")
doc.build(story)
print("BUILT OK")
