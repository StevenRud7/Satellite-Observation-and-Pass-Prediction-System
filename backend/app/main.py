"""
FastAPI application entrypoint.

By Phase 7, the app exposes: health, satellites, observers, passes, and
observations (ranking). All routers are wired here; error handling for
the domain exceptions raised by the underlying services is registered
once via `register_exception_handlers` rather than repeated in every
route (see app/api/error_handlers.py).
"""

import threading
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import register_exception_handlers
from app.api.routes_diagnostics import router as diagnostics_router
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


_PREWARM_INTERVAL_SECONDS = 2 * 60 * 60  # CelesTrak asks clients not to refetch more often
_prewarm_stop = threading.Event()


def _prewarm_loop() -> None:
    """Keep the orbital-data cache warm for the curated catalog.

    Runs in a background thread so startup isn't delayed. Each pass calls the
    normal `SatelliteService.get_satellite`, which does nothing for entries
    that are still fresh and otherwise refreshes them - so by the time a
    user clicks "Find best opportunities", the common satellites are already
    cached and the request never waits on CelesTrak. Failures are logged and
    retried on the next cycle; they never affect request handling.
    """
    # Imported here: deps imports the whole service graph, which isn't needed
    # unless pre-warming is actually enabled.
    from app.api.deps import (
        get_celestrak_client,
        get_satellite_cache,
        get_satellite_service,
        get_tle_api_client,
        get_tle_snapshot_client,
    )
    from app.data.satellite_catalog import SATELLITE_CATALOG

    while not _prewarm_stop.is_set():
        service = get_satellite_service(
            client=get_celestrak_client(),
            cache=get_satellite_cache(),
            snapshot=get_tle_snapshot_client(),
            tle_api=get_tle_api_client(),
        )
        for entry in SATELLITE_CATALOG:
            if _prewarm_stop.is_set():
                return
            try:
                service.get_satellite(entry.norad_id)
            except Exception as exc:  # noqa: BLE001 - background best-effort
                logger.warning("Pre-warm skipped NORAD ID %s: %s", entry.norad_id, exc)
            time.sleep(1.0)  # be polite to CelesTrak
        _prewarm_stop.wait(_PREWARM_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up in '%s' environment", settings.environment)
    logger.info("Allowed CORS origins: %s", settings.cors_origin_list)
    if settings.prewarm_enabled:
        _prewarm_stop.clear()
        threading.Thread(target=_prewarm_loop, name="orbital-data-prewarm", daemon=True).start()
        logger.info("Orbital data pre-warming enabled")
    yield
    _prewarm_stop.set()
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
app.include_router(diagnostics_router)
app.include_router(satellites_router)
app.include_router(geocoding_router)
app.include_router(observers_router)
app.include_router(passes_router)
app.include_router(observations_router)
