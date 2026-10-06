# DISHA 2.0 — Implementation Plan

> Status key used throughout the project: **BUILT** = exists and was run/tested; **PARTIAL** = works with stated limits; **ADAPTER** = interface + fallback only (no weights/data bundled); **PLANNED** = not started.
> This file is updated at the end of every phase. See "Status Ledger" at the bottom for the honest current state.

## 1. Current Architecture (repository inspection)

| Item | Finding |
|---|---|
| Repository | Empty greenfield folder, not a git repo |
| Only existing asset | `TECHFEST-2026-27-Round1-DISHA-11slides-v2.pptx` — the Round 1 proposal |
| Existing code / DB / components | None |
| Toolchain on machine | Node 24, npm 11, Python 3.12, Docker 29 |

**Reusable from the Round 1 deck (preserved as the foundation):**
hazard signals (flood = SAR VV drop + ΔMNDWI; cyclone = coherence loss + ΔNDVI; landslide = ΔNDVI + slope; wildfire = dNBR + VIIRS), pipeline (Trigger → Acquire → Prepare → Detect → Prioritise → Deliver), `PI = 0.35·S + 0.30·E + 0.20·C + 0.15·A` on 500 m H3 cells, P1–P4 semantics, SAR-first/optical-enhanced fusion, confidence + reason codes, GeoJSON/KML/PDF outputs, field-verified feedback loop, Kerala 2018 and Wayanad 2024 demos.

## 2. Target Architecture

```
Next.js (TS, Tailwind, MapLibre + deck.gl, Chart.js)
        │  REST + JWT
FastAPI ── routers ── services/pipeline (background job, progress)
        │                │
        │        engines/  sensors · change_detection (Rule/RF/Siamese/ChangeFormer)
        │                  hazards (flood/fire/landslide/cyclone) · grid(H3) · impact
        │                  vulnerability · cascade · priority · prediction · escalation
        │                  roads · routing · evacuation · resources · fusion · uncertainty
        │                  copilot · recommendations · alerts · field · reports · exports
        │
PostgreSQL+PostGIS (prod)  /  SQLite (zero-setup local + tests)   Redis (queue/cache, optional)
data/ (rasters, photos, exports)  ← S3-compatible via storage abstraction
```

Digital Twin = per-event `H3Cell` rows (live state) + versioned `PriorityResult`/`Prediction` snapshots. Every re-assessment (new satellite pass, field report, resource change) bumps `event.assessment_version`, diffs against the previous version and raises escalation alerts.

## 3. Gap Analysis
Everything is a gap (greenfield). Highest-risk gaps: real Sentinel acquisition (needs credentials/network), real OSM/WorldPop ingestion, trained deep-learning weights. These are handled with **provider interfaces + clearly-labelled simulated providers** (spec §52, §81).

## 4. Database Changes
All 25 required tables (+ `Mission`, `Notification`-channel config). PostGIS `Geometry` columns via GeoAlchemy2 on PostgreSQL; the same models fall back to GeoJSON-text columns on SQLite so the project runs without Docker. GiST indexes on all geometry columns; composite indexes `(event_id, h3_index)`. H3 resolution configurable per event (default 8 ≈ 460 m edge).

## 5. API Changes
Auth, events CRUD/archive, process/status, map (GeoJSON + raster layers), detections, priorities (+why), predictions, resources (+simulate/optimise), routes, shelters (evacuation), field-reports (+photo), timeline, alerts, copilot, report (PDF), export (GeoJSON/KML/CSV/COG), what-changed, recommendations, evaluation, data-health, models, admin/audit. JWT + role dependency on every route.

## 6. Frontend Changes
All 20 pages from spec §60 under a mission-control layout (dense panels, P1–P4 colour language, dark map). Shared: `MapView`, `CellPanel` (Why-P1), `PipelineStepper`, `ConfidenceBadge`, `LayerToggle`, `Provenance` chip, `PresentationMode`.

## 7. AI/ML Changes
`ChangeDetectionEngine` abstraction. **BUILT:** RuleBasedDetector (SAR log-ratio + Otsu + adaptive threshold + terrain/permanent-water masks + optical index confirmation). **ADAPTER:** RandomForestDetector (trainable, no bundled weights), SiameseUNetDetector and ChangeFormerDetector (pluggable ONNX/PyTorch hook; report `unavailable` and the engine falls back to rule-based, never silently). Model registry stores name/version/dataset/accuracy(null when unknown)/hazard.

## 8. GIS Changes
H3 gridding, raster→cell zonal aggregation, road graph (NetworkX) with hazard intersection, connectivity-based isolation, risk-weighted routing, shelter assignment, equirectangular local pixel↔lon/lat transform, optional rasterio COG export.

