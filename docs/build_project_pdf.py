"""Builds docs/DISHA_Project_Guide.pdf (landscape A4) from screenshots + real satellite layers captured from the running app.

Usage (stack running, assets captured):  python docs/build_project_pdf.py
Assets live in docs/pdf_assets (git-ignored): shots/*.jpg (e2e/capture.mjs), <event>_<layer>.png + facts.json (data/fetch_assets.py-style export).
"""
import json
import os

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, Image as RLImage, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "pdf_assets")
SHOTS = os.path.join(ASSETS, "shots")
OUT = os.path.join(HERE, "DISHA_Project_Guide.pdf")
FACTS = json.load(open(os.path.join(ASSETS, "facts.json"), encoding="utf8"))

for name, f in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Arial-Italic", "ariali.ttf"), ("Arial-BoldItalic", "arialbi.ttf")):
    pdfmetrics.registerFont(TTFont(name, os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", f)))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

NAVY, INK, MUTED, LINE = colors.HexColor("#0b1b33"), colors.HexColor("#24344a"), colors.HexColor("#5d6f87"), colors.HexColor("#d3dce8")
ACCENT, OK, WARN, P1, P2, P3, P4 = (colors.HexColor(x) for x in ("#1d6fd8", "#1f9d6b", "#a56a00", "#d62f35", "#e0721a", "#d9a400", "#6b7a90"))
PANEL = colors.HexColor("#f3f6fb")
W, H = landscape(A4)
M = 36

S = {
    "kicker": ParagraphStyle("kicker", fontName="Arial-Bold", fontSize=9.5, textColor=ACCENT, leading=12, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=22, textColor=NAVY, leading=26, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12.5, textColor=NAVY, leading=16, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", fontName="Arial", fontSize=10.3, textColor=INK, leading=14.6, spaceAfter=5),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=8.6, textColor=MUTED, leading=11.5),
    "cap": ParagraphStyle("cap", fontName="Arial-Italic", fontSize=8.4, textColor=MUTED, leading=11, spaceBefore=3),
    "bul": ParagraphStyle("bul", fontName="Arial", fontSize=10.1, textColor=INK, leading=14, leftIndent=12, bulletIndent=1, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=9.2, textColor=INK, leading=12.4),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=9.2, textColor=NAVY, leading=12.4),
    "big": ParagraphStyle("big", fontName="Arial-Bold", fontSize=24, textColor=NAVY, leading=26, alignment=TA_LEFT),
    "quote": ParagraphStyle("quote", fontName="Arial-Italic", fontSize=12.5, textColor=NAVY, leading=18),
}


def P(t, st="body"):
    return Paragraph(t, S[st])


def bullets(items, st="bul"):
    return [Paragraph(t, S[st], bulletText="•") for t in items]


def head(kicker, title):
    return [P(kicker, "kicker"), P(title, "h1")]


def callout(text, kind="info", width=None):
    bg, bd = {"info": (colors.HexColor("#eaf2fd"), ACCENT), "warn": (colors.HexColor("#fdf3df"), WARN), "ok": (colors.HexColor("#e5f5ee"), OK)}[kind]
    t = Table([[Paragraph(text, S["cell"])]], colWidths=[width] if width else None)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, bd), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def img(path, width, border=True):
    w, h = Image.open(path).size
    im = RLImage(path, width=width, height=width * h / w)
    if not border:
        return im
    t = Table([[im]], colWidths=[width + 2])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def shot(name, width, caption=None):
    items = [img(os.path.join(SHOTS, name + ".jpg"), width)]
    if caption:
        items.append(P(caption, "cap"))
    return items


def twocol(left, right, lw, rw, gap=18):
    t = Table([[left, right]], colWidths=[lw, rw + gap])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), gap), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def grid(cells, cols, cw):
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    for r in rows:
        while len(r) < cols:
            r.append("")
    t = Table(rows, colWidths=[cw + 12] * cols)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def stats(items, width=W - 2 * M):
    cells = [[Paragraph(f'<font name="Arial-Bold" size="21" color="#0b1b33">{v}</font><br/><font size="8.6" color="#5d6f87">{l}</font>', S["cell"]) for v, l in items]]
    t = Table(cells, colWidths=[width / len(items)] * len(items))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LINEAFTER", (0, 0), (-2, -1), 0.6, LINE), ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("TOPPADDING", (0, 0), (-1, -1), 9),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 9), ("LEFTPADDING", (0, 0), (-1, -1), 12)]))
    return t


def table(rows, widths, header=True, zebra=True):
    data = [[Paragraph(str(c), S["cellb"] if (header and i == 0) else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), PANEL))
    t.setStyle(TableStyle(st))
    return t


