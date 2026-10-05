"""
Propagation tests.

The reference position/velocity vectors below come from `tcppver.out`,
the official test case file distributed with Vallado's reference SGP4
implementation (and bundled with the `sgp4` PyPI package itself, under
satellite number 5 / Vanguard 1). Using them means our propagation code
is checked against an independent, authoritative source rather than only
against itself.
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple

import pytest

from app.core.propagation import PropagationError, build_satrec, propagate, propagate_many
from app.schemas.orbital_elements import OrbitalElementSet

EPOCH = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)

# (minutes since epoch, x, y, z [km], vx, vy, vz [km/s]) from tcppver.out
REFERENCE_VECTORS = [
    (0.0, (7022.46529266, -1400.08296755, 0.03995155), (1.893841015, 6.405893759, 4.534807250)),
    (
        360.0,
        (-7154.03120202, -3783.17682504, -3536.19412294),
        (4.741887409, -4.151817765, -2.093935425),
    ),
    (
        720.0,
        (-7134.59340119, 6531.68641334, 3260.27186483),
        (-4.113793027, -2.911922039, -2.557327851),
    ),
]


@pytest.fixture
def elements(valid_gp_record: dict, valid_tle_lines: tuple) -> OrbitalElementSet:
    return OrbitalElementSet(
        epoch=EPOCH,
        line1=valid_tle_lines[0],
        line2=valid_tle_lines[1],
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


def test_build_satrec_reads_norad_id(elements: OrbitalElementSet) -> None:
    satrec = build_satrec(elements)
    assert satrec.satnum == 5


@pytest.mark.parametrize("minutes,expected_pos,expected_vel", REFERENCE_VECTORS)
def test_propagate_matches_official_reference_vectors(
    elements: OrbitalElementSet,
    minutes: float,
    expected_pos: Tuple[float, float, float],
    expected_vel: Tuple[float, float, float],
) -> None:
    satrec = build_satrec(elements)
    when = EPOCH + timedelta(minutes=minutes)

    result = propagate(satrec, when)

    for actual, expected in zip(result.position_km, expected_pos):
        assert actual == pytest.approx(expected, abs=1e-4)
    for actual, expected in zip(result.velocity_km_s, expected_vel):
        assert actual == pytest.approx(expected, abs=1e-6)


def test_propagate_converts_to_utc(elements: OrbitalElementSet) -> None:
    satrec = build_satrec(elements)
    from datetime import timezone as tz

    non_utc = EPOCH.astimezone(tz(timedelta(hours=3)))
    result = propagate(satrec, non_utc)
    assert result.time.utcoffset() == timedelta(0)
    assert result.time == EPOCH


def test_propagate_rejects_naive_datetime(elements: OrbitalElementSet) -> None:
    satrec = build_satrec(elements)
    with pytest.raises(ValueError, match="timezone-aware"):
        propagate(satrec, datetime(2024, 1, 1))


def test_propagate_raises_on_sgp4_error_code() -> None:
    class _FakeSatrec:
        def sgp4(self, jd: float, fr: float) -> Tuple[int, tuple, tuple]:
            return 6, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    with pytest.raises(PropagationError, match="decayed"):
        propagate(_FakeSatrec(), datetime.now(timezone.utc))


def test_propagate_raises_with_unknown_error_code_message() -> None:
    class _FakeSatrec:
        def sgp4(self, jd: float, fr: float) -> Tuple[int, tuple, tuple]:
            return 42, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    with pytest.raises(PropagationError, match="unknown SGP4 error code 42"):
        propagate(_FakeSatrec(), datetime.now(timezone.utc))


def test_propagate_many_matches_individual_propagate_calls(elements: OrbitalElementSet) -> None:
    """The batched (vectorized) path exists purely for performance - see
    passes.py's Phase 10 notes - so it must produce identical results to
    calling propagate() one at a time."""
    satrec = build_satrec(elements)
    times = [EPOCH + timedelta(minutes=m) for m in (0, 90, 360)]

    individual = [propagate(satrec, t) for t in times]
    batched = propagate_many(satrec, times)

    assert len(batched) == len(individual)
    assert len(individual) == len(batched)
    for single, batch in zip(individual, batched):
        assert batch is not None
        assert batch.time == single.time
        assert len(batch.position_km) == len(single.position_km)
        for a, b in zip(batch.position_km, single.position_km):
            assert a == pytest.approx(b, abs=1e-6)
        assert len(batch.velocity_km_s) == len(single.velocity_km_s)
        for a, b in zip(batch.velocity_km_s, single.velocity_km_s):
            assert a == pytest.approx(b, abs=1e-9)


def test_propagate_many_empty_input_returns_empty_list(elements: OrbitalElementSet) -> None:
    satrec = build_satrec(elements)
    assert propagate_many(satrec, []) == []


def test_propagate_many_returns_none_for_failed_samples_without_aborting_others() -> None:
    class _FakeSatrec:
        def sgp4_array(self, jds, frs):
            import numpy as np

            n = len(jds)
            errors = np.zeros(n, dtype=int)
            errors[1] = 6  # simulate one bad sample in the middle
            positions = np.zeros((n, 3))
            velocities = np.zeros((n, 3))
            return errors, positions, velocities

    times = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=m) for m in range(3)]
    results = propagate_many(_FakeSatrec(), times)

    assert results[0] is not None
    assert results[1] is None
    assert results[2] is not None


def test_propagate_many_rejects_naive_datetime(elements: OrbitalElementSet) -> None:
    satrec = build_satrec(elements)
    with pytest.raises(ValueError, match="timezone-aware"):
        propagate_many(satrec, [datetime(2024, 1, 1)])
