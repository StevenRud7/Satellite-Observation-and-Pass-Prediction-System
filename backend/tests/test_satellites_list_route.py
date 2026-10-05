import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_satellite_service
from app.data.celestrak import CelestrakClient
from app.data.postgres_cache import PostgresSatelliteCache
from app.main import app
from app.services.satellite_service import SatelliteService

client = TestClient(app)

# Real, well-known reference TLE lines (see tests/conftest.py's
# SAMPLE_TLE_LINE1/2). CelesTrak's JSON GP format doesn't include raw TLE
# line text (see app/data/celestrak.py), so the mocked transport below
# has to answer the separate FORMAT=TLE request too.
_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def test_list_satellites_includes_previously_fetched_satellite(
    clean_database, valid_gp_record
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["FORMAT"] == "JSON":
            return httpx.Response(200, json=[valid_gp_record])
        return httpx.Response(200, text=f"{_LINE1}\n{_LINE2}\n")

    service = SatelliteService(
        client=CelestrakClient(http_client=httpx.Client(transport=httpx.MockTransport(handler))),
        cache=PostgresSatelliteCache(ttl_seconds=3600),
    )
    app.dependency_overrides[get_satellite_service] = lambda: service
    try:
        client.get("/api/satellites/5")  # populates the cache/DB

        response = client.get("/api/satellites")

        assert response.status_code == 200
        norad_ids = {s["norad_id"] for s in response.json()}
        assert 5 in norad_ids
    finally:
        app.dependency_overrides.clear()


def test_list_satellites_empty_when_none_cached(clean_database) -> None:
    response = client.get("/api/satellites")
    assert response.status_code == 200
    assert response.json() == []
