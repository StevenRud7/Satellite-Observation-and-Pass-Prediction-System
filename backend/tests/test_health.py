from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_shape() -> None:
    response = client.get("/health")
    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "satellite-observation-api"
    assert "timestamp" in body


def test_health_wrong_method_not_allowed() -> None:
    response = client.post("/health")
    assert response.status_code == 405
