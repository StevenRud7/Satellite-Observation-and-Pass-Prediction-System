import httpx
import pytest

from app.data.celestrak import CelestrakClient
from app.data.exceptions import (
    CelestrakClientError,
    OrbitalDataValidationError,
    SatelliteNotFoundError,
)


def _client_with_response(handler) -> CelestrakClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return CelestrakClient(http_client=http_client)


def _json_then_tle_handler(gp_record: dict, tle_text: str):
    """Real CelesTrak needs two requests (see app/data/celestrak.py): this
    dispatches on the FORMAT query param the way the live API would.
    `tle_text` is returned verbatim for the FORMAT=2LE request, so tests
    can exercise both the well-formed 2-line response and CelesTrak's
    "TLE/3LE actually means 3 lines" quirk (see the malformed-response
    test below) without changing this handler."""

    def handler(request: httpx.Request) -> httpx.Response:
        fmt = request.url.params["FORMAT"]
        if fmt == "JSON":
            return httpx.Response(200, json=[gp_record])
        if fmt == "2LE":
            return httpx.Response(200, text=tle_text)
        raise AssertionError(f"Unexpected FORMAT: {fmt}")

    return handler


def test_fetch_satellite_requests_2le_not_tle(valid_gp_record: dict, valid_tle_lines) -> None:
    """Regression test: CelesTrak documents FORMAT=TLE as an alias for
    FORMAT=3LE (name line + 2 data lines), NOT a 2-line-only response.
    FORMAT=2LE is the one that omits the name line. Requesting FORMAT=TLE
    here previously failed against the real API with
    "had 3 non-blank line(s), expected 2" - this pins down which FORMAT
    value is actually sent."""
    line1, line2 = valid_tle_lines
    seen_formats = []

    def handler(request: httpx.Request) -> httpx.Response:
        fmt = request.url.params["FORMAT"]
        seen_formats.append(fmt)
        if fmt == "JSON":
            return httpx.Response(200, json=[valid_gp_record])
        return httpx.Response(200, text=f"{line1}\n{line2}\n")

    client = _client_with_response(handler)
    client.fetch_satellite_by_norad_id(5)

    assert "2LE" in seen_formats
    assert "TLE" not in seen_formats
    assert "3LE" not in seen_formats


def test_fetch_satellite_returns_parsed_record(valid_gp_record: dict, valid_tle_lines) -> None:
    line1, line2 = valid_tle_lines
    handler = _json_then_tle_handler(valid_gp_record, f"{line1}\n{line2}\n")

    client = _client_with_response(handler)
    record = client.fetch_satellite_by_norad_id(5)

    assert record.norad_id == 5
    assert record.name == "VANGUARD 1"
    assert record.international_designator == "1958-002B"
    assert record.orbital_elements.line1 == line1
    assert record.orbital_elements.line2 == line2
    assert record.orbital_elements.source == "celestrak"
    assert record.orbital_elements.retrieved_at is not None


def test_fetch_satellite_tolerates_a_stray_name_line(
    valid_gp_record: dict, valid_tle_lines
) -> None:
    """Even for FORMAT=2LE, be defensive: if a name line ever shows up
    anyway (a future CelesTrak change, a misconfigured mirror, etc.), the
    two real data lines should still be found by their "1 "/"2 " prefix
    rather than the whole fetch failing."""
    line1, line2 = valid_tle_lines
    handler = _json_then_tle_handler(valid_gp_record, f"VANGUARD 1\n{line1}\n{line2}\n")

    client = _client_with_response(handler)
    record = client.fetch_satellite_by_norad_id(5)

    assert record.orbital_elements.line1 == line1
    assert record.orbital_elements.line2 == line2


def test_fetch_satellite_raises_not_found_on_empty_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = _client_with_response(handler)

    with pytest.raises(SatelliteNotFoundError):
        client.fetch_satellite_by_norad_id(999999)


def test_fetch_satellite_raises_client_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    client = _client_with_response(handler)

    with pytest.raises(CelestrakClientError, match="503"):
        client.fetch_satellite_by_norad_id(5)


def test_fetch_satellite_raises_client_error_on_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = _client_with_response(handler)

    with pytest.raises(CelestrakClientError, match="not valid JSON"):
        client.fetch_satellite_by_norad_id(5)


def test_fetch_satellite_raises_client_error_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_response(handler)

    with pytest.raises(CelestrakClientError, match="Could not reach CelesTrak"):
        client.fetch_satellite_by_norad_id(5)


def test_fetch_satellite_raises_validation_error_on_missing_gp_field(valid_gp_record: dict) -> None:
    del valid_gp_record["MEAN_MOTION"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[valid_gp_record])

    client = _client_with_response(handler)

    with pytest.raises(OrbitalDataValidationError, match="missing fields"):
        client.fetch_satellite_by_norad_id(5)


def test_fetch_satellite_raises_validation_error_on_bad_checksum(
    valid_gp_record: dict, valid_tle_lines
) -> None:
    line1, line2 = valid_tle_lines
    bad_line1 = line1[:-1] + ("9" if line1[-1] != "9" else "8")
    handler = _json_then_tle_handler(valid_gp_record, f"{bad_line1}\n{line2}\n")

    client = _client_with_response(handler)

    with pytest.raises(OrbitalDataValidationError, match="checksum"):
        client.fetch_satellite_by_norad_id(5)


def test_fetch_satellite_raises_client_error_on_malformed_tle_response(
    valid_gp_record: dict,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["FORMAT"] == "JSON":
            return httpx.Response(200, json=[valid_gp_record])
        # A satellite with no current GP data returns an empty/near-empty
        # body for FORMAT=2LE even when FORMAT=JSON still lists it.
        return httpx.Response(200, text="\n")

    client = _client_with_response(handler)

    with pytest.raises(CelestrakClientError, match="did not contain both"):
        client.fetch_satellite_by_norad_id(5)
