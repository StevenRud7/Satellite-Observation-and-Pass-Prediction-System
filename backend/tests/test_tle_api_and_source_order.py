"""Tests for the TLE API secondary source, snapshot-first ordering, caching of
fallback results, and search fallback."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pytest

from app.data.cache import InMemoryTTLCache
from app.data.exceptions import CelestrakClientError
from app.data.snapshot import TleSnapshotClient
from app.data.tle_api import TleApiClient
from app.schemas.satellite import SatelliteRecord, SatelliteSearchResult
from app.services.satellite_search_service import SatelliteSearchService
from app.services.satellite_service import SatelliteService

# Real ISS TLE as served by the TLE API (current "00000+0" bstar style).
ISS_LINE1 = "1 25544U 98067A   26286.43465595  .00005946  00000+0  11657-3 0  9991"
ISS_LINE2 = "2 25544  51.6321  74.9235 0006732 257.7935 102.2300 15.48850287590084"


def _iss_payload() -> dict:
    return {
        "satelliteId": 25544,
        "name": "ISS (ZARYA)",
        "date": "2026-10-13T10:25:54+00:00",
        "line1": ISS_LINE1,
        "line2": ISS_LINE2,
    }


def _api_client(handler) -> TleApiClient:
    return TleApiClient(
        base_url="https://tle.test/api/tle",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        cooldown_seconds=60,
    )


class _DownCelestrak:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_satellite_by_norad_id(self, norad_id: int) -> SatelliteRecord:
        self.calls += 1
        raise CelestrakClientError("Could not reach CelesTrak: timed out")

    def search_by_name(self, name: str, limit: int = 20):
        raise CelestrakClientError("Could not reach CelesTrak: timed out")


def _recent(record: SatelliteRecord, epoch_age_days: float) -> SatelliteRecord:
    now = datetime.now(timezone.utc)
    el = record.orbital_elements.model_copy(
        update={"epoch": now - timedelta(days=epoch_age_days), "retrieved_at": now}
    )
    return record.model_copy(update={"orbital_elements": el})


def test_tle_api_parses_real_current_format_tle() -> None:
    client = _api_client(lambda r: httpx.Response(200, json=_iss_payload()))
    record = client.fetch(25544)

    assert record is not None
    assert record.name == "ISS (ZARYA)"
    assert record.orbital_elements.source == "tle-api"
    assert record.orbital_elements.mean_motion == pytest.approx(15.48850287)
    assert record.orbital_elements.bstar == pytest.approx(1.1657e-4)
    assert record.orbital_elements.epoch.year == 2026
    assert record.international_designator == "1998-067A"


def test_tle_api_returns_none_on_404_bad_json_and_wrong_satellite() -> None:
    assert _api_client(lambda r: httpx.Response(404)).fetch(25544) is None
    assert _api_client(lambda r: httpx.Response(200, text="<html>")).fetch(25544) is None
    # Response is for a different satellite than requested -> rejected.
    assert _api_client(lambda r: httpx.Response(200, json=_iss_payload())).fetch(5) is None


def test_tle_api_unreachable_sets_cooldown() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectTimeout("t")

    client = _api_client(handler)
    assert client.fetch(25544) is None
    assert client.fetch(25544) is None
    assert len(calls) == 1


def test_celestrak_down_uses_tle_api_and_caches_result() -> None:
    cache: InMemoryTTLCache = InMemoryTTLCache(ttl_seconds=3600)
    live = _DownCelestrak()
    api = _api_client(lambda r: httpx.Response(200, json=_iss_payload()))
    # TLE epoch in the payload is 2026-10-13; allow a wide window so the test
    # doesn't depend on today's date.
    service = SatelliteService(
        client=live, cache=cache, tle_api=api, max_fallback_epoch_age=timedelta(days=36500)
    )

    first = service.get_satellite(25544)
    second = service.get_satellite(25544)

    assert first.orbital_elements.source == "tle-api"
    assert second.norad_id == 25544
    assert live.calls == 1  # second call served from cache, no new live attempt


def test_tle_api_too_old_epoch_is_rejected_then_error_raised() -> None:
    live = _DownCelestrak()
    api = _api_client(lambda r: httpx.Response(200, json=_iss_payload()))
    service = SatelliteService(
        client=live,
        cache=InMemoryTTLCache(ttl_seconds=3600),
        tle_api=api,
        max_fallback_epoch_age=timedelta(seconds=1),  # nothing is that fresh
    )
    with pytest.raises(CelestrakClientError):
        service.get_satellite(25544)


class _Snap:
    enabled = True

    def __init__(self, record: Optional[SatelliteRecord]) -> None:
        self._record = record

    def get(self, norad_id: int):
        return self._record


def _iss_record(epoch_age_days: float, generated_hours_ago: float) -> SatelliteRecord:
    api = _api_client(lambda r: httpx.Response(200, json=_iss_payload()))
    record = api.fetch(25544)
    assert record is not None
    now = datetime.now(timezone.utc)
    el = record.orbital_elements.model_copy(
        update={
            "epoch": now - timedelta(days=epoch_age_days),
            "retrieved_at": now - timedelta(hours=generated_hours_ago),
            "source": "celestrak-snapshot",
        }
    )
    return record.model_copy(update={"orbital_elements": el})


def test_fresh_snapshot_is_used_before_live_and_stored_once() -> None:
    cache: InMemoryTTLCache = InMemoryTTLCache(ttl_seconds=0.0)  # cache never "fresh"
    live = _DownCelestrak()
    snap = _Snap(_iss_record(epoch_age_days=0.5, generated_hours_ago=2))
    service = SatelliteService(
        client=live,
        cache=cache,
        snapshot=snap,
        snapshot_prefer_max_age=timedelta(hours=8),
    )

    for _ in range(3):
        assert service.get_satellite(25544).orbital_elements.source == "celestrak-snapshot"

    assert live.calls == 0  # CelesTrak never needed
    assert cache.get_stale("25544") is not None  # row exists for features needing the DB


def test_old_snapshot_is_not_preferred_over_live() -> None:
    live = _DownCelestrak()
    snap = _Snap(_iss_record(epoch_age_days=0.5, generated_hours_ago=30))
    service = SatelliteService(
        client=live,
        cache=InMemoryTTLCache(ttl_seconds=3600),
        snapshot=snap,
        snapshot_prefer_max_age=timedelta(hours=8),
    )
    # Live is tried first (and fails); the older snapshot is then the fallback.
    assert service.get_satellite(25544).orbital_elements.source == "celestrak-snapshot"
    assert live.calls == 1


def test_force_refresh_skips_snapshot_first() -> None:
    live = _DownCelestrak()
    snap = _Snap(_iss_record(epoch_age_days=0.5, generated_hours_ago=1))
    service = SatelliteService(
        client=live,
        cache=InMemoryTTLCache(ttl_seconds=3600),
        snapshot=snap,
        snapshot_prefer_max_age=timedelta(hours=8),
    )
    service.get_satellite(25544, force_refresh=True)
    assert live.calls == 1


def test_search_falls_back_to_tle_api_then_snapshot_then_raises() -> None:
    cache: InMemoryTTLCache = InMemoryTTLCache(ttl_seconds=60)
    member = {"member": [{"satelliteId": 25544, "name": "ISS (ZARYA)"}]}
    api = _api_client(lambda r: httpx.Response(200, json=member))
    service = SatelliteSearchService(client=_DownCelestrak(), cache=cache, tle_api=api)
    assert service.search("iss") == [SatelliteSearchResult(norad_id=25544, name="ISS (ZARYA)")]

    api_down = _api_client(lambda r: httpx.Response(500))
    payload = {
        "generated_at": "2026-10-14T00:00:00+00:00",
        "satellites": {"25544": {"name": "ISS (ZARYA)", "line1": ISS_LINE1, "line2": ISS_LINE2}},
    }
    snapshot = TleSnapshotClient(
        "https://snap.test/x.json",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
        ),
    )
    service2 = SatelliteSearchService(
        client=_DownCelestrak(),
        cache=InMemoryTTLCache(ttl_seconds=60),
        tle_api=api_down,
        snapshot=snapshot,
    )
    assert service2.search("zarya")[0].norad_id == 25544

    with pytest.raises(CelestrakClientError):
        SatelliteSearchService(
            client=_DownCelestrak(), cache=InMemoryTTLCache(ttl_seconds=60), tle_api=api_down
        ).search("nothing")
