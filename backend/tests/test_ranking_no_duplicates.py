"""Every pass in the ranked results must be a distinct (satellite, pass) pair,
and passes of one satellite must never overlap in time."""

from datetime import datetime, timedelta, timezone

from sgp4.api import Satrec  # noqa: F401  (ensures sgp4 is importable for build_satrec)

from app.schemas.observer import ObserverLocation
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord
from app.services.ranking_service import RankingService


class _FakeSatelliteService:
    def __init__(self) -> None:
        self.calls = 0

    def get_satellite(self, norad_id: int) -> SatelliteRecord:
        self.calls += 1
        now = datetime(2019, 12, 10, 12, tzinfo=timezone.utc)
        return SatelliteRecord(
            norad_id=norad_id,
            name=f"SAT {norad_id}",
            orbital_elements=OrbitalElementSet(
                epoch=now,
                line1="1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991",
                line2="2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482",
                mean_motion=15.5,
                eccentricity=0.0007,
                inclination_deg=51.6,
                raan_deg=211.2,
                arg_perigee_deg=17.6,
                mean_anomaly_deg=85.6,
                bstar=3.8e-5,
                element_set_number=999,
                revolution_number=1,
                source="test",
                retrieved_at=now,
            ),
        )


def _run(norad_ids):
    start = datetime(2019, 12, 10, 12, tzinfo=timezone.utc)
    service = RankingService(_FakeSatelliteService())
    return service.find_best_opportunities(
        ObserverLocation(latitude_deg=32.08, longitude_deg=34.78, altitude_m=0.0),
        start,
        start + timedelta(hours=72),
        norad_ids=tuple(norad_ids),
        limit=100,
    )


def test_repeated_norad_id_does_not_duplicate_passes() -> None:
    once = _run([25544])
    thrice = _run([25544, 25544, 25544])
    assert len(once) > 0
    assert len(thrice) == len(once)


def test_no_duplicate_or_overlapping_passes_per_satellite() -> None:
    results = _run([25544, 25545])
    keys = [(o.norad_id, o.pass_event.rise_time) for o in results]
    assert len(keys) == len(set(keys))

    by_sat = {}
    for o in results:
        by_sat.setdefault(o.norad_id, []).append(o.pass_event)
    for passes in by_sat.values():
        passes.sort(key=lambda p: p.rise_time)
        for earlier, later in zip(passes, passes[1:]):
            assert earlier.set_time <= later.rise_time
