from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, physicians, requests as requests_routes, schedules, shifts
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(physicians.router)
app.include_router(shifts.router)
app.include_router(requests_routes.router)
app.include_router(schedules.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
