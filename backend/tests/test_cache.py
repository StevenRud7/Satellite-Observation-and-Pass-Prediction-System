import time

from app.data.cache import InMemoryTTLCache


def test_get_returns_none_for_missing_key() -> None:
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(ttl_seconds=60)
    assert cache.get("missing") is None


def test_set_then_get_returns_value() -> None:
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(ttl_seconds=60)
    cache.set("key", "value")
    assert cache.get("key") == "value"


def test_entry_expires_after_ttl() -> None:
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(ttl_seconds=0.05)
    cache.set("key", "value")
    assert cache.get("key") == "value"

    time.sleep(0.1)

    assert cache.get("key") is None


def test_clear_removes_all_entries() -> None:
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(ttl_seconds=60)
    cache.set("a", "1")
    cache.set("b", "2")

    cache.clear()

    assert cache.get("a") is None
    assert cache.get("b") is None


def test_set_overwrites_existing_value_and_resets_ttl() -> None:
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(ttl_seconds=60)
    cache.set("key", "first")
    cache.set("key", "second")
    assert cache.get("key") == "second"
