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
        "FORTUNA · Branch A · Index Options · v01")
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



# ======================================================================
# ================= FORTUNA · BRANCH A · INDEX OPTIONS ==================
# ======================================================================

cst = mk("cst", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=AMBER)
cintro = mk("cintro", fontName="Helvetica", fontSize=10, leading=15, textColor=TEAL_L)
cintro2 = mk("cintro2", fontName="Helvetica", fontSize=9, leading=14, textColor=colors.HexColor("#9fc9c9"))

# ================= COVER =================
story += [
    NextPageTemplate("body"),
    Spacer(1, 30*mm),
    Paragraph("FORTUNA", titleBig),
    Spacer(1, 3),
    Paragraph("Branch A — Index Options", cst),
    Spacer(1, 10),
    Paragraph("Fortuna-Index &nbsp;|&nbsp; v01 &nbsp;|&nbsp; 13 Jul 2026", titleSub),
    Spacer(1, 16*mm),
    Paragraph("The first of the two book-level branches. Once the shared trunk "
              "(MAC / NAT / FLO / PRE / ENG) outputs the index-direction verdict, Branch A layers "
              "options intelligence on top of it to produce the actual index-options trade: "
              "strike + CE/PE + entry / exit + SL. Every item keeps a permanent old-ID alias "
              "(OPT-1 was G3) so references match across every document.", cintro),
    Spacer(1, 8),
    Paragraph("v01 — five OPT items researched to the trunk format: OPT-1 IV percentile / PCR "
              "(premium & crowding gate), OPT-2 max pain + OI walls (location / gravity), "
              "OPT-3 change-in-OI (intent / strike selection), OPT-4 expiry behaviour "
              "(day-type / timing), OPT-5 Greeks for the buyer (sizing / risk). This document "
              "references the v0.8 trunk rather than duplicating it — one source of truth.", cintro2),
    PageBreak(),
]

# ================= WHAT BRANCH A CONSUMES =================
story += [
    Paragraph("What Branch A Consumes from the Trunk", h1),
    HBar(color=AMBER, thick=1.4), sp(6),
    Paragraph("Read the trunk first. Branch A <b>does not re-derive direction</b> — it inherits the "
              "trunk's verdict object and layers options intelligence to choose the instrument. Direction "
              "is one field it receives; on many days it reads <i>unknown / irrelevant</i> and Branch A "
              "still fully specifies a trade (or a sit-out) from premium, location, intent, timing and "
              "risk. The trunk lives in the Direction-Funnel document (v0.8) and is referenced by ID here.",
              lead),
    sp(2),
    Paragraph("The inherited verdict object", h3),
    callout("verdict = { <b>tradeable</b> · <b>day_type</b> · <b>direction</b> · <b>conviction</b> · "
            "<b>volatility_character</b> · <b>size</b> · <b>trap_risk</b> · <b>stop</b> }  "
            "&nbsp;— produced by the trunk, consumed by Branch A.",
            bg=TEAL_L, bar=TEAL, tcolor=INK),
    sp(8),
    Paragraph("Trunk → Branch A wiring", h3),
    generic_table(
        ["OPT item", "Consumes from trunk", "What Branch A adds"],
        [
            ["OPT-1 · IV %ile / PCR", "PRE-1 India VIX", "per-strike premium richness + crowding / IV-crush gate"],
            ["OPT-2 · Max pain + walls", "ENG-11 OI walls", "expiry gravity + the writer-defended range (location)"],
            ["OPT-3 · Change-in-OI", "FLO-2 (EOD) · ENG-11", "live intraday intent → strike selection"],
            ["OPT-4 · Expiry behaviour", "PRE-5 weekday map", "DTE theta / gamma clock + intraday timing"],
            ["OPT-5 · Greeks (buyer)", "PRE-1 + NAT-1", "sizing + the IV-crush veto + exit clock"],
        ],
        [CONTENT_W*0.26, CONTENT_W*0.28, CONTENT_W*0.46]),
    sp(6),
    callout("<b>The output.</b> Branch A turns the inherited direction into a concrete order: "
            "<b>strike + CE/PE + entry + exit + SL</b>. It never overrides the trunk's direction — it "
            "decides <i>whether</i> to express it in options at all (premium gate), <i>where</i> "
            "(walls / max pain), <i>which strike</i> (intent + Greeks), <i>when</i> (expiry clock) and "
            "<i>how much</i> (Greeks sizing).", bg=AMBER_L, bar=AMBER),
    PageBreak(),
]

# ================= BRANCH A · OPT ITEMS =================
story += divider("A", "Branch A · Index options",
                 "Options intelligence on index direction -> strike + CE/PE · OPT-1..5")

