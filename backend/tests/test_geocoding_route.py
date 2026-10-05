from typing import Optional

from fastapi.testclient import TestClient

from app.api.deps import get_geocoding_service
from app.data.exceptions import GeocodingError
from app.main import app
from app.schemas.geocoding import GeocodeResult

client = TestClient(app)


class _StubGeocodingService:
    def __init__(self, result=None, error: Optional[Exception] = None) -> None:
        self._result = result if result is not None else []
        self._error = error
        self.last_call = None

    def search(self, query: str, *, limit: int = 6):
        self.last_call = (query, limit)
        if self._error is not None:
            raise self._error
        return self._result


def _override(stub: _StubGeocodingService) -> None:
    app.dependency_overrides[get_geocoding_service] = lambda: stub


def _clear() -> None:
    app.dependency_overrides.clear()


def test_geocode_returns_matching_places() -> None:
    stub = _StubGeocodingService(
        result=[
            GeocodeResult(display_name="Tel Aviv, Israel", latitude_deg=32.08, longitude_deg=34.78)
        ]
    )
    _override(stub)
    try:
        response = client.get("/api/geocode?q=Tel+Aviv")
        assert response.status_code == 200
        body = response.json()
        assert body[0]["display_name"] == "Tel Aviv, Israel"
        assert stub.last_call == ("Tel Aviv", 6)
    finally:
        _clear()


def test_geocode_requires_at_least_two_characters() -> None:
    response = client.get("/api/geocode?q=a")
    assert response.status_code == 422


def test_geocode_propagates_upstream_error_as_502() -> None:
    stub = _StubGeocodingService(error=GeocodingError("unreachable"))
    _override(stub)
    try:
        response = client.get("/api/geocode?q=somewhere")
        assert response.status_code == 502
    finally:
        _clear()
