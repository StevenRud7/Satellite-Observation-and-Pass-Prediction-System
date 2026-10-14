"""
CelesTrak client.

Fetches current General Perturbations (GP) data for a single satellite by
NORAD catalog ID from CelesTrak (https://celestrak.org), the primary real
orbital data source for this project.

This takes two separate requests, because CelesTrak's two output formats
carry different, non-overlapping information:

- `FORMAT=JSON` returns the OMM (Orbit Mean-Elements Message) keyword
  fields (OBJECT_NAME, MEAN_MOTION, ECCENTRICITY, INCLINATION, ...) as
  structured JSON - convenient, but it does NOT include the raw TLE line
  text.
- `FORMAT=2LE` returns exactly that raw TLE line text, as two plain lines
  (not JSON) - which is what `Satrec.twoline2rv` (see
  app/core/propagation.py) actually needs to propagate the orbit. Per
  CelesTrak's own documentation, `FORMAT=TLE` (or `3LE`) would return a
  *three*-line response (a satellite-name line plus the same two data
  lines) - `2LE` is specifically the two-data-lines-only format, which is
  what's wanted here since the name already comes from the JSON request.
  `_fetch_tle_lines` below also doesn't just assume "exactly 2 lines
  back": it picks out the lines starting with "1 " and "2 " specifically,
  so an unexpected extra line (e.g. if CelesTrak's formats change again)
  fails loudly rather than silently propagating a wrong orbit.

(An earlier version of this client assumed the JSON response included
TLE_LINE1/TLE_LINE2 fields directly. It doesn't - CelesTrak's JSON schema
is OMM-keywords-only. That assumption was never caught locally because
tests mocked the HTTP response with fabricated JSON matching the wrong
assumption, and the mismatch only showed up as an
`OrbitalDataValidationError: ... missing fields: ['TLE_LINE1', 'TLE_LINE2']`
against the real API. A follow-up attempt to fix that by requesting
`FORMAT=TLE` hit the "TLE is really 3LE" quirk described above and failed
with `... had 3 non-blank line(s), expected 2` - also only visible
against the real API, for the same reason.)

The HTTP client is injectable so tests can supply a mocked transport
instead of making real network calls. The default timeout is
more generous than httpx's own 5s default (since cached/snapshot/TLE-API
fallbacks now exist, it is no longer the 30s it once was): on free-tier hosts
(e.g. Render) outbound requests share an IP across many unrelated
accounts, and CelesTrak can be slow - or effectively unreachable for a
window - for reasons that have nothing to do with this app's own code.
A longer timeout gives a slow-but-working response more room to succeed
rather than failing before CelesTrak even gets a chance to answer.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.logging import get_logger
from app.data.exceptions import CelestrakClientError, SatelliteNotFoundError
from app.data.validation import validate_gp_record, validate_tle_lines
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord, SatelliteSearchResult

logger = get_logger(__name__)

CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
DATA_SOURCE_NAME = "celestrak"

# See the module docstring above for why this is more generous than
# httpx's own 5-second default.
DEFAULT_TIMEOUT_SECONDS = 15.0

# Connecting is capped much lower than reading: a host that can't reach
# CelesTrak at all (blocked/dropped connections) should fail in seconds and
# fall back to cached/snapshot data, not sit through a full 30s per attempt.
CONNECT_TIMEOUT_SECONDS = 8.0

# After a network-level failure, skip live attempts for this long (seconds)
# so repeated requests don't each wait out another timeout. Overridable via
# Settings.celestrak_unreachable_cooldown_seconds (wired in deps.py).
DEFAULT_UNREACHABLE_COOLDOWN_SECONDS = 90.0


class CelestrakClient:
    """Thin, testable wrapper around CelesTrak's GP query API."""

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        unreachable_cooldown_seconds: float = DEFAULT_UNREACHABLE_COOLDOWN_SECONDS,
        force_ipv4: bool = False,
    ) -> None:
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(timeout, CONNECT_TIMEOUT_SECONDS)),
            transport=httpx.HTTPTransport(local_address="0.0.0.0") if force_ipv4 else None,
            headers={"User-Agent": "satellite-pass-predictor/1.0"},
        )
        self._owns_client = http_client is None
        self._cooldown_seconds = unreachable_cooldown_seconds
        self._unreachable_until = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> CelestrakClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def fetch_satellite_by_norad_id(self, norad_id: int) -> SatelliteRecord:
        """Fetch, validate, and parse the current orbital elements for one satellite.

        Raises:
            SatelliteNotFoundError: CelesTrak has no data for this NORAD ID.
            CelestrakClientError: a request failed or its response was unusable.
            OrbitalDataValidationError: a response was structurally invalid or
                physically implausible.
        """
        if time.monotonic() < self._unreachable_until:
            raise CelestrakClientError(
                "Could not reach CelesTrak: it was unreachable moments ago, "
                "so live fetching is paused briefly"
            )

        # The two requests are independent, so they run concurrently: on a
        # slow link that halves the time spent waiting on CelesTrak. Results
        # are still *consumed* in the original order (JSON, validate it, then
        # TLE lines, validate those), so error precedence is unchanged.
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                json_future = pool.submit(self._fetch_gp_json, norad_id)
                tle_future = pool.submit(self._fetch_tle_lines, norad_id)
                record = json_future.result()
                retrieved_at = datetime.now(timezone.utc)
                validate_gp_record(record, expected_norad_id=norad_id)
                line1, line2 = tle_future.result()
        except CelestrakClientError as exc:
            if _is_network_failure(exc):
                self._unreachable_until = time.monotonic() + self._cooldown_seconds
            raise
        self._unreachable_until = 0.0

        validate_tle_lines(line1, line2)

        return _to_satellite_record(record, line1=line1, line2=line2, retrieved_at=retrieved_at)

    def _fetch_gp_json(self, norad_id: int) -> Dict[str, Any]:
        params = {"CATNR": str(norad_id), "FORMAT": "JSON"}

        logger.info("Fetching NORAD ID %s from CelesTrak", norad_id)

        try:
            response = self._client.get(CELESTRAK_GP_URL, params=params)
        except httpx.HTTPError as exc:
            raise CelestrakClientError(
                f"Could not reach CelesTrak: {exc or type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            raise CelestrakClientError(
                f"CelesTrak returned HTTP {response.status_code} for NORAD ID {norad_id}"
            )

        try:
            payload: List[Dict[str, Any]] = response.json()
        except ValueError as exc:
            raise CelestrakClientError("CelesTrak response was not valid JSON") from exc

        if not payload:
            raise SatelliteNotFoundError(f"No CelesTrak data found for NORAD ID {norad_id}")

        return payload[0]

    def _fetch_tle_lines(self, norad_id: int) -> Tuple[str, str]:
        params = {"CATNR": str(norad_id), "FORMAT": "2LE"}

        logger.info("Fetching TLE lines for NORAD ID %s from CelesTrak", norad_id)

        try:
            response = self._client.get(CELESTRAK_GP_URL, params=params)
        except httpx.HTTPError as exc:
            raise CelestrakClientError(f"Could not reach CelesTrak: {exc}") from exc

        if response.status_code != 200:
            raise CelestrakClientError(
                f"CelesTrak returned HTTP {response.status_code} for NORAD ID {norad_id}"
            )

        lines = [line for line in response.text.splitlines() if line.strip()]
        # Pick out the two data lines by their required line-number prefix
        # rather than assuming a fixed line count: CelesTrak's `2LE` format
        # is documented as exactly these two lines with no name line, but
        # parsing this way means a stray extra/missing line (whether from
        # a future CelesTrak change or an unexpected response) fails
        # loudly here instead of silently mis-propagating an orbit.
        line1 = next((line for line in lines if line.startswith("1 ")), None)
        line2 = next((line for line in lines if line.startswith("2 ")), None)

        if line1 is None or line2 is None:
            raise CelestrakClientError(
                f"CelesTrak TLE response for NORAD ID {norad_id} did not contain both "
                f"TLE lines (got {len(lines)} non-blank line(s))"
            )

        return line1, line2

    def search_by_name(self, name: str, limit: int = 20) -> List[SatelliteSearchResult]:
        """Look up satellites by (partial, case-insensitive) name.

        Unlike `fetch_satellite_by_norad_id`, this deliberately does NOT run
        full orbital-data validation on every hit: a name search can return
        many objects (including decayed ones with incomplete data), and one
        malformed record shouldn't take down the whole search - it is simply
        skipped. Callers that want to actually use a result still go through
        `fetch_satellite_by_norad_id` (or the cache-backed satellite service)
        to get validated orbital elements.

        Raises:
            CelestrakClientError: the request failed or the response was unusable.
        """
        params = {"NAME": name, "FORMAT": "JSON"}

        logger.info("Searching CelesTrak for name %r", name)

        try:
            response = self._client.get(CELESTRAK_GP_URL, params=params)
        except httpx.HTTPError as exc:
            raise CelestrakClientError(f"Could not reach CelesTrak: {exc}") from exc

        if response.status_code != 200:
            raise CelestrakClientError(
                f"CelesTrak returned HTTP {response.status_code} searching for {name!r}"
            )

        try:
            payload: List[Dict[str, Any]] = response.json()
        except ValueError as exc:
            raise CelestrakClientError("CelesTrak response was not valid JSON") from exc

        results: List[SatelliteSearchResult] = []
        for record in payload[:limit]:
            hit = _to_search_result(record)
            if hit is not None:
                results.append(hit)
        return results


