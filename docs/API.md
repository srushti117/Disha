# API reference

57 endpoints. Base URL `http://localhost:8000`. Interactive docs: `/docs` (OpenAPI). All routes except `POST /api/auth/login` and `GET /api/health` require `Authorization: Bearer <JWT>` (image/download URLs also accept `?access_token=`).

Errors: JSON `{"detail": ...}` with 401 (auth), 403 (role), 404, 409 (state conflict, e.g. not analysed / job already running), 413/415 (uploads), 422 (validation).

| Method | Path | Allowed roles | Summary |
|---|---|---|---|
| GET | `/api/admin/audit` | admin, commander, analyst (`event.write`) | Audit |
| GET | `/api/admin/data-sources` | admin, analyst (`data.manage`) | Sources |
| GET | `/api/admin/users` | admin (`admin`) | Users |
| POST | `/api/auth/login` | public | Login |
| GET | `/api/auth/me` | any signed-in user | Me |
| POST | `/api/auth/users` | admin (`admin`) | Create User |
| GET | `/api/command-center` | any signed-in user | Command Center |
| GET | `/api/events` | any signed-in user | List Events |
| POST | `/api/events` | admin, commander, analyst (`event.write`) | Create Event |
| GET | `/api/events/{event_id}` | any signed-in user | Get One |
| PATCH | `/api/events/{event_id}` | admin, commander, analyst (`event.write`) | Patch |
| GET | `/api/events/{event_id}/alerts` | any signed-in user | Get Alerts |
| PUT | `/api/events/{event_id}/alerts/config` | admin, commander (`priority.configure`) | Alert Config |
| POST | `/api/events/{event_id}/alerts/{alert_id}/ack` | admin, commander (`resource.assign`) | Ack |
| POST | `/api/events/{event_id}/archive` | admin, commander, analyst (`event.write`) | Archive |
| GET | `/api/events/{event_id}/cells/{h3_index}` | any signed-in user | Cell Detail |
| POST | `/api/events/{event_id}/copilot` | any signed-in user | Ask |
| GET | `/api/events/{event_id}/data-health` | any signed-in user | Data Health |
| GET | `/api/events/{event_id}/detections` | any signed-in user | Detections |
| GET | `/api/events/{event_id}/evaluation` | any signed-in user | Evaluation |
| POST | `/api/events/{event_id}/evaluation` | admin, analyst (`data.manage`) | Register Ground Truth |
| GET | `/api/events/{event_id}/export` | admin, commander, analyst, responder, observer (`view`) | Export |
| GET | `/api/events/{event_id}/field-photos/{photo_id}` | any signed-in user | Photo |
| GET | `/api/events/{event_id}/field-reports` | any signed-in user | List Reports |
| POST | `/api/events/{event_id}/field-reports` | admin, commander, responder (`field.report`) | Submit |
| POST | `/api/events/{event_id}/field-reports/simulate` | admin, commander (`resource.assign`) | Simulate |
| GET | `/api/events/{event_id}/field-reports/training-export` | admin, analyst (`data.manage`) | Training Export |
| GET | `/api/events/{event_id}/kpis` | any signed-in user | Kpis |
| GET | `/api/events/{event_id}/layers` | any signed-in user | Layer Info |
| GET | `/api/events/{event_id}/layers/{layer}.png` | any signed-in user | Layer |
| GET | `/api/events/{event_id}/map` | any signed-in user | Map Data |
| GET | `/api/events/{event_id}/missions` | any signed-in user | Missions |
| POST | `/api/events/{event_id}/missions/{mission_id}/status` | admin, commander, responder (`field.report`) | Mission Status |
| POST | `/api/events/{event_id}/new-pass` | admin, commander, analyst (`event.process`) | New Pass |
| GET | `/api/events/{event_id}/predictions` | any signed-in user | Predictions |
| GET | `/api/events/{event_id}/priorities` | any signed-in user | Priorities |
| PUT | `/api/events/{event_id}/priorities/config` | admin, commander (`priority.configure`) | Priority Config |
| POST | `/api/events/{event_id}/process` | admin, commander, analyst (`event.process`) | Process |
| GET | `/api/events/{event_id}/recommendations` | any signed-in user | Recs |
| GET | `/api/events/{event_id}/report` | admin, commander, analyst (`report.generate`) | Report |
| GET | `/api/events/{event_id}/resources` | any signed-in user | Resources |
| POST | `/api/events/{event_id}/resources/dispatch` | admin, commander (`resource.assign`) | Dispatch |
| POST | `/api/events/{event_id}/resources/optimise` | admin, commander (`resource.assign`) | Optimise |
| POST | `/api/events/{event_id}/resources/release` | admin, commander (`resource.assign`) | Release |
| PUT | `/api/events/{event_id}/resources/roster` | admin, commander (`resource.assign`) | Set Roster |
| POST | `/api/events/{event_id}/resources/simulate` | admin, commander (`resource.assign`) | Simulate |
| GET | `/api/events/{event_id}/routes` | any signed-in user | List Routes |
| POST | `/api/events/{event_id}/routes` | admin, commander, responder (`route.plan`) | Plan Route |
| GET | `/api/events/{event_id}/shelters` | any signed-in user | Shelters |
| GET | `/api/events/{event_id}/status` | any signed-in user | Status |
| GET | `/api/events/{event_id}/summary` | any signed-in user | Exec Summary |
| GET | `/api/events/{event_id}/timeline` | any signed-in user | Get Timeline |
| GET | `/api/events/{event_id}/what-changed` | any signed-in user | What Changed |
| GET | `/api/health` | public | Health |
| GET | `/api/models` | any signed-in user | Models |
| GET | `/api/permissions` | any signed-in user | Permissions |
| GET | `/api/scenarios` | any signed-in user | Scenarios |

## Key payloads

**Process** `POST /api/events/{id}/process[?pace=true]` → `202 {job_id,status}`; poll `GET /api/events/{id}/status` → `{event, job, steps[10]}`. `POST /api/events/{id}/new-pass` simulates a later satellite pass and keeps history.

**Cell** `GET /api/events/{id}/cells/{h3}` → priority `{level,score,components,contributions,weights}`, `why{top_factors,reason_codes}`, `confidence{overall,label,detection,sources[]}`, population / vulnerability / infrastructure / roads / cascade blocks, `predictions[]` (each labelled `ESTIMATE`), `recommended_action`, `field_reports[]`.

**Routes** `POST /api/events/{id}/routes {h3_index|cell_no, origin_lat?, origin_lon?}` → `routes[]` (`shortest|fastest|safest`: `distance_km, eta_min, risk, blocked_segments, recommended, coords`), `recommended`, `summary`, `last_mile_note`.

**Resources** `POST …/resources/simulate {counts:{rescue_team:5,ambulance:3,boat:2}}` → `metrics{p1_coverage_pct, unserved_p1_count, est_response_delay_min}` (nothing dispatched). `POST …/resources/optimise {commit}` then `POST …/resources/dispatch`.

**Field** `POST …/field-reports` (multipart: `h3_index, verdict ∈ {confirmed,false_alarm,partially_affected,severe,resolved}, notes, photos[]`) → `{before, after, effect_note, photo_analysis[], escalations[]}`.

**Copilot** `POST …/copilot {question}` → `{answer, intent, data, sources, assessment_version, provenance}`; unanswerable questions return exactly `DISHA does not currently have sufficient data to determine this.`

**Export** `GET …/export?format=geojson|kml|csv|pdf|cog[&layer=severity]`; `GET …/report` (PDF).

**Time machine** `GET …/map?t=-1|0|6|12|24|48` (−1 = before event; >0 = predicted estimates).
