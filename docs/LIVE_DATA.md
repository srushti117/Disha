# Real-data mode

Events can run on **real open data** instead of the simulator. Choose a scenario marked *Real data* (Events → Start from a scenario) or create an event with **Data source: Real satellite data** and a date window. Everything downstream (priority, routing, resources, field loop, reports) is identical; only the inputs change, and every source is labelled in the UI, API, exports and PDF.

## What is real
| Input | Source | Notes |
|---|---|---|
| Radar (SAR) before/after | Sentinel-1 RTC (Copernicus/ESA), Microsoft Planetary Computer STAC, anonymous | VV gamma0, terrain-corrected, resampled to ~30 m in the linear power domain. Pre/post scenes must share **orbit track and direction**; the pair closest to the requested dates is chosen. |
| Optical | Sentinel-2 L2A (same catalogue) | Cloud/shadow masked with the scene classification layer. Used for before/after NDWI/NDVI/NBR **only if both a pre- and post-event scene exist**; otherwise the post-event image is shown for context and detection is SAR-only (stated in the UI). |
| Terrain | Copernicus DEM GLO-30 | Slope masks, relative-depth proxy. |
| Land cover | ESA WorldCover 2021 | Built-up and water masks. |
| Population | WorldPop 2020 (1 km, UN-adjusted) | **Modelled estimate, not a census.** Disaggregated onto WorldCover built-up pixels (dasymetric). Needs the country's ISO3 code (auto-looked-up, or set for scenarios). The ~40 MB national file is downloaded once and cached. |
| Roads, hospitals, schools, substations, water, fire/police, places | OpenStreetMap via Overpass (ODbL) | Real names and geometry. Roads are split at intersections and keep their real curved shape; bridges come from `bridge=*` tags. Coverage depends on OSM completeness. |
| Rainfall | Open-Meteo (ERA5 reanalysis for past events, forecast for ongoing ones) | For a historical event the 24 h of rain after the satellite pass stands in for a forecast ("historical replay"). River level is not available (0). |
| Hotspots (wildfire) | NASA FIRMS VIIRS, only if `FIRMS_MAP_KEY` is set | Free key; without it wildfire events have no thermal hotspots. |

## What is assumed or missing (and how the app treats it)
* **Response resources**: no real feed exists. A *hypothetical* roster is placed at the response bases and flagged `simulated` in the data sources, the Resources page and exports.
* **Response bases**: nearest OSM fire/police stations; if absent, road nodes at AOI corners ("assumed staging point").
* **Shelter capacity**: OSM has none. Capacity is assumed by facility type (school 400, community centre 250 …) and marked as assumed; no real occupancy.
* **Hospital → substation dependency** (cascade engine): assumed, nearest substation within 8 km.
* **Children / elderly / housing vulnerability**: not available from the sources. These factors are **skipped** (weights renormalised), vulnerable-population counts are 0, and the cell panel says so. Nothing is invented.
* **Buildings**: not estimated for real data.
* **Prediction model**: unchanged hand-set heuristic, not validated.
* **Accuracy**: no ground truth is bundled, so no accuracy figures are shown. A real flood-extent reference can be registered through the evaluation endpoint to get precision/recall/IoU.

## Honest results from the scenarios included
| Scenario | Result |
|---|---|
| Kerala floods 2018 - **Kuttanad** (9 Aug vs 21 Aug 2018, descending track 165) | ~8 km² newly flooded plus ~25 km² of permanent backwater; 189 cells, P1 5 / P2 11; 140 real bridges; real facilities. |
| Kerala floods 2018 - **Chalakudy** | Only a few patches detected: the first same-track radar pass after the peak is 21 Aug, when most water had already receded. Shown on purpose as a limitation of revisit time. |
| Pakistan floods 2022 - **Sindh** | ~33 km² flooded, 266 cells, P1 9 / P2 18, 25 cells cut off by blocked roads. |
| Wayanad landslide 2024 | **Removed.** With the same-track pass available (6 Aug) and 30 m multilooked radar, the real signal was too weak (0.11 % of pixels changed by > 3 dB) and the rule detected nothing - a silent false negative for a real event. Landslides need higher resolution/coherence and optical evidence. |

Known weak spots of radar flood mapping that also apply here: flooded built-up areas and flooded forest/vegetation are under-detected; wind-roughened water and shadow can cause false alarms; the severity value is an uncalibrated intensity index, not depth.

## Operating notes
* **Needs internet** on first use of an AOI. Retrievals take ~1-3 minutes and are cached under `data/cache` (OSM JSON, WorldPop file, assembled world pickle), so repeats take seconds. Progress is shown live on the ACQUIRE step.
* Area limit 400 km² (cost grows with area). Pixel size ~30 m, capped at 512 px per side.
* Services used are free and rate-limited (Planetary Computer signing, public Overpass mirrors, Nominatim, Open-Meteo). The code retries with backoff and fails the job with a readable message rather than substituting simulated data.
* Licences: Copernicus Sentinel data (open); ESA WorldCover (CC BY 4.0); WorldPop (CC BY 4.0); OpenStreetMap contributors (ODbL - attribution shown on the online basemap); Open-Meteo (CC BY 4.0, non-commercial free tier). Check terms before commercial use.
* "New satellite pass" is a simulation feature and is refused for real events; create a new event with a later post-event window instead.
* Tests: offline tests cover OSM graph building, dasymetric conservation, polyline road classification, Sentinel-1 pairing rules, validation, and the whole live pipeline branch with the network mocked. `DISHA_LIVE_TESTS=1 pytest tests/test_live.py -k real_kuttanad` hits the real services (≈ 5 min uncached).
