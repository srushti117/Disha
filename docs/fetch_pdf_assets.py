import json, sys, time, requests
B = "http://localhost:8000"
tok = requests.post(f"{B}/api/auth/login", json={"email": "commander@disha.demo", "password": "Disha@2026"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
evs = requests.get(f"{B}/api/events", headers=H).json()
print([(e["id"], e["name"][:40], e["data_mode"], e["assessment_version"]) for e in evs])
def ensure(key):
    for e in evs:
        if e["scenario_key"] == key and e["assessment_version"]:
            return e["id"]
    r = requests.post(f"{B}/api/events", json={"aoi_method": "demo", "scenario_key": key}, headers=H); r.raise_for_status()
    eid = r.json()["id"]; requests.post(f"{B}/api/events/{eid}/process", headers=H).raise_for_status()
    for _ in range(300):
        st = requests.get(f"{B}/api/events/{eid}/status", headers=H).json()
        if st["job"] and st["job"]["status"] in ("succeeded", "failed"): break
        time.sleep(2)
    print(key, "->", eid, st["job"]["status"], st["job"].get("error"))
    return eid
ids = {"kuttanad": ensure("kerala_kuttanad_2018"), "sindh": ensure("sindh_floods_2022"), "chalakudy": ensure("kerala_chalakudy_2018"), "sim": ensure("kerala_flood_2018")}
json.dump(ids, open("docs/pdf_assets/ids.json", "w"))
facts = {}
for name, eid in ids.items():
    k = requests.get(f"{B}/api/events/{eid}/kpis", headers=H).json()
    d = requests.get(f"{B}/api/events/{eid}/detections", headers=H).json()["detections"][0]
    facts[name] = {"id": eid, "levels": k["levels"], "people_at_risk": k["people_at_risk"], "people_exposed": k["people_exposed"], "isolated": k["people_isolated"], "roads": k["roads"],
                   "infra": k["critical_infrastructure"], "area": d["area_km2"], "mode": d["sensor_mode"], "conf": d["mean_confidence"], "perm": d["outputs"].get("permanent_water_km2"), "cells": sum(k["levels"].values()),
                   "simulated": d["simulated_input"]}
    for layer in ("sar_pre", "sar_post", "hazard", "optical", "population"):
        r = requests.get(f"{B}/api/events/{eid}/layers/{layer}.png", headers=H)
        if r.status_code == 200:
            open(f"docs/pdf_assets/{name}_{layer}.png", "wb").write(r.content)
json.dump(facts, open("docs/pdf_assets/facts.json", "w"), indent=1)
print(json.dumps(facts, indent=1)[:1800])
