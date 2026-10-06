# Deployment

## Verification status (be aware)
| Path | Status |
|---|---|
| Local, SQLite (`start-dev.ps1`) | **Verified** (tests + browser E2E) |
| Backend on PostgreSQL 16 + PostGIS 3.4 | **Verified** - 45/45 tests pass against a real PostGIS container |
| Docker images (backend + frontend) | **Verified in CI** - both images build on a clean GitHub Actions runner on every push. `docker compose up` (running the full stack) has **not** been exercised yet. |
| Cloud / Kubernetes | Not attempted; nothing is provider-specific |

## Docker (single host)
```bash
cp .env.example .env     # set JWT_SECRET (long random), POSTGRES_PASSWORD; set SEED_DEMO_ACCOUNTS=false for real use
docker compose up --build
```
Services: `db` (postgis/postgis:16-3.4), `redis` (provisioned; not yet consumed by the code), `backend` (FastAPI :8000), `frontend` (Next.js standalone :3000). The optional `worker` is not defined because jobs currently run inside the API process. `NEXT_PUBLIC_API_URL` is baked into the frontend at build time (`PUBLIC_API_URL`).

## Configuration (env)
| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | SQLite file under `data/` | `postgresql+psycopg://user:pass@host:5432/db`; PostGIS extension is created on startup (needs privilege) |
| `JWT_SECRET` | dev default | **must** be overridden outside local dev |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated |
| `SEED_DEMO_ACCOUNTS`, `DEMO_PASSWORD` | true / `Disha@2026` | demo credentials are public - disable in real deployments |
| `NOTIFY_PROVIDER` | `mock` | non-mock returns `NOT_CONFIGURED` until a real provider is implemented |
| `DATA_DIR`, `MODELS_DIR` | `./data`, `./models` | mount persistent volumes; production target is an S3-compatible store (adapter not yet written) |
| `H3_RESOLUTION`, `DEMO_STEP_DELAY` | 8, 1.6 s | per-event resolution is chosen at creation |
| `FIRMS_MAP_KEY` | unset | optional NASA FIRMS key for VIIRS hotspots (wildfire, real-data mode) |

Real-data mode needs outbound HTTPS to planetarycomputer.microsoft.com, overpass-api.de (and mirrors), data.worldpop.org, nominatim.openstreetmap.org and open-meteo.com, and persistent storage for `data/cache`.

## Hardening checklist before any real use
1. Replace `JWT_SECRET`; disable demo accounts; set strong DB password; terminate TLS in front (reverse proxy).
2. Add Alembic migrations (currently `create_all`).
3. Add rate limiting and token refresh/revocation; shorten `ACCESS_TOKEN_MINUTES` (default 12 h for demos).
4. Move job execution to a real queue (Celery/RQ on the provisioned Redis); run multiple API replicas.
5. Real-data mode already uses open sources; for operations add authoritative feeds (national flood/rainfall agencies, real shelter and resource registries, census-grade population) and re-validate detection on labelled events.
6. Serve rasters as COG tiles via a tiler instead of PNG overlays.
7. Implement real notification providers (SMTP, Twilio SMS/WhatsApp) with delivery receipts.
8. Review `?access_token=` query auth for images/downloads (switch to short-lived signed URLs).

## Running tests
```bash
cd backend && python -m pytest tests -q                                   # SQLite
DISHA_TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost:5432/db python -m pytest tests -q   # PostGIS
cd e2e && npm install && node run.mjs        # needs frontend :3000 + backend :8000 running; uses system Edge/Chrome
```
