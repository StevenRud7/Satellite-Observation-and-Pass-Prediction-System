from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_observer_returns_201_with_id(clean_database) -> None:
    response = client.post(
        "/api/observers",
        json={"name": "Home", "latitude_deg": 32.08, "longitude_deg": 34.78, "altitude_m": 5.0},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Home"
    assert body["latitude_deg"] == 32.08


def test_create_observer_rejects_invalid_latitude(clean_database) -> None:
    response = client.post("/api/observers", json={"latitude_deg": 200.0, "longitude_deg": 34.78})
    assert response.status_code == 422


def test_list_observers_returns_all_created(clean_database) -> None:
    client.post("/api/observers", json={"latitude_deg": 1.0, "longitude_deg": 1.0})
    client.post("/api/observers", json={"latitude_deg": 2.0, "longitude_deg": 2.0})

    response = client.get("/api/observers")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_observer_by_id(clean_database) -> None:
    created = client.post(
        "/api/observers", json={"name": "Cabin", "latitude_deg": 45.0, "longitude_deg": -70.0}
    ).json()

    response = client.get(f"/api/observers/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Cabin"


def test_get_observer_returns_404_for_unknown_id(clean_database) -> None:
    response = client.get("/api/observers/999999")
    assert response.status_code == 404


def test_delete_observer_returns_204_then_get_returns_404(clean_database) -> None:
    created = client.post("/api/observers", json={"latitude_deg": 0.0, "longitude_deg": 0.0}).json()

    delete_response = client.delete(f"/api/observers/{created['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/observers/{created['id']}")
    assert get_response.status_code == 404


def test_delete_observer_returns_404_for_unknown_id(clean_database) -> None:
    response = client.delete("/api/observers/999999")
    assert response.status_code == 404


def test_observer_endpoints_return_503_when_no_database_configured(monkeypatch) -> None:
    """A missing database surfaces as a clean 503 with setup guidance, not
    a raw connection error - see app/api/error_handlers.py."""
    from app.core.config import Settings
    from app.db import session as db_session_module

    monkeypatch.setattr(db_session_module, "get_settings", lambda: Settings(database_url=None))
    db_session_module.reset_engine_cache()
    try:
        response = client.get("/api/observers")
        assert response.status_code == 503
        assert "database" in response.json()["detail"].lower()
    finally:
        db_session_module.reset_engine_cache()
