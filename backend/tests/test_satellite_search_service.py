from unittest.mock import MagicMock

from app.schemas.satellite import SatelliteSearchResult
from app.services.satellite_search_service import SatelliteSearchService

_RESULTS = [SatelliteSearchResult(norad_id=25544, name="ISS (ZARYA)")]


def test_search_uses_cache_on_hit() -> None:
    cache = MagicMock()
    cache.get.return_value = _RESULTS
    client = MagicMock()

    service = SatelliteSearchService(client=client, cache=cache)
    result = service.search("iss")

    assert result == _RESULTS
    client.search_by_name.assert_not_called()


def test_search_fetches_and_caches_on_miss() -> None:
    cache = MagicMock()
    cache.get.return_value = None
    client = MagicMock()
    client.search_by_name.return_value = _RESULTS

    service = SatelliteSearchService(client=client, cache=cache)
    result = service.search("iss", limit=5)

    assert result == _RESULTS
    client.search_by_name.assert_called_once_with("iss", limit=5)
    cache.set.assert_called_once()
