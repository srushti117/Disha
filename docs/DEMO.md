# Demo guide

Everything shown is **simulated** (labelled DEMONSTRATION DATA in UI, API, exports, PDF). Detection, impact, priority, routing and allocation run for real on the simulated inputs.

## Scenarios (`GET /api/scenarios`)
| Key | Hazard | What it shows |
|---|---|---|
| `kerala_flood_2018` | flood | Monsoon river flood, 78 % cloud → **SAR-FIRST**; blocked bridges isolate communities; hospital + substation cascade |
| `wayanad_landslide_2024` | landslide | Steep-slope scar + debris run-out onto a valley settlement; 86 % cloud → SAR-driven, low-confidence debris |
| `urban_flood_synthetic` | flood | Dense city pluvial flooding; flooded built-up brightens SAR so detection is deliberately weaker |
| `wildfire_demo` | wildfire | dNBR burn scar + VIIRS-style hotspots; 22 % cloud → **SAR+OPTICAL**; hazard-only forest is not ranked P1 |
| `cyclone_demo` | cyclone | Vegetation + roof damage swath and coastal surge; 95 % cloud → SAR-only |

Counts differ by scenario and are computed, not scripted (Kerala currently ≈ P1 17 · P2 24 · P3 25 · P4 124).

## One-click: ▶ RUN DISHA DEMO (≈ 40 s)
Command Centre → **Run DISHA demo** → **Start demo**. Narrated steps: Alert → Acquire (simulated) → Prepare → Detect → Assess → Prioritise (with *Why P1?*) → Predict (estimate) → Plan route → Optimise + dispatch resources → Field report (simulated) → recalculated priority. Ends with links to the map, report and presentation mode.

## 5-minute story (manual)
1. **Command Centre** - flood alert banner on a new Kerala event.
2. Events → Kerala quick-start → **Analyse event** (pipeline steps stream live, ~13 s with demo pacing).
3. **Map** - satellite (simulated SAR) + hazard layer; P1/P2/P3/P4 counts in the header.
4. Click a P1 cell → **Why is this P1?**: component bars, top factors, population, hospital, road, confidence, source freshness.
5. **Predict next 6 h** (jumps the time machine; ESTIMATE labels, probabilities).
6. **Find safest route** - Route A/B/C comparison; blocked shortest route flagged, recommended open route drawn.
7. **Optimise resources** - assignments with reasons (Rescue Team / Boat / Ambulance). Resources page: *what-if* simulation (coverage %, unserved P1, delay).
8. **Field** page (as `responder@disha.demo`: missions, accept, report, photo upload; or commander: *Simulate a field report*).
9. **FIELD VERIFIED** → priority recalculated (e.g. P2 → P1, or P1 → resolved); **Timeline** and **What changed?** show it; alerts show `CELL NN ESCALATED FROM P2 TO P1`.
10. **Reports** → situation report PDF, GeoJSON/KML/CSV/COG.
11. Optional: **New satellite pass** (hazard progressed; escalations computed against v1), **Copilot** questions.

## Presentation mode
Event → **Presentation** (or `/events/{id}/present`): projector layout, nine big step buttons (Trigger event · Run analysis · Show detected change · Show priority · Show prediction · Show route · Allocate resources · Simulate field report · Recalculate), narration box, live P-counts, `LIVE DISHA DEMONSTRATION` banner.

## Copilot examples
"Which areas should we rescue first?" · "Why is cell 7 P1?" · "Give me the safest route to cell 12" · "How many people are currently at high risk?" · "Which hospital is most at risk?" · "What changed since the previous assessment?" · "What should I do next?" - and "What is the capital of France?" returns the *insufficient data* sentence.

## Roles to try
`commander` (everything operational) · `analyst` (data/AI, no dispatch) · `responder` (missions, routes, field reports) · `observer` (read-only) · `admin`.