# ---- OPT-1 ----
render_item(dict(
    id="OPT-1", title="IV Percentile / PCR", was="G3 (PCR)",
    meta=["IV-percentile = new item", "Branch A · Index options · consumes PRE-1"],
    verdict="Two sentiment / premium gauges, neither a direction signal — the branch's premium-and-crowding "
            "gate, the OPT twin of PRE-1. IV percentile answers is premium cheap or expensive, buy vs sell, "
            "and how brutal IV-crush risk is — the buyer's single most important pre-trade check. PCR is a "
            "lagging, relative, contrarian-at-extremes gauge: near-useless in its mid-band and dangerous as "
            "a standalone trigger (the folk 'PCR &gt; 1.2 = buy calls' is exactly the overfit to avoid). "
            "Score both as Gate / Context: they set size, trap_risk and premium context, never direction.",
    paras=[("What job + does it affect direction?",
            "IV percentile is a premium / regime gate (0 direction): high IV rank / pctile (~80%+) = options "
            "expensive, favour selling; low (~10-20%) = cheap, favour buying. For a buyer it decides whether "
            "a directional bet can even pay off, since a correct call still loses if IV crushes. PCR is "
            "contrarian only at extremes and is explicitly not a timing tool — its honest use is a "
            "conviction filter on a price read, not a trigger."),
           ("Mechanism + the writer trap",
            "High PCR (&gt; 1.2) — 'more puts, bearish' — often acts as support because much index-put OI is "
            "just insurance / hedging, so the level misleads. PCR also compresses the whole chain into one "
            "number and hides where the writing sits — that 'where' is OPT-2's job. Read PCR as a trend vs "
            "its own recent range, OI-based not volume-based."),
           ("Skeptic's note",
            "No magic thresholds; PCR is lagging and relative. Nifty typically 0.8-1.3; extremes "
            "&gt; 1.3 / &lt; 0.7 mark stretched positioning, &gt; 1.8 / &lt; 0.5 genuine capitulation — none "
            "are automatic signals. SEBI FY22-FY25: ~90-91% of F&amp;O individuals net-lose — this gate "
            "exists to stop trades, not start them.")],
    signals=[
        ("IV %ile &lt; 20 (cheap)", "Gate", "LOW", "TRADE", "Buying viable; pair with ENG-10 squeeze"),
        ("IV %ile 60-80 (rich)", "Gate", "MED", "CAUTION", "Size down; prefer spreads over naked longs"),
        ("IV %ile &gt; 80 (expensive)", "Gate", "HIGH", "AVOID", "IV-crush risk; buying penalised even if right"),
        ("Pre-event IV ramp", "Gate", "HIGH", "AVOID", "Buy before the ramp (ENG-10), never into it"),
        ("PCR &gt; 1.3 / &lt; 0.7", "Context", "MED", "CAUTION", "Contrarian fade-warning, not an entry"),
        ("PCR &gt; 1.8 / &lt; 0.5", "Context", "HIGH", "TRADE", "Genuine capitulation; needs price confirm"),
        ("PCR mid 0.8-1.2", "~0/noise", "-", "AVOID", "No edge; do not read the level"),
        ("PCR trend + price agree", "Conv+", "MED", "TRADE", "Multiplier only; never the trigger"),
    ],
    tf=[("Monthly", "Low", "IV extremes = a Fortuna-Cash vol backdrop; PCR ~0."),
        ("Weekly", "Mod", "The week's premium-cost + crowding regime; feeds size."),
        ("Daily", "High (gate)", "Pre-open buy / sell / sit + size + IV-crush call."),
        ("1H / intraday", "Gate (0 dir)", "Conditions size + trap_risk; PCR trend only.")],
    reco="Include IV percentile as the premium / IV-crush gate — a rolling 252-day percentile of ATM IV "
         "(not fixed bands) setting buy-vs-sell-vs-sit and size, flagging IV-crush trap_risk (couple "
         "NAT-1 / MAC-1), greenlighting cheap-premium buys with the ENG-10 squeeze; normalise per "
         "instrument. Include PCR as a contrarian-extreme + conviction filter only (OI-based, read as a "
         "trend). Drop the folk directional bands and volume-PCR standalone. OPT-1 sets the weather; it "
         "hands 'where is the writing' to OPT-2 and 'fresh intent' to OPT-3.",
    reco_kind="caveat",
))

