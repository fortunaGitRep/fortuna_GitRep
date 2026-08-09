#!/usr/bin/env python3
# FORTUNA · Foundation List · Direction Funnel · Track A · v0.8 build script
# Regenerated from the v0.7 document structure. Teal trunk / amber output aesthetic.

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, Flowable
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

# ---------- palette ----------
INK       = colors.HexColor("#1b2733")
INK_SOFT  = colors.HexColor("#3d4b59")
TEAL      = colors.HexColor("#0f8b8d")
TEAL_DK   = colors.HexColor("#0a5d5f")
TEAL_XdK  = colors.HexColor("#083f41")
TEAL_L    = colors.HexColor("#e2f2f2")
AMBER     = colors.HexColor("#d98a1f")
AMBER_DK  = colors.HexColor("#a8660f")
AMBER_L   = colors.HexColor("#fdf1dc")
GREEN     = colors.HexColor("#2f8f5b")
GREEN_L   = colors.HexColor("#e6f4ec")
RED       = colors.HexColor("#c0453a")
RED_L     = colors.HexColor("#f8e9e7")
GREY      = colors.HexColor("#6b7885")
GREY_L    = colors.HexColor("#f2f5f6")
GREY_LL   = colors.HexColor("#f8fafb")
LINE      = colors.HexColor("#d5dde2")
WHITE     = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm

# ---------- styles ----------
ss = getSampleStyleSheet()

def mk(name, **kw):
    parent = kw.pop("parent", ss["Normal"])
    return ParagraphStyle(name, parent=parent, **kw)

body = mk("body", fontName="Helvetica", fontSize=9.3, leading=13.5,
          textColor=INK, alignment=TA_JUSTIFY, spaceAfter=5)
body_l = mk("body_l", parent=body, alignment=TA_LEFT, spaceAfter=4)
lead = mk("lead", fontName="Helvetica", fontSize=9.6, leading=14.5, textColor=INK_SOFT,
          alignment=TA_LEFT, spaceAfter=6)
small = mk("small", fontName="Helvetica", fontSize=8.2, leading=11, textColor=GREY, alignment=TA_LEFT)
tiny = mk("tiny", fontName="Helvetica", fontSize=7.4, leading=9.5, textColor=GREY)

h1 = mk("h1", fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=TEAL_DK, spaceAfter=3, spaceBefore=2)
h2 = mk("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=INK, spaceAfter=4, spaceBefore=8)
h3 = mk("h3", fontName="Helvetica-Bold", fontSize=9.6, leading=13, textColor=TEAL_DK, spaceAfter=3, spaceBefore=6)

# cell styles
cH  = mk("cH",  fontName="Helvetica-Bold", fontSize=8.0, leading=10, textColor=WHITE, alignment=TA_LEFT)
cB  = mk("cB",  fontName="Helvetica", fontSize=8.0, leading=10.5, textColor=INK, alignment=TA_LEFT)
cBb = mk("cBb", fontName="Helvetica-Bold", fontSize=8.0, leading=10.5, textColor=INK, alignment=TA_LEFT)
cC  = mk("cC",  fontName="Helvetica-Bold", fontSize=7.7, leading=10, textColor=WHITE, alignment=TA_CENTER)
cNote = mk("cNote", fontName="Helvetica", fontSize=7.5, leading=9.8, textColor=INK_SOFT, alignment=TA_LEFT)

titleBig = mk("titleBig", fontName="Helvetica-Bold", fontSize=40, leading=42, textColor=WHITE, alignment=TA_LEFT)
titleSub = mk("titleSub", fontName="Helvetica", fontSize=11, leading=16, textColor=TEAL_L, alignment=TA_LEFT)
divTitle = mk("divTitle", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=WHITE, alignment=TA_LEFT)
divSub   = mk("divSub", fontName="Helvetica", fontSize=10.5, leading=15, textColor=TEAL_L, alignment=TA_LEFT)
hdrWhite = mk("hdrWhite", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=WHITE, alignment=TA_LEFT)
hdrMeta  = mk("hdrMeta", fontName="Helvetica", fontSize=8, leading=11, textColor=TEAL_L, alignment=TA_LEFT)

# ---------- helpers ----------
def sp(h=6): return Spacer(1, h)

def P(txt, style=body): return Paragraph(txt, style)

def stance_color(s):
    s = s.upper()
    if s == "TRADE": return GREEN, GREEN_L
    if s == "CAUTION": return AMBER_DK, AMBER_L
    if s == "AVOID": return RED, RED_L
    return GREY, GREY_L

CONTENT_W = PAGE_W - 2*MARGIN

class HBar(Flowable):
    """thin colored rule"""
    def __init__(self, w=CONTENT_W, color=TEAL, thick=1.2):
        super().__init__(); self.w=w; self.color=color; self.thick=thick
    def wrap(self, aw, ah): return (self.w, self.thick+2)
    def draw(self):
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(self.thick)
        self.canv.line(0, 1, self.w, 1)

class Band(Flowable):
    """full-width colored band with white bold text (section header inside flow)"""
    def __init__(self, text, color=TEAL_DK, h=22, size=11, tcolor=WHITE, w=CONTENT_W, pad=7):
        super().__init__(); self.text=text; self.color=color; self.h=h; self.size=size
        self.tcolor=tcolor; self.w=w; self.pad=pad
    def wrap(self, aw, ah): return (self.w, self.h)
    def draw(self):
        c=self.canv; c.setFillColor(self.color); c.roundRect(0,0,self.w,self.h,2,fill=1,stroke=0)
        c.setFillColor(self.tcolor); c.setFont("Helvetica-Bold", self.size)
        c.drawString(self.pad, self.h/2 - self.size*0.34, self.text)

def callout(text, bg=AMBER_L, bar=AMBER, tcolor=INK):
    para = Paragraph(text, mk("calloutP", fontName="Helvetica", fontSize=8.6, leading=12,
                              textColor=tcolor, alignment=TA_LEFT))
    t = Table([[para]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),bg),
        ("LINEABOVE",(0,0),(-1,0),0,bg),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LINEBEFORE",(0,0),(0,-1),3,bar),
    ]))
    return t

# ---------- table builders ----------
def signal_table(rows, headers=("Sub-signal","Direction","Volatility","Trade stance","Note")):
    col_w = [CONTENT_W*0.24, CONTENT_W*0.13, CONTENT_W*0.12, CONTENT_W*0.14, CONTENT_W*0.37]
    data = [[Paragraph(h, cC if i in (1,2,3) else cH) for i,h in enumerate(headers)]]
    style = [
        ("BACKGROUND",(0,0),(-1,0),TEAL_DK),
        ("LINEBELOW",(0,0),(-1,0),0.4,TEAL_DK),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("ALIGN",(1,0),(3,-1),"CENTER"),
        ("LINEBELOW",(0,1),(-1,-1),0.3,LINE),
    ]
    r = 1
    for sub, dirn, vol, stance, note in rows:
        fg,bg = stance_color(stance)
        data.append([
            Paragraph(sub, cBb),
            Paragraph(dirn, mk("d",fontName="Helvetica-Bold",fontSize=7.6,leading=9.5,textColor=INK_SOFT,alignment=TA_CENTER)),
            Paragraph(vol, mk("v",fontName="Helvetica",fontSize=7.6,leading=9.5,textColor=INK_SOFT,alignment=TA_CENTER)),
            Paragraph(stance, mk("s",fontName="Helvetica-Bold",fontSize=7.6,leading=9.5,textColor=fg,alignment=TA_CENTER)),
            Paragraph(note, cNote),
        ])
        style.append(("BACKGROUND",(3,r),(3,r),bg))
        if r % 2 == 0:
            style.append(("BACKGROUND",(0,r),(2,r),GREY_LL))
            style.append(("BACKGROUND",(4,r),(4,r),GREY_LL))
        r += 1
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t

def tf_table(rows, headers=("Chart","Weight","Rationale")):
    col_w = [CONTENT_W*0.20, CONTENT_W*0.20, CONTENT_W*0.60]
    data = [[Paragraph(h, cH) for h in headers]]
    style = [
        ("BACKGROUND",(0,0),(-1,0),TEAL),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),
        ("LINEBELOW",(0,1),(-1,-1),0.3,LINE),
    ]
    for i,(a,b,c) in enumerate(rows, start=1):
        data.append([Paragraph(a,cBb), Paragraph(b,mk("w",fontName="Helvetica-Bold",fontSize=7.9,leading=10,textColor=TEAL_DK)), Paragraph(c,cNote)])
        if i % 2 == 0: style.append(("BACKGROUND",(0,i),(-1,i),GREY_LL))
    t = Table(data, colWidths=col_w, repeatRows=1); t.setStyle(TableStyle(style)); return t

def generic_table(headers, rows, widths, header_color=TEAL_DK, center_cols=()):
    data = [[Paragraph(h, cH) for h in headers]]
    style = [
        ("BACKGROUND",(0,0),(-1,0),header_color),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LINEBELOW",(0,1),(-1,-1),0.3,LINE),
    ]
    for i,row in enumerate(rows, start=1):
        cells=[]
        for j,val in enumerate(row):
            st = mk("gc",fontName="Helvetica",fontSize=7.8,leading=10,textColor=INK,
                    alignment=TA_CENTER if j in center_cols else TA_LEFT)
            if j==0: st = cBb
            cells.append(Paragraph(val, st))
        data.append(cells)
        if i % 2 == 0: style.append(("BACKGROUND",(0,i),(-1,i),GREY_LL))
    t = Table(data, colWidths=widths, repeatRows=1); t.setStyle(TableStyle(style)); return t

# ---------- item header ----------
def item_header(item_id, title, was, meta_bits):
    left = Paragraph(f'{item_id} &nbsp;—&nbsp; {title}', hdrWhite)
    sub  = Paragraph(f'was {was} &nbsp;·&nbsp; ' + ' &nbsp;·&nbsp; '.join(meta_bits), hdrMeta)
    inner = Table([[left],[sub]], colWidths=[CONTENT_W-14])
    inner.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                               ("TOPPADDING",(0,0),(-1,0),0),("BOTTOMPADDING",(0,0),(0,0),2),
                               ("TOPPADDING",(0,1),(0,1),0),("BOTTOMPADDING",(0,1),(-1,-1),0)]))
    t = Table([[inner]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),TEAL_DK),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LINEBEFORE",(0,0),(0,-1),4,AMBER),
    ]))
    return t

def verdict_block(label, text, color=TEAL_DK):
    lab = Paragraph(label, mk("vl",fontName="Helvetica-Bold",fontSize=8.5,leading=11,textColor=color))
    txt = Paragraph(text, mk("vt",fontName="Helvetica",fontSize=8.8,leading=12.6,textColor=INK,alignment=TA_LEFT))
    t = Table([[lab],[txt]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),GREY_L),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(0,0),7),("BOTTOMPADDING",(0,0),(0,0),1),
        ("TOPPADDING",(0,1),(0,1),0),("BOTTOMPADDING",(0,1),(-1,-1),7),
        ("LINEBEFORE",(0,0),(0,-1),3,color),
    ]))
    return t

def reco_block(text, kind="include"):
    palette = {"include":(GREEN,GREEN_L,"INCLUDE"),
               "caveat":(AMBER_DK,AMBER_L,"INCLUDE (with caveats)"),
               "drop":(RED,RED_L,"DROP")}
    c,bg,_ = palette.get(kind, palette["include"])
    lab = Paragraph("FORMAL RECOMMENDATION", mk("rl",fontName="Helvetica-Bold",fontSize=8.2,leading=11,textColor=c))
    txt = Paragraph(text, mk("rt",fontName="Helvetica",fontSize=8.6,leading=12.2,textColor=INK,alignment=TA_LEFT))
    t = Table([[lab],[txt]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),bg),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(0,0),7),("BOTTOMPADDING",(0,0),(0,0),1),
        ("TOPPADDING",(0,1),(0,1),0),("BOTTOMPADDING",(0,1),(-1,-1),7),
        ("LINEBEFORE",(0,0),(0,-1),3,c),
        ("BOX",(0,0),(-1,-1),0.5,c),
    ]))
    return t

