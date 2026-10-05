"""
Satellite endpoints.

`GET /{norad_id}` looks up one satellite's current orbital elements by
NORAD ID (Phase 1). `GET /` lists satellites this backend has previously
fetched and cached - it is deliberately NOT a full catalog browse: real
browsing/searching across every satellite CelesTrak knows about would
need a bulk CelesTrak query and is out of scope for now (see Phase 1
limitations). Requires a database; without one there is nothing to list
(the in-memory cache fallback isn't queryable this way).

`GET /catalog` and `GET /search` exist so the frontend can offer a
"pick a satellite" experience instead of requiring a raw NORAD ID:
`/catalog` returns a short, hand-picked list of well-known satellites
(no network call - see app/data/satellite_catalog.py), and `/search`
does a live, partial, case-insensitive name search against CelesTrak.

These two are registered *before* `/{norad_id}` below so that, e.g.,
`/api/satellites/search` matches the literal `/search` route rather than
being parsed as `{norad_id}` (which would fail int conversion and return
a 422 instead of the search results).

Error handling for all routes is centralized in
app/api/error_handlers.py rather than repeated try/except blocks here -
SatelliteNotFoundError, OrbitalDataValidationError, and
CelestrakClientError are simply allowed to propagate.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_satellite_search_service, get_satellite_service
from app.data.satellite_catalog import SATELLITE_CATALOG
from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.session import get_db_session
from app.schemas.satellite import SatelliteRecord, SatelliteSearchResult
from app.services.satellite_search_service import SatelliteSearchService
from app.services.satellite_service import SatelliteService

router = APIRouter(prefix="/api/satellites", tags=["satellites"])

_SatelliteServiceDep = Depends(get_satellite_service)
_SatelliteSearchServiceDep = Depends(get_satellite_search_service)
_DbSessionDep = Depends(get_db_session)


@router.get("/catalog", response_model=List[SatelliteSearchResult])
def get_satellite_catalog() -> List[SatelliteSearchResult]:
    return [
        SatelliteSearchResult(norad_id=entry.norad_id, name=entry.name, category=entry.category)
        for entry in SATELLITE_CATALOG
    ]


@router.get("/search", response_model=List[SatelliteSearchResult])
def search_satellites(
    q: str = Query(min_length=2, max_length=64, description="Satellite name to search for"),
    limit: int = Query(default=20, ge=1, le=50),
    service: SatelliteSearchService = _SatelliteSearchServiceDep,
) -> List[SatelliteSearchResult]:
    return service.search(q, limit=limit)


@router.get("", response_model=List[SatelliteRecord])
def list_satellites(session: Session = _DbSessionDep) -> List[SatelliteRecord]:
    return SatelliteRepository(session).list_all()


@router.get("/{norad_id}", response_model=SatelliteRecord)
def get_satellite(
    norad_id: int,
    refresh: bool = Query(
        default=False, description="Bypass the cache and re-fetch from CelesTrak"
    ),
    service: SatelliteService = _SatelliteServiceDep,
) -> SatelliteRecord:
    return service.get_satellite(norad_id, force_refresh=refresh)
