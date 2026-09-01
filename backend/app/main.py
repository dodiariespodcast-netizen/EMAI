from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    audit,
    auth,
    calendar_feed,
    credentials,
    physicians,
    requests as requests_routes,
    schedules,
    shifts,
    swaps,
)
from app.config import get_settings
from app.database import init_db

settings = get_settings()


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
app.include_router(swaps.router)
app.include_router(credentials.router)
app.include_router(audit.router)
app.include_router(calendar_feed.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