# ---------- funnel diagram flowable ----------
class Funnel(Flowable):
    def __init__(self, w=CONTENT_W):
        super().__init__(); self.w=w
        self.stages=[
            ("1 · Macro scan","Fed · US/Asia · DXY/crude — global tone",TEAL),
            ("2 · National news","RBI · budget · elections · policy",TEAL),
            ("3 · Institutional flows","FII/DII cash + derivatives intent",TEAL),
            ("4 · Pre-market gates","VIX · GIFT · gap · CPR · seasonality",TEAL),
            ("5 · Direction engine","Regime → trend → timing → S/R (11)",TEAL),
        ]
        self.h = 20 + len(self.stages)*40 + 46 + 44
    def wrap(self, aw, ah): return (self.w, self.h)
    def draw(self):
        c=self.canv; y=self.h-4
        cx=self.w/2
        def box(cy, w, h, fill, txt, sub, tcol=WHITE, sh=True):
            x=cx-w/2
            c.setFillColor(fill); c.roundRect(x,cy-h,w,h,3,fill=1,stroke=0)
            c.setFillColor(tcol); c.setFont("Helvetica-Bold",9.5)
            c.drawCentredString(cx, cy-h/2+1, txt)
            if sub:
                c.setFont("Helvetica",7.2); c.setFillColor(tcol)
                c.drawCentredString(cx, cy-h/2-9, sub)
        # trunk width shrinks slightly each stage (funnel feel)
        for i,(t,s,col) in enumerate(self.stages):
            w = self.w*(0.86 - i*0.03)
            top = y - i*40
            box(top, w, 32, col, t, s)
            # arrow
            c.setStrokeColor(GREY); c.setLineWidth(1)
            ay = top-32
            c.line(cx, ay, cx, ay-6)
            c.setFillColor(GREY)
            c.setFont("Helvetica",8); c.drawCentredString(cx, ay-6, "")
        # index direction (amber)
        yb = y - len(self.stages)*40 - 4
        box(yb, self.w*0.66, 34, AMBER, "INDEX DIRECTION", "bull / bear / sideways + confidence", WHITE)
        # two branches
        yc = yb-34-14
        bw=self.w*0.44
        c.setStrokeColor(GREY); c.setLineWidth(1)
        c.line(cx, yb-34, cx, yb-34-8)
        lx=self.w*0.25; rx=self.w*0.75
        c.setFillColor(TEAL_DK); c.roundRect(lx-bw/2,yc-32,bw,32,3,fill=1,stroke=0)
        c.setFillColor(AMBER_DK); c.roundRect(rx-bw/2,yc-32,bw,32,3,fill=1,stroke=0)
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold",8.6)
        c.drawCentredString(lx, yc-14, "Branch A · index options")
        c.drawCentredString(rx, yc-14, "Branch B · swing / stock")
        c.setFont("Helvetica",6.8)
        c.drawCentredString(lx, yc-24, "PCR · max pain · OI · expiry")
        c.drawCentredString(rx, yc-24, "sector · screen · RS · fundamentals")

# ---------- page decoration ----------
def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, 9*mm,
        "FORTUNA · Foundation List · Direction Funnel · Track A · v0.8")
    canvas.drawRightString(PAGE_W-MARGIN, 9*mm,
        f"Confidential — Internal Use Only · Page {doc.page}")
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.4)
    canvas.line(MARGIN, 12*mm, PAGE_W-MARGIN, 12*mm)
    canvas.restoreState()

def cover_deco(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(TEAL_XdK); canvas.rect(0,0,PAGE_W,PAGE_H,fill=1,stroke=0)
    # amber accent stripe
    canvas.setFillColor(AMBER); canvas.rect(0, PAGE_H-4*mm, PAGE_W, 4*mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL_DK); canvas.rect(MARGIN, 40*mm, PAGE_W-2*MARGIN, 0.5, fill=1, stroke=0)
    canvas.restoreState()

# ---------- doc scaffold ----------
class Doc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(path, pagesize=A4,
                         leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=18*mm, bottomMargin=16*mm)
        frame = Frame(MARGIN, 16*mm, CONTENT_W, PAGE_H-18*mm-16*mm, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        cover_frame = Frame(MARGIN, 16*mm, CONTENT_W, PAGE_H-40*mm, id="cover",
                            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPage=cover_deco),
            PageTemplate(id="body", frames=[frame], onPage=footer),
        ])

story = []

from reportlab.platypus import NextPageTemplate, FrameBreak

# ================= COVER =================
story += [
    NextPageTemplate("body"),
    Spacer(1, 30*mm),
    Paragraph("FORTUNA", titleBig),
    Spacer(1, 3),
    Paragraph("Foundation List — Direction Funnel", mk("cst",fontName="Helvetica-Bold",fontSize=15,leading=19,textColor=AMBER)),
    Spacer(1, 10),
    Paragraph("Track A &nbsp;|&nbsp; v0.8 &nbsp;|&nbsp; 13 Jul 2026", titleSub),
    Spacer(1, 16*mm),
    Paragraph("A daily direction funnel — broadest macro scan at the top, narrowing to a single "
              "index-direction verdict, then branching into the two trading books. Every item keeps "
              "a permanent old-ID alias (MAC-1 was B4, ENG-11 was E10) so references match across "
              "every document.", mk("cintro",fontName="Helvetica",fontSize=10,leading=15,textColor=TEAL_L)),
    Spacer(1, 8),
    Paragraph("v0.8 — the Foundation List trunk is complete at 22/22. This revision adds the three "
              "pre-market gates (PRE-1 India VIX, PRE-2 GIFT Nifty, PRE-5 calendar day-type), a new "
              "front-matter page on what the funnel actually outputs, the GIFT to PRE-3 opening "
              "handoff, and the post-Sep-2025 Tuesday-expiry weekday map.",
              mk("cintro2",fontName="Helvetica",fontSize=9,leading=14,textColor=colors.HexColor("#9fc9c9"))),
    PageBreak(),
]

# ================= WHAT THE FUNNEL OUTPUTS (front) =================
story += [
    Paragraph("What the Funnel Outputs", h1),
    HBar(color=AMBER, thick=1.4), sp(6),
    Paragraph("Read this first. The funnel does not output <b>a direction</b> — it outputs a "
              "<b>decision stack</b>. Direction is one field in it. On many days the most valuable "
              "output is <i>sit out</i>, or <i>this is a trap</i>, or <i>size down</i>. An indicator "
              "that says \u201cdon\u2019t trade Wednesday\u201d earns its keep as much as one that says "
              "\u201cgo long.\u201d Not every item is about direction; each answers a different question.", lead),
    sp(2),
    Paragraph("The verdict object", h3),
    Paragraph("The System Score should not be a single directional number. It should output a small "
              "<b>verdict object</b> — with direction as just one field, free to read "
              "<i>unknown / irrelevant</i> while the day is still fully classified:", body_l),
    callout("verdict = { <b>tradeable</b> · <b>day_type</b> · <b>direction</b> · <b>conviction</b> · "
            "<b>volatility_character</b> · <b>size</b> · <b>trap_risk</b> · <b>stop</b> }",
            bg=TEAL_L, bar=TEAL, tcolor=INK),
    sp(8),
]

# Output category tables
def out_table(title, rows):
    band = Band(title, color=TEAL, h=18, size=9.5)
    tbl = generic_table(
        ["Output","What it tells you","Primary items"],
        rows,
        [CONTENT_W*0.22, CONTENT_W*0.42, CONTENT_W*0.36])
    return KeepTogether([band, sp(3), tbl, sp(8)])

story += [
    out_table("A · GO / NO-GO — should I trade at all today?", [
        ["Trade / sit-out","Is today worth trading, or stand aside","PRE-1 VIX (>25 avoid), ENG-1 CHOP (>61.8), PRE-4 CPR wide, PRE-5 (Wed low-vol), ENG-8 liquidity"],
        ["Day-type forecast","Trend / range / chop / dead day","PRE-4 CPR width, PRE-1 VIX, ENG-1, PRE-3 gap type, PRE-5 weekday"],
        ["Event landmine","Is today dangerous (news / expiry)","MAC-1, NAT-1, PRE-5 (expiry / month-end)"],
        ["Liquidity gate","Can I actually get filled","ENG-8 (index auto-pass; stock 4-metric screen)"],
    ]),
    out_table("B · CHARACTER — what kind of day / move is this?", [
        ["Regime: trend vs chop","Trust the signals, or don\u2019t","ENG-1 (ADX+CHOP) master · ENG-2 EMA slope"],
        ["Volatility magnitude","How big are moves / how wide stops","ENG-9 ATR · PRE-1 VIX · PRE-4 CPR width · ENG-10 BB width"],
        ["Volatility character","Clean expansion vs wave-like reversal chop that traps retail","PRE-1 VIX (high=whippy) · ENG-1 CHOP · MAC-1/NAT-1 (news) · PRE-3 exhaustion · ENG-8 divergence"],
        ["Volume / participation","Is the move backed by real flow","ENG-8 (RVOL, breakout vol, climax, dry-up)"],
    ]),
    out_table("C · DIRECTION — which way?", [
        ["Bias / direction","Up / down / sideways","ENG-2 EMA · ENG-3 RSI · ENG-4 MACD · ENG-5 Supertrend · +DI/\u2212DI"],
        ["Opening direction","Gap up / down at 9:15","PRE-2 GIFT · PRE-3 gap · MAC-2 cues"],
    ]),
    PageBreak(),
    out_table("D · EXECUTION — where / when / how much / where\u2019s the exit?", [
        ["Location (where)","Where entries trigger / moves stall","ENG-11 S/R+OI · ENG-7 VWAP · ENG-2 EMA · PRE-4 CPR levels"],
        ["Timing (when)","The exact entry tick","ENG-6 StochRSI · ENG-7 VWAP reclaim · ENG-10 squeeze-fire · PRE-3 open range"],
        ["Conviction","How much to trust the setup","ENG-1 (gates all) · ENG-8 volume · ENG-9 ATR · multi-TF alignment"],
        ["Position sizing","How many lots","ENG-9 ATR (risk\u00f7stop) · PRE-1 VIX (inverse)"],
        ["Risk / stop","Where\u2019s the exit","ENG-7 VWAP+hunt zone · ENG-5 Supertrend trail · ENG-9 ATR · ENG-11 structure"],
        ["Premium / IV","Buy vs sell; IV-crush risk","PRE-1 VIX · IV percentile · NAT-1/MAC-1 (crush) · ENG-10 (buy cheap premium)"],
    ]),
    out_table("E · INTELLIGENCE — what\u2019s smart money doing / who\u2019s trapped?", [
        ["Institutional intent","What FIIs / DIIs are positioned for","FLO-1 cash · FLO-2 derivatives L/S · ENG-11 OI walls"],
        ["Trap / reversal warning","Retail being trapped; exhaustion","FLO-2 (FII-vs-retail divergence) · PRE-3 (exhaustion ~78% reverse) · ENG-8 (divergence/climax) · ENG-7 (failed reclaim) · ENG-3 (ceiling reject)"],
        ["Time-of-day context","First-15-min noise · expiry-PM pin · last hour","PRE-3 · ENG-7 (first 30m) · OPT (max-pain PM) · PRE-5"],
        ["Swing / positional backdrop","The multi-day / week regime","MAC-3 DXY/10Y · FLO trend · HTF ENG-2/3 · VIX extremes · NAT-1 elections"],
    ]),
]

# worked examples
story += [
    Paragraph("Two worked examples", h3),
    callout("<b>Wednesday low-volume sit-out.</b> A new day-type created by the Sep-2025 Tuesday-expiry "
            "shift — the opposite of folk wisdom, a fresh consequence of a rule change. Tuesday expiry "
            "concentrates volume/volatility into Tuesday; Wednesday is the post-expiry hangover (fresh "
            "weekly contract, unbuilt OI, thin volume, drift). Output = <b>reduced size / sit out</b>, a "
            "GO/NO-GO call, not a direction. Trust the mechanism; verify the magnitude on post-Sep-2025 data.",
            bg=GREY_L, bar=TEAL),
    sp(4),
    callout("<b>News-day wave-reversal trap.</b> The clearest case of why direction-only framing fails. "
            "On these days direction is <i>unknowable</i> — price reverses in waves precisely to trap both "
            "sides. Correct output is not a side but <b>character = chaotic two-sided \u2192 sit out / wait "
            "for the rollover</b>. Produced by a cluster: high VIX (PRE-1) + high CHOP (ENG-1) + event flag "
            "(MAC-1/NAT-1) + failed VWAP reclaims (ENG-7) + volume divergence (ENG-8) + exhaustion gap "
            "(PRE-3). When the cluster lights up, the score outputs NO-TRADE / trap-risk.",
            bg=RED_L, bar=RED),
    PageBreak(),
]

