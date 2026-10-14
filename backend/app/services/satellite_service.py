"""
Satellite service.

Sits between API routes and the data layer so routes don't need to know
whether a satellite record came from cache or a fresh CelesTrak fetch.

Resilience (added after a deployment where CelesTrak was slow/unreachable
from the host). Order of preference for a satellite's orbital data:

1. a fresh cached copy (within the cache TTL);
2. the static TLE snapshot, if one is configured AND it was generated
   recently (`snapshot_prefer_max_age`) - same freshness class as the cache,
   with no dependence on CelesTrak being reachable;
3. a live CelesTrak fetch;
4. if (3) fails at the network/upstream level: the TLE API, a second live
   source on a different host;
5. last resort: the newest of the last cached copy (even past its TTL) and
   the snapshot (even if older), provided its TLE epoch isn't older than
   `max_fallback_epoch_age`.

Anything obtained in 2-4 is stored in the cache (once per new TLE epoch), so
features that need the satellite to exist in the database - e.g. persisting
predicted passes - keep working. If nothing usable exists, the original
live-fetch error is raised exactly as before. "Satellite doesn't exist"
errors never fall back (a missing NORAD ID must not be papered over).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.logging import get_logger
from app.data.cache import Cache
from app.data.celestrak import CelestrakClient
from app.data.exceptions import CelestrakClientError, SatelliteNotFoundError
from app.data.snapshot import TleSnapshotClient
from app.data.tle_api import TleApiClient
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
        tle_api: Optional[TleApiClient] = None,
        snapshot_prefer_max_age: timedelta = timedelta(0),
    ) -> None:
        self._client = client
        self._cache = cache
        self._snapshot = snapshot
        self._max_fallback_epoch_age = max_fallback_epoch_age
        self._tle_api = tle_api
        self._snapshot_prefer_max_age = snapshot_prefer_max_age

    def get_satellite(self, norad_id: int, *, force_refresh: bool = False) -> SatelliteRecord:
        """Return the current orbital elements for `norad_id`, using the cache when fresh."""
        cache_key = str(norad_id)

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for NORAD ID %s", norad_id)
                return cached

            preferred = self._fresh_snapshot(norad_id)
            if preferred is not None:
                self._remember_if_newer(cache_key, preferred)
                return preferred

        try:
            record = self._client.fetch_satellite_by_norad_id(norad_id)
        except SatelliteNotFoundError:
            raise
        except CelestrakClientError as live_error:
            alternate = self._from_tle_api(norad_id)
            if alternate is not None:
                logger.warning(
                    "Live CelesTrak fetch failed for NORAD ID %s (%s); used TLE API instead",
                    norad_id,
                    live_error,
                )
                self._cache.set(cache_key, alternate)
                return alternate

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
            self._remember_if_newer(cache_key, fallback)
            return fallback

        self._cache.set(cache_key, record)
        return record

    # -- helpers ---------------------------------------------------------

    def _usable(self, record: SatelliteRecord) -> bool:
        cutoff = datetime.now(timezone.utc) - self._max_fallback_epoch_age
        return record.orbital_elements.epoch >= cutoff

    def _fresh_snapshot(self, norad_id: int) -> Optional[SatelliteRecord]:
        if (
            self._snapshot is None
            or not self._snapshot.enabled
            or self._snapshot_prefer_max_age <= timedelta(0)
        ):
            return None
        record = self._snapshot.get(norad_id)
        if record is None or not self._usable(record):
            return None
        age = datetime.now(timezone.utc) - record.orbital_elements.retrieved_at
        return record if age <= self._snapshot_prefer_max_age else None

    def _from_tle_api(self, norad_id: int) -> Optional[SatelliteRecord]:
        if self._tle_api is None or not self._tle_api.enabled:
            return None
        record = self._tle_api.fetch(norad_id)
        return record if record is not None and self._usable(record) else None

    def _remember_if_newer(self, key: str, record: SatelliteRecord) -> None:
        """Store `record` in the cache unless the cache already holds that TLE
        epoch (or newer) - avoids writing a duplicate database row on every
        request while a snapshot is being served."""
        try:
            get_stale = getattr(self._cache, "get_stale", None)
            existing = get_stale(key) if get_stale is not None else None
            if existing is None or existing.orbital_elements.epoch < record.orbital_elements.epoch:
                self._cache.set(key, record)
        except Exception as exc:  # caching is best-effort here; never fail the request
            logger.warning("Could not cache fallback record for NORAD ID %s: %s", key, exc)

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

        usable = [c for c in candidates if self._usable(c)]
        if not usable:
            return None
        return max(usable, key=lambda c: c.orbital_elements.epoch)