# ---- OPT-2 ----
render_item(dict(
    id="OPT-2", title="Max Pain + OI Walls", was="G4",
    meta=["extends ENG-11", "Branch A · Index options"],
    verdict="The location layer for the options book — where the market is likely to stall and gravitate, "
            "not which way it goes. Extends ENG-11 with the options view: the chain as a defended range "
            "(put wall = support, call wall = resistance) and a gravity point (max pain) that pulls in "
            "quiet expiries and is ignored on trend / news days. Honest reliability is modest and the "
            "academic case for pinning is genuinely mixed, so it scores Location / Gravity + trap_risk — "
            "the 'always pins to max pain' belief is the overfit to reject.",
    paras=[("Max pain — gravity, not a magnet",
            "The strike where buyers lose most / writers keep most. It drifts toward in quiet range-bound "
            "expiries and is ignored when real news moves the market; relevant only in the final sessions, "
            "near-useless early. Pins within ~100 pts only ~55-65% when conditions favour — and even that "
            "overstates it: pinning evidence is strongest for single stocks with concentrated OI, weaker "
            "for liquid indices (sometimes the index just finishes near max pain because OI clustered where "
            "price already was)."),
           ("OI walls + the hand-off",
            "Highest Call OI = call wall (writers profit if price closes below); highest Put OI = put wall "
            "(writers defend by adding). The range between is where writers expect price to hold. Walls are "
            "probabilistic — price either stalls or blows through, and which shows first as change-in-OI "
            "(OPT-3): total OI is the map, change-in-OI is the movement on it. Stops pile just beyond walls "
            "— this is your G8 / ENG-7 SL-hunt zone."),
           ("Distance + shift",
            "Max pain near spot = a plausible pull; far = a big claim, unreliable. The one forward-looking "
            "edge: the direction max pain shifts intraday (rising = bullish repositioning) leads price — but "
            "that is change-in-OI in aggregate (wire once). OI resets every expiry; never carry yesterday's "
            "walls.")],
    signals=[
        ("Max pain near spot (quiet)", "Location", "LOW", "TRADE", "Gravity does little work; reliable"),
        ("Max pain far from spot", "~0", "MED", "AVOID", "A 300-400 pt pull is a big claim; don't believe it"),
        ("Max pain stable late", "Location", "LOW", "TRADE", "Stabilised early -> pinning more probable"),
        ("Max-pain shift direction", "Conv+", "MED", "TRADE", "Rising = bullish reposition; leads price"),
        ("Put wall (highest PE OI)", "Location", "MED", "TRADE", "Support; buy CE off it on reaction not touch"),
        ("Call wall (highest CE OI)", "Location", "MED", "TRADE", "Resistance; don't target a CE past a fat wall"),
        ("Broad OI plateau", "Location", "MED", "CAUTION", "A zone not a line; widen the stop"),
        ("Trend / news day", "~0", "HIGH", "AVOID", "Catalyst overrides max pain; size for wrong"),
    ],
    tf=[("Monthly", "Mod", "Monthly-expiry walls frame the bigger range."),
        ("Weekly", "Mod-high", "The weekly OI range is the week's battle-map."),
        ("Daily", "High", "Prior-close chain sets today's walls + gravity."),
        ("Intraday (expiry)", "High", "Live max pain + wall defend / break."),
        ("Intraday (non-expiry)", "Low", "Positions still building; too fluid.")],
    reco="Include (with caveats) as the location + gravity layer extending ENG-11: OI walls for strike "
         "selection (don't target a CE past a fat call wall; buy off the put wall on reaction; walls = "
         "SL-hunt zones) and max pain as conditional expiry-gravity — weighted only near expiry, only when "
         "near spot and stabilising, off entirely on trend / news days. Use the max-pain-shift as a weak "
         "conviction lead. Reject 'always pins'; size for being wrong. Hands the hold-vs-break question to "
         "OPT-3.",
    reco_kind="caveat",
))