# ================= THE DIRECTION FUNNEL (visual) =================
story += [
    Paragraph("The Direction Funnel", h1),
    HBar(color=TEAL, thick=1.4), sp(2),
    Paragraph("Macro \u2192 national \u2192 flows \u2192 pre-market \u2192 engine \u2192 index direction \u2192 two books",
              mk("fsub",fontName="Helvetica-Oblique",fontSize=9,leading=12,textColor=GREY)),
    sp(8),
    Funnel(),
    sp(6),
    Paragraph("The teal stages are the shared trunk — read top-to-bottom every morning, they produce the "
              "index direction (also the Module I-8 dashboard order). The amber box is the single output. "
              "The two coloured boxes are the further filters per book: Branch A layers options intelligence "
              "onto the direction; Branch B narrows index \u2192 sector \u2192 stock.", small),
    PageBreak(),
]

# ================= RE-INDEX MAP =================
reindex = [
    ["MAC-1","B4","Global macro news (Fed/geo/commodity)","Macro","DONE"],
    ["MAC-2","B6","US / Asian market correlation","Macro","DONE"],
    ["MAC-3","B12","Macro levels (DXY/US10Y/crude/gold)","Macro","DONE"],
    ["NAT-1","B5","National news (RBI/budget/elections)","National","DONE"],
    ["FLO-1","C1","FII/DII daily cash flow","Flows","DONE"],
    ["FLO-2","C2","FII index derivatives positioning","Flows","DONE"],
    ["PRE-1","G5","India VIX regime","Pre-market","DONE"],
    ["PRE-2","G7","GIFT Nifty pre-market","Pre-market","DONE"],
    ["PRE-3","E9","Gap up / gap down behaviour","Pre-market","DONE"],
    ["PRE-4","D8-11","CPR (central pivot range)","Pre-market","DONE"],
    ["PRE-5","A7","Day-of-week / seasonality","Pre-market","DONE"],
    ["ENG-1","D8-7","Regime filter (ADX + Choppiness)","Engine","DONE"],
    ["ENG-2","D8-6","EMAs across timeframes","Engine","DONE"],
    ["ENG-3","D8-2","RSI (Cardwell ranges)","Engine","DONE"],
    ["ENG-4","D8-1","MACD crossover","Engine","DONE"],
    ["ENG-5","D8-8","Supertrend","Engine","DONE"],
    ["ENG-6","D8-3","Stochastic RSI","Engine","DONE"],
    ["ENG-7","D8-4","VWAP + SL decisions","Engine","DONE"],
    ["ENG-8","D8-5","Volume & liquidity","Engine","DONE"],
    ["ENG-9","D8-10","ATR (volatility backbone)","Engine","DONE"],
    ["ENG-10","D8-9","Bollinger + squeeze","Engine","DONE"],
    ["ENG-11","E10","Support & resistance + OI walls","Engine","DONE"],
]
story += [
    Paragraph("Re-index Map", h1),
    HBar(color=TEAL, thick=1.4), sp(2),
    Paragraph("New funnel ID \u2194 old research ID — use everywhere for consistent referencing.", small),
    sp(6),
    generic_table(
        ["New ID","Was","Item","Stage","Status"],
        reindex,
        [CONTENT_W*0.12, CONTENT_W*0.10, CONTENT_W*0.44, CONTENT_W*0.18, CONTENT_W*0.16],
        center_cols=(1,4)),
    sp(6),
    callout("All 22 trunk items are now researched. The three former pre-market gates (PRE-1 VIX, "
            "PRE-2 GIFT, PRE-5 seasonality) — previously mis-filed under Patterns / Backtesting — are "
            "completed in this revision. Next: the branch filters (OPT / STK), with stock-level work "
            "moving to Document B.", bg=AMBER_L, bar=AMBER),
    PageBreak(),
]

# ---------- stage divider ----------
class Divider(Flowable):
    def __init__(self, num, title, sub, w=CONTENT_W, h=None):
        super().__init__(); self.num=num; self.title=title; self.sub=sub; self.w=w
        self.h = h or (PAGE_H-40*mm)
    def wrap(self, aw, ah): return (self.w, self.h)
    def draw(self):
        c=self.canv
        c.setFillColor(TEAL_XdK); c.roundRect(0,0,self.w,self.h,4,fill=1,stroke=0)
        c.setFillColor(AMBER); c.roundRect(0,self.h-6,self.w*0.30,6,0,fill=1,stroke=0)
        c.setFillColor(colors.HexColor("#0d6f71")); c.setFont("Helvetica-Bold",90)
        c.drawString(24, self.h-150, f"{self.num}")
        c.setFillColor(WHITE); c.setFont("Helvetica-Bold",30)
        c.drawString(26, self.h-200, self.title)
        c.setFillColor(TEAL_L); c.setFont("Helvetica",12)
        c.drawString(28, self.h-224, self.sub)

def divider(num, title, sub):
    return [Divider(num, title, sub), PageBreak()]

# ---------- full item renderer ----------
def render_item(d):
    """d: dict with keys id,title,was,meta,verdict,paras(list of (label,text) or ('',text)),
       signals(rows), tf(rows), reco, reco_kind, page_break(bool)"""
    blk = [ item_header(d["id"], d["title"], d["was"], d["meta"]), sp(6) ]
    blk += [ verdict_block("HEADLINE VERDICT", d["verdict"]), sp(6) ]
    for label, text in d.get("paras", []):
        if label: blk += [ Paragraph(label, h3) ]
        blk += [ Paragraph(text, body) ]
    blk += [ sp(3), Paragraph("Signal strength", h3),
             signal_table(d["signals"]), sp(6) ]
    blk += [ Paragraph("Per-timeframe weight", h3), tf_table(d["tf"]), sp(6) ]
    blk += [ reco_block(d["reco"], d.get("reco_kind","include")) ]
    story.append(KeepTogether([]))  # noop
    story.extend(blk)
    if d.get("page_break", True): story.append(PageBreak())

# ================= STAGE 1 · MACRO =================
story += divider("1","Macro scan","Global risk tone — the widest layer · MAC-1 · MAC-2 · MAC-3")

render_item(dict(
    id="MAC-1", title="Global Macro News", was="B4",
    meta=["Fed · geopolitical · commodity shocks","Stage 1 · Macro"],
    verdict="A real but conditional, mostly gap-delivered signal. Not continuously weighted — an "
            "event-gate / regime overlay: Neutral on ~90% of days, dominant on the rare event day. Edge "
            "is at the open and decays within 30\u201345 min. High volatility here is overnight gap risk, "
            "not in-session whipsaw.",
    paras=[("Proof & mechanism",
            "Fed rate news moves Indian equity/debt/forex via FII flows. Feb-2026 US\u2013Israel\u2013Iran "
            "corrected Nifty ~9%; resolution flipped FIIs to net buyers after 13 selling sessions. Crude: "
            "a $110 spike hit Nifty same-day, but 16 spikes &gt;20%/mo since 1999 gave positive 1\u20133mo "
            "returns in 13; corr ~0.36 — crude moves volatility more than direction."),
           ("Timeframe",
            "Timezone means these are gap events. FOMC lands ~11:30 PM\u20132:30 AM IST and hits the 9:15 "
            "open; by ~9:45\u201310:00 it is priced.")],
    signals=[
        ("Fed / FOMC","MED","HIGH","CAUTION","Directional via FII, often pre-priced; overnight gap"),
        ("Acute geopolitical","HIGH","V.HIGH","AVOID","Dominates while active; chaotic, wide gaps"),
        ("Geo resolution","MED","HIGH","CAUTION","Mirror recovery; trade after confirmation"),
        ("Crude shock (same-day)","MED","MED","CAUTION","Weak direction; mean-reverts; size down"),
        ("Crude level / trend","LOW","LOW","AVOID","Excluded — owned by MAC-3"),
    ],
    tf=[("Monthly","Very low","Structural resilience + crude mean-reversion."),
        ("Weekly","Low\u2013mod","FII-flow response plays out over days when live."),
        ("Daily","Binary","~0 non-event; can dominate event days."),
        ("1H / intraday","High \u2192 0 by 10:30","Sets gap + regime, then hand to VWAP.")],
    reco="Include as a conditional event-gate / regime overlay, baseline Neutral. On event days caps "
         "confidence + flags two-sided risk; on acute shocks can override toward the gap. Fed + acute "
         "geopolitics are directional; crude = volatility/context with a mean-reversion guard.",
    reco_kind="caveat",
))

render_item(dict(
    id="MAC-2", title="US / Asian Market Correlation", was="B6",
    meta=["GIFT · S&P/Nasdaq · Nikkei/Hang Seng","Stage 1 · Macro"],
    verdict="The most codeable macro item — a continuous, quantifiable correlation (Nifty\u2013S&P 30-day "
            "reached 0.68). Edge is at the open: cues set the gap + first 30 min, then decay. "
            "Trade/no-trade from cue alignment + VIX regime (aligned + VIX 12\u201316 = gap-and-go; "
            "contradiction / gap &gt;200 / VIX&gt;18 = fade/sit out).",
    paras=[("Proof & mechanism",
            "Bidirectional short-run causality with Dow/S&P; no long-run cointegration. NASDAQ daytime "
            "drives ~9.5% of Nifty overnight-return volatility. GIFT prices it all in real time; "
            "Nasdaq\u2192IT is the sharpest sector channel."),
           ("Consumes PRE-2",
            "The GIFT implied-gap sub-signal below is sourced from PRE-2 — MAC-2 uses it as one of three "
            "cues (US close + Asia + GIFT). Wire it once, reference it twice; do not double-count the gap.")],
    signals=[
        ("GIFT implied gap","HIGH","MED","TRADE","75\u201385% opening-direction when aligned, gap &gt;100pts"),
        ("US overnight close","HIGH","MED","CAUTION","Most important overnight input; Nasdaq\u2192IT"),
        ("Cue alignment (US+Asia+GIFT)","HIGH","LOW","TRADE","Gap-and-go conviction; VIX 12\u201316"),
        ("Contradiction / gap&gt;200 / VIX&gt;18","LOW","HIGH","AVOID","Fade or sit out first 15 min"),
        ("US trend regime (wk/mo)","MED","\u2014","TRADE","0.68 co-move biases swing direction"),
    ],
    tf=[("Monthly","Moderate","0.68 co-move biases trend; decoupling risk."),
        ("Weekly","Moderate","US swing trend co-moves; Fortuna-Cash input."),
        ("Daily","Mod\u2013high","Sets the opening gap + risk tone every session."),
        ("1H / intraday","High at open \u2192 decays 10:00","Owns gap + first 30 min; Asia = live filter.")],
    reco="Include as the opening-direction + swing-bias input: GIFT gap + US close + Asian confirmation, "
         "gated by VIX (12\u201316 = trade; &gt;18/contradiction = fade; &lt;50 pts = noise). Moderate "
         "weekly/monthly weight; decays by 10 AM. Route Nasdaq\u2192IT to Fortuna-Cash.",
    reco_kind="include",
))

