"""Situation report PDF (reportlab). All content is drawn from DB values via summary/response services."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AOI, Event, FieldReport, H3Cell, Infrastructure, Prediction, RoadSegment
from . import response, summary
from .common import now

LVL = {"P1": colors.HexColor("#d92b2b"), "P2": colors.HexColor("#e87b1f"), "P3": colors.HexColor("#f2cd1c"), "P4": colors.HexColor("#8a8a8a")}
NAVY = colors.HexColor("#0f1b2d")


class MapFlowable(Flowable):
    def __init__(self, cells, roads, width, height):
        super().__init__()
        self.cells, self.roads, self.width, self.height = cells, roads, width, height

    def draw(self):
        xs = [x for c in self.cells for x, _ in c.geom["coordinates"][0]]
        ys = [y for c in self.cells for _, y in c.geom["coordinates"][0]]
        if not xs:
            return
        w, s, e, n = min(xs), min(ys), max(xs), max(ys)
        k = min(self.width / max(e - w, 1e-9), self.height / max(n - s, 1e-9))
        ox, oy = (self.width - (e - w) * k) / 2, (self.height - (n - s) * k) / 2
        tx = lambda x: ox + (x - w) * k  # noqa: E731
        ty = lambda y: oy + (y - s) * k  # noqa: E731
        self.canv.setFillColor(colors.HexColor("#0b1320"))
        self.canv.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        for c in self.cells:
            p = self.canv.beginPath()
            pts = c.geom["coordinates"][0]
            p.moveTo(tx(pts[0][0]), ty(pts[0][1]))
            for x, y in pts[1:]:
                p.lineTo(tx(x), ty(y))
            p.close()
            col = LVL[c.priority_level]
            self.canv.setFillColor(col)
            self.canv.setFillAlpha(0.15 if c.priority_level == "P4" else 0.75)
            self.canv.setStrokeColor(colors.HexColor("#27384f"))
            self.canv.setLineWidth(0.3)
            self.canv.drawPath(p, stroke=1, fill=1)
        self.canv.setFillAlpha(1)
        for r in self.roads:
            (x1, y1), (x2, y2) = r.geom["coordinates"]
            self.canv.setStrokeColor({"blocked": colors.HexColor("#ff3b3b"), "potentially_blocked": colors.HexColor("#ffb020")}.get(r.status, colors.HexColor("#5b6b82")))
            self.canv.setLineWidth(1.4 if r.status == "blocked" else 0.5)
            self.canv.line(tx(x1), ty(y1), tx(x2), ty(y2))
        self.canv.setFillColor(colors.white)
        self.canv.setFont("Helvetica-Bold", 6)
        for c in [c for c in self.cells if c.priority_level == "P1"][:14]:
            self.canv.drawCentredString(tx(c.lon), ty(c.lat) - 2, f"{c.cell_no:02d}")


def build_pdf(db: Session, event: Event, user=None) -> bytes:
    if not event.assessment_version:
        raise ValueError("Run analysis before generating a report")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"DISHA Situation Report {event.code}", author="DISHA")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], textColor=NAVY, fontSize=22, alignment=0, spaceAfter=2)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=NAVY, fontSize=12, spaceBefore=10, spaceAfter=4)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    S = ParagraphStyle("s", parent=B, fontSize=7.5, textColor=colors.HexColor("#555555"))
    k = summary.kpis(db, event)
    es = summary.exec_summary(db, event)
    aoi = db.scalars(select(AOI).where(AOI.event_id == event.id)).first()
    cells = sorted(summary.cells_of(db, event.id), key=lambda c: c.cell_no)
    roads = db.scalars(select(RoadSegment).where(RoadSegment.event_id == event.id)).all()
    el = [Paragraph("DISHA", H1), Paragraph("Situation Report", ParagraphStyle("sub", parent=ss["Heading3"], textColor=colors.HexColor("#4a5d78"))), Spacer(1, 3)]
    if event.is_demo:
        el.append(Table([[Paragraph("<b>DEMONSTRATION DATA</b> - generated from simulated satellite, population, road and facility inputs. Not live. Not for operational use.", B)]],
                        style=[("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff3cd")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#c9a227")), ("PADDING", (0, 0), (-1, -1), 5)]))
    el += [Spacer(1, 6), Table([["Event", f"{event.name} ({event.code})"], ["Hazard", event.hazard.title()], ["Date", event.start_date.strftime("%Y-%m-%d")],
                                ["Area", f"{aoi.name} - {aoi.area_km2:.0f} km2" if aoi else "n/a"], ["Report generated", now().strftime("%Y-%m-%d %H:%M UTC")],
                                ["Assessment version", f"v{event.assessment_version}"]], colWidths=[40 * mm, 130 * mm],
                               style=[("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4a5d78")), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)])]
    el += [Paragraph("Executive Summary", H2), Paragraph(es["text"], B)]
    lv = k["levels"]
    el += [Paragraph("Affected Area & Population at Risk", H2),
           Table([["Affected area", "People at high risk", "People exposed", "People potentially isolated"],
                  [f"{k['affected_area_km2']:.1f} km2", f"{k['people_at_risk']:,}", f"{k['people_exposed']:,}", f"{k['people_isolated']:,}"]],
                 style=[("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]),
           Spacer(1, 4),
           Table([["P1 CRITICAL", "P2 HIGH", "P3 MODERATE", "P4 LOW"], [lv["P1"], lv["P2"], lv["P3"], lv["P4"]]],
                 style=[("BACKGROUND", (0, 0), (0, 0), LVL["P1"]), ("BACKGROUND", (1, 0), (1, 0), LVL["P2"]), ("BACKGROUND", (2, 0), (2, 0), LVL["P3"]), ("BACKGROUND", (3, 0), (3, 0), LVL["P4"]),
                        ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)])]
    p1 = [c for c in cells if c.priority_level == "P1"]
    rows = [["Cell", "Score", "Conf.", "Exposed", "Road", "Top reasons"]] + [[f"{c.cell_no:02d}", f"{c.priority_score:.2f}", f"{c.confidence:.0%}", f"{c.population_exposed:,}", c.road_status.replace("_", " "),
                                                                               Paragraph("; ".join(r["label"] for r in c.reason_codes[:3]), S)] for c in p1[:15]]
    el += [Paragraph(f"P1 Locations ({len(p1)})", H2), Table(rows, colWidths=[12 * mm, 14 * mm, 14 * mm, 20 * mm, 28 * mm, 86 * mm], repeatRows=1,
                                                              style=[("BACKGROUND", (0, 0), (-1, 0), LVL["P1"]), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")])]
    p2 = [c for c in cells if c.priority_level == "P2"]
    el += [Paragraph(f"P2 Locations ({len(p2)})", H2), Paragraph("Cells: " + (", ".join(f"{c.cell_no:02d}" for c in p2[:40]) + (" ..." if len(p2) > 40 else "") or "none"), B)]
    infra = db.scalars(select(Infrastructure).where(Infrastructure.event_id == event.id, Infrastructure.risk >= 0.25).order_by(Infrastructure.risk.desc())).all()
    el += [Paragraph("Critical Infrastructure at Risk", H2)]
    el.append(Table([["Facility", "Type", "Risk", "Status", "Reason"]] + [[Paragraph(i.name, S), i.kind, f"{i.risk:.0%}", i.status.replace("_", " "), Paragraph(i.risk_reason[:120], S)] for i in infra[:14]],
                    colWidths=[48 * mm, 18 * mm, 14 * mm, 20 * mm, 74 * mm], style=[("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]) if infra else Paragraph("None above the risk threshold.", B))
    r = k["roads"]
    el += [Paragraph("Road Disruptions", H2), Paragraph(f"{r['blocked']} blocked, {r['potentially_blocked']} potentially blocked, {r['unknown']} unknown of {r['total']} segments. Blocked critical roads/bridges: " +
                                                       (", ".join(x.name for x in roads if x.status == "blocked" and x.is_critical)[:300] or "none") + ".", B)]
    preds = db.scalars(select(Prediction).where(Prediction.event_id == event.id, Prediction.horizon_h == 6, Prediction.predicted_level == "P1", Prediction.current_level != "P1").order_by(Prediction.expansion_probability.desc())).all()
    cmap = {c.h3_index: c for c in cells}
    el += [Paragraph("Predicted Risk (estimates)", H2), Paragraph(
        f"Heuristic model, uncalibrated. {len(preds)} location(s) may escalate to P1 within 6 h: " + (", ".join(f"Cell {cmap[p.h3_index].cell_no:02d} ({p.expansion_probability:.0%})" for p in preds[:10]) or "none") + ". Predictions are estimates, not guaranteed outcomes.", B)]
    alloc = response.allocation(db, event)
    m = alloc["metrics"]
    el += [Paragraph("Resource Allocation (recommended)", H2), Paragraph(f"P1 coverage {m['p1_coverage_pct']}% ({m['p1_served']}/{m['p1_total']}); estimated response delay {m['est_response_delay_min']} min; unserved P1: {m['unserved_p1_count']}.", B)]
    el.append(Table([["Resource", "Cell", "Level", "ETA (min)"]] + [[a["resource"], f"{a['cell_no']:02d}", a["priority_level"], f"{a['eta_min']:.0f}"] for a in alloc["assignments"][:16]],
                    colWidths=[50 * mm, 20 * mm, 20 * mm, 24 * mm], style=[("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
    el.append(Paragraph("Recommended Actions", H2))
    for a in summary.recommendations(db, event, 8):
        el.append(Paragraph(f"<b>{a['rank']}. {a['action']}</b> - why: {'; '.join(a['why'][:3])}", B))
    el += [PageBreak(), Paragraph("Priority Map", H2), MapFlowable(cells, roads, 170 * mm, 150 * mm),
           Paragraph("Red/orange/yellow/grey = P1/P2/P3/P4. Red lines = blocked roads, amber = potentially blocked. Numbers label P1 cells.", S)]
    h = summary.data_health(db, event)
    from ..models import DataSource as _DS
    srcs = db.scalars(select(_DS).where(_DS.event_id == event.id)).all()
    nfield = db.query(FieldReport).filter(FieldReport.event_id == event.id).count()
    src_line = "; ".join(f"{d.name} - {'SIMULATED' if d.is_simulated else d.provider} (quality {d.quality:.0%}{', UNAVAILABLE' if d.availability == 0 else ''})" for d in srcs)
    el += [Paragraph("Confidence & Data Sources", H2), Paragraph(
        f"Sensor mode: {h['sensor_mode']}. {h['sensor_explanation']} Field observations: {nfield}.", B),
           Paragraph("Data sources: " + src_line, S),
           Paragraph("Freshness: " + "; ".join(f"{f['name']}: {f['last_updated'][:16]}{' (STALE)' if f['stale'] else ''}" for f in h["freshness"]), S),
           Spacer(1, 6), Paragraph("AI outputs are decision support and must be verified by qualified responders. Predictions are estimates with stated uncertainty."
                                   + (" Population is a modelled estimate (not a census); shelter capacities and the response-resource roster are assumptions." if not event.is_demo else ""), S)]

    def foot(canv, d):
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.grey)
        canv.drawString(16 * mm, 9 * mm, f"DISHA | {event.code} | v{event.assessment_version} | {now().strftime('%Y-%m-%d %H:%M UTC')}" + (" | DEMONSTRATION DATA" if event.is_demo else ""))
        canv.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {d.page}")
        canv.restoreState()

    doc.build(el, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()
