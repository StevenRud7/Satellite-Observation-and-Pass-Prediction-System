from datetime import datetime, timedelta, timezone
from typing import Optional

from app.data.exceptions import CelestrakClientError
from app.schemas.observer import ObserverLocation
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord
from app.schemas.visibility import ObservationMethod
from app.services.ranking_service import DEFAULT_CANDIDATE_NORAD_IDS, RankingService

VANGUARD1_EPOCH = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)

# Real, well-known reference TLE lines (see tests/conftest.py's
# SAMPLE_TLE_LINE1/2 - duplicated here rather than threaded through every
# call site below, since these lines aren't part of what `valid_gp_record`
# covers: CelesTrak's JSON GP format doesn't include raw TLE line text).
_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def _vanguard1_record(norad_id: int, name: str, valid_gp_record: dict) -> SatelliteRecord:
    elements = OrbitalElementSet(
        epoch=VANGUARD1_EPOCH,
        line1=_LINE1,
        line2=_LINE2,
        mean_motion=valid_gp_record["MEAN_MOTION"],
        eccentricity=valid_gp_record["ECCENTRICITY"],
        inclination_deg=valid_gp_record["INCLINATION"],
        raan_deg=valid_gp_record["RA_OF_ASC_NODE"],
        arg_perigee_deg=valid_gp_record["ARG_OF_PERICENTER"],
        mean_anomaly_deg=valid_gp_record["MEAN_ANOMALY"],
        bstar=valid_gp_record["BSTAR"],
        element_set_number=valid_gp_record["ELEMENT_SET_NO"],
        revolution_number=valid_gp_record["REV_AT_EPOCH"],
        source="celestrak",
        retrieved_at=datetime.now(timezone.utc),
    )
    return SatelliteRecord(norad_id=norad_id, name=name, orbital_elements=elements)


class _FakeSatelliteService:
    def __init__(self, records: dict, errors: Optional[dict] = None) -> None:
        self._records = records
        self._errors = errors or {}

    def get_satellite(self, norad_id: int, *, force_refresh: bool = False) -> SatelliteRecord:
        if norad_id in self._errors:
            raise self._errors[norad_id]
        return self._records[norad_id]


OBSERVER = ObserverLocation(latitude_deg=0.0, longitude_deg=149.95, altitude_m=0.0)
START = VANGUARD1_EPOCH - timedelta(minutes=15)
END = VANGUARD1_EPOCH + timedelta(minutes=15)


def test_find_best_opportunities_returns_results_for_all_satellites(valid_gp_record: dict) -> None:
    records = {
        5: _vanguard1_record(5, "SAT-A", valid_gp_record),
        6: _vanguard1_record(6, "SAT-B", valid_gp_record),
    }
    service = RankingService(_FakeSatelliteService(records))

    results = service.find_best_opportunities(
        OBSERVER, START, END, norad_ids=(5, 6), method=ObservationMethod.NAKED_EYE
    )

    assert {o.norad_id for o in results} == {5, 6}
    assert all(o.visibility.method == ObservationMethod.NAKED_EYE for o in results)
    # Results should be sorted descending by score.
    assert results == sorted(results, key=lambda o: o.visibility.score, reverse=True)


def test_find_best_opportunities_skips_satellite_that_fails_to_fetch(
    valid_gp_record: dict,
) -> None:
    records = {5: _vanguard1_record(5, "SAT-A", valid_gp_record)}
    errors = {6: CelestrakClientError("unreachable")}
    service = RankingService(_FakeSatelliteService(records, errors))

    results = service.find_best_opportunities(OBSERVER, START, END, norad_ids=(5, 6))

    assert {o.norad_id for o in results} == {5}


def test_find_best_opportunities_applies_min_score_filter(valid_gp_record: dict) -> None:
    records = {5: _vanguard1_record(5, "SAT-A", valid_gp_record)}
    service = RankingService(_FakeSatelliteService(records))

    results = service.find_best_opportunities(OBSERVER, START, END, norad_ids=(5,), min_score=1000)

    assert results == []


def test_find_best_opportunities_applies_limit(valid_gp_record: dict) -> None:
    records = {
        5: _vanguard1_record(5, "SAT-A", valid_gp_record),
        6: _vanguard1_record(6, "SAT-B", valid_gp_record),
    }
    service = RankingService(_FakeSatelliteService(records))

    results = service.find_best_opportunities(OBSERVER, START, END, norad_ids=(5, 6), limit=1)

    assert len(results) == 1


def test_find_best_opportunities_returns_empty_when_no_passes(valid_gp_record: dict) -> None:
    records = {5: _vanguard1_record(5, "SAT-A", valid_gp_record)}
    service = RankingService(_FakeSatelliteService(records))

    # Observer on the opposite side of the Earth - no pass in this short window.
    far_observer = ObserverLocation(latitude_deg=0.0, longitude_deg=-30.05, altitude_m=0.0)

    results = service.find_best_opportunities(far_observer, START, END, norad_ids=(5,))

    assert results == []


def test_default_candidate_norad_ids_is_iss() -> None:
    assert DEFAULT_CANDIDATE_NORAD_IDS == (25544,)


def test_find_best_opportunities_skips_a_pass_that_fails_to_score(
    valid_gp_record: dict, monkeypatch
) -> None:
    """If scoring one particular pass raises PropagationError (a real,
    if rare, possibility - see scoring.py), that pass is skipped with a
    warning rather than failing the whole ranking request."""
    from app.core.propagation import PropagationError
    from app.services import ranking_service as ranking_service_module

    records = {5: _vanguard1_record(5, "SAT-A", valid_gp_record)}
    service = RankingService(_FakeSatelliteService(records))

    monkeypatch.setattr(
        ranking_service_module,
        "assess_pass_visibility",
        lambda satrec, observer, pass_event: (_ for _ in ()).throw(PropagationError("boom")),
    )

    results = service.find_best_opportunities(OBSERVER, START, END, norad_ids=(5,))

    assert results == []
