# DISHA 2.0

[![CI](https://github.com/srushti117/Disha/actions/workflows/ci.yml/badge.svg)](https://github.com/srushti117/Disha/actions/workflows/ci.yml)

**Disaster Intelligence, Situational Hazard Assessment & Response Orchestration**
*From Satellite Pixels to Life-Saving Decisions. Detect. Predict. Prioritise. Respond.*

DISHA turns pre/post-event satellite change into a ranked, explainable, actionable response plan:

```
DETECT → UNDERSTAND → PREDICT → PRIORITISE → PLAN → DISPATCH → VERIFY → LEARN
```

It answers: **where should responders go first, what should they do, with which resources, by which route, and why?**
Built on the Round 1 DISHA proposal (SAR-first change detection, 500 m H3 cells, `PI = 0.35·S + 0.30·E + 0.20·C + 0.15·A`, P1–P4, confidence + reason codes, field feedback), extended into a decision-support platform.

> ## Read this first - what is real and what is not
> DISHA runs in two modes, always labelled on screen, in the API, exports and the PDF:
> * **Real data** events retrieve actual Sentinel-1/2 imagery, Copernicus DEM, ESA WorldCover, WorldPop population, OpenStreetMap roads/facilities and Open-Meteo rainfall (see [docs/LIVE_DATA.md](docs/LIVE_DATA.md)). Population is a *modelled estimate*, shelter capacities and the response-unit roster are *assumptions*, children/elderly vulnerability is *unavailable* (skipped, not invented), and detection has **not been validated** against ground truth.
> * **Simulated** events generate synthetic rasters and facilities for a self-contained demonstration (`DEMONSTRATION DATA`). The algorithms run for real on them, but nothing represents a real place's facilities or people.
>
> Evaluation metrics are never invented. AI output is decision support, not an authority. This is a prototype, not an operational emergency system.

## Quick start

### Option A - Docker (PostgreSQL + PostGIS)
```bash
cp .env.example .env          # set JWT_SECRET and POSTGRES_PASSWORD
docker compose up --build
# UI  http://localhost:3000      API docs  http://localhost:8000/docs
```

### Option B - local, no Docker (SQLite)
```powershell
./start-dev.ps1               # creates venv, installs deps, starts API :8000 and UI :3000
```
Manual: `cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/uvicorn app.main:app --port 8000` and `cd frontend && npm install && npm run dev`.

### Demo accounts (**DEMO ONLY** - password `Disha@2026`)
`commander@disha.demo` · `analyst@disha.demo` · `responder@disha.demo` · `observer@disha.demo` · `admin@disha.demo`
Disable with `SEED_DEMO_ACCOUNTS=false` for any real deployment.

### Real data (needs internet)
Events → **Kerala floods 2018 - Kuttanad (real data)** → **Analyse event**. First run downloads and caches the datasets (1-3 min); then open **Map** and switch on *Sentinel-2 true colour*.

### 60-second simulated demo
Sign in as commander → **Command Centre → ▶ Run DISHA demo → Start demo**. It creates the Kerala Flood Demo and runs the whole loop (alert → acquisition → detection → impact → priority → prediction → route → resources → field verification → recalculated priority) in ~40 s. Then open **Map**, click a cell for *Why P1?*, drag the **time machine**, or open **Presentation mode**. See [docs/DEMO.md](docs/DEMO.md).

## What is implemented

| Area | Status |
|---|---|
| Events, 5 AOI methods (draw, coordinates, admin area, demo, GeoJSON upload), archive | **Built + tested** |
| Flood module: SAR log-ratio + Otsu, terrain/permanent-water masks, NDWI confirmation, severity, confidence | **Built + tested** (on simulated rasters) |
| Wildfire (dNBR + VIIRS-style hotspots), landslide (dNDVI + slope + SAR), cyclone (SAR + vegetation + roof proxy + surge) | **Built + tested** (simulated inputs; prototypes) |
| Sensor-switching engine with explanation | **Built + tested** |
| Pluggable `ChangeDetectionEngine` (Rule-based, Random Forest) | **Built + tested** |
| Siamese U-Net / ChangeFormer | **Adapter only** - ONNX contract + automatic, reported fallback; no weights bundled |
| H3 digital twin, impact, population, vulnerability (configurable weights), infrastructure, cascade engine, roads, isolation | **Built + tested** |
| Priority engine (PI, P1–P4, reason codes, Why-P1, uncertainty labels, multi-source confidence, freshness) | **Built + tested** |
| Prediction +6/12/24/48 h | **Built, heuristic** - hand-set coefficients, not validated; always labelled ESTIMATE |
| Time machine, escalation engine, what-changed, new satellite pass (continuous reassessment) | **Built + tested** |
| Route optimiser (shortest/fastest/safest), evacuation planner, resource allocation + what-if simulation | **Built + tested** |
| Field mode, missions, photo analysis, feedback loop that recalculates priority, training-label export | **Built + tested**; photo analysis is **colour/texture heuristics, not a trained CV model** |
| DISHA Copilot | **Built** - retrieval-grounded intent router over DB values; **not an LLM**; refuses when data is absent |
| Alerts (8 triggers) + Email/SMS/WhatsApp abstraction | **Built**; providers are **mock** (recorded `MOCK_SENT`); no real sending |
| PDF situation report, GeoJSON, KML, CSV, COG exports | **Built + tested** |
| JWT auth, 5 roles + permission matrix, audit log | **Built + tested** |
| Presentation mode, RUN DISHA DEMO | **Built + browser-tested** |
| Real-data mode: Sentinel-1/2, Copernicus DEM, WorldCover, WorldPop, OSM, Open-Meteo | **Built + tested** (offline tests, plus a real-services test); 3 real scenarios incl. Kerala 2018 and Sindh 2022 floods |
| NASA FIRMS hotspots | **Optional** - needs a free `FIRMS_MAP_KEY`; not exercised |
| Background jobs | In-process (FastAPI background tasks + `processing_jobs` table). Redis/worker are provisioned in compose but **not yet used**; see ARCHITECTURE |

## Verification performed
* `pytest` - **52 tests pass on SQLite** (+1 opt-in real-services test, also passed); the earlier 45 also passed on **PostgreSQL 16 + PostGIS 3.4** (not re-run after the real-data work).
* `next build` - type-checked production build.
* **GitHub Actions CI** (on every push/PR): backend tests on SQLite and on a PostGIS service container, frontend type-check + build, the headless-browser end-to-end test (system Chrome), and Docker image builds. `docker compose up` itself has not been run.
* Browser E2E (`e2e/`, headless Edge): login → full demo loop → map render → cell click → route → time machine → all 17 pages → Copilot → RBAC; **0 console errors**.

Run them: `cd backend && .venv/Scripts/python -m pytest tests -q` · `cd e2e && npm i && node run.mjs` (stack running).

## Documentation
[LIVE_DATA](docs/LIVE_DATA.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [API](docs/API.md) · [DATABASE](docs/DATABASE.md) · [ML](docs/ML.md) · [DEMO](docs/DEMO.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) · [Implementation plan & status ledger](DISHA_IMPLEMENTATION_PLAN.md)

## Repository layout
```
backend/   FastAPI app (app/engines pure algorithms, app/services orchestration, app/routers HTTP, app/demo simulators) + tests
frontend/  Next.js 14 · TypeScript · Tailwind · MapLibre GL · deck.gl · Chart.js
e2e/       Playwright (system Edge/Chrome) browser test
docs/      architecture, API, database, ML, demo, deployment
data/      runtime rasters, photos, SQLite file (git-ignored)   models/  model metadata (+ any trained weights)
```
