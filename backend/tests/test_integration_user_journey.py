"""
Full user-journey integration test (Phase 11).

Every other test file exercises one endpoint, service, or module at a
time. This one deliberately walks the whole realistic flow in a single
test, checking that data flows *consistently* across the stack rather
than each piece just working in isolation:

    save an observer
        -> predict passes for a satellite from that observer (persists)
        -> fetch that exact pass back by id
        -> fetch its visibility separately
        -> find it again via search
        -> confirm it's what ranking would also surface
        -> delete the observer and confirm cascade cleanup

CelesTrak is mocked (as throughout this project); Postgres is real.
"""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_satellite_service
from app.data.celestrak import CelestrakClient
from app.data.postgres_cache import PostgresSatelliteCache
from app.main import app
from app.services.satellite_service import SatelliteService

client = TestClient(app)

VANGUARD1_EPOCH = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)
OVERHEAD_LAT = 0.0
OVERHEAD_LON = 149.95

# Real, well-known reference TLE lines (see tests/conftest.py's
# SAMPLE_TLE_LINE1/2). CelesTrak's JSON GP format doesn't include raw TLE
# line text (see app/data/celestrak.py), so the mocked transport below
# has to answer the separate FORMAT=TLE request too.
_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def test_full_user_journey_across_endpoints(clean_database, valid_gp_record) -> None:
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
        # 1. Save a named observer location.
        observer = client.post(
            "/api/observers",
            json={"name": "Test Site", "latitude_deg": OVERHEAD_LAT, "longitude_deg": OVERHEAD_LON},
        ).json()
        assert observer["id"] > 0

        # 2. Predict passes for Vanguard 1 using that saved observer -
        # this both fetches (and caches) the satellite and persists the pass.
        predicted = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "observer_id": observer["id"],
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
                "min_elevation_deg": 10.0,
            },
        ).json()
        assert len(predicted) == 1
        pass_id = predicted[0]["id"]
        assert predicted[0]["observer_id"] == observer["id"]

        # 3. The satellite fetched along the way should now be listable.
        satellites = client.get("/api/satellites").json()
        assert any(s["norad_id"] == 5 for s in satellites)

        # 4. Fetching the pass by id should return the identical geometry.
        fetched = client.get(f"/api/passes/{pass_id}").json()
        assert fetched["pass_event"] == predicted[0]["pass_event"]
        assert len(fetched["visibility"]) == 3

        # 5. Visibility is also independently fetchable, and consistent.
        visibility = client.get(f"/api/passes/{pass_id}/visibility").json()
        assert {v["method"] for v in visibility} == {"naked_eye", "binoculars", "telescope"}
        assert visibility == fetched["visibility"]

        # 6. Searching by observer_id and by norad_id should both find it.
        by_observer = client.get(f"/api/passes/search?observer_id={observer['id']}").json()
        by_satellite = client.get("/api/passes/search?norad_id=5").json()
        assert any(p["id"] == pass_id for p in by_observer)
        assert any(p["id"] == pass_id for p in by_satellite)

        # 7. Deleting the observer should cascade-delete the pass (and its
        # visibility predictions with it).
        delete_response = client.delete(f"/api/observers/{observer['id']}")
        assert delete_response.status_code == 204

        assert client.get(f"/api/passes/{pass_id}").status_code == 404
        assert client.get("/api/passes/search?norad_id=5").json() == []
    finally:
        app.dependency_overrides.clear()
