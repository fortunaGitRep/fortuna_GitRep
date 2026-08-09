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

FOOTER_LEFT = "FORTUNA"

# ---------- page decoration ----------
def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, 9*mm,
        FOOTER_LEFT)
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