render_item(dict(
    id="MAC-3", title="Macro Levels", was="B12",
    meta=["DXY · US 10Y · crude · gold","Stage 1 · Macro"],
    verdict="The mirror image of the intraday items: strong at weekly/monthly, near-zero intraday. DXY "
            "yes (strong inverse); US 10Y yes (threshold-based); crude barely (defers to MAC-1); gold "
            "essentially no (R\u00b2&lt;0.3%, risk-off confirm only). Route to swing + regime, not the "
            "intraday engine.",
    paras=[("Proof & mechanism",
            "Rising DXY \u2192 FII outflows \u2192 Nifty down (thresholds 100/106/110). US 10Y &gt;4.5% "
            "coincides with FII selling; crossing 5% (Oct-23) sent Nifty \u22121,000 in a week. Gold flipped "
            "to +0.88 corr in 2021\u201325 — unreliable as a hedge now.")],
    signals=[
        ("DXY (dollar index)","MED","MED","CAUTION","Inverse, threshold-based, often leads"),
        ("US 10Y yield","MED","MED","CAUTION","Non-linear; &gt;4.5% pressure, 5% shock"),
        ("Crude (level)","LOW","MED","CAUTION","Corr ~0.36; defers shock to MAC-1"),
        ("Gold","LOW","LOW","CAUTION","Not a predictor; regime confirm only"),
    ],
    tf=[("Monthly","Mod\u2013high (3\u20134/10)","DXY + 10Y are genuine positional drivers."),
        ("Weekly","Moderate","DXY/10Y trends bias swing; core Fortuna-Cash input."),
        ("Daily","Low","Only extreme threshold breaks matter same-day."),
        ("1H / intraday","Near-zero","Risk-on/off backdrop only.")],
    reco="Include DXY + US 10Y as weekly/monthly directional inputs (threshold-banded) for swing + "
         "regime. Crude defers to MAC-1; drop gold as a predictor (risk-off confirm only). ~0 intraday.",
    reco_kind="caveat",
))

# ================= STAGE 2 · NATIONAL =================
story += divider("2","National news","Domestic event flags · NAT-1")

render_item(dict(
    id="NAT-1", title="National News", was="B5",
    meta=["RBI · Union Budget · elections · policy","Stage 2 · National"],
    verdict="B5 events fire during NSE hours (RBI 10 AM, Budget 11 AM), not as overnight gaps — genuinely "
            "intraday-tradeable and dangerous, and they crush volatility after. For an options buyer the "
            "primary output is trade / no-trade + IV-crush warning, with bias only on a real "
            "consensus-surprise.",
    paras=[("Proof",
            "RBI: tone-driven (rate pre-priced). Budget: &gt;1% move on 16/25 days, 2.65% avg intraday "
            "range, no reliable direction, VIX falls on all 15 days studied. Elections (surprise-only): "
            "4-Jun-2024 \u22125.93% close (~\u20b926 lakh cr wiped); expected 2019 moved just \u22120.69%. "
            "Regulatory (SEBI F&O) = structural, not direction.")],
    signals=[
        ("Elections (results day)","V.HIGH","V.HIGH","AVOID","Surprise-only; VIX ramp + brutal post-crush"),
        ("RBI MPC","MED","HIGH","CAUTION","Tone-driven; wait for 10 AM statement"),
        ("Union Budget","LOW","V.HIGH","AVOID","No direction; whipsaw + VIX crush kills longs"),
        ("Govt / regulatory policy","LOW","MED","CAUTION","Sector-specific; route to Fortuna-Cash"),
    ],
    tf=[("Monthly","Low, exc. elections","Only a general-election surprise sets a multi-month tone."),
        ("Weekly","Mod on event weeks","RBI / Budget / election week; ~0 otherwise."),
        ("Daily","Binary","~0 normal; can dominate the event day."),
        ("1H / intraday","High post-announcement","Two-sided before; no-trade/caution flag pre-event.")],
    reco="Include as a scheduled-event gate whose output for an options buyer is trade/no-trade + "
         "IV-crush warning, not a continuous weight. Bias only on a genuine surprise; default to caution "
         "+ reduced size on all event days.",
    reco_kind="caveat",
))

# ================= STAGE 3 · FLOWS =================
story += divider("3","Institutional flows","Realized flow + leveraged intent · FLO-1 · FLO-2")

render_item(dict(
    id="FLO-1", title="FII/DII Daily Cash Flow", was="C1",
    meta=["Net cash + 3\u20135 day rolling trend","Stage 3 · Flows"],
    verdict="Cash data publishes after close (6\u20137 PM) — structurally a next-day / swing signal, never "
            "intraday. Real but moderate and regime-dependent (single-day R\u00b2 ~16.5%). The number that "
            "matters is the net (FII + DII), not FII alone — DII absorption prevents the \u2018FIIs selling "
            "so market falls\u2019 error.",
    paras=[("Proof & mechanism",
            "One of the most consistent relationships in Indian markets, but single-day explains ~16.5%; "
            "3+ sessions carry far more value. Self-reinforcing FII\u2192rupee loop. FIIs momentum-trade, "
            "DIIs contrarian — so they offset.")],
    signals=[
        ("FII net cash (single day)","LOW","MED","CAUTION","Retrospective, EOD, noisy alone"),
        ("FII 3\u20135 day rolling trend","MED","MED","TRADE","The reliable read; swing bias"),
        ("DII net / absorption ratio","MED","LOW","CAUTION","The decoupling / floor detector"),
        ("Sharp rupee fall + FII sell","MED","HIGH","AVOID","Compound risk-off"),
    ],
    tf=[("Monthly","Moderate","Cumulative FII trend + structural DII floor."),
        ("Weekly","Mod\u2013high","The 3\u20135 day rolling net flow is the sweet spot."),
        ("Daily","Mod (next-day)","Last evening\u2019s print biases the open."),
        ("1H / intraday","Low","Only yesterday\u2019s-flow context; no live signal.")],
    reco="Include as a next-day / swing bias on the net (FII+DII) figure, 3\u20135 day rolling trend, and "
         "DII absorption ratio — normalized by turnover, regime-gated. ~0 same-day intraday. Never read "
         "FII alone. Pair with FLO-2.",
    reco_kind="caveat",
))

render_item(dict(
    id="FLO-2", title="FII Index Derivatives Positioning", was="C2",
    meta=["Participant-wise OI · long/short ratio","Stage 3 · Flows"],
    verdict="Correction to the old spec\u2019s \u2018intraday\u2019 note: participant-wise OI publishes EOD "
            "(~7 PM) — a next-day / multi-week signal (live intraday OI = the option chain, ENG-11). Its "
            "edge over FLO-1: it shows leveraged directional intent, and the long-short ratio leads "
            "reversals 24\u201348h.",
    paras=[("Proof & mechanism",
            "Sustained FII net-long index futures \u2192 markets rise; net-short \u2192 correct. Best read "
            "is divergence: retail buying calls at highs while FIIs liquidate longs + buy puts \u2192 market "
            "follows FIIs, traps retail. A confirmer, not a standalone trigger."),
           ("The hedge trap",
            "An FII futures short is often a hedge vs a cash long, not a bear bet — always cross-check "
            "FLO-1 to tell bet from hedge.")],
    signals=[
        ("FII long-short ratio","MED","MED","TRADE","24\u201348h to multi-week lead"),
        ("FII-vs-retail divergence","HIGH","MED","TRADE","The trap-reversal signal; best edge"),
        ("FII net short (raw)","MED","HIGH","AVOID","Check FLO-1: short+cash-long = HEDGE"),
        ("FII/Pro option writing","MED","LOW","CAUTION","S/R context; overlaps ENG-11"),
    ],
    tf=[("Monthly","Moderate","Futures long-short trend frames the multi-week regime."),
        ("Weekly","Mod\u2013high","C2\u2019s strongest horizon — leading positioning trend."),
        ("Daily","Mod (next-day)","Positioning + divergence bias the next open."),
        ("1H / intraday","Low","EOD data; live OI = ENG-11.")],
    reco="Include as the institutional-intent layer — long-short ratio + FII-vs-retail divergence. Always "
         "read with FLO-1 to separate a directional short from a hedge; treat as a confirmer, not a "
         "trigger. Highest conviction when cash, futures and the option chain align.",
    reco_kind="include",
))

# ================= STAGE 4 · PRE-MARKET =================
story += divider("4","Pre-market gates","The 9:00 AM scan — trade / no-trade + day-type · PRE-1..5")

# ---- PRE-1 India VIX (NEW) ----
render_item(dict(
    id="PRE-1", title="India VIX Regime", was="G5",
    meta=["the master volatility gate","Stage 4 · Pre-market"],
    verdict="The master volatility gate — the pre-market twin of ENG-1. <b>Zero directional weight</b>: "
            "every authoritative source states VIX does not predict up/down, only the expected size of "
            "moves. What it sets is trade/no-trade posture, position size, and — critically for an options "
            "buyer — how expensive premium is and how brutal the IV-crush risk is. Score it like ENG-1: it "
            "multiplies confidence and sets size; it never picks a side.",
    paras=[("Does it affect direction?",
            "No — the key correction. VIX-change \u2192 next-day gap direction is only ~53% (barely above "
            "chance). The relationship is inverse but asymmetric: on 7-Apr-2025 VIX surged 65% as Nifty "
            "fell 3.24%; on 28-Oct-2008 VIX fell only ~33% as Nifty rose 6.35% — a spike is a downside-risk "
            "flag, not a symmetric signal. The rigorous long-run correlation is \u22120.41 (the folk "
            "\u22120.85 is a stress-window figure). One real edge is positional, not intraday: extreme VIX "
            "mean-reverts and precedes rallies (post-2008 +80.8%, post-COVID +83.6%, post-Jul-2023 low "
            "+26.4%) — a Fortuna-Cash swing input."),
           ("Mechanism",
            "VIX = aggregate implied vol of OTM Nifty options, annualised (15 \u2248 \u00b14.33% over 30 "
            "days). The chain that matters: VIX level \u2192 premium richness \u2192 theta/IV-crush exposure "
            "\u2192 whether a directional buy can even pay off. Low VIX = cheap premium, slow grind; high "
            "VIX = rich premium, violent two-sided moves, IV-collapse risk on a correct call.")],
    signals=[
        ("VIX &lt;13 (calm)","Gate/Size","LOW","TRADE","Cheap premium, grind-trend regime; buying viable"),
        ("VIX 13\u201317 (normal)","Gate/Size","MED","TRADE","Workable zone; full cascade weight"),
        ("VIX 17\u201320 (nervous)","Gate/Size","MED","CAUTION","Size down; premium richening"),
        ("VIX &gt;20 (elevated)","Gate/Size","HIGH","CAUTION","Buying penalised — IV-crush + wide stops"),
        ("VIX &gt;25 (turbulence)","Gate","V.HIGH","AVOID","Two-sided chaos; stand aside for buys"),
        ("VIX delta (day/day)","\u2014","\u2014","AVOID","53% direction — do NOT trade the delta"),
        ("Extreme reversion","Swing","HIGH","TRADE","Contrarian positional only — NOT intraday"),
    ],
    tf=[("Monthly","Mod (positional)","Extreme-VIX mean-reversion is a genuine contrarian tell."),
        ("Weekly","Mod\u2013high","Sets the week\u2019s premium-cost + gap-risk regime."),
        ("Daily","High (gate)","The pre-open trade/no-trade + sizing decision, both books."),
        ("1H / intraday","Gate (0 dir)","Conditions cascade confidence + stop width; 0 direction.")],
    reco="Include as the master pre-market volatility gate feeding both books — the twin of ENG-1. "
         "Contributes 0 to direction; sets (a) trade/no-trade + size and (b) premium/IV-crush context. Use "
         "a rolling VIX percentile, not fixed bands (the regime drifted lower post-2023). Cross-confirm "
         "width with PRE-4: low VIX + narrow CPR = strongest trend day; high VIX + wide CPR = chop, sit "
         "out. Never trade the VIX delta.",
    reco_kind="include",
))

