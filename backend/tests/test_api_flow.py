"""End-to-end: create event -> process -> priorities -> map -> cell -> route -> resources -> field -> recalculation -> report."""
from .conftest import login


def test_health_and_auth(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/events").status_code == 401
    assert client.post("/api/auth/login", json={"email": "commander@disha.demo", "password": "wrong"}).status_code == 401


def test_rbac(client, analysed_event):
    obs, resp = login(client, "observer"), login(client, "responder")
    assert client.get(f"/api/events/{analysed_event}", headers=obs).status_code == 200
    assert client.post(f"/api/events/{analysed_event}/process", headers=obs).status_code == 403
    assert client.post("/api/events", json={"aoi_method": "demo", "scenario_key": "kerala_flood_2018"}, headers=resp).status_code == 403
    assert client.post(f"/api/events/{analysed_event}/resources/optimise", json={}, headers=resp).status_code == 403


def test_pipeline_outputs(client, commander, analysed_event):
    st = client.get(f"/api/events/{analysed_event}/status", headers=commander).json()
    keys = [s["key"] for s in st["steps"]]
    assert keys == ["TRIGGER", "ACQUIRE", "PREPARE", "DETECT", "ASSESS", "PRIORITISE", "PREDICT", "PLAN", "DISPATCH", "VERIFY"]
    assert all(s["status"] == "done" for s in st["steps"][:8])
    det = client.get(f"/api/events/{analysed_event}/detections", headers=commander).json()
    d = det["detections"][0]
    assert d["sensor_mode"] == "SAR-FIRST" and "downgraded" in d["sensor_explanation"]
    assert d["model_name"] and d["model_version"] and d["simulated_input"] is True
    p = client.get(f"/api/events/{analysed_event}/priorities", headers=commander).json()
    assert sum(p["counts"].values()) == len(client.get(f"/api/events/{analysed_event}/map", headers=commander).json()["cells"]["features"])
    assert p["counts"]["P1"] > 0 and p["counts"]["P2"] > 0
    top = p["cells"][0]
    assert top["level"] == "P1" and top["reason_codes"]


def test_cell_why_and_explainability(client, commander, analysed_event):
    top = client.get(f"/api/events/{analysed_event}/priorities?level=P1", headers=commander).json()["cells"][0]
    c = client.get(f"/api/events/{analysed_event}/cells/{top['h3_index']}", headers=commander).json()
    assert set(c["priority"]["components"]) == {"severity", "exposure", "infrastructure", "accessibility"}
    assert len(c["why"]["top_factors"]) >= 2
    assert c["confidence"]["sources"] and c["predictions"] and all(p["label"] == "ESTIMATE" for p in c["predictions"])
    assert abs(sum(c["priority"]["contributions"].values()) - c["priority"]["score"]) < 1e-3


def test_map_time_machine(client, commander, analysed_event):
    now = client.get(f"/api/events/{analysed_event}/map?t=0", headers=commander).json()
    before = client.get(f"/api/events/{analysed_event}/map?t=-1", headers=commander).json()
    f6 = client.get(f"/api/events/{analysed_event}/map?t=6", headers=commander).json()
    assert before["counts"]["P1"] == 0
    assert f6["counts"]["P1"] >= now["counts"]["P1"]
    assert client.get(f"/api/events/{analysed_event}/map?t=7", headers=commander).status_code == 422


def test_route_resource_shelter(client, commander, analysed_event):
    top = client.get(f"/api/events/{analysed_event}/priorities?level=P1", headers=commander).json()["cells"][0]
    r = client.post(f"/api/events/{analysed_event}/routes", json={"h3_index": top["h3_index"]}, headers=commander).json()
    assert {x["kind"] for x in r["routes"]} == {"shortest", "fastest", "safest"}
    rec = [x for x in r["routes"] if x["recommended"]]
    assert len(rec) <= 1 and (not rec or rec[0]["blocked_segments"] == 0)
    sim = client.post(f"/api/events/{analysed_event}/resources/simulate", json={"counts": {"rescue_team": 1, "boat": 0, "ambulance": 0}}, headers=commander).json()
    full = client.post(f"/api/events/{analysed_event}/resources/simulate", json={"counts": {"rescue_team": 20, "boat": 10, "ambulance": 10}}, headers=commander).json()
    assert full["metrics"]["p1_coverage_pct"] >= sim["metrics"]["p1_coverage_pct"]
    opt = client.post(f"/api/events/{analysed_event}/resources/optimise", json={"commit": True}, headers=commander).json()
    assert opt["assignments"] and all(a["reason"] for a in opt["assignments"])
    d = client.post(f"/api/events/{analysed_event}/resources/dispatch", json={}, headers=commander)
    assert d.status_code == 200 and d.json()["dispatched"] > 0
    sh = client.get(f"/api/events/{analysed_event}/shelters", headers=commander).json()
    assert sh["summary"]["people_assigned"] <= sh["summary"]["people_needing_shelter"]
    cap = {s["id"]: s["capacity"] - s["occupied"] for s in sh["shelters"]}
    used = {}
    for a in sh["assignments"]:
        used[a["shelter_id"]] = used.get(a["shelter_id"], 0) + a["people"]
    assert all(used[k] <= cap[k] for k in used)


def test_field_loop_recalculates(client, commander, analysed_event):
    rs = login(client, "responder")
    ms = client.get(f"/api/events/{analysed_event}/missions", headers=rs).json()
    assert ms and ms[0]["label"].startswith("MISSION #")
    p = client.get(f"/api/events/{analysed_event}/priorities?level=P1", headers=commander).json()["cells"]
    target = p[-1]
    r = client.post(f"/api/events/{analysed_event}/field-reports/simulate", json={"h3_index": target["h3_index"], "verdict": "false_alarm"}, headers=rs)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["field_verified"] and out["before"]["level"] == "P1" and out["after"]["level"] != "P1"
    assert out["photo_analysis"] and "disclaimer" in out["photo_analysis"][0]
    wc = client.get(f"/api/events/{analysed_event}/what-changed", headers=commander).json()
    assert wc["available"] and wc["delta"]["p1"] <= -1
    pool = client.get(f"/api/events/{analysed_event}/priorities?level=P3,P4", headers=commander).json()["cells"]
    low = next(c for c in pool if c["population_exposed"] >= 50 and c["level"] in ("P3", "P4"))
    r2 = client.post(f"/api/events/{analysed_event}/field-reports/simulate", json={"h3_index": low["h3_index"], "verdict": "severe"}, headers=rs).json()
    assert r2["after"]["score"] > r2["before"]["score"]
    al = client.get(f"/api/events/{analysed_event}/alerts", headers=commander).json()
    assert any(a["trigger"] in ("escalation", "field_severe") for a in al["alerts"])
    assert all(n["status"] == "MOCK_SENT" for n in al["notifications"])


def test_copilot_grounded(client, commander, analysed_event):
    def ask(q):
        return client.post(f"/api/events/{analysed_event}/copilot", json={"question": q}, headers=commander).json()

    a = ask("Which areas should we rescue first?")
    assert a["intent"] == "priorities" and "P1" in a["answer"]
    top = client.get(f"/api/events/{analysed_event}/priorities", headers=commander).json()["cells"][0]["cell_no"]
    assert f"Cell {top:02d}" in ask(f"Why is cell {top} P1?")["answer"]
    assert ask("How many people are currently at high risk?")["intent"] == "population"
    assert ask(f"Give me the safest route to cell {top}")["intent"] == "route"
    assert "does not currently have sufficient data" in ask("What is the capital of France?")["answer"]


def test_report_exports_timeline(client, commander, analysed_event):
    pdf = client.get(f"/api/events/{analysed_event}/report", headers=commander)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 5000
    gj = client.get(f"/api/events/{analysed_event}/export?format=geojson", headers=commander).json()
    assert gj["metadata"]["model"] and gj["features"][0]["properties"]["priority_level"]
    assert b"<kml" in client.get(f"/api/events/{analysed_event}/export?format=kml", headers=commander).content
    assert client.get(f"/api/events/{analysed_event}/export?format=csv", headers=commander).text.startswith("# event")
    cog = client.get(f"/api/events/{analysed_event}/export?format=cog", headers=commander)
    assert cog.status_code == 200 and cog.content[:2] in (b"II", b"MM")
    tl = client.get(f"/api/events/{analysed_event}/timeline", headers=commander).json()
    assert any(t["kind"] == "alert" for t in tl) and any(t["kind"] == "field" for t in tl)
    aud = client.get("/api/admin/audit", headers=commander).json()
    assert any(a["what"] == "resource.assign" for a in aud)
    png = client.get(f"/api/events/{analysed_event}/layers/hazard.png", headers=commander)
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"


def test_aoi_methods_and_validation(client, commander):
    ok = client.post("/api/events", json={"hazard": "flood", "aoi_method": "coordinates", "aoi": {"west": 76.2, "south": 10.2, "east": 76.3, "north": 10.3}}, headers=commander)
    assert ok.status_code == 201
    big = client.post("/api/events", json={"hazard": "flood", "aoi_method": "coordinates", "aoi": {"west": 70, "south": 10, "east": 80, "north": 20}}, headers=commander)
    assert big.status_code == 422 and "too large" in big.text
    gj = {"type": "Polygon", "coordinates": [[[76.2, 10.2], [76.3, 10.2], [76.3, 10.3], [76.2, 10.3], [76.2, 10.2]]]}
    assert client.post("/api/events", json={"hazard": "wildfire", "aoi_method": "upload", "aoi": {"geojson": gj}}, headers=commander).status_code == 201
    assert client.post("/api/events", json={"hazard": "flood", "aoi_method": "admin", "aoi": {"admin_id": "nope"}}, headers=commander).status_code == 422
    assert client.post("/api/events", json={"hazard": "tornado", "aoi_method": "demo", "scenario_key": None}, headers=commander).status_code == 422


def test_evaluation_honesty(client, commander, analysed_event):
    ev = client.get(f"/api/events/{analysed_event}/evaluation", headers=commander).json()
    assert ev["available"] is False and "unavailable for synthetic demonstration data" in ev["message"]
