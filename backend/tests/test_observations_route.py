from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_satellite_service
from app.data.celestrak import CelestrakClient
from app.data.postgres_cache import PostgresSatelliteCache
from app.main import app
from app.services.satellite_service import SatelliteService

client = TestClient(app)

VANGUARD1_EPOCH = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)

# Real, well-known reference TLE lines (see tests/conftest.py's
# SAMPLE_TLE_LINE1/2). CelesTrak's JSON GP format doesn't include raw TLE
# line text (see app/data/celestrak.py), so the mocked transport below
# has to answer the separate FORMAT=TLE request too.
_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def _override(valid_gp_record: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["FORMAT"] == "JSON":
            return httpx.Response(200, json=[valid_gp_record])
        return httpx.Response(200, text=f"{_LINE1}\n{_LINE2}\n")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    service = SatelliteService(
        client=CelestrakClient(http_client=http_client),
        cache=PostgresSatelliteCache(ttl_seconds=3600),
    )
    app.dependency_overrides[get_satellite_service] = lambda: service


def test_best_observations_returns_scored_ranked_pass(clean_database, valid_gp_record) -> None:
    _override(valid_gp_record)
    try:
        with patch("app.api.routes_observations.datetime") as mock_datetime:
            mock_datetime.now.return_value = VANGUARD1_EPOCH - timedelta(minutes=15)

            response = client.get(
                "/api/observations/best",
                params={
                    "latitude_deg": 0.0,
                    "longitude_deg": 149.95,
                    "within_hours": 0.5,
                    "norad_ids": [5],
                },
            )

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["norad_id"] == 5
        assert 0 <= results[0]["visibility"]["score"] <= 100
    finally:
        app.dependency_overrides.clear()


def test_best_observations_empty_when_min_score_too_high(clean_database, valid_gp_record) -> None:
    _override(valid_gp_record)
    try:
        with patch("app.api.routes_observations.datetime") as mock_datetime:
            mock_datetime.now.return_value = VANGUARD1_EPOCH - timedelta(minutes=15)

            response = client.get(
                "/api/observations/best",
                params={
                    "latitude_deg": 0.0,
                    "longitude_deg": 149.95,
                    "within_hours": 0.5,
                    "norad_ids": [5],
                    "min_score": 100,
                },
            )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()
