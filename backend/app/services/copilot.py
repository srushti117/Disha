"""DISHA Copilot: retrieval-grounded question answering over the event's database.

It is intentionally NOT a free-text LLM: it classifies the question into an intent, runs the matching query against actual system
state (priorities, routes, predictions, resources, data health) and renders the answer from those values with provenance.
Questions it cannot ground get the standard 'insufficient data' reply instead of a guess.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Event, H3Cell, Infrastructure, Prediction, Shelter
from . import response, summary
from .common import now

NO_DATA = "DISHA does not currently have sufficient data to determine this."


def _cell_no(q: str) -> int | None:
    m = re.search(r"cell\s*(?:no\.?|number|#)?\s*(\d{1,4})", q) or re.search(r"\bc(\d{1,4})\b", q)
    return int(m.group(1)) if m else None


def _get_cell(db, event, n):
    return db.scalars(select(H3Cell).where(H3Cell.event_id == event.id, H3Cell.cell_no == n)).first()


def _resp(answer, intent, data=None, sources=None, event=None):
    return {"answer": answer, "intent": intent, "data": data or {}, "sources": sources or [], "generated_at": now().isoformat(),
            "assessment_version": event.assessment_version if event else None,
            "provenance": ("DEMO / SIMULATED DATA. " if event and event.is_demo else "") + "Answer generated from stored system values; estimates are labelled."}


def why_text(c: H3Cell) -> str:
    comp = c.components.get("priority", {})
    parts = ", ".join(f"{k} {v:.0%}" for k, v in comp.items())
    return (f"Cell {c.cell_no:02d} is {c.priority_level} ({c.priority_score:.2f}). Components: {parts}. Top factors: " +
            "; ".join(f"{i + 1}. {r['label']}" for i, r in enumerate(c.reason_codes[:4])) + f". Confidence {c.confidence:.0%} ({c.confidence_label.lower()}).")


def ask(db: Session, event: Event, question: str) -> dict:
    q = question.lower().strip()
    if not event.assessment_version:
        return _resp("This event has not been analysed yet. Run ANALYSE EVENT first.", "not_analysed", event=event)
    n = _cell_no(q)

    if re.search(r"\b(route|path|way|navigate|get to|reach)\b", q) and n:
        c = _get_cell(db, event, n)
        if not c:
            return _resp(f"There is no Cell {n} in this event.", "route", event=event)
        r = response.compute_routes(db, event, c.h3_index, persist=False)
        rec = next((x for x in r["routes"] if x["recommended"]), None)
        want = "safest" if "safe" in q else "fastest" if "fast" in q else "shortest" if "short" in q else None
        pick = next((x for x in r["routes"] if x["kind"] == want), None) if want else rec
        if not pick or not pick["node_path"]:
            return _resp(f"No road route to Cell {n} is available from the response base; boat or air access is needed. {r['last_mile_note']}", "route", {"routing": r}, ["routing engine"], event)
        status = "BLOCKED" if pick["blocked_segments"] else f"open, risk {pick['risk']:.0%}"
        ans = f"{pick['label']} to Cell {n}: {pick['distance_km']} km, ETA {pick['eta_min']:.0f} min, {status}. " + (f"Recommended route: {r['recommended'].upper() if r['recommended'] else 'none open'}. " if r['recommended'] != pick['kind'] else "This is the recommended route. ") + (r["last_mile_note"] or "")
        return _resp(ans.strip(), "route", {"routing": r}, ["road network", "routing engine"], event)

    if n and re.search(r"\bwhy\b|explain|reason", q):
        c = _get_cell(db, event, n)
        return _resp(why_text(c) if c else f"There is no Cell {n} in this event.", "why_cell", {"cell_no": n}, ["priority engine"], event)

    if re.search(r"what.*changed|changes? since|compare|previous", q):
        w = summary.what_changed(db, event)
        if not w["available"]:
            return _resp(w["message"], "what_changed", event=event)
        return _resp(f"Between assessment v{w['from_version']} and v{w['to_version']}: " + "; ".join(w["lines"]) + ". " + (f"{len(w['escalations'])} priority-level changes." if w["escalations"] else ""), "what_changed", w, ["assessment history"], event)

    if re.search(r"hospital", q):
        hs = db.scalars(select(Infrastructure).where(Infrastructure.event_id == event.id, Infrastructure.kind == "hospital").order_by(Infrastructure.risk.desc())).all()
        if not hs:
            return _resp(NO_DATA, "hospital", event=event)
        h = hs[0]
        return _resp(f"{h.name} is the most at-risk hospital: risk {h.risk:.0%} ({h.status.replace('_', ' ')}). {h.risk_reason or 'No specific driver recorded.'}", "hospital",
                     {"hospitals": [{"name": x.name, "risk": x.risk, "status": x.status, "reason": x.risk_reason} for x in hs]}, ["infrastructure", "cascade engine"], event)

    if re.search(r"how many (people|persons|residents)|population|at risk|exposed|affected people", q):
        k = summary.kpis(db, event)
        return _resp(f"{k['people_at_risk']:,} people are at high risk and {k['people_exposed']:,} are exposed to the hazard; {k['people_isolated']:,} are potentially isolated by blocked access. "
                     "Population values are demonstration estimates.", "population", {"people_at_risk": k["people_at_risk"], "people_exposed": k["people_exposed"], "people_isolated": k["people_isolated"]}, ["population layer"], event)

    if re.search(r"first|rescue|priorit|where.*(go|send)|which areas|p1", q):
        p1 = summary.top_cells(db, event, "P1", 50)
        if not p1:
            return _resp("There are currently no P1 locations.", "priorities", event=event)
        t = p1[0]
        return _resp(f"There are {len(p1)} P1 locations. Cell {t.cell_no:02d} has the highest priority score ({t.priority_score:.2f}) because of " +
                     ", ".join(r["label"].lower() for r in t.reason_codes[:4]) + f". Next: " + ", ".join(f"Cell {c.cell_no:02d} ({c.priority_score:.2f})" for c in p1[1:5]) + ".",
                     "priorities", {"p1": [{"cell_no": c.cell_no, "score": c.priority_score} for c in p1]}, ["priority engine"], event)

    if re.search(r"predict|next \d+ ?h|escalat|forecast|worse|will", q):
        hz = 12 if "12" in q else 24 if "24" in q else 48 if "48" in q else 6
        rows = db.scalars(select(Prediction).where(Prediction.event_id == event.id, Prediction.horizon_h == hz, Prediction.predicted_level == "P1", Prediction.current_level != "P1").order_by(Prediction.expansion_probability.desc())).all()
        cells = {c.h3_index: c for c in summary.cells_of(db, event.id)}
        if not rows:
            return _resp(f"The estimate shows no additional locations escalating to P1 within {hz} h.", "prediction", event=event)
        return _resp(f"Estimate (heuristic model, not guaranteed): {len(rows)} location(s) may escalate to P1 within {hz} h; most likely: " +
                     ", ".join(f"Cell {cells[r.h3_index].cell_no:02d} ({r.expansion_probability:.0%})" for r in rows[:4]) + ".", "prediction", {"horizon_h": hz, "count": len(rows)}, ["prediction engine"], event)

    if re.search(r"resource|team|ambulance|boat|drone|deploy|allocate|assign", q):
        a = response.allocation(db, event)
        m = a["metrics"]
        return _resp(f"Recommended allocation uses {m['units_assigned']} units; P1 coverage {m['p1_coverage_pct']}% ({m['p1_served']}/{m['p1_total']}). " +
                     (f"Estimated response delay {m['est_response_delay_min']} min. " if m["est_response_delay_min"] else "") + (f"{m['unserved_p1_count']} P1 location(s) remain unserved." if m["unserved_p1_count"] else "All P1 locations covered."),
                     "resources", {"metrics": m}, ["resource engine"], event)

    if re.search(r"shelter|evacuat", q):
        p = response.evacuation_plan(db, event)
        s = p["summary"]
        return _resp(f"{s['people_assigned']:,} of {s['people_needing_shelter']:,} people in P1/P2 cells can be placed in safe, reachable shelters; shortfall {s['shortfall']:,}. " +
                     (f"{len(p['flags'])} flag(s): " + "; ".join(f['detail'] for f in p['flags'][:2]) if p["flags"] else ""), "shelters", {"summary": s}, ["evacuation planner"], event)

    if re.search(r"road|bridge|isolat|access", q):
        k = summary.kpis(db, event)["roads"]
        return _resp(f"{k['blocked']} road segments are blocked, {k['potentially_blocked']} potentially blocked, {k['unknown']} unknown.", "roads", k, ["road network"], event)

    if re.search(r"confiden|data (quality|health)|fresh|stale|source", q):
        h = summary.data_health(db, event)
        return _resp(f"Sensor mode {h['sensor_mode']}. {h['sensor_explanation']} Cloud cover {h['cloud_cover_pct']}%. Field observations: {h['field_observations']}. " +
                     (f"Stale layers: {', '.join(h['stale_layers'])}." if h["stale_layers"] else "No stale layers."), "data_health", h, ["data health"], event)

    if re.search(r"summary|situation|overview|brief|status", q):
        s = summary.exec_summary(db, event)
        return _resp(s["text"], "summary", s["facts"], ["database"], event)

    if re.search(r"what should|recommend|action|do next", q):
        rec = summary.recommendations(db, event, 5)
        return _resp("Recommended actions: " + " ".join(f"{r['rank']}. {r['action']} (why: {'; '.join(r['why'][:2])})." for r in rec), "recommendations", {"actions": rec}, ["recommendation engine"], event)

    if n:
        c = _get_cell(db, event, n)
        if c:
            return _resp(f"Cell {n:02d}: {c.priority_level}, score {c.priority_score:.2f}, severity {c.severity:.0%}, {c.population_exposed:,} exposed, road {c.road_status.replace('_', ' ')}, confidence {c.confidence:.0%}. {c.recommended_action}", "cell", {"cell_no": n}, ["digital twin"], event)
    return _resp(NO_DATA, "unknown", event=event)
