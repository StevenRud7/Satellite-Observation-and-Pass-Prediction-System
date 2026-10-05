"""
PostgreSQL-backed implementation of the `Cache[SatelliteRecord]` protocol
(see app/data/cache.py). This is exactly what Phase 1's docstring
promised: a database-backed cache that `SatelliteService` can use without
any change to `SatelliteService` itself, because it depends only on the
`Cache` protocol.

Freshness is judged the same way as the in-memory cache: a stored record
is considered fresh if it was retrieved within `ttl_seconds` ago. Keeping
that logic identical means swapping cache implementations doesn't change
`SatelliteService`'s observable behavior, which is the whole point of
depending on a protocol instead of a concrete class.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.session import session_scope
from app.schemas.satellite import SatelliteRecord


class PostgresSatelliteCache:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[SatelliteRecord]:
        norad_id = int(key)
        with session_scope() as session:
            record = SatelliteRepository(session).get_latest_by_norad_id(norad_id)

        if record is None:
            return None

        age = datetime.now(timezone.utc) - record.orbital_elements.retrieved_at
        if age > timedelta(seconds=self._ttl_seconds):
            return None

        return record

    def set(self, key: str, value: SatelliteRecord) -> None:
        with session_scope() as session:
            SatelliteRepository(session).upsert(value)