## 9. Data Sources
| Source | Mode in this build |
|---|---|
| Sentinel-1/2, VIIRS, DEM, WorldPop, OSM, weather | **Simulated providers** (procedural rasters/features placed over the real AOI) labelled `DEMO / SIMULATED DATA`. Provider interfaces + env vars ready for live CDSE/Earth Engine/OSM. |
| Field reports/photos | Real user input |

## 10. Demo Data
Five procedural scenarios (Kerala 2018 flood, Wayanad 2024 landslide, synthetic urban flood, wildfire, cyclone). Raster physics (speckle, permanent water, clouds, false change) is simulated; **detection runs on those rasters for real**. Facility names are generic placeholders, not real facilities. Evaluation metrics are not reported for synthetic data.

## 11. Testing Plan
pytest: priority engine, Otsu/log-ratio, sensor switching, H3 aggregation, routing (blocked-road avoidance), evacuation capacity, resource allocation, escalation, auth/RBAC, copilot grounding, full API flow (create → process → priorities → cell → route → report). Frontend: type-check + production build, Jest-free smoke via `next build`. E2E: scripted API flow (`scripts/e2e_smoke.py`).

## 12. Deployment Plan
`docker-compose.yml`: frontend, backend, worker (same image), postgres/postgis, redis. Env-driven config, no cloud-provider lock-in, S3-compatible storage adapter.

## 13. Timeline (build order, per spec §83)
P1 Foundation → P2 GIS → P3 Flood → P4 Impact → P5 Priority → P6 Twin → P7 Prediction → P8 Response → P9 Field → P10 Copilot → P11 Reporting → P12 Other hazards → P13 Polish/Docs/Tests. Each phase: build → run → test → fix → verify.

## 14. Risks
| Risk | Mitigation |
|---|---|
| No live satellite access | Simulated providers, honest labelling, provider interface |
| Scope size | Vertical slices; engines are pure functions with unit tests |
| Deep-learning weights unavailable | Pluggable adapters + rule-based default |
| Map tiles need internet | Core demo uses a tile-free base; online basemap is optional toggle |
| Predictions over-trusted | Always labelled estimates with probability + confidence |

## 15. Dependencies
Backend: FastAPI, SQLAlchemy 2, GeoAlchemy2, h3, shapely, numpy/scipy, networkx, pillow, reportlab, PyJWT (+ optional rasterio, geopandas, scikit-learn). Frontend: Next.js 14, React 18, Tailwind 3, maplibre-gl, deck.gl 9, chart.js.

---
## Status Ledger
_Last updated after full build + verification._

| Phase | Result |
|---|---|
| 1 Foundation (repo inspection, architecture, DB, auth, frontend/backend shells) | **Done, tested.** Docker files written, **image build not verified** (Docker VM network failure) |
| 2 GIS core (map, 5 AOI methods, H3, GeoJSON, toggleable layers) | **Done, tested** (API + browser) |
| 3 Flood intelligence (SAR log-ratio, Otsu, masks, severity, confidence) | **Done, tested on simulated rasters**; not validated on real imagery |
| 4 Impact (population, vulnerability, infrastructure, roads, cascade, isolation) | **Done, tested**; demographics/buildings are labelled demo estimates |
| 5 Priority (PI, P1-P4, reason codes, Why-P1, uncertainty) | **Done, tested** |
| 6 Digital twin (cell state, versions, timeline, comparison, what-changed, new pass) | **Done, tested** |
| 7 Prediction (+6/12/24/48 h) | **Done, heuristic/uncalibrated**, labelled ESTIMATE |
| 8 Response (routes, shelters, resources, simulation) | **Done, tested** |
| 9 Field (responder mode, photo analysis, feedback loop) | **Done, tested**; photo model is heuristic |
| 10 Copilot | **Done** as grounded retrieval/intent router, not an LLM |
| 11 Reporting (PDF, GeoJSON, KML, CSV, COG) | **Done, tested** |
| 12 Other hazards (wildfire, landslide, cyclone) | **Prototype, tested on simulated scenes** |
| 13 Polish (presentation mode, demo runner, docs, tests) | **Done**; no animations beyond status pulses |

**Verified:** 45 backend tests on SQLite and on PostgreSQL+PostGIS; production `next build`; headless-browser E2E (36 checks, 0 console errors).
**Added after review - real-data mode:** Sentinel-1/2, Copernicus DEM, WorldCover, WorldPop, OSM and Open-Meteo retrieval with caching, curved real road geometry, dasymetric population, honest labelling of assumptions; 3 real scenarios (a 4th, Wayanad, was removed because it produced a silent false negative). UI restyled to a plain light, conventional layout.
**Not done / known gaps:** validated accuracy on real events; FIRMS hotspots untested; trained DL weights (Siamese U-Net / ChangeFormer adapters only); external job queue (Redis provisioned, unused); Alembic migrations; S3 storage adapter; COG tile serving; real notification providers; docker-compose build verification; frontend unit tests (covered by browser E2E instead).
