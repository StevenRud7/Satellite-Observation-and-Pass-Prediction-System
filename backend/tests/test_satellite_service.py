from datetime import datetime, timezone

from app.data.cache import InMemoryTTLCache
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord
from app.services.satellite_service import SatelliteService


def _fake_record(norad_id: int) -> SatelliteRecord:
    return SatelliteRecord(
        norad_id=norad_id,
        name="TEST SAT",
        international_designator="2000-001A",
        orbital_elements=OrbitalElementSet(
            epoch=datetime.now(timezone.utc),
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
            source="celestrak",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )


class _FakeCelestrakClient:
    def __init__(self) -> None:
        self.call_count = 0

    def fetch_satellite_by_norad_id(self, norad_id: int) -> SatelliteRecord:
        self.call_count += 1
        return _fake_record(norad_id)


def test_first_call_fetches_from_client() -> None:
    fake_client = _FakeCelestrakClient()
    service = SatelliteService(client=fake_client, cache=InMemoryTTLCache(ttl_seconds=60))

    record = service.get_satellite(5)

    assert record.norad_id == 5
    assert fake_client.call_count == 1


def test_second_call_uses_cache_not_client() -> None:
    fake_client = _FakeCelestrakClient()
    service = SatelliteService(client=fake_client, cache=InMemoryTTLCache(ttl_seconds=60))

    service.get_satellite(5)
    service.get_satellite(5)

    assert fake_client.call_count == 1


def test_force_refresh_bypasses_cache() -> None:
    fake_client = _FakeCelestrakClient()
    service = SatelliteService(client=fake_client, cache=InMemoryTTLCache(ttl_seconds=60))

    service.get_satellite(5)
    service.get_satellite(5, force_refresh=True)

    assert fake_client.call_count == 2


def test_different_norad_ids_are_cached_independently() -> None:
    fake_client = _FakeCelestrakClient()
    service = SatelliteService(client=fake_client, cache=InMemoryTTLCache(ttl_seconds=60))

    service.get_satellite(5)
    service.get_satellite(25544)

    assert fake_client.call_count == 2
