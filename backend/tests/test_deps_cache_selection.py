from app.api import deps
from app.core.config import Settings
from app.data.cache import InMemoryTTLCache
from app.data.postgres_cache import PostgresSatelliteCache


def _reset_caches() -> None:
    deps.get_satellite_cache.cache_clear()
    deps.get_celestrak_client.cache_clear()


def test_uses_postgres_cache_when_database_url_configured(monkeypatch) -> None:
    _reset_caches()
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: Settings(database_url="postgresql+psycopg://user:pass@localhost/db"),
    )

    cache = deps.get_satellite_cache()

    assert isinstance(cache, PostgresSatelliteCache)
    _reset_caches()


def test_uses_in_memory_cache_when_no_database_configured(monkeypatch) -> None:
    _reset_caches()
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(database_url=None))

    cache = deps.get_satellite_cache()

    assert isinstance(cache, InMemoryTTLCache)
    _reset_caches()