# ---- OPT-3 ----
render_item(dict(
    id="OPT-3", title="OI Buildup / Change-in-OI", was="G6",
    meta=["the intent read", "Branch A · Index options"],
    verdict="The live intent layer — if OPT-2's total OI is the map, change-in-OI is the movement on it: "
            "whether a wall is being reinforced (holds) or abandoned (breaks), and who is committing fresh "
            "money now. The most directionally-flavoured OPT item, but still an intent / conviction "
            "confirmer, not a standalone direction generator. Its deliverable is strike selection. The "
            "trap: the four-quadrant matrix is a futures framework — on the option chain read it "
            "writer-first, per side, or you invert the signal. It is the live intraday twin of FLO-2 (EOD).",
    paras=[("The four states + the confirmer role",
            "Long buildup (px up + OI up) = fresh longs, strongest bullish; short buildup (px dn + OI up) = "
            "fresh shorts; long unwinding (px dn + OI dn) = longs exiting, weak, often a bounce brewing; "
            "short covering (px up + OI dn) = a rally with no fresh buyers that fades fast. It confirms "
            "conviction behind a move already visible on price — positioning can diverge from price (a "
            "false rally), so confirm against price."),
           ("Writer-first — the whole edge",
            "On the chain: call OI rising = call writing (resistance building, not bullish buyers); put OI "
            "rising = put writing (support building); call OI falling as price approaches = writers "
            "unwinding = the pre-breakout signature; put OI falling = support weakening. Confirm strength "
            "with the OI + volume grid (high vol + rising OI = strong; high vol + flat OI = churn; high vol "
            "+ falling OI = level abandoned)."),
           ("Timing + the opening-drive",
            "First 30 min mixes overnight / rollover / MTM noise — wait for the 10:00-10:30 clean read; "
            "mid-session cleanest; final-hour churn is often mechanical square-off (check the opposite "
            "side). So in the 9:39-10:00 window, change-in-OI is context, not a trigger (the price candle is "
            "the trigger); it becomes a true signal on the ~10:10 re-entry, which lands in the clean "
            "window. It also computes OPT-2's max-pain shift.")],
    signals=[
        ("Long buildup (px up + OI up)", "MED", "MED", "TRADE", "Fresh longs; buy CE with-trend"),
        ("Short buildup (px dn + OI up)", "MED", "MED", "TRADE", "Fresh shorts; buy PE with-trend"),
        ("Fresh put writing at a strike", "MED", "LOW", "TRADE", "Support firming; floor CE stop here"),
        ("Call-writer zone unwinding", "MED", "MED", "TRADE", "Pre-breakout signature; buy the break"),
        ("Short covering (px up + OI dn)", "LOW", "MED", "CAUTION", "No fresh buyers; fades fast, don't chase"),
        ("OI cluster (3-4 strikes)", "MED", "MED", "TRADE", "Institutional position; zone = conviction"),
        ("Single-strike change", "~0", "MED", "AVOID", "A hint, not a trade"),
        ("First-30-min change-in-OI", "~0", "HIGH", "AVOID", "Overnight / rollover noise; wait 10:00-10:30"),
    ],
    tf=[("Monthly / Weekly", "Low", "Multi-day OI trend (overlaps FLO-2 EOD)."),
        ("Daily", "Mod", "Prior-session change-in-OI biases the open."),
        ("Intraday (10:30->close)", "High", "Wall reinforce / abandon + strike selection."),
        ("Intraday (first 30m)", "Near-zero", "Noise; do not act.")],
    reco="Include (strong, intraday) as the live intent layer, read writer-first per side: the "
         "four-quadrant buildup as a conviction confirmer (MED direction — highest of the OPT items, still "
         "a confirmer) and the wall reinforce-vs-abandon read answering OPT-2's hand-off. Deliverable = "
         "strike selection: buy toward strikes where opposing writers unwind, floor stops at fresh-writer "
         "defence, size on cluster (zone) signals with volume. Gate behind the 10:00-10:30 window; confirm "
         "against price (divergence = trap-warning).",
    reco_kind="include",
))

