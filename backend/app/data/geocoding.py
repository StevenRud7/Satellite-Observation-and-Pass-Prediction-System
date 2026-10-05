"""
Geocoding client - resolves a typed place name ("Tel Aviv", "Camden, London")
to coordinates, so the location form can accept cities and districts as well
as raw latitude/longitude.

Uses OpenStreetMap's Nominatim search API (https://nominatim.org), which is
free and needs no API key. Nominatim's usage policy asks for a descriptive
User-Agent and no more than ~1 request/second from a given client; the route
that calls this (`GET /api/geocode`) caches results briefly (see
`app/api/routes_geocoding.py`) precisely to stay well under that.

Like `CelestrakClient`, the HTTP client is injectable so tests can supply a
mocked transport instead of making real network calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.core.logging import get_logger
from app.data.exceptions import GeocodingError
from app.schemas.geocoding import GeocodeResult

logger = get_logger(__name__)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim asks API consumers to identify themselves with a descriptive
# User-Agent rather than a generic HTTP client string.
_USER_AGENT = "satellite-observation-system/0.1 (personal project; contact via project README)"


class GeocodingClient:
    """Thin, testable wrapper around Nominatim's place-search API."""

    def __init__(self, http_client: Optional[httpx.Client] = None, timeout: float = 10.0) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GeocodingClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def search(self, query: str, limit: int = 6) -> List[GeocodeResult]:
        """Look up places (cities, districts, towns, landmarks) by free-text name.

        Raises:
            GeocodingError: the request failed or the response was unusable.
        """
        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": str(limit),
        }
        headers = {"User-Agent": _USER_AGENT}

        logger.info("Geocoding query %r", query)

        try:
            response = self._client.get(NOMINATIM_SEARCH_URL, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise GeocodingError(f"Could not reach the place-search service: {exc}") from exc

        if response.status_code != 200:
            raise GeocodingError(f"Place-search service returned HTTP {response.status_code}")

        try:
            payload: List[Dict[str, Any]] = response.json()
        except ValueError as exc:
            raise GeocodingError("Place-search response was not valid JSON") from exc

        results = []
        for record in payload:
            parsed = _to_geocode_result(record)
            if parsed is not None:
                results.append(parsed)
        return results


def _to_geocode_result(record: Dict[str, Any]) -> Optional[GeocodeResult]:
    try:
        latitude_deg = float(record["lat"])
        longitude_deg = float(record["lon"])
    except (KeyError, TypeError, ValueError):
        # Malformed entry - skip it rather than failing the whole search.
        return None

    if not (-90 <= latitude_deg <= 90 and -180 <= longitude_deg <= 180):
        return None

    address: Dict[str, Any] = record.get("address") or {}
    place_type = record.get("type") or record.get("class")

    return GeocodeResult(
        display_name=record.get("display_name", f"{latitude_deg:.4f}, {longitude_deg:.4f}"),
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        place_type=place_type,
        country=address.get("country"),
    )
