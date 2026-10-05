from datetime import datetime, timedelta, timezone

import pytest

from app.core import scoring
from app.core.propagation import PropagationError, PropagationResult, build_satrec
from app.core.scoring import (
    _duration_score,
    _elevation_score,
    _range_score,
    _trackability_score,
    assess_pass_visibility,
    illumination_status_for_pass,
)
from app.schemas.observer import ObserverLocation
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.pass_event import PassEvent
from app.schemas.visibility import (
    ObservationMethod,
    SatelliteIlluminationStatus,
    SkyConditions,
    SkyDarkness,
)

REFERENCE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_pass_event(
    *,
    max_elevation_deg: float = 60.0,
    duration_seconds: float = 300.0,
    max_range_km: float = 1000.0,
    min_elevation_threshold_deg: float = 10.0,
) -> PassEvent:
    rise = REFERENCE
    peak = REFERENCE + timedelta(seconds=duration_seconds / 2)
    set_ = REFERENCE + timedelta(seconds=duration_seconds)
    return PassEvent(
        rise_time=rise,
        peak_time=peak,
        set_time=set_,
        rise_azimuth_deg=0.0,
        peak_azimuth_deg=90.0,
        set_azimuth_deg=180.0,
        max_elevation_deg=max_elevation_deg,
        duration_seconds=duration_seconds,
        rise_range_km=max_range_km * 1.5,
        max_range_km=max_range_km,
        set_range_km=max_range_km * 1.5,
        min_elevation_threshold_deg=min_elevation_threshold_deg,
    )


# --- Pure geometry scoring functions ---------------------------------------


def test_elevation_score_at_threshold_is_zero() -> None:
    pass_event = _make_pass_event(max_elevation_deg=10.0, min_elevation_threshold_deg=10.0)
    assert _elevation_score(pass_event) == pytest.approx(0.0)


def test_elevation_score_at_zenith_is_full() -> None:
    pass_event = _make_pass_event(max_elevation_deg=90.0, min_elevation_threshold_deg=10.0)
    assert _elevation_score(pass_event) == pytest.approx(100.0)


def test_elevation_score_is_clamped_to_valid_range() -> None:
    # Shouldn't be possible in practice, but the function must not blow up
    # or return an out-of-range score if it happens.
    pass_event = _make_pass_event(max_elevation_deg=5.0, min_elevation_threshold_deg=10.0)
    score = _elevation_score(pass_event)
    assert 0.0 <= score <= 100.0


def test_elevation_score_returns_full_score_when_threshold_is_at_zenith() -> None:
    """Edge case: a configured min_elevation_threshold_deg of 90 (straight
    up) leaves no span to normalize against - should return 100, not
    divide by zero."""
    pass_event = _make_pass_event(max_elevation_deg=90.0, min_elevation_threshold_deg=90.0)
    assert _elevation_score(pass_event) == pytest.approx(100.0)


def test_duration_score_saturates_at_full_score_seconds() -> None:
    pass_event = _make_pass_event(duration_seconds=scoring.DURATION_FULL_SCORE_SECONDS * 2)
    assert _duration_score(pass_event) == pytest.approx(100.0)


def test_duration_score_scales_linearly_below_cap() -> None:
    half_duration = scoring.DURATION_FULL_SCORE_SECONDS / 2
    pass_event = _make_pass_event(duration_seconds=half_duration)
    assert _duration_score(pass_event) == pytest.approx(50.0, abs=0.1)


def test_range_score_is_full_within_full_score_distance() -> None:
    assert _range_score(400.0, full_score_km=500.0, zero_score_km=2000.0) == pytest.approx(100.0)


def test_range_score_is_zero_beyond_zero_score_distance() -> None:
    assert _range_score(2500.0, full_score_km=500.0, zero_score_km=2000.0) == pytest.approx(0.0)


def test_range_score_is_linear_in_between() -> None:
    # Halfway between full and zero score distance -> halfway score.
    midpoint = (500.0 + 2000.0) / 2
    assert _range_score(midpoint, full_score_km=500.0, zero_score_km=2000.0) == pytest.approx(
        50.0, abs=0.1
    )