# ---- OPT-4 ----
render_item(dict(
    id="OPT-4", title="Expiry Behaviour", was="G1 / G2",
    meta=["consumes PRE-5", "Branch A · Index options"],
    verdict="The weekday theta / gamma clock that turns the PRE-5 day-type map into concrete DTE-based "
            "strike and timing rules — a day-type + timing engine, never a direction call. The "
            "deterministic core (theta acceleration, gamma concentration) is trustworthy; the exact daily "
            "decay percentages are broker folk-numbers needing your own post-Sep-2025 backtest — trust the "
            "shape, verify the magnitude. Under Tuesday expiry this is where the 9:39-10:00 opening-drive "
            "gets formalised: that window is the 0DTE buyer's one structural edge.",
    paras=[("The regime (verify vs NSE circulars)",
            "Nifty weekly = Tuesday (from 1 Sep 2025); Nifty monthly = last Tuesday; BankNifty monthly-only "
            "(weeklies gone Nov 2024, last-Tuesday); Sensex weekly = Thursday (BSE). DTE counts trading days "
            "only; a Tuesday holiday shifts expiry to the prior session. Weekly theta curve for a buyer: "
            "Wed lightest but thin / low-vol, Thu buyer-friendliest, Fri accelerating (don't hold over the "
            "weekend), Mon heavy, Tue extreme (compresses into hours)."),
           ("Gamma + theta shape",
            "Gamma peaks ATM into expiry — a 0DTE ATM option is 2-3x more responsive than one 100 pts away, "
            "so small moves = outsized premium swings (the edge and the trap, since gamma fades off-ATM "
            "into failed breakouts). Theta is non-linear: an ATM option can lose 70-80% of remaining value "
            "between 1:00 and 3:00 PM; 9:30 theta is nothing like 2:30 theta."),
           ("The exit clock — the opening trade",
            "On Tuesday the 10:00 exit is mandatory (afternoon theta is a cliff); on Wed-Thu (DTE 3-4) theta "
            "is light enough to trail a clean winner past 10:00 — same setup, different exit discipline by "
            "DTE. Strike by DTE: ATM or slightly-ITM into expiry; never OTM 0DTE (delta too low, theta too "
            "fast). Never buy into an RBI / Budget day in expiry week — event IV-crush overwhelms theta "
            "regardless of direction.")],
    signals=[
        ("Tue 0DTE 9:15-10:30 (AM)", "Timing", "HIGH", "TRADE", "Buyer's window; ORB / VWAP break; ATM only"),
        ("Tue 0DTE 12-2 PM", "Timing", "LOW", "AVOID", "Theta grind / range; sellers' window"),
        ("Tue 0DTE after 2 PM", "Timing", "V.HIGH", "AVOID", "Pin + MM games; spreads widen"),
        ("Wed (DTE 4)", "Day-type", "LOW", "CAUTION", "Lightest theta but thin OI drift"),
        ("Thu (DTE 3)", "Day-type", "MED", "TRADE", "Best buyer day; time value + mod theta"),
        ("Mon (DTE 1)", "Day-type", "MED", "CAUTION", "Heavy theta; strong confirmed only"),
        ("ATM strike (0DTE)", "Strike", "HIGH", "TRADE", "2-3x responsive; the only sane 0DTE buy"),
        ("OTM strike (0DTE)", "Strike", "-", "AVOID", "Delta too low, theta too fast"),
        ("Event IV-crush (expiry wk)", "Trap", "HIGH", "AVOID", "30-40% drop overwhelms theta (-> NAT-1)"),
    ],
    tf=[("Monthly", "Mod", "Last-Tue monthly pin; BankNifty's only pin week."),
        ("Weekly", "High", "The weekday theta map is the weekly structure."),
        ("Daily", "High", "Which DTE today -> viability + strike + exit."),
        ("Intraday (Tue)", "High", "AM-window / dead-zone / PM-danger rules."),
        ("Intraday (Wed-Fri)", "Mod", "Lighter theta -> room to trail past 10:00.")],
    reco="Include (strong, timing / day-type) as the branch's DTE clock consuming PRE-5: day-type viability "
         "(Thu best, Wed thin, Mon heavy, Tue AM-only), strike-by-DTE (ATM / slightly-ITM into expiry, "
         "never OTM 0DTE), and the intraday timing rules (9:30-10:30 buyer's window, midday dead zone, "
         "post-2 PM danger) with the exit clock hardening as DTE -> 0 (mandatory 10:00 exit Tuesday, "
         "trailing allowed Wed-Thu). Flag pin-risk + event IV-crush as trap_risk (couple OPT-2, "
         "NAT-1 / OPT-1). Backtest every magnitude on post-Sep-2025 data.",
    reco_kind="include",
))

