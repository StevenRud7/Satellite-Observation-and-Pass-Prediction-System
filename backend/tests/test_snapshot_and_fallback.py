"""Tests for the CelesTrak-unreachable resilience layer: TLE snapshot parsing,
stale/snapshot fallback in SatelliteService, and the unreachable cooldown."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pytest

from app.data.cache import InMemoryTTLCache
from app.data.celestrak import CelestrakClient
from app.data.exceptions import CelestrakClientError, SatelliteNotFoundError
from app.data.snapshot import TleSnapshotClient, record_from_tle
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord
from app.services.satellite_service import SatelliteService


def _record(norad_id: int, epoch_age_days: float, source: str = "celestrak") -> SatelliteRecord:
    now = datetime.now(timezone.utc)
    return SatelliteRecord(
        norad_id=norad_id,
        name="TEST",
        orbital_elements=OrbitalElementSet(
            epoch=now - timedelta(days=epoch_age_days),
            line1="1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753",
            line2="2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667",
            mean_motion=10.8,
            eccentricity=0.18,
            inclination_deg=34.2,
            raan_deg=348.7,
            arg_perigee_deg=331.7,
            mean_anomaly_deg=19.3,
            bstar=2.8e-5,
            element_set_number=475,
            revolution_number=13667,
            source=source,
            retrieved_at=now,
        ),
    )


class _FailingClient:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    def fetch_satellite_by_norad_id(self, norad_id: int) -> SatelliteRecord:
        self.calls += 1
        raise self._error


class _FakeSnapshot:
    enabled = True

    def __init__(self, record: Optional[SatelliteRecord]) -> None:
        self._record = record

    def get(self, norad_id: int) -> Optional[SatelliteRecord]:
        return self._record


def test_record_from_tle_parses_fields_matching_celestrak_json(
    valid_gp_record: dict, valid_tle_lines
) -> None:
    line1, line2 = valid_tle_lines
    record = record_from_tle(5, "VANGUARD 1", line1, line2, datetime.now(timezone.utc))
    el = record.orbital_elements

    assert el.mean_motion == pytest.approx(valid_gp_record["MEAN_MOTION"], rel=1e-7)
    assert el.eccentricity == pytest.approx(valid_gp_record["ECCENTRICITY"], rel=1e-6)
    assert el.inclination_deg == pytest.approx(valid_gp_record["INCLINATION"], abs=1e-4)
    assert el.raan_deg == pytest.approx(valid_gp_record["RA_OF_ASC_NODE"], abs=1e-4)
    assert el.arg_perigee_deg == pytest.approx(valid_gp_record["ARG_OF_PERICENTER"], abs=1e-4)
    assert el.mean_anomaly_deg == pytest.approx(valid_gp_record["MEAN_ANOMALY"], abs=1e-4)
    assert el.bstar == pytest.approx(valid_gp_record["BSTAR"], rel=1e-4)
    assert el.element_set_number == valid_gp_record["ELEMENT_SET_NO"]
    # (The shared JSON fixture's REV_AT_EPOCH doesn't match its TLE line; the
    # TLE columns themselves say 41366, which is what a TLE parser must return.)
    assert el.revolution_number == 41366
    assert record.international_designator == "1958-002B"
    assert el.epoch.year == 2000 and el.epoch.month == 6


def test_snapshot_client_serves_entry_and_ignores_unknown_ids(valid_tle_lines) -> None:
    line1, line2 = valid_tle_lines
    payload = {
        "generated_at": "2026-10-14T06:00:00+00:00",
        "satellites": {"5": {"name": "VANGUARD 1", "line1": line1, "line2": line2}},
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    )
    snapshot = TleSnapshotClient("https://example.test/snap.json", http_client=client)

    assert snapshot.get(5).name == "VANGUARD 1"
    assert snapshot.get(5).orbital_elements.source == "celestrak-snapshot"
    assert snapshot.get(999) is None


def test_snapshot_client_returns_none_when_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    snapshot = TleSnapshotClient(
        "https://example.test/snap.json",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert snapshot.get(5) is None


def test_live_failure_falls_back_to_recent_stale_cache() -> None:
    cache = InMemoryTTLCache(ttl_seconds=0.0)  # everything is immediately "stale"
    cache.set("5", _record(5, epoch_age_days=2))
    client = _FailingClient(CelestrakClientError("Could not reach CelesTrak: timed out"))
    service = SatelliteService(client=client, cache=cache)

    assert service.get_satellite(5).norad_id == 5
    assert client.calls == 1


def test_live_failure_with_too_old_data_still_raises_original_error() -> None:
    cache = InMemoryTTLCache(ttl_seconds=0.0)
    cache.set("5", _record(5, epoch_age_days=60))
    client = _FailingClient(CelestrakClientError("Could not reach CelesTrak: timed out"))
    service = SatelliteService(client=client, cache=cache)

    with pytest.raises(CelestrakClientError, match="timed out"):
        service.get_satellite(5)


def test_fallback_prefers_newest_epoch_between_stale_cache_and_snapshot() -> None:
    cache = InMemoryTTLCache(ttl_seconds=0.0)
    cache.set("5", _record(5, epoch_age_days=6))
    snapshot = _FakeSnapshot(_record(5, epoch_age_days=1, source="celestrak-snapshot"))
    client = _FailingClient(CelestrakClientError("Could not reach CelesTrak: timed out"))
    service = SatelliteService(client=client, cache=cache, snapshot=snapshot)

    assert service.get_satellite(5).orbital_elements.source == "celestrak-snapshot"


def test_not_found_never_falls_back() -> None:
    cache = InMemoryTTLCache(ttl_seconds=0.0)
    cache.set("5", _record(5, epoch_age_days=1))
    client = _FailingClient(SatelliteNotFoundError("No CelesTrak data found for NORAD ID 5"))
    service = SatelliteService(client=client, cache=cache)

    with pytest.raises(SatelliteNotFoundError):
        service.get_satellite(5)


def test_fresh_cache_hit_does_not_touch_client_or_snapshot() -> None:
    cache = InMemoryTTLCache(ttl_seconds=60)
    cache.set("5", _record(5, epoch_age_days=1))
    client = _FailingClient(CelestrakClientError("should not be called"))
    service = SatelliteService(client=client, cache=cache)

    service.get_satellite(5)
    assert client.calls == 0


def test_network_failure_triggers_cooldown_then_skips_live_requests() -> None:
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        raise httpx.ConnectTimeout("timed out")

    client = CelestrakClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        unreachable_cooldown_seconds=60,
    )

    with pytest.raises(CelestrakClientError, match="Could not reach CelesTrak"):
        client.fetch_satellite_by_norad_id(5)
    seen_after_first = len(requests_seen)
    assert seen_after_first >= 1

    with pytest.raises(CelestrakClientError, match="Could not reach CelesTrak"):
        client.fetch_satellite_by_norad_id(5)
    assert len(requests_seen) == seen_after_first  # no new network attempt


def test_http_error_status_does_not_trigger_cooldown() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    client = CelestrakClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        unreachable_cooldown_seconds=60,
    )
    for _ in range(2):
        with pytest.raises(CelestrakClientError, match="HTTP 503"):
            client.fetch_satellite_by_norad_id(5)
    assert len(calls) >= 2