def test_trackability_score_is_full_below_easy_threshold() -> None:
    assert _trackability_score(0.01) == pytest.approx(100.0)


def test_trackability_score_hits_floor_above_hard_threshold() -> None:
    assert _trackability_score(10.0) == pytest.approx(scoring.TRACKABILITY_HARD_FLOOR_SCORE)


def test_trackability_score_decreases_monotonically() -> None:
    slow = _trackability_score(0.3)
    fast = _trackability_score(1.5)
    assert slow > fast


# --- Illumination status for a pass (monkeypatched propagation) -----------


def _patch_propagation(monkeypatch, illuminated_at: dict) -> None:
    def fake_propagate(satrec, when):
        return PropagationResult(time=when, position_km=(0, 0, 0), velocity_km_s=(0, 0, 0))

    monkeypatch.setattr(scoring, "propagate", fake_propagate)
    monkeypatch.setattr(
        scoring, "is_satellite_illuminated", lambda result: illuminated_at[result.time]
    )


def test_illumination_status_all_lit_is_illuminated(monkeypatch) -> None:
    pass_event = _make_pass_event()
    illuminated_at = {
        pass_event.rise_time: True,
        pass_event.peak_time: True,
        pass_event.set_time: True,
    }
    _patch_propagation(monkeypatch, illuminated_at)

    assert illumination_status_for_pass(None, pass_event) == SatelliteIlluminationStatus.ILLUMINATED


def test_illumination_status_all_dark_is_eclipsed(monkeypatch) -> None:
    pass_event = _make_pass_event()
    illuminated_at = {
        pass_event.rise_time: False,
        pass_event.peak_time: False,
        pass_event.set_time: False,
    }
    _patch_propagation(monkeypatch, illuminated_at)

    assert illumination_status_for_pass(None, pass_event) == SatelliteIlluminationStatus.ECLIPSED


def test_illumination_status_mixed_is_partial(monkeypatch) -> None:
    pass_event = _make_pass_event()
    illuminated_at = {
        pass_event.rise_time: True,
        pass_event.peak_time: True,
        pass_event.set_time: False,
    }
    _patch_propagation(monkeypatch, illuminated_at)

    assert illumination_status_for_pass(None, pass_event) == SatelliteIlluminationStatus.PARTIAL


def test_illumination_status_skips_failed_propagations(monkeypatch) -> None:
    pass_event = _make_pass_event()

    def fake_propagate(satrec, when):
        if when == pass_event.set_time:
            raise PropagationError("boom")
        return PropagationResult(time=when, position_km=(0, 0, 0), velocity_km_s=(0, 0, 0))

    monkeypatch.setattr(scoring, "propagate", fake_propagate)
    monkeypatch.setattr(scoring, "is_satellite_illuminated", lambda result: True)

    assert illumination_status_for_pass(None, pass_event) == SatelliteIlluminationStatus.ILLUMINATED


def test_illumination_status_all_failed_is_eclipsed(monkeypatch) -> None:
    pass_event = _make_pass_event()

    def fake_propagate(satrec, when):
        raise PropagationError("boom")

    monkeypatch.setattr(scoring, "propagate", fake_propagate)

    assert illumination_status_for_pass(None, pass_event) == SatelliteIlluminationStatus.ECLIPSED


# --- Full pipeline: real SGP4 + coordinates + astronomy --------------------


@pytest.fixture
def vanguard1_pass(valid_gp_record: dict, valid_tle_lines: tuple):
    from app.core.passes import find_passes

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
    satrec = build_satrec(elements)
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=149.95, altitude_m=0.0)
    epoch = elements.epoch

    passes = find_passes(
        satrec,
        observer,
        epoch - timedelta(minutes=15),
        epoch + timedelta(minutes=15),
        min_elevation_deg=10.0,
    )
    assert len(passes) == 1
    return satrec, observer, passes[0]


def test_assess_pass_visibility_produces_all_three_methods(vanguard1_pass) -> None:
    satrec, observer, pass_event = vanguard1_pass

    assessment = assess_pass_visibility(satrec, observer, pass_event)

    methods = {m.method for m in assessment.methods}
    assert methods == {
        ObservationMethod.NAKED_EYE,
        ObservationMethod.BINOCULARS,
        ObservationMethod.TELESCOPE,
    }


