"""
Centralized mapping from domain exceptions to HTTP responses.

Registered once in main.py via `register_exception_handlers(app)`, so
individual route functions can simply let these exceptions propagate
rather than repeating try/except blocks in every endpoint - the earlier
`/api/satellites/{norad_id}` route (Phase 1) did its own try/except
before this existed; it's been simplified to match now that there's a
shared place for this.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.data.exceptions import (
    CelestrakClientError,
    GeocodingError,
    OrbitalDataValidationError,
    SatelliteNotFoundError,
)
from app.db.session import DatabaseNotConfiguredError
from app.services.pass_service import ObserverNotFoundError, SatelliteNotCachedError


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _handle_not_found(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(404, str(exc))


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(422, str(exc))


async def _handle_upstream_error(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(502, str(exc))


async def _handle_database_not_configured(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(
        503, f"{exc} This feature requires a database - see the README for setup."
    )


async def _handle_not_cached(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(409, str(exc))


def register_exception_handlers(app: FastAPI) -> None:
    # Registered from most to least specific; FastAPI/Starlette dispatches
    # on the exact exception type first, so a SatelliteNotFoundError (a
    # CelestrakClientError subclass) still gets its own 404 handler rather
    # than CelestrakClientError's 502 one.
    app.add_exception_handler(SatelliteNotFoundError, _handle_not_found)
    app.add_exception_handler(ObserverNotFoundError, _handle_not_found)
    app.add_exception_handler(OrbitalDataValidationError, _handle_validation_error)
    app.add_exception_handler(CelestrakClientError, _handle_upstream_error)
    app.add_exception_handler(GeocodingError, _handle_upstream_error)
    app.add_exception_handler(DatabaseNotConfiguredError, _handle_database_not_configured)
    app.add_exception_handler(SatelliteNotCachedError, _handle_not_cached)