def wide_pair(a, b, cap_a, cap_b, width=372, crop_a=None, crop_b=None):
    def one(name, cap, crop):
        path = os.path.join(SHOTS, name + ".jpg")
        if crop:
            im = Image.open(path).crop(crop)
            path = os.path.join(ASSETS, f"crop_{name}.jpg")
            im.save(path, quality=88)
        return [img(path, width), P(cap, "cap")]
    t = Table([[one(a, cap_a, crop_a), one(b, cap_b, crop_b)]], colWidths=[width + 14, width + 14])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def two_text(items_left, items_right, width=CW_ if False else None):
    t = Table([[items_left, items_right]], colWidths=[(W - 2 * M) / 2, (W - 2 * M) / 2])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 16), ("RIGHTPADDING", (1, 0), (1, 0), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


# ----------------------------------------------------------------------------------------- diagrams
class Diagram(Flowable):
    def __init__(self, w, h, fn):
        super().__init__()
        self.width, self.height, self.fn = w, h, fn

    def draw(self):
        self.fn(self.canv, self.width, self.height)


def box(c, x, y, w, h, text, fill=colors.white, stroke=LINE, fs=9, tc=INK, bold=False, r=5):
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(0.9)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    c.setFillColor(tc); c.setFont("Arial-Bold" if bold else "Arial", fs)
    lines = text.split("\n")
    ty = y + h / 2 + (len(lines) - 1) * fs * 0.6 - fs * 0.35
    for ln in lines:
        c.drawCentredString(x + w / 2, ty, ln); ty -= fs * 1.2


def arrow(c, x1, y1, x2, y2, col=MUTED, lw=1.1):
    import math
    c.setStrokeColor(col); c.setFillColor(col); c.setLineWidth(lw); c.line(x1, y1, x2, y2)
    a = math.atan2(y2 - y1, x2 - x1); L = 5.5
    p = c.beginPath(); p.moveTo(x2, y2); p.lineTo(x2 - L * math.cos(a - 0.45), y2 - L * math.sin(a - 0.45)); p.lineTo(x2 - L * math.cos(a + 0.45), y2 - L * math.sin(a + 0.45)); p.close(); c.drawPath(p, fill=1, stroke=0)


def loop_diagram(c, w, h):
    names = ["Detect", "Understand", "Predict", "Prioritise", "Plan", "Dispatch", "Verify", "Learn"]
    sub = ["satellite\nchange", "people, roads,\nfacilities", "what gets\nworse", "where\nfirst?", "route, shelter,\nresources", "send\nunits", "field\nreport", "feed back\nlabels"]
    bw, gap = (w - 7 * 8) / 8, 8
    for i, n in enumerate(names):
        x = i * (bw + gap)
        box(c, x, h - 62, bw, 50, n, fill=ACCENT if i < 4 else NAVY, stroke=colors.white, fs=7.3, tc=colors.white, bold=True)
        c.setFillColor(MUTED); c.setFont("Arial", 6.9)
        for k, ln in enumerate(sub[i].split("\n")):
            c.drawCentredString(x + bw / 2, h - 74 - k * 8.5, ln)
        if i < 7:
            arrow(c, x + bw + 1, h - 37, x + bw + gap - 1, h - 37)
    c.setStrokeColor(OK); c.setLineWidth(1.3); c.setDash(4, 3)
    c.line(w - bw / 2, h - 96, w - bw / 2, 14); c.line(w - bw / 2, 14, bw / 2, 14); c.line(bw / 2, 14, bw / 2, h - 96); c.setDash()
    c.setFillColor(OK); c.setFont("Arial-Bold", 8.5); c.drawCentredString(w / 2, 20, "Every field report recalculates the priorities: the loop closes")


def pipeline_diagram(c, w, h):
    steps = [("1", "Trigger", "alert + area"), ("2", "Acquire", "satellite, map,\npopulation data"), ("3", "Prepare", "align, mask clouds,\nreduce speckle"), ("4", "Detect", "where did it\nchange?"), ("5", "Assess", "people, roads,\nfacilities"),
             ("6", "Prioritise", "score every\nhexagon"), ("7", "Predict", "next 6 to 48 h\n(estimate)"), ("8", "Plan", "routes, shelters,\nresources"), ("9", "Dispatch", "commander\nsends units"), ("10", "Verify", "field report\nrecalculates")]
    bw, bh, gx = (w - 4 * 12) / 5, 56, 12
    for i, (n, t, d) in enumerate(steps):
        row, col = divmod(i, 5)
        x, y = col * (bw + gx), h - (row + 1) * (bh + 22)
        auto = i < 8
        box(c, x, y, bw, bh, "", fill=colors.white if auto else PANEL, stroke=ACCENT if auto else NAVY)
        c.setFillColor(ACCENT if auto else NAVY); c.circle(x + 15, y + bh - 15, 8.5, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Arial-Bold", 8); c.drawCentredString(x + 15, y + bh - 17.8, n)
        c.setFillColor(NAVY); c.setFont("Arial-Bold", 10); c.drawString(x + 30, y + bh - 18, t)
        c.setFillColor(MUTED); c.setFont("Arial", 7.8)
        for k, ln in enumerate(d.split("\n")):
            c.drawString(x + 12, y + bh - 34 - k * 9.5, ln)
        if col < 4:
            arrow(c, x + bw + 1, y + bh / 2, x + bw + gx - 1, y + bh / 2)
    c.setFillColor(MUTED); c.setFont("Arial", 8)
    c.drawString(0, 2, "Steps 1-8 run automatically in the background. Steps 9-10 are people: a commander dispatches, a responder verifies.")


def hex_diagram(c, w, h):
    import math
    cx, cy, r = w / 2, h / 2, 46
    pts = [(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
    p = c.beginPath(); p.moveTo(*pts[0]); [p.lineTo(*q) for q in pts[1:]]; p.close()
    c.setFillColor(colors.HexColor("#fbe3e4")); c.setStrokeColor(P1); c.setLineWidth(2); c.drawPath(p, fill=1, stroke=1)
    c.setFillColor(NAVY); c.setFont("Arial-Bold", 13); c.drawCentredString(cx, cy + 4, "Cell 07")
    c.setFont("Arial", 8.5); c.setFillColor(P1); c.drawCentredString(cx, cy - 10, "P1 Critical")
    L = [(0, 1, "Hazard\nseverity, area"), (0, 0.15, "People\nexposed, isolated"), (0, -0.7, "Vulnerability\nfactors available"), (1, 1, "Hospitals, schools,\npower, bridges"), (1, 0.15, "Road status\nopen / blocked"), (1, -0.7, "Shelter\ndistance"),
         ]
    for i, (side, yy, txt) in enumerate(L):
        bx = 6 if side == 0 else w - 112
        by = cy + yy * 62 - 17
        box(c, bx, by, 106, 34, txt, fill=PANEL, fs=7.8)
        tx = cx - r * 0.86 if side == 0 else cx + r * 0.86
        arrow(c, bx + (106 if side == 0 else 0), by + 17, tx + (-3 if side == 0 else 3), cy + yy * 18 + (0), LINE if False else MUTED, 0.8)
    box(c, cx - 56, 4, 112, 28, "Priority score +\nreasons + confidence", fill=colors.white, stroke=ACCENT, fs=7.8)
    arrow(c, cx, 33, cx, cy - r * 0.8, ACCENT, 0.9)
    box(c, cx - 56, h - 32, 112, 28, "Predicted level at\n+6, +12, +24, +48 h", fill=colors.white, stroke=ACCENT, fs=7.8)
    arrow(c, cx, h - 33, cx, cy + r * 0.85, ACCENT, 0.9)


def score_diagram(c, w, h):
    parts = [("Hazard severity", 35, ACCENT), ("People exposed", 30, P1), ("Critical facilities", 20, P3), ("Road access lost", 15, OK)]
    x = 0
    for name, pct, col in parts:
        bw = w * pct / 100
        c.setFillColor(col); c.rect(x, h - 38, bw - 2, 32, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Arial-Bold", 13); c.drawCentredString(x + bw / 2 - 1, h - 27, f"{pct}%")
        c.setFillColor(INK); c.setFont("Arial", 8.4); c.drawCentredString(x + bw / 2 - 1, h - 52, name)
        x += bw
    c.setFillColor(MUTED); c.setFont("Arial", 8.4)
    c.drawString(0, h - 70, "Score = 0.35 x severity  +  0.30 x exposure  +  0.20 x facilities  +  0.15 x road access lost      (each part scaled 0 to 1; weights are adjustable)")
    levels = [("P1", "Critical", "0.48 and above", P1), ("P2", "High", "0.34 to 0.48", P2), ("P3", "Moderate", "0.20 to 0.34", P3), ("P4", "Low", "below 0.20", P4)]
    bw = (w - 3 * 10) / 4
    for i, (p, n, r, col) in enumerate(levels):
        x = i * (bw + 10)
        c.setFillColor(col); c.roundRect(x, 4, bw, 40, 5, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Arial-Bold", 13); c.drawString(x + 10, 26, f"{p}  {n}")
        c.setFont("Arial", 8.6); c.drawString(x + 10, 11, f"score {r}")


def arch_diagram(c, w, h):
    def layer(y, hh, title, items, fill):
        c.setFillColor(fill); c.setStrokeColor(LINE); c.roundRect(0, y, w, hh, 6, fill=1, stroke=1)
        c.setFillColor(NAVY); c.setFont("Arial-Bold", 8.6); c.drawString(8, y + hh - 13, title)
        n = len(items); bw = (w - 16 - (n - 1) * 8) / n
        for i, t in enumerate(items):
            box(c, 8 + i * (bw + 8), y + 8, bw, hh - 28, t, fill=colors.white, fs=7.8)
    layer(h - 58, 56, "Browser (Next.js 14, React, TypeScript, Tailwind)", ["MapLibre GL + deck.gl\nmap and layers", "Pages: overview, map,\npriorities, resources, field", "Copilot, command centre,\npresentation mode", "Chart.js, JWT client"], colors.HexColor("#eef4fc"))
    arrow(c, w / 2, h - 60, w / 2, h - 76, MUTED)
    layer(h - 136, 58, "API (FastAPI, Pydantic) - 57 REST endpoints, JWT + role checks, audit log", ["routers\nauth, events, response, field, admin", "services\npipeline, digital twin, reports, exports", "background jobs\nprogress stored per step"], colors.HexColor("#f3f6fb"))
    arrow(c, w / 2, h - 138, w / 2, h - 154, MUTED)
    layer(h - 214, 58, "Engines (pure algorithms, unit-tested without a database)", ["detection\nSAR log-ratio, Otsu, masks", "priority, vulnerability,\nconfidence, cascade", "roads, routing,\nshelters, resources", "prediction,\nescalation, alerts"], colors.HexColor("#f3f6fb"))
    arrow(c, w / 4, h - 216, w / 4, h - 232, MUTED); arrow(c, 3 * w / 4, h - 216, 3 * w / 4, h - 232, MUTED)
    bw = (w - 8) / 2
    layer(h - 296, 62, "Storage", ["PostgreSQL + PostGIS (production)\nSQLite (zero-setup local)\nGiST spatial indexes", "files: rasters, photos, cached downloads"], colors.HexColor("#f3f6fb"))
    c.setFillColor(MUTED); c.setFont("Arial", 7.6)


def sources_diagram(c, w, h):
    srcs = ["Sentinel-1 radar", "Sentinel-2 optical", "Copernicus DEM", "ESA WorldCover", "WorldPop population", "OpenStreetMap", "Open-Meteo rainfall"]
    bw, bh = 104, 22
    cx0, cw_ = 128, 62
    for i, sr in enumerate(srcs):
        y = h - 26 - i * 31
        box(c, 0, y, bw, bh, sr, fill=colors.HexColor("#e5f5ee"), stroke=OK, fs=7.8)
        arrow(c, bw + 1, y + bh / 2, cx0 - 2, h / 2 + (y + bh / 2 - h / 2) * 0.22, MUTED, 0.8)
    box(c, cx0, h / 2 - 40, cw_, 80, "DISHA\nsame engines\nfor real and\nsimulated", fill=NAVY, stroke=NAVY, fs=7.4, tc=colors.white, bold=True)
    arrow(c, cx0 + cw_ + 1, h / 2, w - 100, h / 2, MUTED)
    box(c, w - 98, h / 2 - 40, 98, 80, "Ranked areas\nwith reasons,\nroutes, shelters,\nresources", fill=PANEL, stroke=ACCENT, fs=7.6)


# ----------------------------------------------------------------------------------------- page decoration
def page_deco(canv, doc):
    canv.saveState()
    canv.setStrokeColor(LINE); canv.setLineWidth(0.5); canv.line(M, H - 26, W - M, H - 26)
    canv.setFont("Arial-Bold", 8.4); canv.setFillColor(NAVY); canv.drawString(M, H - 21, "DISHA 2.0")
    canv.setFont("Arial", 8.4); canv.setFillColor(MUTED); canv.drawString(M + 52, H - 21, "Project guide for the team and judges")
    canv.drawRightString(W - M, 18, f"{doc.page}")
    canv.drawString(M, 18, "github.com/srushti117/Disha")
    canv.restoreState()


def cover_deco(canv, doc):
    canv.saveState()
    hero = os.path.join(ASSETS, "hero.jpg")
    canv.setFillColor(NAVY); canv.rect(0, 0, W, H, fill=1, stroke=0)
    hw = W * 0.56
    canv.drawImage(hero, W - hw, 0, width=hw, height=H, preserveAspectRatio=False, mask=None)
    canv.setFillColor(colors.HexColor("#0b1b33")); canv.setFillAlpha(0.18); canv.rect(W - hw, 0, hw, H, fill=1, stroke=0); canv.setFillAlpha(1)
    canv.setFillColor(colors.white); canv.setFont("Arial-Bold", 58); canv.drawString(M + 8, H - 150, "DISHA")
    canv.setFont("Arial-Bold", 25); canv.drawString(M + 8, H - 188, "2.0")
    canv.setFont("Arial", 13); canv.setFillColor(colors.HexColor("#c9d6ea"))
    for i, ln in enumerate(["Disaster Intelligence, Situational Hazard", "Assessment and Response Orchestration"]):
        canv.drawString(M + 8, H - 226 - i * 18, ln)
    canv.setFillColor(colors.white); canv.setFont("Arial-Bold", 17)
    for i, ln in enumerate(["From satellite images to a clear answer", "on where to respond first."]):
        canv.drawString(M + 8, H - 300 - i * 24, ln)
    canv.setFont("Arial", 10.5); canv.setFillColor(colors.HexColor("#c9d6ea"))
    for i, ln in enumerate(["Project guide for the team and the judges", "TechFest 2026-27 - Space Technology Hackathon", "Problem: Rapid post-disaster change intelligence", "from multi-temporal satellite data"]):
        canv.drawString(M + 8, 118 - i * 15, ln)
    canv.setFont("Arial", 9); canv.setFillColor(colors.HexColor("#8da2c2")); canv.drawString(M + 8, 40, "github.com/srushti117/Disha")
    canv.setFont("Arial", 7.6); canv.setFillColor(colors.white); canv.setFillAlpha(0.85)
    canv.drawRightString(W - 14, 12, "Cover: Sentinel-2 image of Sindh, Pakistan (Copernicus data) with the flood DISHA detected shown in blue")
    canv.restoreState()


def build_hero():
    """Cover image from the real raster layers (no app chrome): Sentinel-2 over Sindh with the detected flood overlaid, cropped to the cover aspect."""
    opt = Image.open(os.path.join(ASSETS, "sindh_optical.png")).convert("RGBA")
    haz = Image.open(os.path.join(ASSETS, "sindh_hazard.png")).convert("RGBA")
    opt.alpha_composite(haz)
    big = opt.convert("RGB").resize((1400, 1400), Image.BICUBIC)
    ratio = (W * 0.56) / H
    cw, ch = (int(1400 * ratio), 1400) if ratio < 1 else (1400, int(1400 / ratio))
    x0 = (1400 - cw) // 2
    big.crop((x0, 0, x0 + cw, ch)).save(os.path.join(ASSETS, "hero.jpg"), quality=90)


def compose(name, layers, size=620):
    """Real raster layers over a neutral background, nearest-neighbour upscaled so pixels stay crisp."""
    im = Image.open(os.path.join(ASSETS, f"{name}_{layers}.png")).convert("RGBA")
    bg = Image.new("RGBA", im.size, (236, 240, 246, 255))
    if layers == "hazard":
        base = Image.open(os.path.join(ASSETS, f"{name}_sar_post.png")).convert("RGBA")
        bg = base
    bg.alpha_composite(im) if layers == "hazard" else bg.paste(im, (0, 0))
    out = bg.convert("RGB").resize((size, size), Image.NEAREST)
    p = os.path.join(ASSETS, f"c_{name}_{layers}.jpg")
    out.save(p, quality=90)
    return p


def raster_strip(name, w):
    items = [("sar_pre", "Radar before (Sentinel-1)"), ("sar_post", "Radar after (Sentinel-1)"), ("hazard", "Detected flood (blue) on the radar"), ("optical", "Satellite image after (Sentinel-2)")]
    cw = (w - 3 * 12) / 4
    cells = []
    for layer, cap in items:
        p = compose(name, layer)
        cells.append([img(p, cw), P(cap, "cap")])
    t = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=[cw + 12] * 4)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


# ----------------------------------------------------------------------------------------- content
def build():
    build_hero()
    fk, fs, fc, fm = FACTS["kuttanad"], FACTS["sindh"], FACTS["chalakudy"], FACTS["sim"]
    doc = BaseDocTemplate(OUT, pagesize=landscape(A4), leftMargin=M, rightMargin=M, topMargin=40, bottomMargin=30, title="DISHA 2.0 - Project guide", author="DISHA team",
                          subject="Disaster intelligence and response orchestration")
    frame = Frame(M, 30, W - 2 * M, H - 70, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    cover_frame = Frame(M, 30, 1, 1, id="c")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[cover_frame], onPage=cover_deco), PageTemplate(id="main", frames=[frame], onPage=page_deco)])
    CW = W - 2 * M
    F = [NextPageTemplate("main"), PageBreak()]

    # 2 ---------------------------------------------------------------- the idea
    left = head("The idea", "DISHA in one minute")
    left += [P("<b>The problem.</b> After a flood, wildfire, landslide or cyclone, response teams have hours to decide where to go first. The information they need is scattered: satellite images, rainfall, population, roads, hospitals, field reports. A satellite change map shows <i>what changed</i>. It does not say <i>who needs help first</i>."),
             P("<b>What DISHA does.</b> It takes satellite images from before and after a disaster, finds where the damage is, links it to people, hospitals and roads, and produces a ranked, explained list of places to reach first. It then proposes routes, shelters and resources, and recalculates every time a responder reports from the ground."),
             Spacer(1, 4), callout("The question DISHA answers:<br/><i>Where should emergency responders go first, what should they do there, which resources should be deployed, which route should they take, and why?</i>", "info", 300)]
    right = [Diagram(CW - 330, 150, loop_diagram), Spacer(1, 12), P("The five questions it answers", "h2"),
             table([["Question", "Where DISHA answers it"], ["1. What happened?", "Satellite change detection (radar first, optical when clear)"], ["2. Who is affected?", "Population, vulnerability, hospitals, schools, roads"], ["3. Where do we go first?", "Priority score P1 to P4 with the reasons shown"],
                    ["4. What should we do?", "Recommended actions, safest route, shelters, resource plan"], ["5. Did the situation change?", "New satellite passes and field reports recalculate everything"]], [150, CW - 330 - 150])]
    F += [twocol(left, right, 310, CW - 330), PageBreak()]

    # 3 ---------------------------------------------------------------- why it matters
    left = head("Why it matters", "The gap DISHA is built to close")
    left += [P("The figures below come from the team's Round 1 proposal (sources cited there: NDMA and the Geological Survey of India)."), stats([("12%", "of India's land is flood-prone (~40 Mha)"), ("5,700 km", "of 7,516 km coastline exposed to cyclones")], 300),
             Spacer(1, 6), stats([("12.6%", "of land area is landslide-prone"), ("72 hours", "golden window to save lives")], 300), Spacer(1, 10), P("What goes wrong today", "h2")]
    left += bullets(["<b>Too slow.</b> Manual interpretation of satellite images can take days, after the golden window has closed.", "<b>Blind under cloud.</b> Optical satellites cannot see through monsoon and cyclone cloud, exactly when the disaster happens.",
                     "<b>Change is not a decision.</b> A change map does not say which village to reach first."])
    right = shot("51_sindh_map_detection", 400, "Real example: detected flooding (blue) and ranked hexagon cells (red = P1) next to the Indus river, Sindh, Pakistan, after the 2022 floods. Real Sentinel data.")
    F += [twocol(left, right, 330, 400), PageBreak()]

    # 4 ---------------------------------------------------------------- command centre
    F += head("The product", "The Command Centre: the first screen")
    F += [twocol(shot("02_command_centre", 500), [P("What you are looking at", "h2")] + bullets([
        "<b>Five headline numbers</b> at the top: critical areas, high-priority areas, people at high risk, people cut off by blocked roads, hospitals at risk. A single click on <i>More figures</i> shows five more.",
        "<b>The map</b> shows the detected hazard, the priority hexagons, roads, hospitals and shelters. Click any hexagon to see why it has its priority.",
        "<b>Next steps</b> and <b>Recent alerts</b> on the right tell the commander what to do now.",
        "<b>Run guided demo</b> plays the whole workflow in about a minute.",
        "A simple <b>Guide</b> page explains the project in plain English."]), 500, 240), PageBreak()]

    # 5 ---------------------------------------------------------------- workflow
    F += head("How it works", "What happens when you press Run analysis")
    F += [Diagram(CW, 196, pipeline_diagram), Spacer(1, 10)]
    F += [twocol([P("In plain words", "h2")] + bullets([
        "<b>Acquire</b> downloads the satellite scenes, terrain, land cover, population, roads and rainfall for the chosen area.",
        "<b>Detect</b> compares before and after radar images and marks where water, burn scars or ground change appear.",
        "<b>Assess</b> divides the area into hexagons about 500 m across and works out people, facilities and road access for each.",
        "<b>Prioritise</b> scores every hexagon from P1 (critical) to P4 (low) and records the reasons.",
        "<b>Plan</b> prepares routes to the top priority areas and a shelter plan; a commander then decides on resources and dispatch."]),
        shot("11_overview_expanded", 300), 420, 300)]
    F += [PageBreak()]

    # 6 ---------------------------------------------------------------- real vs simulated
    left = head("Data", "Real data and simulated data: what is what")
    left += [P("DISHA runs in two modes and always labels which one you are looking at. <b>Real data</b> events download actual open datasets when you run them. <b>Simulated</b> events generate synthetic imagery and facilities so the product can be shown offline; the algorithms are identical.")]
    rows = [["Input", "Source", "Status"], ["Radar before/after", "Sentinel-1 RTC (Copernicus / ESA), Microsoft Planetary Computer", "Real"], ["Optical image", "Sentinel-2 L2A, cloud-masked", "Real (optional)"], ["Terrain", "Copernicus DEM GLO-30", "Real"],
            ["Land cover", "ESA WorldCover 2021", "Real"], ["Population", "WorldPop 2020 (1 km) spread onto built-up land", "Real, modelled estimate"], ["Roads, hospitals, schools, bridges, places", "OpenStreetMap (Overpass)", "Real"],
            ["Rainfall", "Open-Meteo (ERA5 for past events)", "Real"], ["Rescue units", "No real source", "Hypothetical roster"], ["Shelter capacity", "OSM has none; assumed by type", "Assumed"], ["Children / elderly shares", "Not available", "Skipped, not invented"]]
    left += [table(rows, [118, 190, 100])]
    right = [Diagram(310, 224, sources_diagram), Spacer(1, 6)] + shot("04_new_event_scenarios", 300, "Scenarios are labelled <i>Real data</i> or <i>Simulated</i> when you start an event.")
    F += [twocol(left, right, 420, 300), PageBreak()]

    # 7 ---------------------------------------------------------------- Kuttanad
    F += head("Real data in action", "Kerala floods, August 2018: the Kuttanad backwaters")
    F += [P("Two real Sentinel-1 radar scenes from the <b>same orbit track</b> (9 August and 21 August 2018) plus a real Sentinel-2 image. Water is dark in radar, so a sudden drop in brightness marks new flooding. The permanent backwaters are excluded."), Spacer(1, 4),
          raster_strip("kuttanad", CW), Spacer(1, 10),
          stats([(f"{fk['area']:.1f} km²", "newly flooded area detected"), (f"{fk['perm']:.1f} km²", "permanent water (excluded)"), (f"{fk['cells']}", "hexagon cells analysed"), (f"P1 {fk['levels']['P1']}  P2 {fk['levels']['P2']}", "critical and high-priority cells"),
                 (f"{fk['people_at_risk']:,}", "people at high risk (modelled)"), (f"{fk['roads']['total']:,}", "real road segments checked")]), Spacer(1, 6),
          P("Numbers come from running the real pipeline on these scenes. Population is a modelled estimate from WorldPop; detection has not been validated against ground truth.", "small"), Spacer(1, 10),
          two_text([P("How to read the images", "h2")] + bullets(["<b>Dark areas in radar</b> are smooth surfaces such as open water. Bright areas are towns and vegetation.", "<b>Blue overlay</b> marks pixels that became dark between the two dates and passed the checks (not permanent water, not steep ground)."]),
                   [P("Why this event", "h2")] + bullets(["Kuttanad lies below sea level and stayed under water for weeks, so the radar pass on 21 August still shows the flood.", "It also has dense real roads and 140 mapped bridges, so blocked-road analysis is meaningful."])), PageBreak()]

    # 8 ---------------------------------------------------------------- method
    left = head("Method", "How the flood is found in the radar image")
    left += bullets(["<b>Same view, twice.</b> Only scenes from the same satellite track and direction are compared, so differences are real, not geometry.", "<b>Reduce noise.</b> Radar images are grainy (speckle); they are averaged in linear power before comparing.",
                     "<b>Look for drops.</b> The log-ratio (after minus before, in dB) is thresholded automatically with Otsu's method, with limits that keep the threshold physically sensible.",
                     "<b>Remove false alarms.</b> Permanent water (already dark before), steep slopes (radar shadow) and tiny blobs are masked out.",
                     "<b>Use optical when it helps.</b> On cloud-free pixels, a Sentinel-2 water index confirms or weakens the radar result.", "<b>Score it.</b> Each pixel gets a severity index and a confidence value; both are carried into the priority score."])
    left += [callout("<b>Honest limits.</b> Radar misses flooded built-up areas and flooded vegetation, and the severity is an intensity index, not water depth in metres. Detection has not been checked against surveyed flood maps.", "warn", 330)]
    right = [raster_strip("sindh", 400), Spacer(1, 6), P("Second real example: Sindh, Pakistan, 2022. Left to right: radar before, radar after, detected flood, satellite image.", "cap"), Spacer(1, 6),
             callout("<b>The system explains its sensor choice.</b> Example from the app: <i>Optical imagery downgraded due to high cloud cover. Sentinel-1 SAR selected as primary source.</i> With no usable optical scene it says so and runs radar-only.", "info", 400)]
    F += [twocol(left, right, 330, 400), PageBreak()]

    # 9 ---------------------------------------------------------------- Sindh
    F += head("Real data in action", "Pakistan floods 2022: Sindh, beside the Indus")
    F += [twocol(shot("50_sindh_map_satellite", 395, "Sentinel-2 satellite image with DISHA's priority hexagons."), shot("51_sindh_map_detection", 395, "Same area on the street map: detected flood (blue), blocked roads (red), P1 cells numbered."), 395, 395, 10), Spacer(1, 8),
          stats([(f"{fs['area']:.1f} km²", "flooded area detected"), (f"P1 {fs['levels']['P1']}  P2 {fs['levels']['P2']}", "critical and high cells"), (f"{fs['people_at_risk']:,}", "people at high risk"), (f"{fs['isolated']:,}", "people cut off by blocked roads"), (f"{fs['cells']}", "cells analysed")]), Spacer(1, 10),
          two_text([P("What the commander sees", "h2")] + bullets(["Detected flood runs along the Indus side of the area, so P1 cells cluster there.", "Roads that cross the flooded strip are marked blocked, which cuts off several villages."]),
                   [P("What to treat with care", "h2")] + bullets(["Population is a modelled estimate; actual counts may differ.", "Only 273 road segments are mapped here, so isolation may be understated or overstated where OpenStreetMap is sparse."])), PageBreak()]

    # 10 --------------------------------------------------------------- weak data
    left = head("Honesty", "What happens when the data is weak")
    left += [P("A decision tool must be clear about what it cannot see. Two real examples from this project:"),
             P("<b>Chalakudy, Kerala (Aug 2018).</b> The first usable radar pass after the flood peak is 21 August, when most water had already receded. DISHA detects only "
               f"<b>{fc['area']:.2f} km²</b> and ranks <b>no P1 areas</b>. We kept the scenario to show that the tool reports what the satellite shows, not what we expect."),
             P("<b>Wayanad landslide (Jul 2024).</b> With the only same-track scene available (6 August) and 30 m radar, the real change signal was too weak and the rule detected nothing. A silent miss on a real disaster would mislead, so this scenario was <b>removed</b> rather than shown."),
             P("<b>Low-confidence labels.</b> Every area shows a confidence level (high, medium, low, insufficient data). When satellite coverage, population or roads are weak, confidence drops and the app says verify on the ground first."),
             callout("Principle: the app never replaces missing data with invented values. Missing demographic factors are skipped, unavailable population is shown as unknown, and failed downloads stop the job with a readable error.", "ok", 320)]
    right = [grid([img(compose("chalakudy", "sar_post"), 205), img(compose("chalakudy", "hazard"), 205), P("Chalakudy radar after the event", "cap"), P("Detected flood: only small patches", "cap")], 2, 205)]
    F += [twocol(left, right, 340, 430), PageBreak()]

    # 11 --------------------------------------------------------------- hex twin
    left = head("Digital twin", "From pixels to places: one hexagon, one live state")
    left += [P("The area is divided into H3 hexagons about 500 m across (resolution is configurable). Each hexagon is a small <b>digital twin</b>: its hazard, people, facilities, road access, priority and predicted future are stored together and recalculated whenever new information arrives (a new satellite pass, a field report, or a change in settings)."),
             P("Every recalculation is saved as a numbered assessment, so DISHA can show <b>what changed</b> between versions and raise an alert such as <i>Cell 12 escalated from P2 to P1</i> with the reasons.")]
    left += [Spacer(1, 4), Diagram(340, 190, hex_diagram)]
    right = shot("24_cell_more_details", 360, "The cell panel: key facts first, details one click away.")
    F += [twocol(left, right, 360, 360), PageBreak()]

    # 12 --------------------------------------------------------------- impact
    left = head("Impact assessment", "From change to consequences")
    left += bullets(["<b>People.</b> Pixel-level population (WorldPop 1 km spread onto built-up land) summed per hexagon: total, exposed to the hazard, at high risk, and potentially cut off.",
                     "<b>Vulnerability.</b> A configurable score from density, distance to a hospital, isolation, road access and severity. Age and housing factors are skipped when no data exists.",
                     "<b>Critical facilities.</b> Hospitals, schools, power, water, fire and police, bridges; each carries a risk and the reason.",
                     "<b>Roads.</b> Every real OpenStreetMap road segment is checked against the hazard and labelled open, potentially blocked, blocked or unknown. Bridges and single points of failure are marked critical.",
                     "<b>Isolation.</b> Blocked roads are removed from the network; hexagons that can no longer be reached from a response base count as cut off.",
                     "<b>Knock-on risk.</b> Dependency chains: a flooded substation puts its hospital at risk; a blocked bridge isolates a village and delays rescue."])
    right = shot("21_map_streets", 430, "Real roads, hospitals (red dots) and shelters (green dots) over the detected flood and priority hexagons.")
    F += [twocol(left, right, 310, 430), PageBreak()]

    # 13 --------------------------------------------------------------- priority score
    F += head("Prioritisation", "The priority score: simple enough to explain")
    F += [Diagram(CW, 158, score_diagram), Spacer(1, 10),
          twocol([P("Why a formula, not a black box", "h2")] + bullets(["The weights come from the original DISHA proposal (35/30/20/15) and can be changed on the Priorities page; changing them recalculates everything and is recorded in the audit log.",
                                                                       "Each part is scaled between 0 and 1 and multiplied by its weight, so the four contributions always add up exactly to the score.",
                                                                       "Areas with almost no people (under 10) and no critical assets are capped below P2: an empty burning forest is flagged, but rescue teams are not sent there.",
                                                                       "Severity is multiplied by detection confidence, so a doubtful detection ranks lower."]), shot("31_priorities", 420), 330, 420)]
    F += [PageBreak()]

    # 14 --------------------------------------------------------------- why P1
    left = head("Explainability", "Why is this P1? Every ranking shows its reasons")
    left += bullets(["<b>Four bars</b> show how much hazard, people, facilities and lost road access contribute.", "<b>Plain reasons</b> in order of importance, for example: <i>High population exposure (209 people); Hospital in or adjacent to affected area; Moderate flood severity (45%)</i>.",
                     "<b>Recommended action</b> written from the data, for example <i>Stage relief and plan evacuation within 6-12 h; confirm access route.</i>", "<b>Confidence</b> combines satellite, population, roads, weather and facilities, weighted by quality and freshness. Stale data lowers it.",
                     "<b>Sources and age</b> of each input are listed under <i>More details</i>."])
    left += [Spacer(1, 6), table([["Confidence label", "Meaning"], ["High (80% and above)", "Act on it; routine checks"], ["Medium (60% to 80%)", "Likely correct; verify when possible"], ["Low (40% to 60%)", "Verify on the ground first"], ["Insufficient data", "Do not rely on it"]], [120, 190])]
    right = shot("22_map_p1_cell", 410, "Selecting a hexagon opens the explanation panel.")
    F += [twocol(left, right, 320, 410), PageBreak()]

    # 15 --------------------------------------------------------------- predictions
    F += head("Looking ahead", "Predictions and the time control")
    F += [two_text([P("DISHA estimates which areas may get worse in the next 6, 12, 24 and 48 hours. A transparent model combines how much of the surrounding area is already affected, how low the terrain is, the rainfall that follows, and persistence. Each estimate has a probability, and its confidence decays with time."),
                    P("The control at the bottom of the map switches between <i>Before</i>, <i>Now</i> and the four forecast horizons so commanders can see the likely spread.")],
                   [callout("<b>Always an estimate.</b> The coefficients are set by hand, not trained on observed floods, and have not been validated. Every prediction is labelled ESTIMATE and never shown as a guarantee.", "warn", 360)]), Spacer(1, 10),
          wide_pair("25_map_plus6h", "32_predictions", "The map at +6 hours: estimated spread (labelled as an estimate).", "Predictions page: current counts against predicted counts for each horizon."), PageBreak()]

    # 16 --------------------------------------------------------------- routes
    F += head("Response planning", "Which road should responders take?")
    F += [two_text([P("DISHA builds a road network from OpenStreetMap, marks each segment by the hazard, and computes three routes from a response base to a priority area:")] +
                   bullets(["<b>Shortest</b> by distance. If it crosses a blocked segment, it is flagged.", "<b>Fastest</b> by estimated travel time, avoiding blocked roads.", "<b>Safest</b> minimising risk, also avoiding blocked roads."]),
                   bullets(["A recommendation weighs time and risk. If no fully open road exists, it says so and points to boat or air access.", "When the last stretch lies inside the flooded zone, DISHA warns that the final approach needs a boat or a high-clearance vehicle.", "Travel times are estimates, not guarantees."])), Spacer(1, 6),
          wide_pair("33_routes", "23_map_route", "Route comparison: recommended route drawn on the real road network.", "Route from the cell panel on the map: Find safest route."), PageBreak()]

    # 17 --------------------------------------------------------------- shelters, resources
    F += head("Response planning", "Shelters and resources")
    F += [two_text([P("<b>Shelters.</b> People in P1 and P2 hexagons are assigned to the nearest safe shelter reachable by open roads, respecting capacity. The planner flags unreachable shelters, shelters inside the hazard zone, overcapacity and any shortfall.")],
                   [P("<b>Resources.</b> Rule-based requirements per area (for example boats where roads are lost, ambulances near a hospital) are filled by priority, and every assignment states its reason and arrival time. A <i>what-if</i> calculator shows how many critical areas stay uncovered with a different number of units.")]), Spacer(1, 4),
          callout("In real-data events the rescue-unit roster is <b>hypothetical</b>: no real resource feed exists. It is flagged on screen and in exports.", "warn", CW), Spacer(1, 8),
          wide_pair("34_shelters", "35_resources_plan", "Evacuation planner: who goes to which shelter, and remaining capacity.", "Resource plan: each unit with its reason and arrival time."), PageBreak()]

    # 18 --------------------------------------------------------------- field loop
    F += head("Closing the loop", "Field verification: the part that makes it a loop")
    F += [two_text([P("A responder opens their mission, reports what they see and may upload a photo. DISHA recalculates immediately.")] + bullets(["<b>Confirmed</b>: confidence rises.", "<b>False alarm</b>: severity and exposure drop sharply; the label is stored for model feedback.", "<b>Partially affected</b>: scaled down."]),
                   bullets(["<b>Severe</b>: severity is raised and a minimum share of residents assumed exposed until measured.", "<b>Resolved</b>: the area drops out of the response list.", "Reports are stored as labelled observations that can be exported for future model training."]) +
                   [P("Photo analysis is a simple colour and texture heuristic, not a trained model; it states a limited confidence and gives no measurements.", "small")]), Spacer(1, 6),
          wide_pair("37_field_missions", "38_field_verified", "The responder's missions (one per priority area).", "A verified report (a simulated one here) changes the priority."), PageBreak()]
    F += head("Closing the loop", "After the report: dispatch and what changed")
    F += [P("The commander dispatches the planned units; after a field report the overview shows <b>what changed</b> between assessments, and alerts such as <i>Cell NN escalated from P2 to P1</i> appear with their reasons. Everything is also written to the incident timeline and audit log."), Spacer(1, 6),
          wide_pair("36_resources_dispatched", "39_overview_after_field", "Dispatched units after pressing Dispatch.", "Overview after a field report: what changed since the last assessment."), PageBreak()]

    # 19 --------------------------------------------------------------- copilot
    left = head("Assistant", "DISHA Copilot: answers from the data, never guesses")
    left += [P("The Copilot is <b>not</b> a general chatbot. It recognises the question, runs the matching query on the event's database (priorities, routes, predictions, resources, data health) and writes the answer from those values, with the sources and assessment version shown."),
             P("If the information is not there it replies exactly: <i>DISHA does not currently have sufficient data to determine this.</i> (see the last question in the screenshot).")]
    left += bullets(["Which areas should we rescue first?", "Why is Cell 12 P1?", "Give me the safest route to Cell 12.", "How many people are currently at high risk?", "Which hospital is most at risk?", "What changed since the previous assessment?"])
    right = shot("42_copilot", 440, "Grounded answers with their sources, and a refusal when data is missing.")
    F += [twocol(left, right, 300, 440), PageBreak()]

    # 20 --------------------------------------------------------------- presentation + demo
    F += head("Demonstration", "Presentation mode and the guided demo")
    F += [P("<b>Presentation mode</b> is a projector-friendly screen with nine big steps: trigger the event, run the analysis, show the detected change, show priorities, show the prediction, show the route, allocate resources, simulate a field report, recalculate. <b>Run guided demo</b> on the Command Centre plays the whole workflow in about 45 seconds with narration, using simulated data so it works without internet."), Spacer(1, 6),
          wide_pair("60_presentation_priority", "62_presentation_route", "Presentation mode, step 4: priorities (simulated Kerala scenario).", "Presentation mode, step 6: route to the top priority area."), PageBreak()]
    F += head("Demonstration", "The guided demo, finished")
    F += [twocol(shot("64_guided_demo_done", 500, "Alert, acquisition, detection, impact, priority, prediction, route, resources, field report and recalculated priority, narrated step by step."),
                 bullets(["Runs on the <b>simulated</b> Kerala scenario so it works without internet.", "Every step is narrated with the numbers it produced.", "Ends with a verified field report that changes a priority: the closed loop.", "Takes about 45 seconds; the browser test checks that it completes."]), 500, 240), PageBreak()]

    # 22 --------------------------------------------------------------- other screens
    F += head("Rest of the product", "Reports, timeline and audit")
    F += [wide_pair("40_reports", "41_timeline", "Reports: PDF situation report plus GeoJSON, KML, CSV and COG exports, each with event, time, sources, model and confidence metadata.", "Incident timeline and audit log: who did what, where and when."), PageBreak()]
    F += head("Rest of the product", "Dashboard and settings")
    F += [wide_pair("44_dashboard", "45_settings", "Dashboard: all events at a glance.", "Settings: alert triggers and channels (email, SMS, WhatsApp are mock providers in this build), plus the role permission table.", crop_b=(0, 0, 1500, 900)), PageBreak()]

    # 23 --------------------------------------------------------------- architecture
    left = head("Under the hood", "Architecture")
    left += [Diagram(430, 296, arch_diagram)]
    right = [P("Technology", "h2"), table([["Layer", "What is used"], ["Frontend", "Next.js 14, React, TypeScript, Tailwind CSS, MapLibre GL, deck.gl, Chart.js"], ["Backend", "Python, FastAPI, Pydantic, SQLAlchemy"],
                                          ["Geospatial", "H3, Shapely, GeoPandas, Rasterio, NetworkX, NumPy/SciPy"], ["Database", "PostgreSQL + PostGIS (GiST indexes), SQLite fallback"], ["Reports", "ReportLab (PDF), GeoJSON, KML, CSV, Cloud Optimised GeoTIFF"],
                                          ["Quality", "pytest, Playwright browser tests, GitHub Actions"], ["Packaging", "Docker, docker-compose (PostGIS, Redis, backend, frontend)"]], [70, 200]),
             Spacer(1, 6), P("Design rule: the algorithms are plain functions that do not touch the database, so each one can be tested on its own. The same algorithms process real and simulated data.", "small")]
    F += [twocol(left, right, 450, 290), PageBreak()]

    # 24 --------------------------------------------------------------- engineering quality
    F += head("Engineering", "Tested and built in the open")
    F += [stats([("35+", "commits, built in logical steps"), ("~7,000", "lines of Python"), ("~3,100", "lines of TypeScript"), ("53", "automated tests (52 run in CI)"), ("5", "CI jobs, all passing")]), Spacer(1, 10),
          twocol(shot("71_github_actions", 380, "GitHub Actions: backend tests (SQLite and PostGIS), frontend build, browser test, Docker image builds."), [P("What is checked on every push", "h2")] + bullets([
              "Backend tests on SQLite <b>and</b> on a real PostGIS database.", "Frontend type-check and production build.", "A headless-Chrome run of the full workflow: login, guided demo, map, cell explanation, route, every page, copilot, role restrictions.",
              "Docker images build from a clean checkout.", "Tests for algorithms (priority formula, detection masks, routing around blocked roads, shelter capacity), the API, all scenarios, and the real-data code with the network mocked."]) +
          [P("An opt-in test also runs the whole pipeline against the real data services.", "small")], 400, 330)]
    F += [PageBreak()]

    # 25 --------------------------------------------------------------- security
    left = head("Trust", "Security, roles and accountability")
    rows = [["Capability", "Admin", "Commander", "Analyst", "Responder", "Observer"], ["View everything", "Yes", "Yes", "Yes", "Yes", "Yes"], ["Create events, run analysis", "Yes", "Yes", "Yes", "-", "-"], ["Change priority weights", "Yes", "Yes", "-", "-", "-"],
            ["Plan and dispatch resources", "Yes", "Yes", "-", "-", "-"], ["Plan routes", "Yes", "Yes", "-", "Yes", "-"], ["Submit field reports", "Yes", "Yes", "-", "Yes", "-"], ["Generate reports", "Yes", "Yes", "Yes", "-", "-"], ["Manage users and data", "Yes", "-", "Data only", "-", "-"]]
    left += [table(rows, [140, 52, 66, 56, 62, 58])]
    right = [P("Principles", "h2")] + bullets(["Sign-in with JWT tokens; passwords hashed with PBKDF2; every endpoint checks the role.", "Important actions (event changes, resource assignments, field reports, configuration, exports) are written to an audit log: who, what, where, why, when.", "Secrets live in environment variables; a template is provided and no secrets are in the repository.",
                                               "AI is decision support. Each important output shows its confidence, data sources, time and reasons; predictions are labelled estimates.", "Notifications (email, SMS, WhatsApp) use a provider interface; in this build they are mock and nothing is sent.",
                                               "The demo accounts and their password are public and are for demonstration only."])
    F += [twocol(left, right, 440, 300), PageBreak()]

    # 26 --------------------------------------------------------------- limitations
    F += head("Honest assessment", "What is not done, and what is assumed")
    F += [table([["Area", "Status"], ["Detection accuracy on real events", "Not validated against surveyed flood extents. No accuracy numbers are claimed; the app shows none unless real ground truth is registered."],
                 ["Deep-learning models (Siamese U-Net, ChangeFormer)", "Interfaces only; no trained weights are included. The rule-based detector is used and the fallback is reported."],
                 ["Prediction model", "Hand-set heuristic, uncalibrated. Always labelled as an estimate."], ["Population", "Modelled estimate from WorldPop, not a census; children/elderly shares unavailable."],
                 ["Shelters and rescue units", "Capacities assumed by type; rescue roster hypothetical. Needs real registries before operational use."], ["Radar limits", "Flooded built-up areas and flooded vegetation are under-detected; small landslides are not visible at 30 m."],
                 ["Photo analysis", "Simple colour/texture rules, not a trained model."], ["Notifications", "Mock providers: nothing is actually sent."], ["Background jobs", "Run inside the API process; Redis is provisioned but not yet used as a queue."],
                 ["Deployment", "Docker images build in CI; running the full docker-compose stack has not been exercised yet."], ["Live wildfire hotspots", "Needs a free NASA FIRMS key; not exercised."]], [220, CW - 220]), PageBreak()]

    # 27 --------------------------------------------------------------- roadmap
    left = head("Next", "Where this can go")
    left += [P("Planned, not built. Items follow the original proposal and the gaps listed on the previous page.")]
    left += bullets(["<b>Validate on real events</b> against surveyed flood extents; publish precision, recall and IoU.", "<b>Train deep-learning change models</b> on public datasets (xBD, Sen1Floods11, LEVIR-CD, Landslide4Sense, CaBuAr) and plug them into the existing detector interface.",
                     "<b>More satellites</b>: ISRO EOS-04 and NISAR L-band radar, higher-resolution imagery for landslides.", "<b>Real registries</b> for shelters, rescue units and hospital capacity from state disaster authorities.",
                     "<b>Real alerts</b>: SMS and WhatsApp through an approved provider, with delivery receipts.", "<b>Learning from the field</b>: use verified reports to retrain models (active learning).",
                     "<b>Scale</b>: move jobs to a queue, serve imagery as map tiles, support many districts at once.", "<b>Pre-positioning</b>: use rainfall and cyclone-track forecasts to estimate impact before landfall."])
    right = shot("43_guide", 330, "The in-app guide explains the project in plain English.")
    F += [twocol(left, right, 400, 330), PageBreak()]

    # 28 --------------------------------------------------------------- Q&A
    F += head("For the judges", "Questions you are likely to be asked")
    qa = [["Question", "Straight answer"],
          ["Is this real satellite data?", "Yes for events marked Real data: Sentinel-1/2, Copernicus DEM, WorldCover, WorldPop, OpenStreetMap and Open-Meteo are downloaded at run time. Simulated events are generated and labelled."],
          ["How accurate is it?", "Unknown. The method is standard, but we have not checked it against surveyed flood maps, so we make no accuracy claim."],
          ["Why radar first?", "Radar sees through cloud and at night, which matters most during monsoons and cyclones."],
          ["Why do the numbers differ from the slides?", "Counts are computed from the data, not scripted. We set priority thresholds after looking at the score distribution; they are adjustable."],
          ["Is the AI making decisions?", "No. It ranks and explains; commanders decide. Every output shows reasons, confidence and sources, and predictions are labelled estimates."],
          ["What is original here?", "The step from change map to decision: priorities, explanations, routes, shelters, resources and a field-verification loop in one system."],
          ["What would it take to use this operationally?", "Validation on real events, real resource and shelter registries, trained models, hardened security and a queue, as listed under limitations."],
          ["Can we see it run?", "Yes: guided demo (about a minute, works offline) or a real-data event (first run downloads for 1 to 3 minutes)."]]
    F += [table(qa, [190, CW - 190]), PageBreak()]

    # 29 --------------------------------------------------------------- demo script + run
    left = head("Show it", "A three-minute demo script")
    left += [P("<b>0:00</b> Command Centre. Say: after a disaster, teams need to know where to go first and why.", "body"),
             P("<b>0:20</b> Open <i>Events</i> and start <b>Kerala floods 2018 - Kuttanad (real data)</b>, then <b>Run analysis</b>. Mention it downloads real Sentinel images and OpenStreetMap roads (use a pre-run event if time is short).", "body"),
             P("<b>0:50</b> <b>Map</b>: switch on <i>Satellite image</i>, then show detected flood and priority hexagons. Click a hexagon: <b>why is it P1</b>.", "body"),
             P("<b>1:30</b> <b>Find safest route</b>, then <b>+6 h</b> on the time control (an estimate).", "body"),
             P("<b>2:00</b> <b>Resources</b>: Plan resources and Dispatch. Show shelters.", "body"),
             P("<b>2:20</b> <b>Field</b>: simulate a severe report. Show the priority change and <i>What changed</i>.", "body"),
             P("<b>2:45</b> <b>Reports</b>: download the situation report. Close with limits: radar blind spots, modelled population, unvalidated accuracy.", "body")]
    right = [P("Run it yourself", "h2"), table([["Step", "Command"], ["Windows, no Docker", "./start-dev.ps1  (API on :8000, UI on :3000)"], ["Docker", "cp .env.example .env, set secrets, then docker compose up --build"], ["Open", "http://localhost:3000"],
                                                ["Demo login", "commander@disha.demo / Disha@2026 (demo only)"], ["Tests", "cd backend; python -m pytest tests -q"], ["Browser test", "cd e2e; node run.mjs  (stack running)"]], [90, 230]),
             Spacer(1, 6), P("Roles to try: commander (everything), analyst (data, no dispatch), responder (missions, routes, field reports), observer (read-only), admin.", "small"),
             Spacer(1, 6), shot("70_github_repo", 320, "Public repository: github.com/srushti117/Disha")]
    F += [twocol(left, right, 400, 330), PageBreak()]

    # 30 --------------------------------------------------------------- glossary
    F += head("Reference", "Glossary")
    g = [["Term", "Meaning"], ["Cell / hexagon", "One H3 hexagon (about 500 m). The smallest unit DISHA scores. 'Cell 07' is hexagon number 7."], ["P1 to P4", "Priority levels: Critical, High, Moderate, Low."], ["Priority score", "0 to 1: 35% severity, 30% people, 20% facilities, 15% road access lost."],
         ["SAR / radar", "Satellite radar (Sentinel-1). Sees through cloud and at night. Water looks dark."], ["Log-ratio", "After minus before brightness in dB; a large drop indicates new water."], ["Otsu threshold", "A standard way to pick a cut-off between two groups of pixel values automatically."],
         ["Sentinel-2", "Optical (colour) satellite images, blocked by cloud."], ["DEM / slope", "Elevation model; slope removes places water cannot pool."], ["WorldPop / WorldCover", "Open population and land-cover datasets used to estimate people per area."],
         ["OpenStreetMap", "Open map of roads, hospitals, schools and place names."], ["Digital twin", "The stored live state of each hexagon, recalculated when new information arrives."], ["Confidence", "How much DISHA trusts a result: high, medium, low or insufficient data."],
         ["Estimate", "A prediction, always shown with a probability and never as a certainty."], ["Field verified", "A responder confirmed the situation; this can change a priority."], ["Real data / Simulated", "Whether an event used actual open data or generated demonstration data."]]
    F += [table(g, [150, CW - 150])]

    doc.build(F)
    print("written", OUT, round(os.path.getsize(OUT) / 1e6, 1), "MB")


if __name__ == "__main__":
    build()