# ---- OPT-5 ----
render_item(dict(
    id="OPT-5", title="Greeks for the Buyer", was="new",
    meta=["consumes PRE-1 + NAT-1", "Branch A · Index options"],
    verdict="The options-risk backbone — the OPT twin of ENG-9 (ATR): pure sizing / risk plumbing, zero "
            "direction, but the machinery every other OPT item runs on. Delta = strike dial + rough "
            "probability; gamma = the expiry-day acceleration behind the 9:39-10:00 window (and the "
            "reversal that traps a fake break); theta = the rent that makes buying a race against time; "
            "vega = the engine of IV-crush. The buyer's honest frame: you need the move big enough, fast "
            "enough, right direction, with vol cooperating, before theta eats the premium. OPT-5 picks no "
            "side — it decides which strike, how many lots, and whether the trade can survive.",
    paras=[("The four Greeks, buyer's lens",
            "Delta: ATM ~0.5 (~50% ITM odds); ITM ~0.6-0.8 tracks the index (the directional buyer's "
            "friend); far-OTM ~0.1 barely moves and bleeds fastest. Gamma: highest ATM near expiry (0DTE "
            "delta swings 0.2 -> 0.8 in minutes) — rewards a real break, punishes a fake one as it fades "
            "off-ATM. Theta: always negative for buyers, exponential into expiry, compresses into hours on "
            "Tuesday; ITM decays slower (intrinsic protected). Vega: positive for all longs, ~0 on 0DTE; "
            "buy low IV, avoid buying high IV (post-event crush of 30-50% works vega against you)."),
           ("Watch it at entry, not tick-by-tick",
            "Greeks are a pre-trade checklist and a set of exit rules, not a live screen. Pick the strike "
            "by delta and run the IV-crush veto (vega x OPT-1 IV %ile x NAT-1 events) BEFORE entry; after "
            "that, watch price — delta, gamma and theta are already baked into how the premium moves. In "
            "Fortuna, OPT-5 is background plumbing: the app computes delta / vega and flags crush risk at "
            "entry, so a 20-minute trade never becomes four Greek numbers to babysit."),
           ("The strike + veto this produces",
            "ATM to slightly-ITM (delta ~0.5-0.7) for directional intraday; slightly-ITM as the theta "
            "shield in expiry week; ATM-only on 0DTE for the gamma; never far-OTM intraday. When IV %ile is "
            "high or an event looms, switch to a debit spread (buy ATM + sell OTM) to cut vega / theta "
            "while keeping delta. Size by net delta with a theta-burn cap (&lt; ~0.5% / day of capital). "
            "Per-instrument — BankNifty Greeks are larger than Nifty.")],
    signals=[
        ("ATM / slightly-ITM (delta 0.5-0.7)", "0", "MED", "TRADE", "Best directional-buyer balance"),
        ("Far-OTM low delta (&lt; 0.3)", "0", "-", "AVOID", "Slow + fastest %-theta bleed"),
        ("High gamma (ATM, expiry)", "0", "HIGH", "TRADE", "Powers the AM drive; exit before it reverses"),
        ("Gamma fade off-ATM", "0", "MED", "CAUTION", "Failed-breakout engine; why chases die"),
        ("High Vega + high IV %ile", "0", "HIGH", "AVOID", "Crush risk; use a debit spread to cut vega"),
        ("Low Vega + low IV %ile", "0", "LOW", "TRADE", "Cheap premium; a vol spike pays you"),
        ("ITM theta shield", "0", "MED", "TRADE", "Intrinsic doesn't decay; expiry-week hedge"),
        ("Net-delta position size", "0", "-", "CAUTION", "Cap lots; theta burn &lt; ~0.5% / day"),
    ],
    tf=[("Monthly / Weekly", "Infra", "Vega + theta frame which strikes are buyable."),
        ("Daily", "Infra", "Strike-by-delta + theta-burn budget."),
        ("Intraday", "Infra (high)", "Live strike / size / exit machinery."),
        ("Directional weight", "Zero", "Substrate for OPT-1 / OPT-4 + sizing (like ATR).")],
    reco="Include (infrastructure) as the sizing / risk backbone, the OPT twin of ENG-9: zero directional "
         "weight, but the machinery that selects the strike by delta, sizes by net delta + a theta-burn "
         "cap, runs the vega / IV-crush veto (consuming PRE-1 / OPT-1 + NAT-1; debit spread when vega is "
         "dangerous), and governs hold / exit via gamma-fade + the theta cliff (hard 10:00 exit Tuesday, "
         "per OPT-4). Track standardised, per-instrument Greeks. It picks no side — it decides which "
         "strike, how many lots, and whether the trade survives.",
    reco_kind="include",
))