# ---- PRE-2 GIFT (NEW) ----
render_item(dict(
    id="PRE-2", title="GIFT Nifty Pre-market", was="G7",
    meta=["the 6:30 AM opening-direction read","Stage 4 · Pre-market"],
    verdict="The most directional of the pending gates — the one item where \u2018does it predict "
            "direction?\u2019 is the right question. GIFT is the USD Nifty futures contract on NSE IX "
            "(successor to SGX since Jul-2023), trading ~21h. It answers one thing well: which way and "
            "roughly how far the Nifty <i>opens</i> — not the day (like MAC-2). Its accuracy is partly "
            "mechanical, not predictive. Treat it as the gap forecaster that hands off to PRE-3, not a "
            "trigger.",
    paras=[("Does it affect direction? (proof + skepticism)",
            "Yes, for the opening print. Nifty spot is frozen overnight while GIFT trades on global news, "
            "so the widened basis <i>is</i> the implied gap; arbitrage pulls the open toward GIFT. The "
            "cited ~75\u201385% is a portal claim, not a backtest — plausible precisely because it is "
            "mechanical (forecasting the gap from indicators scores only ~53%). It measures opening "
            "direction only, and inflates by being mechanical. Validate your own hit-rate by gap-size "
            "bucket."),
           ("Mechanism & the handoff",
            "Two sessions (~6:30 AM\u20133:40 PM, 4:35 PM\u20132:30 AM). Implied gap \u2248 (GIFT \u2212 prev "
            "close) minus the standing carry basis (USD-INR rate differential; ~5\u201330 pts intraday, "
            "widening overnight). Cleanest read 8:45\u20139:10 AM. Feeds MAC-2 (as one cue) and PRE-3 (as "
            "the pre-print forecast). <b>GIFT red on real overnight news \u2192 high-confidence down "
            "OPEN; PRE-3 then classifies runaway vs exhaustion \u2192 enter 9:30\u20139:45, never the 9:15 "
            "print.</b>")],
    signals=[
        ("Large gap (&gt;0.5%), US clear","HIGH","MED","TRADE","Strongest confirmation; open follows GIFT"),
        ("Moderate gap (0.2\u20130.5%), no event","HIGH","MED","TRADE","Reliable opening lean; feed PRE-3"),
        ("Small gap (&lt;\u00b10.2%)","LOW","LOW","AVOID","Noise band — mostly carry, no direction"),
        ("Event day (RBI/Budget/expiry)","LOW","HIGH","AVOID","9:15 domestic flow overrides GIFT"),
        ("Late reversal (6:30\u20139:15)","\u2014","HIGH","CAUTION","Re-check at 9:00; early read can flip"),
        ("Thin overnight liquidity","LOW","HIGH","CAUTION","Exaggerated move cash won\u2019t follow"),
    ],
    tf=[("Monthly / Weekly","~0","No swing signal; a single session\u2019s open."),
        ("Daily","Mod (open only)","Sets the opening gap + first-30-min risk tone."),
        ("Pre-open (6:30\u20139:10)","High (its home)","The gap-direction + magnitude read."),
        ("Intraday after 9:15","~0","Hand off to PRE-3; GIFT is spent.")],
    reco="Include as the pre-open gap forecaster — the 8:45\u20139:10 AM basis-adjusted read of direction + "
         "magnitude that feeds MAC-2 (cue) and PRE-3 (pre-print forecast). High weight in its window, zero "
         "after 9:15. Strong when large + news-driven; noise under \u00b10.2%; gate off on event days; "
         "refresh at 9:00 for flips. Reference-only (retail can\u2019t trade it). Validate the hit-rate by "
         "gap-size bucket rather than inheriting the folk 75\u201385%.",
    reco_kind="include",
))

# ---- PRE-3 Gap (existing) ----
render_item(dict(
    id="PRE-3", title="Gap Up / Gap Down Behaviour", was="E9",
    meta=["opening classifier — the convergence point","Stage 4 · Pre-market"],
    verdict="Gap direction alone is near a coin flip (Nifty gap-ups \u22651% fill same-day only 29.4%). The "
            "edge is gap + trend-alignment + ATR-normalized size + VIX + no-news. This is where the whole "
            "macro/flow stack + VIX converges into the first trade of the day.",
    paras=[("Four-type taxonomy",
            "Common (&lt;0.5\u00d7ATR, range) \u2192 fills ~90%, noise. Runaway (0.5\u20131.5\u00d7ATR, "
            "with-trend, no news, VIX 12\u201316) \u2192 continues 55\u201365%. Breakaway (genuine catalyst) "
            "\u2192 trends, rarely fills. Exhaustion (&gt;1.5\u20132\u00d7ATR, extended, climax vol, high "
            "VIX) \u2192 reverses ~78%, gives back ~1 ATR."),
           ("Inverted-U + gates",
            "Continuation peaks for moderate gaps, falls at both ends. Measure size \u00f7 14-day ATR. Gate "
            "by trend-alignment (ENG-2/3), no-news (MAC/NAT calendar), VIX (&lt;20 go, &gt;25 fade). "
            "Huge-gap reversals come later — wait for the rollover, don\u2019t fade at 9:15.")],
    signals=[
        ("Runaway: with-trend + no-news + VIX 12\u201316","MED","MED","TRADE","Break 9:30 H/L, with the gap; 55\u201365%"),
        ("Breakaway: genuine catalyst","MED","HIGH","TRADE","Trends all day; rarely fills — don\u2019t fade"),
        ("Exhaustion: huge + extended","MED","HIGH","CAUTION","~78% reverse; fade after the rollover"),
        ("Common: tiny / range","LOW","LOW","AVOID","Noise; spread eats options edge"),
        ("Opening range (9:15\u20139:30)","MED","HIGH","CAUTION","First 15 min noise; enter 9:30\u20139:45"),
    ],
    tf=[("Monthly / Weekly","Low","Breakaway/exhaustion classification for swing context."),
        ("Daily","Moderate","The open sets tone; gap type is a swing signal."),
        ("Intraday — first hour","High (its home)","The go/fill/sit-out decision."),
        ("After ~11:30","~0","78% of fills done; opening edge decayed.")],
    reco="Include (strong, opening) as the opening classifier: four-type taxonomy via trend-alignment + "
         "ATR-normalized size + VIX + no-news. Runaway/breakaway \u2192 gap-and-go; exhaustion \u2192 fade "
         "after rollover; tiny/split \u2192 sit out. Never trade the first 15 min blindly.",
    reco_kind="include",
))

# ---- PRE-4 CPR (existing) ----
render_item(dict(
    id="PRE-4", title="CPR (Central Pivot Range)", was="D8-11",
    meta=["pre-market day-type forecast + session S/R","Stage 4 · Pre-market"],
    verdict="The Indian intraday staple. Three levels (BC/PP/TC) from the prior day\u2019s H/L/C — known "
            "before the open. CPR width forecasts the day type (narrow = trend day, wide = range day), "
            "which front-runs the coincident regime gate (ENG-1); the levels give an intraday S/R roadmap.",
    paras=[("Width forecast",
            "Narrow CPR (~&lt;35 pts Nifty) = low vol yesterday \u2192 trending day; wide (~&gt;60 pts) = "
            "range/chop day. Combine with VIX/CHOP: high VIX + narrow CPR = strong trend; low VIX + wide "
            "CPR = safe range day."),
           ("Levels",
            "Above TC = bullish, below BC = bearish, inside BC\u2013TC = indecision; PP = magnet. Virgin "
            "CPR reacts strongly on first test.")],
    signals=[
        ("Narrow CPR (day-type)","LOW","LOW","TRADE","Pre-market trend-day forecast; front-runs ENG-1"),
        ("Wide CPR","LOW","HIGH","AVOID","Range-day forecast; mean-revert the levels"),
        ("Price above TC / below BC","MED","MED","TRADE","Intraday directional bias"),
        ("Virgin CPR tested","MED","MED","TRADE","Strong reaction on first test"),
    ],
    tf=[("Intraday (daily-derived)","High","Morning session bias + day-type forecast."),
        ("Daily","High","Prior-day CPR governs today\u2019s session."),
        ("Weekly / Monthly CPR","Moderate","Swing S/R from prior week/month."),
        ("vs ENG-1","Complement","CPR = forward forecast; ADX/CHOP = coincident.")],
    reco="Include (strong, intraday) as the morning roadmap: CPR width as a pre-market regime predictor "
         "(narrow = trend, wide = range) front-running ENG-1, plus the three levels as intraday S/R. "
         "Cross-confirm width with VIX/Choppiness.",
    reco_kind="include",
))

# ---- PRE-5 Seasonality (re-researched) ----
render_item(dict(
    id="PRE-5", title="Calendar Day-Type / Seasonality", was="A7",
    meta=["weekday theta-cycle map + weak seasonal tilt","Stage 4 · Pre-market"],
    verdict="Re-researched. The return-based seasonality (Monday-bullishness, month-of-year) is weak, "
            "contradictory and mostly insignificant — don\u2019t trade it. But a strong, in-scope output "
            "hides underneath: a <b>weekday day-type map</b> created by the Sep-2025 Tuesday-expiry regime, "
            "driven by the theta/gamma/OI cycle — deterministic math, so its shape is trustworthy even on "
            "&lt;1 year of data. It sets volume, volatility character and theta pressure per weekday "
            "(GO/NO-GO, day-type, sizing, premium), never a side. (Full weekday map on the next page.)",
    paras=[("Does it affect direction? (proof + skepticism)",
            "Return-direction: no, still weak — day-of-week studies are sign-unstable and the recent "
            "rigorous work finds no significant large-cap effect; the ~58% Monday claim doesn\u2019t "
            "survive. But that was the wrong question. What the map affects reliably is <i>day-type and "
            "theta pressure</i>, which is deterministic (a 0-DTE Tuesday option pins and decays regardless "
            "of last year\u2019s returns). Near-zero directional weight, high context value."),
           ("Monthly / annual seasonality — the \u2018all seasons\u2019 answer",
            "Researched and honestly weak. The literature is contradictory (Nov\u2013Dec strength, "
            "Mar\u2013May weakness, a January effect — all with different signs in different studies); the "
            "most recent rigorous Nifty50/BankNifty study (2026) finds only January significant, and "
            "<i>negative</i>, every other month insignificant \u2192 high efficiency. \u2018Sell in May\u2019 "
            "shows up globally including India but weak. For intraday index options this is essentially "
            "irrelevant — a months-long positional tilt. Note it as a faint Fortuna-Cash backdrop; "
            "contribute ~0 to the intraday score. Budget/earnings seasons are already owned by "
            "NAT-1/MAC-1 and STK-SEA (Doc B) — don\u2019t duplicate.")],
    signals=[
        ("Tue expiry (AM)","Context","HIGH","TRADE","High-vol/high-volume; range-break with volume"),
        ("Tue expiry (PM)","Context","V.HIGH","AVOID","Pin + MM games + wide spreads; no new positions"),
        ("Mon expiry-eve","Context","MED\u2192HIGH","CAUTION","Theta headwind for buyers; seller-favoured"),
        ("Wed post-expiry","Context","LOW*","AVOID","Low-volume drift; reduced size (verify)"),
        ("Thu (BSE expiry)","Context","MED","TRADE","Buyer-friendlier; watch BSE vol spillover"),
        ("Fri pre-weekend","Context","MED","TRADE","Fresh directional OK; no weak weekend holds"),
        ("Monday return tilt","~0/noise","LOW","AVOID","Sign-unstable; don\u2019t trade"),
        ("Month-of-year tilt","~0 intraday","\u2014","AVOID","Positional, weak, out-of-scope"),
    ],
    tf=[("Monthly","~0 (intraday)","Month-of-year is a weak months-long positional tilt; Fortuna-Cash backdrop only."),
        ("Weekly","Mod (day-type)","The weekday theta-cycle map — genuinely useful here."),
        ("Daily","Mod (context)","Sets day-type + theta/premium prior + GO/NO-GO."),
        ("Intraday","~0 (exc. Tue PM)","Only expiry-afternoon pin/theta, owned by OPT.")],
    reco="Include (with caveats): strong as the weekday day-type / theta-cycle map — a mechanism-grounded, "
         "in-scope context gate outputting GO/NO-GO (Wed sit-out, Tue-PM avoid), day-type (Tue high-vol "
         "tradeable AM) and premium/theta prior (Mon buyer headwind) — never a direction. Drop the "
         "return-based day-of-week and month-of-year tilts as intraday signals; keep monthly seasonality "
         "only as a faint Fortuna-Cash backdrop. Validate every weekday magnitude on post-Sep-2025 data; "
         "trust the shape now.",
    reco_kind="caveat",
    page_break=True,
))

