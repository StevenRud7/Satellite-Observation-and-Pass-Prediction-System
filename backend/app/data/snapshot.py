"""
Last-resort orbital data source: a JSON snapshot of TLEs for the curated
satellite catalog, refreshed on a schedule by a GitHub Actions workflow
(`.github/workflows/update-tle-snapshot.yml`, which runs
`scripts/update_tle_snapshot.py`) and served as a static file.

Why this exists: CelesTrak can be slow or effectively unreachable from
free-tier hosts (shared outbound IPs). When a live fetch fails and there is
no recent enough cached copy, falling back to a snapshot that was fetched
politely, a few times a day, from somewhere else means the app still
produces real passes instead of an error. It is only ever consulted AFTER a
live fetch has failed - it never replaces live data when live data works.

Snapshot format:

    {"generated_at": "2026-10-14T06:00:00+00:00",
     "satellites": {"25544": {"name": "ISS (ZARYA)", "line1": "1 ...", "line2": "2 ..."}}}

The orbital-element fields are parsed straight out of the TLE columns (the
snapshot stores only the raw lines, which is all SGP4 needs), then go
through the same TLE validation as live data.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.logging import get_logger
from app.data.exceptions import OrbitalDataValidationError
from app.data.validation import validate_tle_lines
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord, SatelliteSearchResult

logger = get_logger(__name__)

SNAPSHOT_SOURCE_NAME = "celestrak-snapshot"
_SNAPSHOT_CACHE_SECONDS = 15 * 60
_SNAPSHOT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _parse_tle_exponent_field(raw: str) -> float:
    """Parse TLE's implied-decimal exponent fields, e.g. ' 38792-4' -> 3.8792e-5."""
    raw = raw.strip()
    if not raw:
        return 0.0
    mantissa, exponent = raw[:-2], raw[-2:]
    sign = -1.0 if mantissa.startswith("-") else 1.0
    digits = mantissa.lstrip("+-").strip()
    return sign * float("0." + digits) * (10.0 ** int(exponent))


def _tle_epoch(line1: str) -> datetime:
    year_2digit = int(line1[18:20])
    year = 2000 + year_2digit if year_2digit < 57 else 1900 + year_2digit
    day_of_year = float(line1[20:32])
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_of_year - 1.0)


def _intl_designator(line1: str) -> Optional[str]:
    raw = line1[9:17].strip()
    if len(raw) < 5:
        return None
    year_2digit = int(raw[:2])
    year = 2000 + year_2digit if year_2digit < 57 else 1900 + year_2digit
    return f"{year}-{raw[2:5]}{raw[5:]}"


def record_from_tle(
    norad_id: int,
    name: str,
    line1: str,
    line2: str,
    retrieved_at: datetime,
    source: str = SNAPSHOT_SOURCE_NAME,
) -> SatelliteRecord:
    validate_tle_lines(line1, line2)
    if int(line1[2:7]) != norad_id:
        raise OrbitalDataValidationError(
            f"Snapshot entry for {norad_id} contains NORAD ID {int(line1[2:7])}"
        )
    try:
        elements = OrbitalElementSet(
            epoch=_tle_epoch(line1),
            line1=line1,
            line2=line2,
            mean_motion=float(line2[52:63]),
            eccentricity=float("0." + line2[26:33].strip()),
            inclination_deg=float(line2[8:16]),
            raan_deg=float(line2[17:25]),
            arg_perigee_deg=float(line2[34:42]),
            mean_anomaly_deg=float(line2[43:51]),
            bstar=_parse_tle_exponent_field(line1[53:61]),
            element_set_number=int(line1[64:68]),
            revolution_number=int(line2[63:68]),
            source=source,
            retrieved_at=retrieved_at,
        )
    except ValueError as exc:
        raise OrbitalDataValidationError(f"Could not parse snapshot TLE: {exc}") from exc

    return SatelliteRecord(
        norad_id=norad_id,
        name=name,
        international_designator=_intl_designator(line1),
        object_type=None,
        orbital_elements=elements,
    )


class TleSnapshotClient:
    """Reads (and briefly caches) the static TLE snapshot. Never raises on a
    network/format problem - it just reports "no data" so callers can move on
    to raising the original live-fetch error."""

    def __init__(self, url: Optional[str], http_client: Optional[httpx.Client] = None) -> None:
        self._url = url
        self._client = http_client or httpx.Client(timeout=_SNAPSHOT_TIMEOUT)
        self._lock = threading.Lock()
        self._payload: Optional[Dict[str, Any]] = None
        self._loaded_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def _load(self) -> Optional[Dict[str, Any]]:
        if not self._url:
            return None
        with self._lock:
            if (
                self._payload is not None
                and time.monotonic() - self._loaded_at < _SNAPSHOT_CACHE_SECONDS
            ):
                return self._payload
            try:
                response = self._client.get(self._url)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Could not load TLE snapshot from %s: %s", self._url, exc)
                return self._payload  # an older in-memory copy is still better than nothing
            if not isinstance(payload, dict) or not isinstance(payload.get("satellites"), dict):
                logger.warning("TLE snapshot at %s has an unexpected shape", self._url)
                return self._payload
            self._payload = payload
            self._loaded_at = time.monotonic()
            return payload

    def search(self, query: str, limit: int = 20) -> List[SatelliteSearchResult]:
        """Case-insensitive substring match on snapshot satellite names."""
        payload = self._load()
        if payload is None:
            return []
        needle = query.strip().lower()
        hits: List[SatelliteSearchResult] = []
        for key, entry in payload["satellites"].items():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", ""))
            if needle and needle in name.lower():
                try:
                    hits.append(SatelliteSearchResult(norad_id=int(key), name=name))
                except ValueError:
                    continue
            if len(hits) >= limit:
                break
        return hits

    def get(self, norad_id: int) -> Optional[SatelliteRecord]:
        payload = self._load()
        if payload is None:
            return None
        entry = payload["satellites"].get(str(norad_id))
        if not isinstance(entry, dict):
            return None
        try:
            generated_at = datetime.fromisoformat(str(payload.get("generated_at")))
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=timezone.utc)
        except ValueError:
            generated_at = datetime.now(timezone.utc)
        try:
            return record_from_tle(
                norad_id,
                str(entry.get("name") or f"NORAD {norad_id}"),
                str(entry.get("line1", "")),
                str(entry.get("line2", "")),
                retrieved_at=generated_at,
            )
        except (OrbitalDataValidationError, ValueError) as exc:
            logger.warning("Ignoring bad snapshot entry for NORAD ID %s: %s", norad_id, exc)
            return None
