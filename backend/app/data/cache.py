"""
Cache abstraction sitting in front of the CelesTrak client.

Deliberately storage-agnostic: Phase 1 ships an in-memory implementation.
Phase 6 can introduce a PostgreSQL-backed implementation behind the same
`Cache` protocol without changing `SatelliteService` at all - that's the
whole point of depending on the protocol rather than a concrete class.

Note on the in-memory implementation: it lives in one process's memory, so
it is NOT shared across multiple backend instances and is cleared on every
restart. That's an acceptable trade-off for a single free-tier instance in
Phase 1, but is a limitation worth knowing about before scaling out.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Generic, Optional, Protocol, TypeVar

T = TypeVar("T")


class Cache(Protocol[T]):
    def get(self, key: str) -> Optional[T]: ...

    def set(self, key: str, value: T) -> None: ...


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class InMemoryTTLCache(Generic[T]):
    """A minimal in-process cache where each entry expires after a fixed TTL."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: Dict[str, _CacheEntry[T]] = {}

    def get(self, key: str) -> Optional[T]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            del self._entries[key]
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        self._entries[key] = _CacheEntry(
            value=value, expires_at=time.monotonic() + self._ttl_seconds
        )

    def clear(self) -> None:
        self._entries.clear()
