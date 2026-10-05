from typing import Optional, Tuple

from fastapi.testclient import TestClient

from app.api.deps import get_satellite_service
from app.data.exceptions import (
    CelestrakClientError,
    OrbitalDataValidationError,
    SatelliteNotFoundError,
)
from app.main import app
from tests.test_satellite_service import _fake_record


class _StubService:
    def __init__(self, result=None, error: Optional[Exception] = None) -> None:
        self._result = result
        self._error = error
        self.last_call: Optional[Tuple[int, bool]] = None

    def get_satellite(self, norad_id: int, *, force_refresh: bool = False):
        self.last_call = (norad_id, force_refresh)
        if self._error is not None:
            raise self._error
        return self._result


def _override_service(stub: _StubService) -> None:
    app.dependency_overrides[get_satellite_service] = lambda: stub


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


client = TestClient(app)


def test_get_satellite_returns_200_with_record() -> None:
    stub = _StubService(result=_fake_record(5))
    _override_service(stub)
    try:
        response = client.get("/api/satellites/5")
        assert response.status_code == 200
        body = response.json()
        assert body["norad_id"] == 5
        assert body["name"] == "TEST SAT"
        assert stub.last_call == (5, False)
    finally:
        _clear_overrides()


def test_refresh_query_param_forces_refresh() -> None:
    stub = _StubService(result=_fake_record(5))
    _override_service(stub)
    try:
        response = client.get("/api/satellites/5?refresh=true")
        assert response.status_code == 200
        assert stub.last_call == (5, True)
    finally:
        _clear_overrides()


def test_satellite_not_found_returns_404() -> None:
    stub = _StubService(error=SatelliteNotFoundError("no data"))
    _override_service(stub)
    try:
        response = client.get("/api/satellites/999999")
        assert response.status_code == 404
    finally:
        _clear_overrides()


def test_validation_error_returns_422() -> None:
    stub = _StubService(error=OrbitalDataValidationError("bad data"))
    _override_service(stub)
    try:
        response = client.get("/api/satellites/5")
        assert response.status_code == 422
    finally:
        _clear_overrides()


def test_celestrak_client_error_returns_502() -> None:
    stub = _StubService(error=CelestrakClientError("unreachable"))
    _override_service(stub)
    try:
        response = client.get("/api/satellites/5")
        assert response.status_code == 502
    finally:
        _clear_overrides()
