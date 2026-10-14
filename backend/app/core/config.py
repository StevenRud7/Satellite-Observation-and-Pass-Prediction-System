"""
Application configuration.

Settings are loaded from environment variables (and a local .env file in
development). Using pydantic-settings means required variables fail fast at
startup with a clear error, instead of surfacing as confusing runtime bugs
later.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    environment: str = "development"
    log_level: str = "INFO"

    # CORS - comma separated list of allowed origins
    cors_origins: str = "http://localhost:5173"

    # Database (not used until Phase 6, but declared now so the shape of
    # config is stable across phases)
    database_url: Optional[str] = None

    # How long a fetched satellite record stays in the in-memory cache
    # before we consider it stale and worth re-fetching from CelesTrak.
    orbital_data_cache_ttl_seconds: int = 6 * 60 * 60  # 6 hours

    # Place-search (geocoding) results are cached briefly, keyed by the
    # search text - mostly to avoid re-querying Nominatim on every
    # keystroke-triggered request and to stay comfortably within its
    # usage policy, not because places move.
    geocode_cache_ttl_seconds: int = 60 * 60  # 1 hour

    # Satellite name-search results (against CelesTrak) are cached briefly
    # for the same reason.
    satellite_search_cache_ttl_seconds: int = 10 * 60  # 10 minutes

    # --- Resilience when CelesTrak is slow or unreachable from the host ---

    # If a live CelesTrak fetch fails, previously cached/snapshotted orbital
    # data is still used - but only while its TLE epoch is no older than
    # this. SGP4 along-track error grows with TLE age, so a couple of weeks
    # is the point past which "stale but usable" turns into "misleading".
    stale_orbital_data_max_epoch_age_seconds: int = 14 * 24 * 60 * 60

    # After a network-level failure (timeout / connection error) talking to
    # CelesTrak, skip live attempts for this long and go straight to
    # cache/snapshot fallbacks, so repeated clicks aren't each made to wait
    # for another full timeout.
    celestrak_unreachable_cooldown_seconds: int = 90

    # Timeout (seconds) for reading a CelesTrak response. Connecting is capped
    # separately and lower (see app/data/celestrak.py). CelesTrak normally
    # answers in about a second; since cached/snapshot/TLE-API fallbacks now
    # exist, waiting 30s for a stalled connection is no longer worth it.
    celestrak_timeout_seconds: float = 15.0

    # Bind outgoing CelesTrak/TLE-API connections to IPv4. Some hosts have
    # IPv6 routes that hang instead of failing, which shows up as a plain
    # "timed out" even though IPv4 would work instantly.
    force_ipv4: bool = True

    # Secondary live source (different host from CelesTrak), consulted only
    # after a live CelesTrak fetch fails. See app/data/tle_api.py.
    tle_api_enabled: bool = True
    tle_api_base_url: str = "https://tle.ivanstanojevic.me/api/tle"

    # If a TLE snapshot is configured and was generated within this many
    # seconds, it is used BEFORE trying CelesTrak (comparable freshness to
    # the 6h cache TTL, with zero dependence on CelesTrak being reachable
    # from this host). 0 disables snapshot-first behaviour.
    snapshot_prefer_max_age_seconds: int = 8 * 60 * 60

    # Optional URL of a JSON TLE snapshot (see scripts/update_tle_snapshot.py
    # and .github/workflows/update-tle-snapshot.yml) used as a last-resort
    # orbital data source when CelesTrak can't be reached from this host.
    tle_snapshot_url: Optional[str] = None

    # Warm the satellite cache for the curated catalog in the background
    # at startup (and every couple of hours while the process is awake), so
    # the first user request doesn't have to wait on CelesTrak.
    prewarm_enabled: bool = False

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so we don't re-parse env vars on every call."""
    return Settings()
