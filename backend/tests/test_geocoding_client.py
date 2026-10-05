import httpx
import pytest

from app.data.exceptions import GeocodingError
from app.data.geocoding import GeocodingClient


def _client_with_response(handler) -> GeocodingClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return GeocodingClient(http_client=http_client)


def test_search_returns_parsed_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "Tel Aviv"
        assert request.headers["User-Agent"].startswith("satellite-observation-system")
        return httpx.Response(
            200,
            json=[
                {
                    "display_name": "Tel Aviv-Yafo, Tel Aviv District, Israel",
                    "lat": "32.0853",
                    "lon": "34.7818",
                    "type": "city",
                    "address": {"country": "Israel"},
                }
            ],
        )

    client = _client_with_response(handler)
    results = client.search("Tel Aviv")

    assert len(results) == 1
    assert results[0].display_name == "Tel Aviv-Yafo, Tel Aviv District, Israel"
    assert results[0].latitude_deg == pytest.approx(32.0853)
    assert results[0].longitude_deg == pytest.approx(34.7818)
    assert results[0].place_type == "city"
    assert results[0].country == "Israel"


def test_search_skips_malformed_entries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"display_name": "Bad entry", "lat": "not-a-number", "lon": "34.7818"},
                {"display_name": "Good entry", "lat": "1.0", "lon": "2.0"},
            ],
        )

    client = _client_with_response(handler)
    results = client.search("x")

    assert len(results) == 1
    assert results[0].display_name == "Good entry"


def test_search_raises_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    client = _client_with_response(handler)

    with pytest.raises(GeocodingError, match="503"):
        client.search("x")


def test_search_raises_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_response(handler)

    with pytest.raises(GeocodingError, match="Could not reach"):
        client.search("x")


def test_search_raises_on_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = _client_with_response(handler)

    with pytest.raises(GeocodingError, match="not valid JSON"):
        client.search("x")
