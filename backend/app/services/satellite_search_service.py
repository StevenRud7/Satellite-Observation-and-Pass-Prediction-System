"""
Satellite name-search service.

Same pattern as `SatelliteService` (see satellite_service.py): sits between
the route and the CelesTrak client, adding a short cache so that repeated
or in-flight-typing searches for the same text don't each hit CelesTrak.
Deliberately a separate, in-memory-only cache from the main satellite
cache - search results are lightweight (name + ID, no orbital elements)
and short-lived, so persisting them in Postgres would be overkill.
"""

from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.data.cache import Cache
from app.data.celestrak import CelestrakClient
from app.schemas.satellite import SatelliteSearchResult

logger = get_logger(__name__)


class SatelliteSearchService:
    def __init__(self, client: CelestrakClient, cache: Cache[List[SatelliteSearchResult]]) -> None:
        self._client = client
        self._cache = cache

    def search(self, query: str, *, limit: int = 20) -> List[SatelliteSearchResult]:
        cache_key = f"{query.strip().lower()}:{limit}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Satellite search cache hit for %r", query)
            return cached

        results = self._client.search_by_name(query, limit=limit)
        self._cache.set(cache_key, results)
        return results
