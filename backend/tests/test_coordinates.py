from datetime import datetime, timezone

import pytest

from app.core.coordinates import (
    observer_earth_location,
    teme_to_topocentric,
    teme_to_topocentric_many,
)
from app.core.propagation import PropagationResult
from app.schemas.observer import ObserverLocation

# Same reference vector used in test_propagation.py (t=0 for Vanguard 1).
REFERENCE_TIME = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)
REFERENCE_POSITION_KM = (7022.46529266, -1400.08296755, 0.03995155)
REFERENCE_VELOCITY_KM_S = (1.893841015, 6.405893759, 4.534807250)

TEL_AVIV = ObserverLocation(latitude_deg=32.08, longitude_deg=34.78, altitude_m=5.0)


@pytest.fixture
def reference_result() -> PropagationResult:
    return PropagationResult(
        time=REFERENCE_TIME,
        position_km=REFERENCE_POSITION_KM,
        velocity_km_s=REFERENCE_VELOCITY_KM_S,
    )


def test_topocentric_values_are_physically_plausible(reference_result: PropagationResult) -> None:
    topo = teme_to_topocentric(reference_result, TEL_AVIV)

    assert 0.0 <= topo.azimuth_deg < 360.0
    assert -90.0 <= topo.elevation_deg <= 90.0
    assert topo.range_km > 0.0
    assert topo.time == REFERENCE_TIME


def test_topocentric_values_are_deterministic(reference_result: PropagationResult) -> None:
    """Same inputs, computed twice, must give identical results.

    This matters specifically because Astropy's IERS auto-download is
    disabled (see coordinates.py) - determinism confirms we are not
    accidentally depending on a network fetch or system clock.
    """
    topo1 = teme_to_topocentric(reference_result, TEL_AVIV)
    topo2 = teme_to_topocentric(reference_result, TEL_AVIV)

    assert topo1.azimuth_deg == topo2.azimuth_deg
    assert topo1.elevation_deg == topo2.elevation_deg
    assert topo1.range_km == topo2.range_km


def test_topocentric_values_match_known_good_computation(
    reference_result: PropagationResult,
) -> None:
    """Regression test pinned to values computed and manually sanity-checked
    during development (see project notes) - catches accidental changes to
    the transform pipeline, not an independent verification of astronomical
    correctness (that confidence comes from using Astropy's own well-tested
    TEME/ITRS/AltAz frames rather than a hand-rolled transform).
    """
    topo = teme_to_topocentric(reference_result, TEL_AVIV)

    assert topo.azimuth_deg == pytest.approx(75.8226, abs=1e-2)
    assert topo.elevation_deg == pytest.approx(-53.2535, abs=1e-2)
    assert topo.range_km == pytest.approx(11172.80, abs=1e-1)


def test_range_increases_with_observer_distance_from_subsatellite_point(
    reference_result: PropagationResult,
) -> None:
    near_pole = ObserverLocation(latitude_deg=89.0, longitude_deg=0.0, altitude_m=0.0)
    near_equator = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0)

    topo_pole = teme_to_topocentric(reference_result, near_pole)
    topo_equator = teme_to_topocentric(reference_result, near_equator)

    # Just a sanity check that changing the observer actually changes the
    # geometry - not asserting which one is closer (that depends on where
    # the satellite's sub-point actually is at this instant).
    assert topo_pole.range_km != topo_equator.range_km


def test_observer_earth_location_round_trips_geodetic_coordinates() -> None:
    location = observer_earth_location(TEL_AVIV)
    geodetic = location.to_geodetic()

    assert float(geodetic.lat.degree) == pytest.approx(TEL_AVIV.latitude_deg, abs=1e-6)
    assert float(geodetic.lon.degree) == pytest.approx(TEL_AVIV.longitude_deg, abs=1e-6)
    assert float(geodetic.height.to("m").value) == pytest.approx(TEL_AVIV.altitude_m, abs=1e-3)


def test_teme_to_topocentric_many_matches_individual_calls() -> None:
    """The batched path (Phase 10) exists purely for performance - see its
    docstring - so it must give identical results to the single-call path."""
    results = [
        PropagationResult(
            time=REFERENCE_TIME,
            position_km=REFERENCE_POSITION_KM,
            velocity_km_s=REFERENCE_VELOCITY_KM_S,
        ),
        PropagationResult(
            time=datetime(2000, 6, 27, 19, 50, 19, 733568, tzinfo=timezone.utc),
            position_km=(-7154.03120202, -3783.17682504, -3536.19412294),
            velocity_km_s=(4.741887409, -4.151817765, -2.093935425),
        ),
    ]

    individual = [teme_to_topocentric(r, TEL_AVIV) for r in results]
    batched = teme_to_topocentric_many(results, TEL_AVIV)

    assert len(batched) == 2
    assert len(individual) == len(batched)
    for single, batch in zip(individual, batched):
        assert batch.time == single.time
        assert batch.azimuth_deg == pytest.approx(single.azimuth_deg, abs=1e-6)
        assert batch.elevation_deg == pytest.approx(single.elevation_deg, abs=1e-6)
        assert batch.range_km == pytest.approx(single.range_km, abs=1e-6)


def test_teme_to_topocentric_many_empty_input_returns_empty_list() -> None:
    assert teme_to_topocentric_many([], TEL_AVIV) == []