# ---- WEEKDAY DAY-TYPE MAP (feature page) ----
story += [
    Band("The Weekday Day-Type Map — post-1-Sep-2025 (Nifty intraday)", color=TEAL_DK, h=22, size=11.5),
    sp(6),
    Paragraph("Because Nifty weekly expiry is now <b>Tuesday</b>, the week\u2019s theta / OI / gamma rhythm "
              "shifted. This map is about volume, volatility character and theta pressure — not direction. "
              "The shape is deterministic (theta math); the magnitude of each cell needs your own "
              "post-Sep-2025 backtest.", body_l),
    sp(4),
    generic_table(
        ["Day","DTE","Character","Vol","Options-buyer stance"],
        [
            ["Mon","1","\u201cPressure cooker\u201d — weekend news meets expiry-eve; Fri\u2192Mon weekend theta compressed; vol building","Rising","Heavy theta headwind; seller-favoured; buy only strong confirmed directional"],
            ["Tue","0 · EXPIRY","Highest volume (~+50%) + volatility; gamma peaks ATM; max-pain pin + MM games late; spreads widen after ~2 PM","Highest","AM tradeable (first-30-min break + volume); avoid new positions PM; read sharp closes as theta not trend"],
            ["Wed","~6","Post-expiry hangover — fresh weekly contract, OI not yet built, drift (your observation)","Low*","Reduced size / sit out unless a clean trend prints; verify magnitude on new-regime data"],
            ["Thu","~5","Nifty mid-cycle, more time value; Sensex expires on BSE today \u2192 possible vol spillover","Moderate","Directional buying viable (more DTE = lighter theta); watch BSE-driven spikes"],
            ["Fri","~4","Pre-weekend; sellers initiate for 3-day weekend theta; weekend gap risk on holds","Moderate","Fine for fresh directional; don\u2019t carry weak longs over the weekend (theta + gap)"],
        ],
        [CONTENT_W*0.07, CONTENT_W*0.09, CONTENT_W*0.40, CONTENT_W*0.10, CONTENT_W*0.34],
        center_cols=(1,3)),
    sp(4),
    Paragraph("* Wednesday\u2019s low-volume drift is mechanism-plausible (fresh series, unbuilt OI) and "
              "matches your observation, but it\u2019s the one cell most needing your own backtest — the "
              "regime is ~10 months / ~40 Wednesdays old. Trust the shape, confirm the size.", small),
    sp(6),
    callout("<b>Structural notes.</b> Tuesday = Nifty pin day (NSE); Thursday = Sensex pin day (BSE) — two "
            "pressure points, not one. BankNifty is monthly-only (no weekly since Nov-2024) — most weeks it "
            "has no expiry pin, a cleaner intraday underlying. Weekend theta is now a 3-day Fri\u2192Mon "
            "drain — punishing for Friday/Monday option-buyer holds. Holiday shifts move Tuesday expiry to "
            "the prior session — read the NSE circular, never assume the weekday.", bg=AMBER_L, bar=AMBER),
    PageBreak(),
]

# ================= STAGE 5 · ENGINE =================
story += divider("5","Direction engine",
                 "Regime \u2192 trend \u2192 direction \u2192 location \u2192 timing \u2192 conviction \u2192 stop · ENG-1..11")

render_item(dict(
    id="ENG-1", title="Regime Filter (ADX + Choppiness)", was="D8-7",
    meta=["the master gate — trade or chop?","Stage 5 · Engine"],
    verdict="The master gate every other engine item assumed. It gives no direction — it decides whether "
            "the cascade\u2019s signals should be trusted at all. 0 directional weight; it multiplies every "
            "other item\u2019s confidence.",
    paras=[("Two measures",
            "ADX = trend strength (+DI/\u2212DI = direction); Choppiness Index = trend existence/efficiency "
            "(directionless). Complementary — a trend can be strong AND choppy. Optional 3rd: Efficiency "
            "Ratio, 2-of-3 vote."),
           ("Codeable rule",
            "CHOP&lt;38.2 AND ADX&gt;25 = trend \u2192 run the cascade at full weight. CHOP&gt;61.8 = chop "
            "\u2192 stand aside / mean-revert. 38.2\u201361.8 = wait. Direction from +DI/\u2212DI, never "
            "ADX/CHOP.")],
    signals=[
        ("CHOP&lt;38.2 + ADX&gt;25 (trend)","LOW","MED","TRADE","Green light: full weight to the cascade"),
        ("CHOP&gt;61.8 (chop)","LOW","LOW","AVOID","Red light: stand aside or mean-revert"),
        ("ADX rising + DI separating","MED","MED","TRADE","Strengthening trend; DI gives the side"),
        ("ADX&lt;20 / falling","LOW","LOW","AVOID","No trend; momentum unreliable"),
    ],
    tf=[("Every timeframe","Gate","Runs each TF; cascade wants trend-regime agreement top-down."),
        ("Higher-TF","Gate","Weekly/daily regime validates lower-TF signals."),
        ("Execution-TF","Gate","5m CHOP&gt;61.8 inside a bull weekly \u2192 wait, don\u2019t force.")],
    reco="Include as the master trend/range gate: CHOP + ADX (+ optional Efficiency Ratio) decides trend "
         "vs chop per TF; momentum gets full weight only in a trend. Contributes 0 to direction but "
         "multiplies every other item\u2019s confidence.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-2", title="EMAs Across Timeframes", was="D8-6",
    meta=["the structural backbone","Stage 5 · Engine"],
    verdict="The backbone the cascade rides on. The EMA stack + slope per TF is the operational definition "
            "of that TF\u2019s trend. The 20/50/200 are the dynamic S/R where pullback entries bounce. "
            "Crossovers are lagging confirmation only.",
    paras=[("Roles",
            "9 = fast trigger; 20 = intraday anchor (shallow-pullback support); 50 = deeper pullback; 200 = "
            "regime filter. Bull stack: price&gt;9&gt;20&gt;50, rising 200. Flat 200 = sideways, signals "
            "unreliable."),
           ("The entry setup",
            "Pullback into the 20 EMA on declining volume, bounce with a volume spike + VWAP confluence = A "
            "setup. EMA = where, StochRSI = when, volume = conviction.")],
    signals=[
        ("EMA stack + slope (regime)","HIGH","MED","TRADE","Backbone — defines each TF\u2019s trend"),
        ("Price vs rising/falling 200","HIGH","MED","TRADE","Major regime; long above, short below"),
        ("Pullback to 20 EMA","MED","MED","TRADE","Dynamic support; shallow-dip bounce"),
        ("Confluence (EMA+VWAP+S/R)","HIGH","LOW","TRADE","Highest-conviction entry location"),
        ("Tangled / flat EMAs","LOW","MED","AVOID","Chop; no crossover saves you"),
    ],
    tf=[("Monthly / Weekly","High","50/200 stack defines the dominant regime."),
        ("Daily","High","Swing structure + institutional 50/200 DMA."),
        ("4H / 1H","High","Intermediate structure + pullback zones."),
        ("15m / 5m","High","Intraday structure: 20 anchor, 9 trigger.")],
    reco="Include (strong) as the regime + dynamic-S/R backbone: stack/slope defines each TF\u2019s trend "
         "(high weight every TF); 20/50/200 = pullback-entry locations; crossover = confirmation only. Use "
         "9/20/50/200 primary; backtest 13-21-34 (A2).",
    reco_kind="include",
))

render_item(dict(
    id="ENG-3", title="RSI (Cardwell Ranges)", was="D8-2",
    meta=["regime + leading shift","Stage 5 · Engine"],
    verdict="Stronger and more leading than MACD — via Cardwell ranges, not naive 70/30. Bull 40\u201380 (40 "
            "floor), bear 20\u201360 (60 ceiling, ~55 on Nifty). The range-shift leads price; overbought "
            "pins in strong trends (ride). Ash\u2019s ceiling-rejection = exit, breakout = re-enter is "
            "exactly this framework.",
    paras=[("Levels",
            "Bull 40\u201380, super-bull 60\u201380+, bear 20\u201360, sideways 40\u201360 (avoid). 50 = "
            "divide; clean 50-cross in HTF direction after a pullback = continuation. Range shift: break 60 "
            "= bear\u2192bull, breach 40 = bull\u2192bear (leads price)."),
           ("Validated",
            "\u2018Rejects 55 then breaks 2nd/3rd try\u2019 = range-shift through the ceiling. \u2018Stays "
            "70\u2013100 long\u2019 = super-trend momentum. \u2018Daily runs 3+ days\u2019 = range persistence.")],
    signals=[
        ("HTF range regime (W/D)","HIGH","MED","TRADE","Defines the whole bias — RSI\u2019s best use"),
        ("Range shift (break 60/40)","HIGH","MED","TRADE","The \u201855 breakout\u2019; leads price"),
        ("Super-trend pinning","HIGH","MED","TRADE","Ride; don\u2019t fade"),
        ("Ceiling rejection (55 reject)","MED","MED","CAUTION","Exit call, NOT buy put (asymmetric)"),
        ("Sideways 40\u201360","LOW","MED","AVOID","Whipsaw; stand aside"),
    ],
    tf=[("Monthly / Weekly","High","Sets the range regime governing all below."),
        ("Daily","High","3-day continuation + swing sweet spot."),
        ("4H / 1H","Mod\u2013high","Intermediate regime + pullback-to-40."),
        ("15m / 5m","Moderate","50/55-cross timing in HTF direction.")],
    reco="Include (strong) as a regime + leading-shift signal via Cardwell ranges. High weekly/daily "
         "weight. Encode the asymmetry: ceiling rejection = exit, breakout = re-enter, super-trend = ride, "
         "sideways = stand aside. Set range from HTF first; backtest the ceiling per instrument.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-4", title="MACD Crossover", was="D8-1",
    meta=["momentum confirm (lagging)","Stage 5 · Engine"],
    verdict="A lagging, price-derived tool. Its value comes from the higher-TF MACD as a trend filter — the "
            "raw 5-min crossover is the weakest, most whipsaw-prone form. Demoted from \u2018primary\u2019 to "
            "confirmation, weighted by multi-TF agreement.",
    paras=[("Mechanism",
            "Three reads by increasing lag: histogram slope \u2192 signal-line cross \u2192 zero-line cross. "
            "Divergence is the one leading read. Works in trends, whipsaws in chop."),
           ("Caveat",
            "On 5-min the 12/26 EMAs span 60\u2013130 min — the cross fires after much of the move. Use the "
            "higher-TF MACD for bias; gate by ENG-1.")],
    signals=[
        ("Higher-TF trend filter","MED","MED","TRADE","Highest-value use for 5-min bias"),
        ("Multi-TF alignment","MED","MED","TRADE","Confirmation stack; highest conviction"),
        ("Zero-line + histogram slope","MED","MED","CAUTION","Regime + earliest momentum tell"),
        ("Raw 5-min crossover","LOW","HIGH","AVOID","Lag + whipsaws; weakest form"),
    ],
    tf=[("Monthly / Weekly","Low\u2013mod","Regime, lags at turns."),
        ("Daily","Moderate","Cleanest MACD trend filter."),
        ("1H","Moderate","Best intraday trend filter."),
        ("5m","Low (confirm)","Whipsaw/lag; timing only after HTF agrees.")],
    reco="Keep MACD as a higher-TF trend filter + confirmation, weighted by multi-TF agreement — never a "
         "standalone 5-min trigger. Prefer histogram slope + divergence over the lagging crossover.",
    reco_kind="caveat",
))

