from unittest.mock import MagicMock

from app.schemas.geocoding import GeocodeResult
from app.services.geocoding_service import GeocodingService

_RESULT = [GeocodeResult(display_name="Tel Aviv", latitude_deg=32.08, longitude_deg=34.78)]


def test_search_uses_cache_on_hit() -> None:
    cache = MagicMock()
    cache.get.return_value = _RESULT
    client = MagicMock()

    service = GeocodingService(client=client, cache=cache)
    result = service.search("Tel Aviv")

    assert result == _RESULT
    client.search.assert_not_called()


def test_search_fetches_and_caches_on_miss() -> None:
    cache = MagicMock()
    cache.get.return_value = None
    client = MagicMock()
    client.search.return_value = _RESULT

    service = GeocodingService(client=client, cache=cache)
    result = service.search("Tel Aviv", limit=3)

    assert result == _RESULT
    client.search.assert_called_once_with("Tel Aviv", limit=3)
    cache.set.assert_called_once()


def test_search_cache_key_is_case_insensitive() -> None:
    cache = MagicMock()
    cache.get.return_value = None
    client = MagicMock()
    client.search.return_value = _RESULT

    service = GeocodingService(client=client, cache=cache)
    service.search("  Tel Aviv  ")

    cache_key = cache.set.call_args[0][0]
    assert cache_key == "tel aviv:6"
