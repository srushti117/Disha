import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import get_settings
from .core.db import SessionLocal, init_db
from .routers import admin, auth, events, field, response
from .seed import seed_core

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("disha")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_core(db)
    log.info("DISHA API ready (demo_mode=%s, db=%s)", settings.demo_mode, settings.database_url.split(":")[0])
    yield


app = FastAPI(title="DISHA API", version="2.0.0", description="Disaster Intelligence, Situational Hazard Assessment & Response Orchestration", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Layer-Bounds", "Content-Disposition"])
for r in (auth.router, events.router, response.router, field.router, admin.router):
    app.include_router(r)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)
