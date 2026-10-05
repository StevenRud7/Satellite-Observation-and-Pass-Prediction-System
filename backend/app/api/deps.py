"""
FastAPI dependency providers.

Kept in one place so routes stay thin and tests can override a single
function (`get_satellite_service`) instead of reaching into internals.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from fastapi import Depends

from app.core.config import get_settings
from app.data.cache import Cache, InMemoryTTLCache
from app.data.celestrak import CelestrakClient
from app.data.geocoding import GeocodingClient
from app.data.postgres_cache import PostgresSatelliteCache
from app.schemas.geocoding import GeocodeResult
from app.schemas.satellite import SatelliteRecord, SatelliteSearchResult
from app.services.geocoding_service import GeocodingService
from app.services.pass_service import PassService
from app.services.ranking_service import RankingService
from app.services.satellite_search_service import SatelliteSearchService
from app.services.satellite_service import SatelliteService


@lru_cache
def get_celestrak_client() -> CelestrakClient:
    """A single shared CelesTrak client (and its underlying HTTP connection pool)."""
    return CelestrakClient()


@lru_cache
def get_satellite_cache() -> Cache[SatelliteRecord]:
    """The satellite cache backing SatelliteService.

    Uses PostgreSQL when DATABASE_URL is configured (so fetched satellites
    survive process restarts and are shared across instances), and falls
    back to an in-memory cache otherwise - so local development and tests
    don't require a running database just to hit `/api/satellites`.
    Either way, `SatelliteService` is unaffected: it only depends on the
    `Cache` protocol (see app/data/cache.py and Phase 1 notes).
    """
    settings = get_settings()
    if settings.database_url:
        return PostgresSatelliteCache(ttl_seconds=settings.orbital_data_cache_ttl_seconds)
    return InMemoryTTLCache(ttl_seconds=settings.orbital_data_cache_ttl_seconds)


def get_satellite_service(
    client: CelestrakClient = Depends(get_celestrak_client),
    cache: Cache[SatelliteRecord] = Depends(get_satellite_cache),
) -> SatelliteService:
    return SatelliteService(client=client, cache=cache)


def get_pass_service(
    satellite_service: SatelliteService = Depends(get_satellite_service),
) -> PassService:
    return PassService(satellite_service=satellite_service)


def get_ranking_service(
    satellite_service: SatelliteService = Depends(get_satellite_service),
) -> RankingService:
    return RankingService(satellite_service=satellite_service)


@lru_cache
def get_satellite_search_cache() -> Cache[List[SatelliteSearchResult]]:
    """Short-lived, in-memory-only cache for CelesTrak name-search results.

    Deliberately never backed by Postgres (unlike the main satellite
    cache): these results are cheap to re-fetch, short-lived by design
    (`satellite_search_cache_ttl_seconds`), and not something we need to
    survive a restart.
    """
    settings = get_settings()
    return InMemoryTTLCache(ttl_seconds=settings.satellite_search_cache_ttl_seconds)


def get_satellite_search_service(
    client: CelestrakClient = Depends(get_celestrak_client),
    cache: Cache[List[SatelliteSearchResult]] = Depends(get_satellite_search_cache),
) -> SatelliteSearchService:
    return SatelliteSearchService(client=client, cache=cache)


@lru_cache
def get_geocoding_client() -> GeocodingClient:
    """A single shared geocoding (Nominatim) client and HTTP connection pool."""
    return GeocodingClient()


@lru_cache
def get_geocoding_cache() -> Cache[List[GeocodeResult]]:
    settings = get_settings()
    return InMemoryTTLCache(ttl_seconds=settings.geocode_cache_ttl_seconds)


def get_geocoding_service(
    client: GeocodingClient = Depends(get_geocoding_client),
    cache: Cache[List[GeocodeResult]] = Depends(get_geocoding_cache),
) -> GeocodingService:
    return GeocodingService(client=client, cache=cache)
