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

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so we don't re-parse env vars on every call."""
    return Settings()
