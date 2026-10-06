# Database

PostgreSQL 16 + PostGIS 3.4 in production; SQLite (GeoJSON text columns) for zero-setup local runs and tests. The same SQLAlchemy models serve both: `core/db.py` defines `Geom(...)` as a GeoAlchemy2 `Geometry(srid=4326, spatial_index=True)` subclass on PostGIS (GiST index per geometry column; Python sees GeoJSON dicts) and a text-backed type on SQLite. Verified: full test suite passes on both; PostGIS reports `geometry_columns` with correct types/SRID and 7 GiST indexes.

Tables are created with `Base.metadata.create_all` on startup. **There are no Alembic migrations yet** - add them before any deployment that must preserve data across schema changes.

## Tables (27)
| Table | Purpose | Geometry |
|---|---|---|
| `users`, `roles` | accounts (PBKDF2 hash), 5 roles | |
| `events` | hazard, status, `h3_resolution`, `config` (world seed, priority weights/thresholds, alert config, sensor decision, road nodes, weather), `assessment_version` | |
| `aois` | area of interest + method + area | POLYGON |
| `satellite_passes` | sensor, phase, acquired_at, cloud %, `is_simulated` | |
| `processing_jobs` | job status, per-step progress | |
| `hazard_detections` | model name/version, sensor mode + explanation, area, confidence, hazard-specific outputs, thresholds | footprint (GEOMETRY) |
| `h3_cells` | **digital twin** cell state (hazard, population, vulnerability, infra, roads, cascade, priority, confidence, provenance) ; unique `(event_id,h3_index)` | POLYGON |
| `population_exposures`, `vulnerabilities` | per-cell population & vulnerability factor breakdown (flagged estimated) | |
| `infrastructure` | hospitals, schools, power, water, emergency, comm, bridges; `depends_on`, `risk`, `status` | POINT |
| `road_segments` | status (open / potentially_blocked / blocked / unknown), flooded fraction, criticality, H3 cells traversed | LINESTRING |
| `shelters` | capacity, occupied, `in_hazard_zone` | POINT |
| `resources`, `resource_assignments` | roster, status, assignments with reason + ETA | |
| `routes` | stored shortest/fastest/safest routes | LINESTRING |
| `predictions` | per cell × horizon (6/12/24/48): probability, predicted level/score, drivers, model version | |
| `priority_results` | **versioned snapshots** for every cell (score, level, components, reason codes, snapshot) - basis for escalation, comparison and time machine | |
| `missions`, `field_reports`, `field_photos` | field workflow; reports store before/after effect; photos store heuristic analysis | |
| `alerts`, `notifications` | triggers + per-channel delivery records (`MOCK_SENT` in demo) | |
| `incident_timeline` | operational log | |
| `model_versions` | name, version, hazard, dataset, accuracy (**null when unknown**), status | |
| `data_sources` | per-event provenance, quality, freshness window, `is_simulated` | |
| `audit_logs` | who / what / where / why / when | |

## Conventions
* Every event-scoped table has `event_id` (FK, `ON DELETE CASCADE`) with an index; spatial lookups use H3 index strings plus GiST on geometries.
* `H3Cell.components.base` keeps detection-derived values so field effects can be re-applied reversibly.
* Reprocessing (`/process`) clears derived tables; `/new-pass` keeps `priority_results`, alerts, resources and field reports and preserves `cell_no`.
