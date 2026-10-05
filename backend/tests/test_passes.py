"""
Pass detection tests.

Two kinds of test here:

1. Algorithm tests (majority) - use a synthetic, hand-computed elevation
   curve via `find_passes_from_position_fn` so rise/peak/set times are
   known exactly and edge cases (pass at window boundary, multiple passes,
   threshold changes) can be checked precisely and fast, with no SGP4 or
   Astropy calls at all.
2. One integration test - uses the real SGP4 + coordinate-transform
   pipeline (`find_passes`) with an observer placed directly under the
   Vanguard 1 sub-satellite point at its TLE epoch (verified in
   test_coordinates.py / test_propagation.py to be geometrically
   correct), which guarantees a real, near-overhead pass to detect.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from app.core import passes as passes_module
from app.core.coordinates import TopocentricPosition
from app.core.passes import find_passes, find_passes_from_position_fn
from app.core.propagation import build_satrec
from app.schemas.observer import ObserverLocation
from app.schemas.orbital_elements import OrbitalElementSet

REFERENCE = datetime(2024, 1, 1, tzinfo=timezone.utc)
THRESHOLD = 10.0
BASELINE = -20.0


def _tent_position_fn(rise_s: float, peak_s: float, set_s: float, peak_elevation: float):
    """A position function whose elevation is a straight-line ramp up to
    `peak_elevation` at `peak_s` seconds after REFERENCE, exactly crossing
    `THRESHOLD` at `rise_s` and `set_s`, and flat at `BASELINE` outside
    [rise_s, set_s]. Azimuth and range vary linearly too, just so we can
    check they're read from the right sample rather than always constant.
    """

    def position_at(t: datetime) -> TopocentricPosition:
        dt = (t - REFERENCE).total_seconds()
        if dt < rise_s or dt > set_s:
            elevation = BASELINE
        elif dt <= peak_s:
            frac = (dt - rise_s) / (peak_s - rise_s)
            elevation = THRESHOLD + frac * (peak_elevation - THRESHOLD)
        else:
            frac = (dt - peak_s) / (set_s - peak_s)
            elevation = peak_elevation - frac * (peak_elevation - THRESHOLD)

        return TopocentricPosition(
            time=t,
            azimuth_deg=(dt % 360.0),
            elevation_deg=elevation,
            range_km=1000.0 + dt,
        )

    return position_at


def test_single_pass_rise_peak_set_times_are_accurate() -> None:
    position_at = _tent_position_fn(rise_s=100.0, peak_s=300.0, set_s=500.0, peak_elevation=80.0)

    passes = find_passes_from_position_fn(
        position_at,
        REFERENCE,
        REFERENCE + timedelta(seconds=600),
        min_elevation_deg=THRESHOLD,
        sample_interval_seconds=30.0,
        time_tolerance_seconds=0.5,
    )

    assert len(passes) == 1
    p = passes[0]

    assert (p.rise_time - REFERENCE).total_seconds() == pytest.approx(100.0, abs=1.0)
    assert (p.peak_time - REFERENCE).total_seconds() == pytest.approx(300.0, abs=1.0)
    assert (p.set_time - REFERENCE).total_seconds() == pytest.approx(500.0, abs=1.0)
    assert p.max_elevation_deg == pytest.approx(80.0, abs=0.5)
    assert p.duration_seconds == pytest.approx(400.0, abs=2.0)
    assert p.min_elevation_threshold_deg == THRESHOLD


def test_rise_and_set_azimuth_and_range_come_from_correct_times() -> None:
    position_at = _tent_position_fn(rise_s=100.0, peak_s=300.0, set_s=500.0, peak_elevation=80.0)

    passes = find_passes_from_position_fn(
        position_at,
        REFERENCE,
        REFERENCE + timedelta(seconds=600),
        min_elevation_deg=THRESHOLD,
    )
    p = passes[0]

    # range_km = 1000 + seconds-since-reference in our synthetic function,
    # so we can check each recorded value came from roughly the right time.
    assert p.rise_range_km == pytest.approx(1000.0 + 100.0, abs=2.0)
    assert p.max_range_km == pytest.approx(1000.0 + 300.0, abs=2.0)
    assert p.set_range_km == pytest.approx(1000.0 + 500.0, abs=2.0)


def test_pass_in_progress_at_window_start_is_excluded() -> None:
    # Rises before the window even opens.
    position_at = _tent_position_fn(rise_s=-100.0, peak_s=50.0, set_s=200.0, peak_elevation=60.0)

    passes = find_passes_from_position_fn(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=600), min_elevation_deg=THRESHOLD
    )

    assert passes == []


def test_pass_in_progress_at_window_end_is_excluded() -> None:
    # Rises inside the window but doesn't set until after it closes.
    position_at = _tent_position_fn(rise_s=500.0, peak_s=650.0, set_s=800.0, peak_elevation=60.0)

    passes = find_passes_from_position_fn(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=600), min_elevation_deg=THRESHOLD
    )

    assert passes == []


def test_no_passes_when_always_below_threshold() -> None:
    position_at = lambda t: TopocentricPosition(  # noqa: E731
        time=t, azimuth_deg=0.0, elevation_deg=BASELINE, range_km=1000.0
    )

    passes = find_passes_from_position_fn(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=600), min_elevation_deg=THRESHOLD
    )

    assert passes == []


def test_multiple_passes_in_one_window_are_all_detected() -> None:
    def position_at(t: datetime) -> TopocentricPosition:
        pass_a = _tent_position_fn(100.0, 200.0, 300.0, 50.0)(t)
        pass_b = _tent_position_fn(1000.0, 1100.0, 1200.0, 70.0)(t)
        elevation = max(pass_a.elevation_deg, pass_b.elevation_deg)
        return TopocentricPosition(
            time=t, azimuth_deg=0.0, elevation_deg=elevation, range_km=1000.0
        )

    passes = find_passes_from_position_fn(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=1500), min_elevation_deg=THRESHOLD
    )

    assert len(passes) == 2
    assert passes[0].max_elevation_deg == pytest.approx(50.0, abs=0.5)
    assert passes[1].max_elevation_deg == pytest.approx(70.0, abs=0.5)
    # Passes should be reported in chronological order.
    assert passes[0].rise_time < passes[1].rise_time


def test_higher_threshold_can_eliminate_a_low_pass() -> None:
    position_at = _tent_position_fn(rise_s=100.0, peak_s=300.0, set_s=500.0, peak_elevation=15.0)

    passes_low_threshold = find_passes_from_position_fn(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=600), min_elevation_deg=10.0
    )
    passes_high_threshold = find_passes_from_position_fn(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=600), min_elevation_deg=20.0
    )

    assert len(passes_low_threshold) == 1
    assert len(passes_high_threshold) == 0


def test_start_must_be_before_end() -> None:
    position_at = _tent_position_fn(100.0, 300.0, 500.0, 80.0)
    with pytest.raises(ValueError, match="start must be before end"):
        find_passes_from_position_fn(position_at, REFERENCE, REFERENCE)


def test_naive_datetimes_are_rejected() -> None:
    position_at = _tent_position_fn(100.0, 300.0, 500.0, 80.0)
    with pytest.raises(ValueError, match="timezone-aware"):
        find_passes_from_position_fn(
            position_at, datetime(2024, 1, 1), datetime(2024, 1, 2, tzinfo=timezone.utc)
        )


# --- Integration test: real SGP4 + coordinate transform pipeline ----------


@pytest.fixture
def vanguard1_satrec(valid_gp_record: dict, valid_tle_lines: tuple):
    elements = OrbitalElementSet(
        epoch=datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc),
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
    return build_satrec(elements), elements.epoch


def test_find_passes_detects_real_overhead_pass(vanguard1_satrec) -> None:
    satrec, epoch = vanguard1_satrec

    # Directly under the satellite's sub-point at epoch (see project notes /
    # PHASE_2_AND_3_NOTES.md for how this was derived) - guarantees a real,
    # near-overhead pass right around `epoch`.
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=149.95, altitude_m=0.0)

    passes = find_passes(
        satrec,
        observer,
        epoch - timedelta(minutes=15),
        epoch + timedelta(minutes=15),
        min_elevation_deg=10.0,
    )

    assert len(passes) == 1
    p = passes[0]

    assert p.max_elevation_deg > 85.0  # near-overhead by construction
    assert p.rise_time < p.peak_time < p.set_time
    assert p.duration_seconds > 0
    assert 0.0 <= p.rise_azimuth_deg < 360.0
    assert 0.0 <= p.set_azimuth_deg < 360.0
    # Peak should be the closest approach of the three recorded ranges.
    assert p.max_range_km <= p.rise_range_km
    assert p.max_range_km <= p.set_range_km


def test_find_passes_with_no_visibility_window_returns_empty(vanguard1_satrec) -> None:
    satrec, epoch = vanguard1_satrec
    # An observer on the opposite side of the Earth from the pass we just
    # confirmed above should not see a pass in the same short window.
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=-30.05, altitude_m=0.0)

    passes = find_passes(
        satrec,
        observer,
        epoch - timedelta(minutes=15),
        epoch + timedelta(minutes=15),
        min_elevation_deg=10.0,
    )

    assert passes == []


def test_find_passes_rejects_naive_datetimes(vanguard1_satrec) -> None:
    """find_passes() (the real SGP4 wrapper) validates before doing any
    batch propagation work - checked directly, not just via
    find_passes_from_position_fn, which validates independently."""
    satrec, epoch = vanguard1_satrec
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0)

    with pytest.raises(ValueError, match="timezone-aware"):
        find_passes(satrec, observer, datetime(2024, 1, 1), epoch + timedelta(hours=1))


def test_find_passes_rejects_start_after_end(vanguard1_satrec) -> None:
    satrec, epoch = vanguard1_satrec
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0)

    with pytest.raises(ValueError, match="start must be before end"):
        find_passes(satrec, observer, epoch + timedelta(hours=1), epoch)


# --- Refinement resilience to propagation failures (white-box) ------------
#
# These test the internal bisection/peak-refinement helpers directly with a
# synthetic PositionFn that simulates SGP4 failing at specific times (e.g.
# a numerically unstable point) - a real possibility for real satellites
# near orbital decay, and a case the algorithm explicitly guards against
# (see the docstrings in passes.py) but that the happy-path tests above
# never exercise.


def test_bisect_crossing_returns_lower_bound_when_it_fails_to_propagate() -> None:
    def position_at(t: datetime) -> Optional[TopocentricPosition]:
        return None

    result = passes_module._bisect_crossing(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=30), THRESHOLD, 1.0
    )

    assert result == REFERENCE


def test_bisect_crossing_nudges_past_a_single_bad_midpoint() -> None:
    """If the exact midpoint fails to propagate once, the algorithm nudges
    forward and retries rather than giving up immediately."""
    bad_time = REFERENCE + timedelta(seconds=15)  # first midpoint of a 0-30s bracket

    def position_at(t: datetime) -> Optional[TopocentricPosition]:
        if t == bad_time:
            return None
        dt = (t - REFERENCE).total_seconds()
        elevation = -20.0 if dt < 15 else 40.0
        return TopocentricPosition(
            time=t, azimuth_deg=0.0, elevation_deg=elevation, range_km=1000.0
        )

    crossing = passes_module._bisect_crossing(
        position_at, REFERENCE, REFERENCE + timedelta(seconds=30), THRESHOLD, 1.0
    )

    # Should still land close to the true crossing (t=15s), not bail out early.
    assert 10.0 < (crossing - REFERENCE).total_seconds() < 20.0


def test_refine_peak_falls_back_to_full_window_when_seed_window_collapses() -> None:
    position_at = _tent_position_fn(rise_s=0.0, peak_s=150.0, set_s=300.0, peak_elevation=70.0)
    rise_time = REFERENCE
    set_time = REFERENCE + timedelta(seconds=300)

    # seed_time far outside [rise_time, set_time] forces lo >= hi initially,
    # which should fall back to searching the whole [rise, set] window.
    peak_time, peak_pos = passes_module._refine_peak(
        position_at,
        REFERENCE + timedelta(seconds=100000),
        30.0,
        rise_time,
        set_time,
        1.0,
    )

    assert (peak_time - REFERENCE).total_seconds() == pytest.approx(150.0, abs=2.0)
    assert peak_pos.elevation_deg == pytest.approx(70.0, abs=0.5)


def test_refine_peak_handles_propagation_failure_at_the_final_peak_time() -> None:
    tent = _tent_position_fn(rise_s=0.0, peak_s=150.0, set_s=300.0, peak_elevation=70.0)

    def position_at(t: datetime) -> Optional[TopocentricPosition]:
        # Fail only at exactly the midpoint of [rise, set] - close to where
        # ternary search will likely land eventually.
        if t == REFERENCE + timedelta(seconds=150):
            return None
        return tent(t)

    peak_time, peak_pos = passes_module._refine_peak(
        position_at,
        REFERENCE + timedelta(seconds=150),
        30.0,
        REFERENCE,
        REFERENCE + timedelta(seconds=300),
        1.0,
    )

    # Should not raise, and should still return a real position from
    # whichever bound remained valid.
    assert peak_pos is not None
