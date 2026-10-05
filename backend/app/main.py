"""
FastAPI application entrypoint.

By Phase 7, the app exposes: health, satellites, observers, passes, and
observations (ranking). All routers are wired here; error handling for
the domain exceptions raised by the underlying services is registered
once via `register_exception_handlers` rather than repeated in every
route (see app/api/error_handlers.py).
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import register_exception_handlers
from app.api.routes_geocoding import router as geocoding_router
from app.api.routes_health import router as health_router
from app.api.routes_observations import router as observations_router
from app.api.routes_observers import router as observers_router
from app.api.routes_passes import router as passes_router
from app.api.routes_satellites import router as satellites_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up in '%s' environment", settings.environment)
    logger.info("Allowed CORS origins: %s", settings.cors_origin_list)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Satellite Observation & Pass Prediction API",
    description=(
        "Predicts optical satellite observation opportunities from a given "
        "observer location using real orbital data and SGP4 propagation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(satellites_router)
app.include_router(geocoding_router)
app.include_router(observers_router)
app.include_router(passes_router)
app.include_router(observations_router)