render_item(dict(
    id="ENG-5", title="Supertrend", was="D8-8",
    meta=["trend filter + dynamic SL","Stage 5 · Engine"],
    verdict="ATR-based trend line: green (buy) below price, red above, flips on a close through it. "
            "Volatility-adaptive + \u2018sticky\u2019, so it doubles as a dynamic trailing stop. India\u2019s "
            "most-used intraday indicator — but a clean trend filter, not an every-flip trigger (raw flips "
            "= 45\u201360% win).",
    paras=[("Use as a filter",
            "Only longs green, shorts red. Raw flips whipsaw in chop (3+ flips in 20 bars = stand flat). The "
            "line = a volatility-adaptive trailing SL (add 0.5\u00d7ATR buffer)."),
           ("Settings + combo",
            "Nifty ~7/3 or 10/2\u20133; BankNifty 10/3\u20133.5. Killer combo: Supertrend(10,2) + VWAP on "
            "Nifty 5m, buy only when green AND above VWAP (~65%+ follow-through).")],
    signals=[
        ("Regime (green/red filter)","MED","MED","TRADE","Only longs green, shorts red"),
        ("The line as trailing SL","MED","MED","TRADE","Volatility-adaptive stop"),
        ("Raw flip standalone","LOW","HIGH","AVOID","45\u201360% win; whipsaws in chop"),
        ("Flip + VWAP + HTF agree","MED","MED","TRADE","The filtered combo; ~65%+"),
    ],
    tf=[("Weekly / Daily","Moderate","Higher-TF filter for the 15m signal."),
        ("15m","Mod (primary)","Primary Indian intraday TF for direction."),
        ("5m","Mod (timing)","Entry timing after 15m confirms."),
        ("SL role","All TFs","The line = a trailing stop.")],
    reco="Include as a trend filter + dynamic trailing SL, gated by ENG-1 and confirmed by VWAP + "
         "higher-TF agreement — never an every-flip entry. Turn off 30 min before RBI/Budget/FOMC.",
    reco_kind="caveat",
))

render_item(dict(
    id="ENG-6", title="Stochastic RSI", was="D8-3",
    meta=["entry-timing trigger (fastest)","Stage 5 · Engine"],
    verdict="The fastest but noisiest oscillator — a pure entry-timing trigger, not direction. It fires at "
            "the pullback bottom the RSI/MACD cascade predicted, and whipsaws the most, so it\u2019s gated "
            "hardest. RSI decides which way; StochRSI decides the exact tick.",
    paras=[("Mechanism",
            "\u2018Momentum of momentum\u2019 — the real signal is %K crossing %D inside an extreme zone "
            "(OB&gt;0.8/OS&lt;0.2); a zone-touch without the crossover is noise."),
           ("Caveat",
            "Pins at extremes worse than RSI — never fade the pinning. In a bull, only oversold crosses = "
            "re-entries; overbought crosses = exit/ignore, not puts. 14-3-3 (21-5-5 to slow).")],
    signals=[
        ("%K/%D out of OS (bull)","MED","MED","TRADE","Times the pullback bottom — CALL entry"),
        ("%K/%D out of OB (bear)","MED","MED","TRADE","Mirror; only with a bear cascade"),
        ("OB cross in a bull","LOW","MED","CAUTION","Exit/ignore, NOT buy put"),
        ("Pinned at extreme","MED","MED","TRADE","Embedded momentum; ride"),
        ("Chop crosses","LOW","MED","AVOID","Worst whipsaw of the three"),
    ],
    tf=[("Monthly / Weekly","Low","Too fast for regime; RSI/MACD own HTF."),
        ("Daily","Low\u2013mod","Times daily swing entries (21-5-5)."),
        ("4H / 1H","Moderate","Pullback timing within the trend."),
        ("15m / 5m","Mod\u2013high","Its home — the entry trigger.")],
    reco="Include as the fast entry trigger at the bottom of the cascade — %K/%D cross out of oversold "
         "(bull)/overbought (bear) = the 5m/15m tick. Gate hardest; counter-trend crosses = exit not "
         "reversal; never fade the pinning.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-7", title="VWAP + SL Decisions", was="D8-4",
    meta=["intraday anchor + SL hub","Stage 5 · Engine"],
    verdict="The intraday complement to EMA — institutional fair-value line. Above = call bias, below = "
            "put, flat-oscillating = no-trade. Pullback to VWAP + 20 EMA = A+ entry. Bands are NOT S/R "
            "(price walks them in trends). Also the hub of the four-SL framework.",
    paras=[("Reclaim / rejection",
            "Lose VWAP, sellers fail on rising volume, reclaim = bullish continuation. Rally into VWAP from "
            "below, roll = flip to resistance. Break + failed retest kills most false signals (your G8 "
            "hunt, cross-referenced)."),
           ("Four-SL framework",
            "VWAP SL, Hunt Zone = VWAP \u2212 0.5\u00d7ATR (stay-in buffer), Structure SL (deeper = exit), "
            "ATR SL (size). One close below = watch; two = hunt; reclaim = stay; deeper than hunt = "
            "structure SL.")],
    signals=[
        ("Above/below VWAP (bias)","HIGH","MED","TRADE","Core intraday call/put lean"),
        ("Pullback to VWAP + 20 EMA","HIGH","LOW","TRADE","Highest-conviction entry location"),
        ("VWAP reclaim on volume","MED","MED","TRADE","Chop-to-trend trigger"),
        ("Rejection / failed reclaim","MED","MED","TRADE","Support\u2192resistance flip"),
        ("Oscillating flat VWAP","LOW","MED","AVOID","Range-day signature; no edge"),
    ],
    tf=[("Monthly / Weekly","Low (anchored)","Session VWAP resets; use anchored from swings."),
        ("Daily","Low\u2013mod","Anchored VWAP as multi-day S/R."),
        ("1H / 15m","High","Intraday bias + S/R + pullback zone."),
        ("5m","High","Execution anchor: reclaim/rejection + hunt-zone SL.")],
    reco="Include (strong, intraday) as the bias anchor + dynamic S/R + SL hub. Pullback + 20 EMA = A+ "
         "entry; reclaim on volume = trigger. SL: VWAP SL + hunt zone \u2192 structure SL. Bands = context "
         "only, never mean-revert in a trend. First 30 min unreliable; index needs a futures-volume proxy.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-8", title="Volume & Liquidity", was="D8-5",
    meta=["conviction filter + tradeability gate","Stage 5 · Engine"],
    verdict="Two signals under one name, neither a direction-setter: (1) volume-as-confirmation = a "
            "conviction multiplier on the cascade\u2019s direction; (2) liquidity-as-gate = a binary "
            "tradeability filter. Nifty/BankNifty pass automatically; stock options must clear a 4-metric "
            "liquidity screen or spreads kill the edge.",
    paras=[("Confirmation",
            "Breakout needs volume &gt;50% over 20-day avg (else fakeout); divergence = exhaustion; climax "
            "(3\u201310\u00d7) = blow-off; dry-up precedes breakout. Low volume \u2260 no move "
            "(ease-of-movement)."),
           ("Liquidity gate",
            "Illiquid stock options cost 5\u00d7+ the spread; check volume + OI + spread + bid/ask SIZE. "
            "Index has no native volume \u2192 futures proxy. Spreads widen with VIX.")],
    signals=[
        ("Breakout volume expansion","MED","MED","TRADE","Validates a cascade-confirmed breakout"),
        ("RVOL intraday","MED","MED","TRADE","Live participation gauge"),
        ("Volume divergence","LOW","MED","CAUTION","Move on fumes; exhaustion"),
        ("Volume climax","LOW","HIGH","CAUTION","Take profit; don\u2019t chase"),
        ("Liquidity gate","LOW","MED","AVOID","Stock options must pass; index auto-pass"),
    ],
    tf=[("Monthly / Weekly","Low\u2013mod","Confirms major breakouts."),
        ("Daily","Mod\u2013high","Breakout-volume for swing conviction."),
        ("15m / 5m","Moderate","RVOL + trigger-candle volume."),
        ("Liquidity gate","Binary","Per-instrument, always; hard GO/NO-GO.")],
    reco="Include as (1) a conviction multiplier on the cascade\u2019s direction and (2) a hard liquidity "
         "gate — stock options must clear a 4-metric screen. Never a direction signal. Index needs a "
         "futures-volume proxy.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-9", title="ATR (Average True Range)", was="D8-10",
    meta=["volatility backbone","Stage 5 · Engine"],
    verdict="The volatility backbone, not a direction signal. Feeds Supertrend bands, Keltner/TTM, SL "
            "sizing, the hunt zone (VWAP \u2212 0.5\u00d7ATR) and position sizing — the engine behind the "
            "Volatility column. 0 directional weight, essential plumbing.",
    paras=[("What it signals",
            "ATR expansion = volatility rising = move starting; contraction = calm (low percentile = "
            "squeeze setup). ATR spike (bar range &gt; ATR) = momentum igniting. SL = 1.5\u00d7ATR; lots = "
            "risk \u00f7 ATR-stop."),
           ("Per-instrument",
            "Nifty, BankNifty, mid-caps have very different ATRs — all ATR-derived levels must be "
            "per-instrument (BankNifty\u2019s larger ATR = higher Supertrend multiplier).")],
    signals=[
        ("ATR expanding + trend","MED","HIGH","TRADE","\u2018The move is real\u2019"),
        ("ATR spike","MED","HIGH","TRADE","Momentum start (with trend)"),
        ("ATR contracting","LOW","LOW","CAUTION","Compression \u2192 squeeze setup"),
        ("High ATR + chop","LOW","HIGH","AVOID","Wide whipsaws; wide stops"),
    ],
    tf=[("Every timeframe","Infra","Volatility per TF; feeds SL/sizing + regime."),
        ("Directional weight","Zero","Substrate for Supertrend/Bollinger/SL."),
        ("Per-instrument","Required","Nifty vs BankNifty vs stocks differ.")],
    reco="Include as the volatility-regime + SL/sizing backbone (0 directional weight). Track ATR + "
         "percentile per instrument per TF; use for all SL distances (1.5\u00d7ATR), the hunt zone, and "
         "sizing.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-10", title="Bollinger Bands + Squeeze", was="D8-9",
    meta=["volatility-expansion timer","Stage 5 · Engine"],
    verdict="Keep the squeeze, not band-touch mean-reversion (fails in trends). The squeeze = bands "
            "compress = coiled spring = a big directional move is loading — exactly what an options buyer "
            "wants. The squeeze tells you when, not which way.",
    paras=[("Squeeze mechanics",
            "BandWidth &lt;~4% = squeeze; longer squeezes resolve more violently. TTM Squeeze: BB(20,2) "
            "inside Keltner(20,1.5\u00d7ATR) = ON; expand back outside = FIRED = trigger; momentum histogram "
            "gives direction (~68\u201372% filtered)."),
           ("For options",
            "Buy premium DURING the squeeze (low IV), profit on expansion. Nifty squeezes before "
            "expiry/events — pairs with NAT-1 (buy the squeeze early, not into the event). Require volume "
            "to avoid head-fakes.")],
    signals=[
        ("Squeeze ON","LOW","LOW","CAUTION","Prepare: buy cheap premium, move loading"),
        ("Squeeze FIRED + histogram","MED","HIGH","TRADE","Direction from histogram + volume"),
        ("Band-touch in range","LOW","MED","CAUTION","Mean-revert only if confirmed range"),
        ("Band-touch in trend","LOW","MED","AVOID","Price walks the band; don\u2019t fade"),
    ],
    tf=[("Monthly / Weekly","Moderate","Daily/weekly squeeze = swing move loading."),
        ("Daily","Moderate","Classic squeeze-to-breakout horizon."),
        ("15m / 5m","Moderate","Intraday burst; pre-event compression."),
        ("Direction","\u2014","Squeeze = when; histogram = which way.")],
    reco="Include as the squeeze / volatility-expansion detector (the \u2018when is a move coming\u2019 "
         "tool) — NOT band-touch mean-reversion. TTM Squeeze + histogram; direction from histogram/volume; "
         "require volume to avoid head-fakes.",
    reco_kind="include",
))

