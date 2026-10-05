"""
Place-search (geocoding) service - same thin cache-then-fetch pattern as
`SatelliteService` / `SatelliteSearchService`.
"""

from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.data.cache import Cache
from app.data.geocoding import GeocodingClient
from app.schemas.geocoding import GeocodeResult

logger = get_logger(__name__)


class GeocodingService:
    def __init__(self, client: GeocodingClient, cache: Cache[List[GeocodeResult]]) -> None:
        self._client = client
        self._cache = cache

    def search(self, query: str, *, limit: int = 6) -> List[GeocodeResult]:
        cache_key = f"{query.strip().lower()}:{limit}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Geocode cache hit for %r", query)
            return cached

        results = self._client.search(query, limit=limit)
        self._cache.set(cache_key, results)
        return results
