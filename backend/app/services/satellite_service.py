"""
Satellite service.

Sits between API routes and the data layer so routes don't need to know
whether a satellite record came from cache or a fresh CelesTrak fetch.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.data.cache import Cache
from app.data.celestrak import CelestrakClient
from app.schemas.satellite import SatelliteRecord

logger = get_logger(__name__)


class SatelliteService:
    def __init__(self, client: CelestrakClient, cache: Cache[SatelliteRecord]) -> None:
        self._client = client
        self._cache = cache

    def get_satellite(self, norad_id: int, *, force_refresh: bool = False) -> SatelliteRecord:
        """Return the current orbital elements for `norad_id`, using the cache when fresh."""
        cache_key = str(norad_id)

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for NORAD ID %s", norad_id)
                return cached

        record = self._client.fetch_satellite_by_norad_id(norad_id)
        self._cache.set(cache_key, record)
        return record