render_item(dict(
    id="ENG-11", title="Support & Resistance + OI Walls", was="E10",
    meta=["the \u2018where\u2019 map","Stage 5 · Engine"],
    verdict="Not a direction signal — the location layer defining where entries trigger, moves stall, and "
            "pullbacks bottom. Its entire edge is confluence (a lonely line is near-worthless). Works "
            "because it\u2019s self-fulfilling — everyone watches the same levels, so stops pile just beyond "
            "them (your G8 hunt).",
    paras=[("Types — price + OI",
            "Price: prior swing H/L, day/week/month H/L/C, round numbers, 52w H/L + dynamic "
            "EMA/VWAP/CPR/Fib. Options-OI (the edge): Call Wall (resistance), Put Wall (support), the OI "
            "range, Max Pain (expiry magnet), Change-in-OI (reinforced = holds, abandoned = breaks). "
            "Writer-first lens: high Call OI = writers betting price stays below."),
           ("Break vs bounce",
            "Bounce (wait for the reaction + volume), breakout (close + volume + follow-through), retest "
            "(role reversal, highest-probability). Zones not lines. Auto-flag prices where \u22653 "
            "level-types stack = A+ zones.")],
    signals=[
        ("Confluence zone (3+ types)","HIGH","MED","TRADE","Prior H/L + round + EMA/VWAP/CPR + OI wall"),
        ("Call wall / Put wall","MED","MED","TRADE","Writer-defended intraday S/R"),
        ("Change-in-OI","MED","MED","CAUTION","Reinforced holds; abandoned breaks fast"),
        ("Role reversal (flip)","MED","MED","TRADE","Broken S\u2194R; very reliable"),
        ("Max pain (expiry)","LOW","LOW","CAUTION","Near expiry only; trend day overrides"),
    ],
    tf=[("Monthly / Weekly","High","Major levels frame the regime; strongest S/R."),
        ("Daily","High","Prior-day H/L/C, swing levels, 50/200 DMA."),
        ("4H / 1H","Mod\u2013high","Intermediate structure; intraday zones."),
        ("Options-OI (walls/max pain)","High (intraday)","Intraday range + expiry gravity; resets each expiry.")],
    reco="Include (strong) as the \u2018where\u2019 map: price-chart S/R + an auto-confluence detector "
         "(\u22653 types = A+ zone), plus options-OI S/R (call/put walls, max pain, change-in-OI, "
         "writer-first lens). Confluence &gt; lonely level; wait for the reaction not the touch; OI resets "
         "each expiry.",
    reco_kind="include",
))

# ================= DIRECTION SEQUENCE — CODING PIPELINE =================
story += [
    Paragraph("Direction Sequence — Coding Pipeline", h1),
    HBar(color=AMBER, thick=1.4), sp(2),
    Paragraph("How the engine items chain (new IDs) — gate-first, top-down. Each stage can veto the next. "
              "Stages 1\u20132 gate everything; each higher timeframe (M\u2192W\u2192D\u21924H\u21921H\u2192"
              "15m\u21925m) gates the one below.", small),
    sp(6),
    generic_table(
        ["#","Stage","Question","Items","Gate / action"],
        [
            ["1","Regime gate","Trend or chop?","ENG-1 ADX+CHOP · PRE-4 CPR width","Chop / wide CPR \u2192 STOP. Runs first."],
            ["2","Higher-TF bias","Which way?","ENG-2 EMA · ENG-3 RSI (M\u21924H)","Sets dominant direction. Conflicting \u2192 wait."],
            ["3","Direction confirm","Momentum agrees?","ENG-4 MACD · ENG-5 Supertrend","Must agree with step 2, else no trade."],
            ["4","Location (where)","Pullback bottom?","ENG-11 S/R+OI · ENG-7 VWAP · ENG-2 EMA","Confluence zone (3+ types) = entry area."],
            ["5","Timing (when)","Turn happening?","ENG-6 StochRSI","%K/%D out of OS/OB at the zone = trigger."],
            ["6","Conviction","Move real?","ENG-8 Volume · ENG-9 ATR · ENG-10 squeeze","Weak vol / no expansion \u2192 skip / size down."],
            ["7","Risk (stop)","Where\u2019s the exit?","ENG-7 VWAP · ENG-5 Supertrend · ENG-9 ATR","SL from VWAP / Supertrend / structure \u00b1 ATR."],
        ],
        [CONTENT_W*0.05, CONTENT_W*0.14, CONTENT_W*0.16, CONTENT_W*0.30, CONTENT_W*0.35],
        center_cols=(0,)),
    sp(6),
    callout("<b>THE RULE.</b> regime \u2192 bias \u2192 direction \u2192 location \u2192 timing \u2192 "
            "conviction \u2192 stop. Pre-open, PRE-3 (gap) sets the first-hour bias. A bull cascade buys "
            "CALLs on the with-trend trigger; the counter-trend signal is an exit / wait, never a PUT "
            "(mirror in a bear cascade).", bg=TEAL_L, bar=TEAL, tcolor=INK),
    sp(6),
    Band("Pre-open handoff — GIFT (PRE-2) \u2192 gap classifier (PRE-3)", color=TEAL_DK, h=20, size=10.5),
    sp(4),
    Paragraph("GIFT gets you leaning the right way overnight; PRE-3 keeps you from buying the "
              "exhaustion-gap bottom. The sequence:", body_l),
    generic_table(
        ["Step","Read","Action"],
        [
            ["1 · Overnight","GIFT red on real, decisive news (Dow &gt;0.5%, clear catalyst); discount &gt;0.5%","Lean short; high-confidence Nifty OPENS down"],
            ["2 · Magnitude","Basis-adjusted implied gap; is it &gt;0.5% or noise (&lt;\u00b10.2%)?","Noise \u2192 stand down; large \u2192 proceed"],
            ["3 · 9:00 refresh","Any 6:30\u20139:15 reversal? Offsetting domestic event? VIX already blown?","Flip / gate off if so"],
            ["4 · Open (9:15)","Gap prints; DO NOT trade the print","Hand to PRE-3"],
            ["5 · Classify","PRE-3: runaway/breakaway (continue) vs exhaustion (~78% reverse)","Runaway \u2192 with-trend; exhaustion \u2192 wait for rollover"],
            ["6 · Enter","9:30\u20139:45 on confirmed type + volume; PRE-1 IV-crush check","Buy puts after confirmation, not at 9:15"],
        ],
        [CONTENT_W*0.16, CONTENT_W*0.46, CONTENT_W*0.38],
        header_color=TEAL),
    sp(4),
    callout("\u2018Same way\u2019 is reliable for the OPEN\u2019s <i>direction</i>, not the session or the "
            "magnitude. A fear-driven gap-down is often an exhaustion gap that opens down then rallies — "
            "and high overnight VIX can IV-crush a correctly-directional put. Read PRE-1 + PRE-2 + PRE-3 "
            "together.", bg=RED_L, bar=RED),
    PageBreak(),
]

# ================= THE TWO BOOKS =================
story += [
    Paragraph("The Two Books — Branch Filters", h1),
    HBar(color=TEAL, thick=1.4), sp(2),
    Paragraph("Once the funnel outputs index direction, each book applies its own further filters. "
              "Document A owns Branch A (index options); Branch B (swing / stock) moves to Document B, which "
              "consumes Document A\u2019s index direction as its first filter rather than re-deriving it.",
              small),
    sp(6),
    generic_table(
        ["Branch","Filters (in order)","Output"],
        [
            ["A · Index options (Nifty/BankNifty intraday) \u2014 this document",
             "Options intelligence (PCR, max pain, OI buildup, IV percentile, Greeks) \u2192 expiry behaviour (Tue weekly, last-Tue monthly) \u2192 5-min execution cascade + VWAP SL-hunt",
             "Strike + CE/PE"],
            ["B · Swing / stock (individual name) \u2014 Document B",
             "Inherit index direction (1st filter) \u2192 sector performance & rotation \u2192 NSE / Nifty-500 screen \u2192 relative strength vs Nifty \u2192 fundamentals (results, NISM Ch.8) \u2192 stock technical cascade (same engine, per-stock params) \u2192 STK-SEA stock/sector seasonality \u2192 stock-option liquidity gate",
             "Stock swing / stock option"],
        ],
        [CONTENT_W*0.20, CONTENT_W*0.62, CONTENT_W*0.18]),
    sp(6),
    callout("<b>Two-document architecture.</b> The shared trunk (MAC/NAT/FLO/PRE/ENG) lives in Document A "
            "and is <i>referenced</i> by Document B, not duplicated — one source of truth. Document B "
            "reuses the ENG cascade with per-stock parameters (different ATR, RSI ceilings, liquidity "
            "checks) and starts from \u2018inherit index direction from Document A\u2019. Same funnel "
            "philosophy, same ID convention (STK- prefix, old-alias kept), so the two read as one system. "
            "Stock/sector seasonality (earnings windows, annual sector cycles) lives in Document B as "
            "STK-SEA — not here.", bg=AMBER_L, bar=AMBER),
    PageBreak(),
]

# ================= FOUNDATION LIST TRACKER =================
tracker = [
    ["MAC-1","B4","Global macro news","Macro","HIGH","HIGH","Y*"],
    ["MAC-2","B6","US / Asian correlation","Macro","HIGH","MED","Y"],
    ["MAC-3","B12","Macro levels (DXY/10Y/crude/gold)","Macro","MED","MED","Y*"],
    ["NAT-1","B5","National news","National","V.HIGH","V.HIGH","Y*"],
    ["FLO-1","C1","FII/DII cash flow","Flows","MED","MED","Y*"],
    ["FLO-2","C2","FII derivatives positioning","Flows","MED","MED","Y"],
    ["PRE-1","G5","India VIX regime","Pre-mkt","Gate","Gate","Y"],
    ["PRE-2","G7","GIFT Nifty","Pre-mkt","HIGH","MED","Y"],
    ["PRE-3","E9","Gap behaviour","Pre-mkt","MED","MED","Y"],
    ["PRE-4","D8-11","CPR (central pivot range)","Pre-mkt","HIGH","Fcast","Y"],
    ["PRE-5","A7","Calendar day-type / seasonality","Pre-mkt","Context","\u2014","Y*"],
    ["ENG-1","D8-7","Regime filter (ADX+CHOP)","Engine","Gate","Gate","Y"],
    ["ENG-2","D8-6","EMAs across timeframes","Engine","HIGH","MED","Y"],
    ["ENG-3","D8-2","RSI (Cardwell ranges)","Engine","HIGH","MED","Y"],
    ["ENG-4","D8-1","MACD crossover","Engine","MED","MED","Y*"],
    ["ENG-5","D8-8","Supertrend","Engine","MED","MED","Y*"],
    ["ENG-6","D8-3","Stochastic RSI","Engine","MED","HIGH","Y"],
    ["ENG-7","D8-4","VWAP + SL decisions","Engine","HIGH","MED","Y"],
    ["ENG-8","D8-5","Volume & liquidity","Engine","MED","MED","Y"],
    ["ENG-9","D8-10","ATR","Engine","Infra","HIGH","Y"],
    ["ENG-10","D8-9","Bollinger + squeeze","Engine","MED","HIGH","Y"],
    ["ENG-11","E10","Support & resistance + OI","Engine","HIGH","MED","Y"],
]
story += [
    Paragraph("Foundation List Tracker", h1),
    HBar(color=TEAL, thick=1.4), sp(2),
    Paragraph("Funnel order · new IDs · direction / volatility rollup. Y = include, Y* = include with "
              "caveats. Gate / Infra / Fcast / Context = non-directional roles.", small),
    sp(6),
    generic_table(
        ["ID","Was","Item","Stage","Dir","Vol","Incl."],
        tracker,
        [CONTENT_W*0.10, CONTENT_W*0.09, CONTENT_W*0.34, CONTENT_W*0.13, CONTENT_W*0.12, CONTENT_W*0.11, CONTENT_W*0.09],
        center_cols=(1,4,5,6)),
    sp(6),
    callout("<b>22 of 22 funnel items researched — the Track A trunk is complete.</b> The three former "
            "pre-market gates are now written up: PRE-1 (VIX, master gate), PRE-2 (GIFT, opening-only), "
            "PRE-5 (calendar day-type). Next: branch filters — Branch A (OPT: PCR / max pain / OI / expiry) "
            "here; Branch B (STK) in Document B. Backtesting A1\u2013A7 and remaining patterns are Track C.",
            bg=TEAL_L, bar=TEAL, tcolor=INK),
    sp(10),
    Paragraph("FORTUNA — Foundation List · Direction Funnel · Track A · v0.8 · Confidential — Internal Use "
              "Only", tiny),
]

# ================= BUILD =================
doc = Doc("/home/claude/Fortuna_TrackA_Direction_Funnel_v0_8.pdf")
doc.build(story)
print("BUILT OK")
