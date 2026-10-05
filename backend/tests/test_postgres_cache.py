from datetime import datetime, timezone

from app.data.postgres_cache import PostgresSatelliteCache
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord


def _make_record(norad_id: int = 25544) -> SatelliteRecord:
    return SatelliteRecord(
        norad_id=norad_id,
        name="ISS (ZARYA)",
        orbital_elements=OrbitalElementSet(
            epoch=datetime.now(timezone.utc),
            line1="1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9990",
            line2="2 25544  51.6400 000.0000 0000000 000.0000 000.0000 15.50000000000010",
            mean_motion=15.5,
            eccentricity=0.0001,
            inclination_deg=51.64,
            raan_deg=0.0,
            arg_perigee_deg=0.0,
            mean_anomaly_deg=0.0,
            bstar=0.0001,
            element_set_number=999,
            revolution_number=1,
            source="celestrak",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )


def test_get_returns_none_before_anything_is_cached(clean_database) -> None:
    cache = PostgresSatelliteCache(ttl_seconds=3600)
    assert cache.get("25544") is None


def test_set_then_get_round_trips(clean_database) -> None:
    cache = PostgresSatelliteCache(ttl_seconds=3600)
    record = _make_record()

    cache.set("25544", record)
    fetched = cache.get("25544")

    assert fetched is not None
    assert fetched.name == "ISS (ZARYA)"


def test_get_returns_none_when_stale(clean_database) -> None:
    cache = PostgresSatelliteCache(ttl_seconds=0)
    cache.set("25544", _make_record())

    # TTL of zero seconds: anything already retrieved is immediately stale.
    assert cache.get("25544") is None


def test_cache_persists_across_separate_cache_instances(clean_database) -> None:
    """Unlike the in-memory cache, a Postgres-backed cache's data outlives
    any single Cache object - this is the whole point of it."""
    PostgresSatelliteCache(ttl_seconds=3600).set("25544", _make_record())

    fetched = PostgresSatelliteCache(ttl_seconds=3600).get("25544")

    assert fetched is not None
    assert fetched.norad_id == 25544
