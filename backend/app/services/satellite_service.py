"""
Satellite service.

Sits between API routes and the data layer so routes don't need to know
whether a satellite record came from cache or a fresh CelesTrak fetch.

Resilience (added after a deployment where CelesTrak was slow/unreachable
from the host): the order of preference for a satellite's orbital data is

1. a fresh cached copy (within the cache TTL),
2. a live CelesTrak fetch (stored in the cache when it succeeds),
3. only if that live fetch fails with a *network-level or upstream* error:
   the newest of (a) the last cached copy, even if past its TTL, and
   (b) the static TLE snapshot, provided its TLE epoch isn't older than
   `max_fallback_epoch_age`.

If nothing usable exists, the original live-fetch error is raised exactly as
before, so the API's error behaviour for a genuinely unavailable satellite
is unchanged. "Satellite doesn't exist" errors never fall back (a missing
NORAD ID must not be papered over with old data).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.logging import get_logger
from app.data.cache import Cache
from app.data.celestrak import CelestrakClient
from app.data.exceptions import CelestrakClientError, SatelliteNotFoundError
from app.data.snapshot import TleSnapshotClient
from app.schemas.satellite import SatelliteRecord

logger = get_logger(__name__)

DEFAULT_MAX_FALLBACK_EPOCH_AGE = timedelta(days=14)


class SatelliteService:
    def __init__(
        self,
        client: CelestrakClient,
        cache: Cache[SatelliteRecord],
        snapshot: Optional[TleSnapshotClient] = None,
        max_fallback_epoch_age: timedelta = DEFAULT_MAX_FALLBACK_EPOCH_AGE,
    ) -> None:
        self._client = client
        self._cache = cache
        self._snapshot = snapshot
        self._max_fallback_epoch_age = max_fallback_epoch_age

    def get_satellite(self, norad_id: int, *, force_refresh: bool = False) -> SatelliteRecord:
        """Return the current orbital elements for `norad_id`, using the cache when fresh."""
        cache_key = str(norad_id)

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for NORAD ID %s", norad_id)
                return cached

        try:
            record = self._client.fetch_satellite_by_norad_id(norad_id)
        except SatelliteNotFoundError:
            raise
        except CelestrakClientError as live_error:
            fallback = self._best_fallback(norad_id)
            if fallback is None:
                raise
            logger.warning(
                "Live CelesTrak fetch failed for NORAD ID %s (%s); using %s data "
                "with TLE epoch %s instead",
                norad_id,
                live_error,
                fallback.orbital_elements.source,
                fallback.orbital_elements.epoch.isoformat(),
            )
            return fallback

        self._cache.set(cache_key, record)
        return record

    def _best_fallback(self, norad_id: int) -> Optional[SatelliteRecord]:
        candidates = []

        get_stale = getattr(self._cache, "get_stale", None)
        if get_stale is not None:
            try:
                stale = get_stale(str(norad_id))
            except Exception as exc:  # a broken cache must not mask the real error
                logger.warning("Stale-cache lookup failed for NORAD ID %s: %s", norad_id, exc)
                stale = None
            if stale is not None:
                candidates.append(stale)

        if self._snapshot is not None and self._snapshot.enabled:
            snap = self._snapshot.get(norad_id)
            if snap is not None:
                candidates.append(snap)

        cutoff = datetime.now(timezone.utc) - self._max_fallback_epoch_age
        usable = [c for c in candidates if c.orbital_elements.epoch >= cutoff]
        if not usable:
            return None
        return max(usable, key=lambda c: c.orbital_elements.epoch)
