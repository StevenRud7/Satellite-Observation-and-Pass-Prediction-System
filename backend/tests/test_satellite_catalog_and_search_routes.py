from typing import Optional

from fastapi.testclient import TestClient

from app.api.deps import get_satellite_search_service
from app.data.exceptions import CelestrakClientError
from app.main import app
from app.schemas.satellite import SatelliteSearchResult

client = TestClient(app)


def test_catalog_returns_curated_entries() -> None:
    response = client.get("/api/satellites/catalog")
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert any(entry["norad_id"] == 25544 for entry in body)
    assert all("category" in entry for entry in body)


class _StubSearchService:
    def __init__(self, result=None, error: Optional[Exception] = None) -> None:
        self._result = result if result is not None else []
        self._error = error
        self.last_call = None

    def search(self, query: str, *, limit: int = 20):
        self.last_call = (query, limit)
        if self._error is not None:
            raise self._error
        return self._result


def _override(stub: _StubSearchService) -> None:
    app.dependency_overrides[get_satellite_search_service] = lambda: stub


def _clear() -> None:
    app.dependency_overrides.clear()


def test_search_returns_matching_satellites() -> None:
    stub = _StubSearchService(result=[SatelliteSearchResult(norad_id=25544, name="ISS (ZARYA)")])
    _override(stub)
    try:
        response = client.get("/api/satellites/search?q=iss")
        assert response.status_code == 200
        assert response.json() == [{"norad_id": 25544, "name": "ISS (ZARYA)", "category": None}]
        assert stub.last_call == ("iss", 20)
    finally:
        _clear()


def test_search_requires_at_least_two_characters() -> None:
    response = client.get("/api/satellites/search?q=a")
    assert response.status_code == 422


def test_search_propagates_upstream_error_as_502() -> None:
    stub = _StubSearchService(error=CelestrakClientError("unreachable"))
    _override(stub)
    try:
        response = client.get("/api/satellites/search?q=starlink")
        assert response.status_code == 502
    finally:
        _clear()


def test_search_route_does_not_shadow_norad_id_route() -> None:
    # "/api/satellites/25544" must still be handled by the {norad_id} route,
    # not accidentally swallowed by the "/search" or "/catalog" routes.
    response = client.get("/api/satellites/not-a-number")
    assert response.status_code == 422  # int conversion failure, not a 404 from /search