def _is_network_failure(exc: Exception) -> bool:
    """True for "couldn't reach CelesTrak at all" (timeout, refused/dropped
    connection) as opposed to CelesTrak answering with an error status or
    unusable data - only the former should trigger the cooldown."""
    return str(exc).startswith("Could not reach CelesTrak")


def _to_search_result(record: Dict[str, Any]) -> Optional[SatelliteSearchResult]:
    try:
        return SatelliteSearchResult(
            norad_id=int(record["NORAD_CAT_ID"]),
            name=str(record["OBJECT_NAME"]),
        )
    except (KeyError, TypeError, ValueError):
        # Missing/malformed fields on one hit shouldn't fail the whole search.
        return None


def _to_satellite_record(
    record: Dict[str, Any], line1: str, line2: str, retrieved_at: datetime
) -> SatelliteRecord:
    elements = OrbitalElementSet(
        epoch=datetime.fromisoformat(record["EPOCH"]).replace(tzinfo=timezone.utc),
        line1=line1,
        line2=line2,
        mean_motion=float(record["MEAN_MOTION"]),
        eccentricity=float(record["ECCENTRICITY"]),
        inclination_deg=float(record["INCLINATION"]),
        raan_deg=float(record["RA_OF_ASC_NODE"]),
        arg_perigee_deg=float(record["ARG_OF_PERICENTER"]),
        mean_anomaly_deg=float(record["MEAN_ANOMALY"]),
        bstar=float(record["BSTAR"]),
        element_set_number=int(record["ELEMENT_SET_NO"]),
        revolution_number=int(record["REV_AT_EPOCH"]),
        source=DATA_SOURCE_NAME,
        retrieved_at=retrieved_at,
    )

    return SatelliteRecord(
        norad_id=int(record["NORAD_CAT_ID"]),
        name=record["OBJECT_NAME"],
        international_designator=record.get("OBJECT_ID"),
        object_type=None,
        orbital_elements=elements,
    )
