"""
End-to-end test of the promise made back in Phase 1: SatelliteService
doesn't need to change at all to gain PostgreSQL persistence, because it
only depends on the Cache protocol. This wires a real PostgresSatelliteCache
(against the test database) together with a mocked CelesTrak HTTP
transport (so no real network call happens) and drives it through the
actual `/api/satellites/{norad_id}` endpoint.

Each logical satellite fetch is two HTTP requests under the hood - one
for the JSON/OMM metadata, one for the raw TLE line text (see
app/data/celestrak.py) - so `call_counter` here counts raw HTTP requests,
not fetches; a single (uncached) fetch is 2, not 1.
"""

from typing import List

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_satellite_service
from app.data.celestrak import CelestrakClient
from app.data.postgres_cache import PostgresSatelliteCache
from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.session import session_scope
from app.main import app
from app.services.satellite_service import SatelliteService

client = TestClient(app)


def _service_with_mocked_celestrak(
    valid_gp_record: dict, valid_tle_lines: tuple, call_counter: List[int]
) -> SatelliteService:
    line1, line2 = valid_tle_lines

    def handler(request: httpx.Request) -> httpx.Response:
        call_counter.append(1)
        if request.url.params["FORMAT"] == "JSON":
            return httpx.Response(200, json=[valid_gp_record])
        return httpx.Response(200, text=f"{line1}\n{line2}\n")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    celestrak_client = CelestrakClient(http_client=http_client)
    cache = PostgresSatelliteCache(ttl_seconds=3600)
    return SatelliteService(client=celestrak_client, cache=cache)


def test_satellite_endpoint_persists_result_to_postgres(
    clean_database, valid_gp_record, valid_tle_lines
) -> None:
    call_counter: List[int] = []
    service = _service_with_mocked_celestrak(valid_gp_record, valid_tle_lines, call_counter)
    app.dependency_overrides[get_satellite_service] = lambda: service

    try:
        response = client.get("/api/satellites/5")
        assert response.status_code == 200
        assert response.json()["name"] == "VANGUARD 1"

        with session_scope() as session:
            stored = SatelliteRepository(session).get_latest_by_norad_id(5)
        assert stored is not None
        assert stored.name == "VANGUARD 1"
        assert stored.orbital_elements.line1 == valid_tle_lines[0]
        assert stored.orbital_elements.line2 == valid_tle_lines[1]
    finally:
        app.dependency_overrides.clear()


def test_second_request_is_served_from_postgres_not_celestrak(
    clean_database, valid_gp_record, valid_tle_lines
) -> None:
    call_counter: List[int] = []
    service = _service_with_mocked_celestrak(valid_gp_record, valid_tle_lines, call_counter)
    app.dependency_overrides[get_satellite_service] = lambda: service

    try:
        client.get("/api/satellites/5")
        client.get("/api/satellites/5")

        # One logical fetch (JSON + TLE requests); the second call is
        # served entirely from Postgres, with no CelesTrak requests at all.
        assert len(call_counter) == 2
    finally:
        app.dependency_overrides.clear()


def test_refresh_query_param_bypasses_postgres_cache(
    clean_database, valid_gp_record, valid_tle_lines
) -> None:
    call_counter: List[int] = []
    service = _service_with_mocked_celestrak(valid_gp_record, valid_tle_lines, call_counter)
    app.dependency_overrides[get_satellite_service] = lambda: service

    try:
        client.get("/api/satellites/5")
        client.get("/api/satellites/5?refresh=true")

        # Two logical fetches (initial + forced refresh), two HTTP
        # requests each.
        assert len(call_counter) == 4
    finally:
        app.dependency_overrides.clear()
