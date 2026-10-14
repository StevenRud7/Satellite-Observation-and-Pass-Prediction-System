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

from typing import List, Optional

from app.core.logging import get_logger
from app.data.cache import Cache
from app.data.celestrak import CelestrakClient
from app.data.exceptions import CelestrakClientError
from app.data.snapshot import TleSnapshotClient
from app.data.tle_api import TleApiClient
from app.schemas.satellite import SatelliteSearchResult

logger = get_logger(__name__)


class SatelliteSearchService:
    def __init__(
        self,
        client: CelestrakClient,
        cache: Cache[List[SatelliteSearchResult]],
        tle_api: Optional[TleApiClient] = None,
        snapshot: Optional[TleSnapshotClient] = None,
    ) -> None:
        self._client = client
        self._cache = cache
        self._tle_api = tle_api
        self._snapshot = snapshot

    def search(self, query: str, *, limit: int = 20) -> List[SatelliteSearchResult]:
        cache_key = f"{query.strip().lower()}:{limit}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Satellite search cache hit for %r", query)
            return cached

        try:
            results = self._client.search_by_name(query, limit=limit)
        except CelestrakClientError as live_error:
            # CelesTrak unreachable: try the secondary source, then the
            # snapshot's names. If neither finds anything, surface the
            # original error rather than a misleading empty result.
            results = []
            if self._tle_api is not None and self._tle_api.enabled:
                results = self._tle_api.search(query, limit=limit)
            if not results and self._snapshot is not None and self._snapshot.enabled:
                results = self._snapshot.search(query, limit=limit)
            if not results:
                raise live_error
            logger.warning("Satellite search for %r served by fallback (%s)", query, live_error)

        self._cache.set(cache_key, results)
        return results
