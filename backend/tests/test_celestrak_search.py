import httpx
import pytest

from app.data.celestrak import CelestrakClient
from app.data.exceptions import CelestrakClientError


def _client_with_response(handler) -> CelestrakClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return CelestrakClient(http_client=http_client)


def test_search_by_name_returns_hits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["NAME"] == "STARLINK"
        assert request.url.params["FORMAT"] == "JSON"
        return httpx.Response(
            200,
            json=[
                {"NORAD_CAT_ID": 44713, "OBJECT_NAME": "STARLINK-1007"},
                {"NORAD_CAT_ID": 44714, "OBJECT_NAME": "STARLINK-1008"},
            ],
        )

    client = _client_with_response(handler)
    results = client.search_by_name("STARLINK")

    assert [r.norad_id for r in results] == [44713, 44714]
    assert results[0].name == "STARLINK-1007"


def test_search_by_name_respects_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"NORAD_CAT_ID": i, "OBJECT_NAME": f"SAT-{i}"} for i in range(10)],
        )

    client = _client_with_response(handler)
    results = client.search_by_name("SAT", limit=3)

    assert len(results) == 3


def test_search_by_name_skips_malformed_hits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"NORAD_CAT_ID": "not-a-number", "OBJECT_NAME": "BAD"},
                {"OBJECT_NAME": "MISSING_ID"},
                {"NORAD_CAT_ID": 25544, "OBJECT_NAME": "ISS (ZARYA)"},
            ],
        )

    client = _client_with_response(handler)
    results = client.search_by_name("x")

    assert len(results) == 1
    assert results[0].norad_id == 25544


def test_search_by_name_raises_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    client = _client_with_response(handler)

    with pytest.raises(CelestrakClientError, match="503"):
        client.search_by_name("x")