def test_assess_pass_visibility_scores_are_in_valid_range(vanguard1_pass) -> None:
    satrec, observer, pass_event = vanguard1_pass

    assessment = assess_pass_visibility(satrec, observer, pass_event)

    for method_result in assessment.methods:
        assert 0 <= method_result.score <= 100
        assert method_result.factors
        assert method_result.limitations


def test_assess_pass_visibility_matches_known_computed_scores(vanguard1_pass) -> None:
    """Regression test pinned to values computed and manually verified by
    hand during development (see project notes) for this exact geometry:
    an ~90-degree overhead pass in astronomical twilight, with the
    satellite partially eclipsed during the pass."""
    satrec, observer, pass_event = vanguard1_pass

    assessment = assess_pass_visibility(satrec, observer, pass_event)
    scores = {m.method: m.score for m in assessment.methods}

    assert assessment.satellite_illumination == SatelliteIlluminationStatus.PARTIAL
    assert scores[ObservationMethod.NAKED_EYE] == pytest.approx(47, abs=1)
    assert scores[ObservationMethod.BINOCULARS] == pytest.approx(48, abs=1)
    assert scores[ObservationMethod.TELESCOPE] == pytest.approx(45, abs=1)


def test_telescope_has_tracking_difficulty_factor(vanguard1_pass) -> None:
    satrec, observer, pass_event = vanguard1_pass

    assessment = assess_pass_visibility(satrec, observer, pass_event)
    telescope_result = next(
        m for m in assessment.methods if m.method == ObservationMethod.TELESCOPE
    )

    labels = {f.label for f in telescope_result.factors}
    assert "Tracking difficulty" in labels


def test_naked_eye_and_binoculars_have_no_tracking_difficulty_factor(vanguard1_pass) -> None:
    satrec, observer, pass_event = vanguard1_pass

    assessment = assess_pass_visibility(satrec, observer, pass_event)

    for method in (ObservationMethod.NAKED_EYE, ObservationMethod.BINOCULARS):
        result = next(m for m in assessment.methods if m.method == method)
        labels = {f.label for f in result.factors}
        assert "Tracking difficulty" not in labels


def test_faster_satellite_scores_lower_telescope_trackability() -> None:
    """A satellite with a higher apparent angular velocity should be
    penalized more heavily for telescope tracking difficulty than a slower
    one, all else equal."""
    slow_angular_velocity = 0.05
    fast_angular_velocity = 1.5

    assert _trackability_score(slow_angular_velocity) > _trackability_score(fast_angular_velocity)


def test_civil_twilight_adds_a_limitation_message() -> None:
    pass_event = _make_pass_event()
    sky = SkyConditions(
        time=REFERENCE.isoformat(), sun_altitude_deg=-3.0, sky_darkness=SkyDarkness.CIVIL_TWILIGHT
    )

    result = scoring._score_method(
        ObservationMethod.NAKED_EYE,
        pass_event,
        sky,
        SatelliteIlluminationStatus.ILLUMINATED,
        satrec=None,
    )

    assert any("twilight" in limitation.lower() for limitation in result.limitations)


def test_fast_pass_adds_a_tracking_difficulty_limitation_for_telescope(monkeypatch) -> None:
    pass_event = _make_pass_event()
    sky = SkyConditions(
        time=REFERENCE.isoformat(), sun_altitude_deg=-20.0, sky_darkness=SkyDarkness.NIGHT
    )

    # Force a very high angular velocity regardless of the (unused) satrec.
    monkeypatch.setattr(
        scoring,
        "propagate",
        lambda satrec, when: PropagationResult(
            time=when, position_km=(1000.0, 0.0, 0.0), velocity_km_s=(50.0, 0.0, 0.0)
        ),
    )

    result = scoring._score_method(
        ObservationMethod.TELESCOPE,
        pass_event,
        sky,
        SatelliteIlluminationStatus.ILLUMINATED,
        satrec=None,
    )

    assert any("tracking" in limitation.lower() for limitation in result.limitations)
    assert any(f.label == "Tracking difficulty" and f.detail == "High" for f in result.factors)