# ================= BRANCH A — MORNING OPTIONS PLAYBOOK =================
story += [
    Paragraph("Branch A — The Morning Options Playbook", h1),
    HBar(color=AMBER, thick=1.4), sp(2),
    Paragraph("How the five OPT items chain — gate-first, mirroring the trunk. The trunk hands over the "
              "index-direction verdict; Branch A turns it into strike + CE/PE + entry / exit + SL.", small),
    sp(6),
    generic_table(
        ["#", "Stage", "Question", "OPT items", "Action"],
        [
            ["1", "Premium gate", "Is premium buyable today?", "OPT-1 IV %ile (+ PRE-1 VIX)",
             "High IV %ile / pre-event -> don't buy or use a spread"],
            ["2", "Crowding", "Positioning stretched?", "OPT-1 PCR",
             "Extreme = contrarian warn; otherwise conviction only"],
            ["3", "Location", "Where do moves stall?", "OPT-2 max pain + walls (ENG-11)",
             "Buy toward the far wall; stop beyond the near wall"],
            ["4", "Intent", "Wall holding or breaking?", "OPT-3 change-in-OI",
             "Fresh writing defends; unwinding = the break"],
            ["5", "Timing / day-type", "Which DTE, which window?", "OPT-4 expiry (+ PRE-5)",
             "Tue AM only + hard 10:00 exit; Thu = best buyer day"],
            ["6", "Strike + size + exit", "Which strike, how many, when out?", "OPT-5 Greeks",
             "ATM / ITM delta; theta cap; vega veto; gamma exit"],
        ],
        [CONTENT_W*0.05, CONTENT_W*0.15, CONTENT_W*0.20, CONTENT_W*0.25, CONTENT_W*0.35],
        center_cols=(0,)),
    sp(6),
    callout("<b>THE OUTPUT.</b> verdict (from the trunk) -> <b>strike + CE/PE</b> + <b>entry</b> "
            "(9:30-9:45 with-trend trigger) + <b>exit</b> (VWAP / structure SL + the theta clock) + "
            "<b>SL</b>. Direction comes from the trunk; Branch A never re-derives it — it decides whether, "
            "where, which strike, when and how much.", bg=TEAL_L, bar=TEAL, tcolor=INK),
    sp(6),
    Band("Greeks are plumbing, not a live screen", color=TEAL_DK, h=20, size=10.5),
    sp(4),
    callout("For a fast opening-drive trade, do <b>not</b> watch the Greeks tick-by-tick — that is noise "
            "that pulls your eyes off the price candle (your real trigger). Use them at <b>two fixed "
            "moments</b>: at entry (pick the strike by delta; run the IV-crush veto — vega x OPT-1 x "
            "NAT-1), and as exit rules (gamma-fade + the theta cliff = get out; hard 10:00 on Tuesday). "
            "In Fortuna, OPT-5 runs as background plumbing — the app computes delta / vega and flags the "
            "crush risk for you at entry, so a 20-minute trade never becomes four Greek numbers to "
            "babysit. Check the strike + crush once, then watch price.", bg=AMBER_L, bar=AMBER),
    sp(6),
    callout("<b>Worked example — the opening-drive (Tue 0DTE, bull cascade, no event).</b> "
            "OPT-1 IV %ile normal -> buying OK, crush clear. OPT-2 clear air to the call wall -> room to "
            "run. OPT-3 put-writing firming below (support real) + call-writers unwinding above (break "
            "brewing). OPT-4 buy the 9:39 ATM CE on the green-candle break; hard 10:00 exit (theta cliff). "
            "OPT-5 ATM delta ~0.5, gamma tailwind. If instead OPT-3 shows only short-covering, expect the "
            "push to die by 10:00 — take the exit, don't trail.", bg=GREY_L, bar=TEAL),
    PageBreak(),
]

# ================= BRANCH A TRACKER =================
story += [
    Paragraph("Branch A · OPT Tracker", h1),
    HBar(color=AMBER, thick=1.4), sp(2),
    Paragraph("Branch order · new IDs · job / direction rollup. Y = include, Y* = include with caveats. "
              "Gate / Location / Intent / Timing / Infra = non-directional roles.", small),
    sp(6),
    generic_table(
        ["ID", "Was", "Item", "Real job", "Dir", "Incl."],
        [
            ["OPT-1", "G3", "IV percentile / PCR", "Premium & crowding gate", "0", "Y*"],
            ["OPT-2", "G4", "Max pain + OI walls", "Location / gravity", "0", "Y*"],
            ["OPT-3", "G6", "Change-in-OI", "Intent / strike select", "MED", "Y"],
            ["OPT-4", "G1/G2", "Expiry behaviour", "Day-type / timing", "0", "Y"],
            ["OPT-5", "new", "Greeks (buyer)", "Sizing / risk (infra)", "0", "Y"],
        ],
        [CONTENT_W*0.10, CONTENT_W*0.09, CONTENT_W*0.30, CONTENT_W*0.28, CONTENT_W*0.12, CONTENT_W*0.11],
        center_cols=(1, 4, 5)),
    sp(6),
    callout("<b>5 of 5 Branch A items researched.</b> Direction comes from the trunk; four of five OPT "
            "items add zero direction and instead answer premium, location, timing and sizing — OPT-3 is "
            "the only one with a directional lean, and even that is a confirmer. Output object: "
            "<b>strike + CE/PE + entry / exit + SL</b>. Next: Branch B (STK) in Document B "
            "(Fortuna-Cash), which inherits this index direction as its first filter; and Track B module "
            "specs (I-4 Options Intelligence Engine) that implement OPT-1..5.",
            bg=AMBER_L, bar=AMBER),
    sp(12),
    HBar(color=TEAL, thick=1.4), sp(4),
    Paragraph("DOCUMENT ENDS HERE",
              mk("ends", fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                 textColor=GREY, alignment=TA_CENTER)),
    sp(4), HBar(color=TEAL, thick=1.4), sp(6),
    Paragraph("FORTUNA — Branch A · Index Options · v01 · Confidential — Internal Use Only", tiny),
    PageBreak(),
]

