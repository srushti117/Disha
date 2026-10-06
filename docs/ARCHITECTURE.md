# Architecture

## Intelligence loop
```
TRIGGER → ACQUIRE → PREPARE → DETECT → ASSESS → PRIORITISE → PREDICT → PLAN   (automatic job)
                                                                    ↓
                              DISPATCH (operator) → VERIFY (field) → recompute → … (LEARN: labels exported)
```
The pipeline UI (`ProcessingJob.steps`) shows all 10 steps; DISPATCH and VERIFY are derived from DB state (dispatched assignments, field reports) because they are human actions.

## Components
```
Browser (Next.js 14, React, TS, Tailwind, MapLibre GL + deck.gl, Chart.js)
   │ REST/JSON + JWT           (rasters as PNG via ?access_token for <img>/BitmapLayer)
FastAPI  ─ routers/  auth · events · response(routes, shelters, resources) · field · admin
   │       services/ pipeline · twin · response · summary · copilot · field · exports · reports · events · common
   │       engines/  pure algorithms (no DB):  geo · sensors · change_detection · hazards · priority · vulnerability · fusion
   │                 roads · routing · cascade · evacuation · resources · prediction · escalation · alerts · field_cv · evaluation
   │       demo/     world.py (procedural simulator) · scenarios.py
   │       live/     net · imagery (Sentinel-1/2, DEM, WorldCover) · osm · population · weather · real_world  -> same `World` contract as the simulator
SQLAlchemy 2 ── PostgreSQL 16 + PostGIS 3.4 (GiST indexes)   |   SQLite fallback (GeoJSON text)  ← same models
data/events/<id>/rasters.npz · photos/      (S3-compatible storage adapter is the intended production target)
```

### Layering rule
`engines/*` take plain arrays/dicts and return plain results, so every algorithm is unit-tested without a database. `services/*` load DB rows, call engines, persist. `routers/*` do HTTP, validation and RBAC only.

## Digital twin
`H3Cell` is the live state of one hexagon (hazard, population, vulnerability, infrastructure, roads, cascade, priority, confidence, provenance). Detection-derived values are stored once in `components.base`; **`services/twin.recompute()`** re-derives the effective state from `base` + the latest field report per cell, recomputes priority for every cell, writes a versioned `PriorityResult` snapshot, diffs against the previous version (escalations), raises alerts, and refreshes predictions. It runs after analysis, a new satellite pass, a field report, or a weight/threshold change. Because it always restarts from `base`, field effects are reversible and auditable.

## Detection
`ChangeDetectionEngine` → detectors: `RuleBasedDetector` (default) → `hazards.py` per-hazard rule modules; `RandomForestDetector` (trainable); `SiameseUNetDetector` / `ChangeFormerDetector` (ONNX contract). If a detector is unavailable the engine falls back to rule-based **and records the reason in the result** (surfaced in the UI/API).

## Priority engine
`PI = wS·S + wE·E + wC·C + wA·A` (defaults 0.35/0.30/0.20/0.15, normalised).
* **S** = cell severity × detection confidence (cell severity = mean pixel severity of affected pixels × `min(1, hazard_fraction/0.4)^0.6`)
* **E** = 0.75 × exposed population ÷ event reference (95th percentile, floor 300 people) + 0.25 × vulnerability × min(1, exposed/200)
* **C** = facility weights (hospital .6, power .4, water .35, school .3, emergency .3, bridge .25, comm .2, shelter .2) in cell + ½ neighbours, scaled by hazard proximity, + 0.35 × cascade risk
* **A** = access loss from road status/isolation analysis
* Levels: P1 ≥ 0.48, P2 ≥ 0.34, P3 ≥ 0.20 (configurable per event). Hazard-only cells (no people, no assets) are capped at P3 and say so.
Output carries components, weighted contributions (sum = score), reason codes, top factors, recommended action, and a fused multi-source confidence.

## Sensor switching
Cloud < 30 % → SAR+OPTICAL; ≥ 30 % → SAR-FIRST (optical weight `0.4·(1-cloud)` on cloud-free pixels only); optical unavailable → SAR-ONLY; SAR unavailable → OPTICAL-ONLY. Wildfire/landslide lead with optical when cloud allows. The explanation string is stored and shown.

## Roads, routing, cascade
Road segments are intersected with the hazard mask (samples every 60 m): blocked ≥ 30 % flooded (bridges ≥ 15 %), potentially blocked ≥ 5 % or adjacent, unknown where SAR quality is poor. Reachability from response bases (blocked edges removed) yields isolated cells. Routing (NetworkX) returns shortest (may be blocked, flagged), fastest and safest (blocked edges excluded, risk-weighted); the recommendation minimises `ETA·(1+2·risk)`. Cascade chains: facility → depends-on substation → hospital; bridge blocked → newly unreachable nodes → isolation → rescue delay.

## Prediction
`disha-risk-propagation v0.1`: logistic model over neighbour-ring hazard fraction, terrain lowness, forecast rainfall, river trend, persistence (+ slope/wind per hazard), producing expansion probability and a re-scored predicted level. **Hand-set coefficients, not trained or validated.** Confidence decays 1.2 %/h; everything is labelled ESTIMATE.

## Security
JWT (HS256) bearer tokens; PBKDF2-SHA256 password hashing (120k iterations); RBAC via `require(permission)` on every route (matrix in `core/security.py`, served at `/api/permissions`); pydantic validation; upload type/size limits; audit log for state-changing actions; secrets only from environment (`.env.example`). `?access_token=` is accepted for image/download URLs only because browsers cannot attach headers to `<img>`.

## Background jobs - current state vs. target
Implemented: FastAPI `BackgroundTasks` (thread pool) with a persisted `processing_jobs` row and step-level progress polled by the UI. **Not implemented:** an external queue. Redis is provisioned in `docker-compose.yml` for that purpose; moving `pipeline.run_analysis` to Celery/RQ is a small change because it already takes only ids and opens its own DB session.

## Real vs simulated inputs
`pipeline.get_world()` returns a `World` from either `demo.world.build_world` (simulated) or `live.real_world.build_live_world` (real open data). All engines consume only the `World`/arrays, so they are identical for both; the world carries `is_real`, `demographics_available`, `optical_available`, per-source `provenance`, and real satellite pass records. See [LIVE_DATA.md](LIVE_DATA.md).

## Known limitations
* Detection accuracy on real imagery is unvalidated (no ground truth bundled).
* Single-process job execution; no horizontal scaling of analysis yet.
* Raster layers are served as PNG; production should serve COG tiles via a tiler (e.g. TiTiler).
* Population "buildings", demographics and housing vulnerability are demo estimates.
* Real-data road graphs keep curved geometry; simulated ones use straight segments. Road status is judged from the hazard mask only (no traffic or closure feed).
