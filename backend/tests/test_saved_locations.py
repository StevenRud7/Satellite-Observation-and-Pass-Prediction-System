"""Saved locations must only ever contain locations the person explicitly
saved - never rows created as a side effect of predicting passes - and
saving the same place twice must not create a duplicate."""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_satellite_service
from app.data.celestrak import CelestrakClient
from app.data.postgres_cache import PostgresSatelliteCache
from app.db.repositories.observer_repository import ObserverRepository
from app.main import app
from app.schemas.observer import ObserverLocation
from app.services.satellite_service import SatelliteService

client = TestClient(app)

_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
_EPOCH = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)


def test_working_observer_is_not_listed_as_saved(db_session) -> None:
    repo = ObserverRepository(db_session)
    working_id = repo.get_or_create_working(
        ObserverLocation(name="X", latitude_deg=1, longitude_deg=2)
    )

    assert repo.get(working_id) is not None
    assert repo.list_all(saved_only=True) == []
    assert len(repo.list_all()) == 1


def test_get_or_create_working_reuses_identical_row(db_session) -> None:
    repo = ObserverRepository(db_session)
    place = ObserverLocation(name="X", latitude_deg=1, longitude_deg=2)

    first = repo.get_or_create_working(place)
    second = repo.get_or_create_working(place)

    assert first == second
    assert len(repo.list_all()) == 1


def test_save_marks_working_row_saved_instead_of_duplicating(db_session) -> None:
    repo = ObserverRepository(db_session)
    place = ObserverLocation(name="X", latitude_deg=1, longitude_deg=2)
    working_id = repo.get_or_create_working(place)

    saved_id = repo.save(place)
    saved_again = repo.save(place)

    assert saved_id == working_id == saved_again
    assert [i for i, _ in repo.list_all(saved_only=True)] == [working_id]


def test_same_coordinates_with_a_different_label_are_separate_saves(db_session) -> None:
    repo = ObserverRepository(db_session)
    a = repo.save(ObserverLocation(name="Home", latitude_deg=1, longitude_deg=2))
    b = repo.save(ObserverLocation(name="Cabin", latitude_deg=1, longitude_deg=2))
    assert a != b


def test_saving_same_place_twice_via_api_lists_it_once(clean_database) -> None:
    body = {"name": "Home", "latitude_deg": 40.7, "longitude_deg": -74.0, "altitude_m": 10}
    first = client.post("/api/observers", json=body).json()
    second = client.post("/api/observers", json=body).json()

    assert first["id"] == second["id"]
    assert len(client.get("/api/observers").json()) == 1


def test_predicting_passes_never_adds_to_saved_locations(clean_database, valid_gp_record) -> None:
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
        request = {
            "norad_id": 5,
            "latitude_deg": 0.0,
            "longitude_deg": 149.95,
            "observer_name": "Somewhere",
            "start": (_EPOCH - timedelta(minutes=15)).isoformat(),
            "end": (_EPOCH + timedelta(minutes=15)).isoformat(),
            "min_elevation_deg": 10.0,
        }
        for _ in range(3):  # like clicking the same pass (or several) repeatedly
            response = client.post("/api/passes/predict", json=request)
            assert response.status_code == 200
            assert len(response.json()) == 1

        assert client.get("/api/observers").json() == []

        # ...and explicitly saving that place afterwards lists it exactly once.
        saved = client.post(
            "/api/observers",
            json={"name": "Somewhere", "latitude_deg": 0.0, "longitude_deg": 149.95},
        ).json()
        listed = client.get("/api/observers").json()
        assert [o["id"] for o in listed] == [saved["id"]]
    finally:
        app.dependency_overrides.pop(get_satellite_service, None)