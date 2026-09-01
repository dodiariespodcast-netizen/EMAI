from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import (
    assignments,
    audit,
    auth,
    calendar_feed,
    credentials,
    physicians,
    reports,
    requests as requests_routes,
    schedules,
    shifts,
    swaps,
)
from app.config import get_settings
from app.core.observability import configure_logging, install as install_observability
from app.database import engine, init_db

settings = get_settings()


configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev/trial convenience: auto-create tables against the configured
    # DATABASE_URL. Production deployments should run Alembic migrations
    # (see alembic/) as part of the release pipeline instead.
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-assisted scheduling backend for emergency medicine groups: "
        "constraint-solver-driven schedule generation with physician "
        "preferences, time-off requests, fairness tracking, and natural-"
        "language request intake."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

install_observability(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Auth is a bearer token in the Authorization header, not a cookie, so
    # we don't need (and per the CORS spec, can't combine with a wildcard
    # origin) allow_credentials.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(physicians.router)
app.include_router(shifts.router)
app.include_router(requests_routes.router)
app.include_router(schedules.router)
app.include_router(assignments.router)
app.include_router(swaps.router)
app.include_router(credentials.router)
app.include_router(reports.router)
app.include_router(audit.router)
app.include_router(calendar_feed.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Liveness: the process is up. Deliberately touches nothing else, so a
    database blip doesn't get the container killed and restarted."""
    return {"status": "ok", "app": settings.app_name, "version": app.version}


@app.get("/health/ready", tags=["health"])
def readiness() -> JSONResponse:
    """Readiness: the process can actually serve traffic, i.e. the database
    answers. This is what a load balancer should gate on."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 -- report any failure as not-ready
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": str(exc)})
    return JSONResponse(status_code=200, content={"status": "ready"})
