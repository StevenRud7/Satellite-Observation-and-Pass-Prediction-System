"""
Secondary live orbital data source: the public TLE API
(https://tle.ivanstanojevic.me, listed on api.nasa.gov), which republishes
CelesTrak's GP data (refreshed daily) as JSON.

Why: when CelesTrak itself can't be reached from the hosting provider, this
is a *different host* that usually can be - so the app can still get a real,
recent TLE for any satellite (not just the curated catalog the static
snapshot covers). It is only consulted after a live CelesTrak fetch has
failed, never instead of it, and it is a free community service with no
uptime guarantee - so every failure here is treated as "no data", never as
an error the user sees.

Response shape (verified against the live service):

    single:  GET {base}/{norad_id} ->
             {"satelliteId": 25544, "name": "ISS (ZARYA)", "date": "...",
              "line1": "1 25544U ...", "line2": "2 25544 ..."}
    search:  GET {base}?search={q}&page-size={n} ->
             {"member": [ {same record shape}, ... ], ...}
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from app.core.logging import get_logger
from app.data.exceptions import OrbitalDataValidationError
from app.data.snapshot import record_from_tle
from app.schemas.satellite import SatelliteRecord, SatelliteSearchResult

logger = get_logger(__name__)

TLE_API_SOURCE_NAME = "tle-api"
DEFAULT_BASE_URL = "https://tle.ivanstanojevic.me/api/tle"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_USER_AGENT = "satellite-pass-predictor/1.0"


def build_http_client(force_ipv4: bool) -> httpx.Client:
    """Shared client builder. `force_ipv4` binds outgoing sockets to the IPv4
    wildcard address, which stops a host with broken/black-holed IPv6 routing
    from stalling on an unreachable IPv6 address before trying IPv4."""
    transport = httpx.HTTPTransport(local_address="0.0.0.0") if force_ipv4 else None
    return httpx.Client(timeout=_TIMEOUT, transport=transport, headers={"User-Agent": _USER_AGENT})


class TleApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        http_client: Optional[httpx.Client] = None,
        cooldown_seconds: float = 90.0,
        enabled: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client or build_http_client(force_ipv4=False)
        self._cooldown_seconds = cooldown_seconds
        self._enabled = enabled
        self._unreachable_until = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        if not self._enabled or time.monotonic() < self._unreachable_until:
            return None
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            self._unreachable_until = time.monotonic() + self._cooldown_seconds
            logger.warning("TLE API unreachable: %s", exc or type(exc).__name__)
            return None
        self._unreachable_until = 0.0
        if response.status_code != 200:
            logger.info("TLE API returned HTTP %s for %s", response.status_code, url)
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def fetch(self, norad_id: int) -> Optional[SatelliteRecord]:
        payload = self._get_json(f"{self._base_url}/{norad_id}")
        if payload is None:
            return None
        return _record_from_payload(payload, expected_norad_id=norad_id)

    def search(self, name: str, limit: int = 20) -> List[SatelliteSearchResult]:
        payload = self._get_json(self._base_url, params={"search": name, "page-size": limit})
        if payload is None:
            return []
        results: List[SatelliteSearchResult] = []
        for member in payload.get("member", [])[:limit]:
            try:
                results.append(
                    SatelliteSearchResult(
                        norad_id=int(member["satelliteId"]), name=str(member["name"])
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return results


def _record_from_payload(payload: dict, expected_norad_id: int) -> Optional[SatelliteRecord]:
    try:
        return record_from_tle(
            expected_norad_id,
            str(payload.get("name") or f"NORAD {expected_norad_id}"),
            str(payload.get("line1", "")).rstrip(),
            str(payload.get("line2", "")).rstrip(),
            retrieved_at=datetime.now(timezone.utc),
            source=TLE_API_SOURCE_NAME,
        )
    except (OrbitalDataValidationError, ValueError) as exc:
        logger.warning("Ignoring bad TLE API record for NORAD ID %s: %s", expected_norad_id, exc)
        return None