# ================= APPENDIX — TRADING WITH SPREADS =================
story += [
    Paragraph("Additional Considerations — Trading with Spreads", h1),
    HBar(color=AMBER, thick=1.4), sp(6),
    callout("<b>Optional — not a sixth OPT item.</b> The core funnel is complete at five. This appendix "
            "covers one optional trade <i>structure</i> that changes only the instrument at the OPT-5 "
            "step. Everything upstream — direction from the trunk, location (OPT-2), intent (OPT-3), "
            "timing (OPT-4) — is unchanged.", bg=GREY_L, bar=TEAL),
    sp(6),
    Paragraph("The one-line contrast", h3),
    callout("<b>Today, when IV-crush is in play, the funnel resolves to AVOID or SIZE DOWN — it keeps you "
             "out.</b> A debit spread converts <i>sit out</i> into <i>participate with the crush "
             "neutralised</i>. That is the whole reason to add it: it lets you trade the days you "
             "currently skip — especially news days.", bg=AMBER_L, bar=AMBER),
    sp(8),
    Paragraph("Current decisions when IV-crush is in play — both paths", h3),
    Paragraph("So you can see both options side by side. The default stays AVOID; the spread is the "
              "participate-anyway alternative.", small),
    sp(4),
    generic_table(
        ["Situation", "Current default (no spread)", "Spread alternative"],
        [
            ["High IV %ile (~80%+) · OPT-1 gate", "AVOID naked buy / size down",
             "Debit spread: keep the directional view, crush neutralised"],
            ["Pre-event IV ramp · NAT-1 flag", "Sit out, or buy the ENG-10 squeeze early before the ramp",
             "Debit spread into the event; defined risk"],
            ["Event day (RBI / Budget / results)", "No-trade / caution; wait for post-announcement",
             "Spread after direction confirms — the news-buying path"],
            ["Expiry-week rich premium + high vega", "AVOID naked (theta + crush compound)",
             "Spread cuts vega + theta; still respect the Tue clock"],
            ["Extreme turbulence (VIX &gt; 25)", "Stand aside",
             "Still stand aside — a spread is not a chaos hedge"],
        ],
        [CONTENT_W*0.28, CONTENT_W*0.36, CONTENT_W*0.36]),
    sp(6),
    Paragraph("What a debit spread does", h3),
    Paragraph("Buy the directional leg (ATM) and sell a further-OTM leg on the same side — a bull call "
              "spread for up, a bear put spread for down. The sold leg pays for most of the vega and "
              "theta of the bought leg, so the position survives an IV-crush that would gut a naked "
              "long, while keeping most of the delta (direction). It is still a net buy (net debit), so "
              "it fits the manual-buyer workflow — just with a built-in hedge leg.", body),
    sp(2),
    Paragraph("News / event buying — the path you want", h3),
    Paragraph("On RBI, Budget and results days IV ramps, then crushes 30-50% the moment the outcome is "
              "known — which is why a naked long can lose even when the direction is right. The debit "
              "spread is how you take a directional news view without the crush deciding the trade. "
              "Sequence: let the trunk / NAT-1 flag the event and stay two-sided before it; do NOT buy "
              "the 9:15 print or pre-announcement; wait for direction to confirm after the statement "
              "(RBI ~10 AM, Budget ~11 AM, results per the calendar); then express it as a spread, not a "
              "naked long. If a squeeze is already loading (ENG-10) you can alternatively buy cheap "
              "premium early, before IV inflates. Location (OPT-2) and intent (OPT-3) still pick the "
              "strikes.", body),
    sp(2),
    Paragraph("The trade-off — when NOT to spread", h3),
    Paragraph("A spread caps your maximum profit (the sold leg is the price of the crush protection) and "
              "doubles the legs, so costs and slippage are higher. That only pays off when premium is "
              "genuinely expensive. When premium is cheap (low IV %ile, quiet day, your normal "
              "9:39-10:00 drive), a naked long is better — a spread would cap the upside for no benefit.",
              body),
    sp(4),
    callout("<b>Decision rule.</b> Cheap premium / normal day -> <b>naked long</b> (the default). "
            "Expensive premium / a news day you want to trade -> <b>debit spread</b>. Extreme chaos "
            "(VIX &gt; 25) -> <b>still sit out</b>. The spread widens what you can trade; it does not "
            "replace the AVOID decision — it sits beside it.", bg=TEAL_L, bar=TEAL, tcolor=INK),
    sp(10),
    Paragraph("FORTUNA — Branch A · Index Options · v01 · Appendix · Confidential — Internal Use Only",
              tiny),
]

# ================= BUILD =================
doc = Doc("/home/claude/Fortuna_index_branchA_v01.pdf")
doc.build(story)
print("BUILT OK")
