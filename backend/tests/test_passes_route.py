"""
Tests for /api/passes/* endpoints.

Vanguard 1's TLE and epoch are used throughout (same fixture as earlier
phases), with CelesTrak mocked via httpx.MockTransport so no real network
call happens. The observer is placed directly under Vanguard 1's real
sub-satellite point at its TLE epoch (see test_passes.py in Phase 3 for
how this geometry was derived), guaranteeing a real, near-overhead pass
to find in a narrow time window.
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


def _mocked_satellite_service(valid_gp_record: dict) -> SatelliteService:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["FORMAT"] == "JSON":
            return httpx.Response(200, json=[valid_gp_record])
        return httpx.Response(200, text=f"{_LINE1}\n{_LINE2}\n")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    celestrak_client = CelestrakClient(http_client=http_client)
    cache = PostgresSatelliteCache(ttl_seconds=3600)
    return SatelliteService(client=celestrak_client, cache=cache)


def _override_satellite_service(valid_gp_record: dict) -> None:
    app.dependency_overrides[get_satellite_service] = lambda: _mocked_satellite_service(
        valid_gp_record
    )


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


# --- POST /api/passes/predict ----------------------------------------------


def test_predict_with_ad_hoc_observer_creates_observer_and_passes(
    clean_database, valid_gp_record
) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        response = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "latitude_deg": OVERHEAD_LAT,
                "longitude_deg": OVERHEAD_LON,
                "observer_name": "Test spot",
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
                "min_elevation_deg": 10.0,
            },
        )

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        result = results[0]
        assert result["id"] is not None
        assert result["observer_id"] is not None
        assert result["norad_id"] == 5
        assert result["pass_event"]["max_elevation_deg"] > 85.0
        assert len(result["visibility"]) == 3
    finally:
        _clear_overrides()


def test_predict_with_existing_observer_id(clean_database, valid_gp_record) -> None:
    observer = client.post(
        "/api/observers", json={"latitude_deg": OVERHEAD_LAT, "longitude_deg": OVERHEAD_LON}
    ).json()

    _override_satellite_service(valid_gp_record)
    try:
        response = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "observer_id": observer["id"],
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
            },
        )

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["observer_id"] == observer["id"]
    finally:
        _clear_overrides()


def test_predict_rejects_both_observer_id_and_coordinates(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        response = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "observer_id": 1,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "start": VANGUARD1_EPOCH.isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 422
    finally:
        _clear_overrides()


def test_predict_rejects_neither_observer_id_nor_coordinates(
    clean_database, valid_gp_record
) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        response = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "start": VANGUARD1_EPOCH.isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 422
    finally:
        _clear_overrides()


def test_predict_rejects_start_after_end(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        response = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "start": (VANGUARD1_EPOCH + timedelta(hours=1)).isoformat(),
                "end": VANGUARD1_EPOCH.isoformat(),
            },
        )
        assert response.status_code == 422
    finally:
        _clear_overrides()


def test_predict_with_unknown_observer_id_returns_404(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        response = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "observer_id": 999999,
                "start": VANGUARD1_EPOCH.isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 404
    finally:
        _clear_overrides()


# --- GET /api/passes/{id} and /api/passes/{id}/visibility ------------------


def test_get_pass_by_id_returns_stored_pass(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        predicted = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "latitude_deg": OVERHEAD_LAT,
                "longitude_deg": OVERHEAD_LON,
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
            },
        ).json()[0]

        response = client.get(f"/api/passes/{predicted['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == predicted["id"]
        assert len(response.json()["visibility"]) == 3
    finally:
        _clear_overrides()


def test_get_pass_by_id_returns_404_for_unknown_id(clean_database) -> None:
    response = client.get("/api/passes/999999")
    assert response.status_code == 404


def test_get_pass_visibility_returns_all_methods(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        predicted = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "latitude_deg": OVERHEAD_LAT,
                "longitude_deg": OVERHEAD_LON,
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
            },
        ).json()[0]

        response = client.get(f"/api/passes/{predicted['id']}/visibility")

        assert response.status_code == 200
        methods = {m["method"] for m in response.json()}
        assert methods == {"naked_eye", "binoculars", "telescope"}
    finally:
        _clear_overrides()


def test_get_pass_visibility_filters_by_method(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        predicted = client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "latitude_deg": OVERHEAD_LAT,
                "longitude_deg": OVERHEAD_LON,
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
            },
        ).json()[0]

        response = client.get(f"/api/passes/{predicted['id']}/visibility?method=telescope")

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["method"] == "telescope"
    finally:
        _clear_overrides()


def test_get_pass_visibility_returns_404_for_unknown_pass(clean_database) -> None:
    response = client.get("/api/passes/999999/visibility")
    assert response.status_code == 404


# --- GET /api/passes/search --------------------------------------------


def test_search_passes_filters_by_norad_id(clean_database, valid_gp_record) -> None:
    _override_satellite_service(valid_gp_record)
    try:
        client.post(
            "/api/passes/predict",
            json={
                "norad_id": 5,
                "latitude_deg": OVERHEAD_LAT,
                "longitude_deg": OVERHEAD_LON,
                "start": (VANGUARD1_EPOCH - timedelta(minutes=15)).isoformat(),
                "end": (VANGUARD1_EPOCH + timedelta(minutes=15)).isoformat(),
            },
        )

        response = client.get("/api/passes/search?norad_id=5")

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["norad_id"] == 5
        assert len(results[0]["visibility"]) == 3
    finally:
        _clear_overrides()


def test_search_passes_with_no_matches_returns_empty_list(clean_database) -> None:
    response = client.get("/api/passes/search?norad_id=99999")
    assert response.status_code == 200
    assert response.json() == []


# --- GET /api/passes/next ---------------------------------------------------


def test_next_pass_returns_404_when_none_found_in_window(clean_database, valid_gp_record) -> None:
    """Deterministic negative case: mock "now" to Vanguard 1's own epoch,
    but place the observer on the opposite side of the Earth from its
    sub-satellite point (the same "no pass" geometry used in Phase 3's
    core tests) - guaranteed no pass in a short window, unlike testing
    against the real wall-clock "now" (which can spuriously find a pass
    after decades of SGP4 extrapolation from 26-year-old elements)."""
    _override_satellite_service(valid_gp_record)
    try:
        from unittest.mock import patch

        with patch("app.api.routes_passes.datetime") as mock_datetime:
            mock_datetime.now.return_value = VANGUARD1_EPOCH - timedelta(minutes=15)

            response = client.get(
                "/api/passes/next",
                params={
                    "norad_id": 5,
                    "latitude_deg": 0.0,
                    "longitude_deg": -30.05,  # opposite side of Earth
                    "within_hours": 0.5,
                },
            )
        assert response.status_code == 404

        search_response = client.get("/api/passes/search?norad_id=5")
        assert search_response.json() == []
    finally:
        _clear_overrides()


def test_next_pass_finds_real_overhead_pass_in_a_window_around_its_epoch(
    clean_database, valid_gp_record
) -> None:
    """Unlike the "now" test above, this searches a small window placed
    right around Vanguard 1's actual epoch - the same guaranteed-overhead
    geometry used elsewhere - to confirm /next can actually find and
    score a real pass, not just handle the not-found case."""
    _override_satellite_service(valid_gp_record)
    try:
        from unittest.mock import patch

        with patch("app.api.routes_passes.datetime") as mock_datetime:
            mock_datetime.now.return_value = VANGUARD1_EPOCH - timedelta(minutes=15)

            response = client.get(
                "/api/passes/next",
                params={
                    "norad_id": 5,
                    "latitude_deg": OVERHEAD_LAT,
                    "longitude_deg": OVERHEAD_LON,
                    "within_hours": 0.5,
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] is None
        assert body["observer_id"] is None
        assert body["pass_event"]["max_elevation_deg"] > 85.0

        # Confirm it really wasn't persisted.
        search_response = client.get("/api/passes/search?norad_id=5")
        assert search_response.json() == []
    finally:
        _clear_overrides()


def test_next_pass_requires_latitude_and_longitude(clean_database) -> None:
    response = client.get("/api/passes/next", params={"norad_id": 5})
    assert response.status_code == 422
