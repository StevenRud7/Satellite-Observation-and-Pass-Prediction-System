"""
Observation Suitability Score.

Combines pass geometry (from passes.py) with sky/illumination conditions
(from visibility.py) into a 0-100 heuristic score per observation method
(naked eye, binoculars, telescope), a classification band, a confidence
level, and a human-readable explanation of why.

This is a heuristic ranking, not a probability of successfully seeing the
satellite (project plan section 12). The weights and curves below are
documented, reasonable defaults - not physical laws, and not the only
reasonable choice. They are kept deliberately simple: the least certain
input (satellite brightness) isn't precise enough to justify a more
elaborate model (see project plan sections 13 and 32).

Method-specific modeling choices, briefly:
- Naked eye: needs the darkest sky and the closest/highest pass; most
  sensitive to range and darkness.
- Binoculars: more forgiving of range and modest twilight than naked eye
  (more light-gathering), otherwise similar.
- Telescope: most forgiving of range and twilight (best light-gathering),
  but penalized by tracking difficulty - a satellite's apparent angular
  speed is roughly (orbital speed / range), and a narrow telescope field
  of view makes fast-moving, close passes hard to track and keep centered.
  This is why a telescope does not automatically get the highest score
  (project plan section 14.3): more magnification does not make a fast
  target easier to follow.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, Optional, Tuple

from sgp4.api import Satrec

from app.core.propagation import PropagationError, propagate
from app.core.visibility import is_satellite_illuminated, sky_conditions_at
from app.schemas.observer import ObserverLocation
from app.schemas.pass_event import PassEvent
from app.schemas.visibility import (
    ConfidenceLevel,
    MethodVisibility,
    ObservationMethod,
    PassVisibilityAssessment,
    SatelliteIlluminationStatus,
    SkyConditions,
    SkyDarkness,
    VisibilityFactor,
    classify_score,
)

# --- Geometry scoring constants --------------------------------------------

DURATION_FULL_SCORE_SECONDS = 360.0  # 6 minutes - close to the longest a typical LEO pass gets

# (full-score range, zero-score range) per method, in km. Naked eye needs
# the satellite close; binoculars and telescopes can pick up fainter,
# farther objects.
_RANGE_CURVE_KM: Dict[ObservationMethod, Tuple[float, float]] = {
    ObservationMethod.NAKED_EYE: (500.0, 2000.0),
    ObservationMethod.BINOCULARS: (500.0, 3000.0),
    ObservationMethod.TELESCOPE: (500.0, 4000.0),
}

# Multiplier applied to the geometry score based on sky darkness. Telescope
# and binoculars are slightly more forgiving of twilight than the naked
# eye; daylight is a near-total gate for all three (this project does not
# model specialized daylight satellite tracking - see limitations).
_DARKNESS_MULTIPLIER: Dict[ObservationMethod, Dict[SkyDarkness, float]] = {
    ObservationMethod.NAKED_EYE: {
        SkyDarkness.NIGHT: 1.0,
        SkyDarkness.ASTRONOMICAL_TWILIGHT: 1.0,
        SkyDarkness.NAUTICAL_TWILIGHT: 0.85,
        SkyDarkness.CIVIL_TWILIGHT: 0.5,
        SkyDarkness.DAYLIGHT: 0.05,
    },
    ObservationMethod.BINOCULARS: {
        SkyDarkness.NIGHT: 1.0,
        SkyDarkness.ASTRONOMICAL_TWILIGHT: 1.0,
        SkyDarkness.NAUTICAL_TWILIGHT: 0.9,
        SkyDarkness.CIVIL_TWILIGHT: 0.65,
        SkyDarkness.DAYLIGHT: 0.1,
    },
    ObservationMethod.TELESCOPE: {
        SkyDarkness.NIGHT: 1.0,
        SkyDarkness.ASTRONOMICAL_TWILIGHT: 1.0,
        SkyDarkness.NAUTICAL_TWILIGHT: 0.9,
        SkyDarkness.CIVIL_TWILIGHT: 0.65,
        SkyDarkness.DAYLIGHT: 0.1,
    },
}

_ILLUMINATION_MULTIPLIER: Dict[SatelliteIlluminationStatus, float] = {
    SatelliteIlluminationStatus.ILLUMINATED: 1.0,
    SatelliteIlluminationStatus.PARTIAL: 0.5,
    SatelliteIlluminationStatus.ECLIPSED: 0.05,
}

# Angular-velocity-to-trackability curve, in degrees/second. Below the easy
# threshold, tracking is effectively no harder than following a plane;
# above the hard threshold, keeping a satellite centered in a telescope
# eyepiece is genuinely difficult even for an experienced observer.
TRACKABILITY_EASY_DEG_PER_SEC = 0.1
TRACKABILITY_HARD_DEG_PER_SEC = 2.0
TRACKABILITY_HARD_FLOOR_SCORE = 15.0  # never treat a fast pass as literally impossible

_GEOMETRY_WEIGHTS: Dict[ObservationMethod, Dict[str, float]] = {
    ObservationMethod.NAKED_EYE: {"elevation": 0.35, "duration": 0.30, "range": 0.35},
    ObservationMethod.BINOCULARS: {"elevation": 0.30, "duration": 0.30, "range": 0.40},
    ObservationMethod.TELESCOPE: {
        "elevation": 0.25,
        "duration": 0.20,
        "range": 0.20,
        "trackability": 0.35,
    },
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _elevation_score(pass_event: PassEvent) -> float:
    span = 90.0 - pass_event.min_elevation_threshold_deg
    if span <= 0:
        return 100.0
    raw = (pass_event.max_elevation_deg - pass_event.min_elevation_threshold_deg) / span * 100.0
    return _clamp(raw)


def _duration_score(pass_event: PassEvent) -> float:
    return _clamp(pass_event.duration_seconds / DURATION_FULL_SCORE_SECONDS * 100.0)


def _range_score(range_km: float, full_score_km: float, zero_score_km: float) -> float:
    if range_km <= full_score_km:
        return 100.0
    if range_km >= zero_score_km:
        return 0.0
    span = zero_score_km - full_score_km
    raw = 100.0 * (1.0 - (range_km - full_score_km) / span)
    return _clamp(raw)


def _angular_velocity_deg_per_sec(satrec: Satrec, peak_time: datetime, range_km: float) -> float:
    """Approximate apparent angular speed at closest approach.

    Uses the satellite's total orbital speed (from SGP4) divided by the
    topocentric range as a proxy for its transverse (across-the-sky)
    angular rate. This slightly overestimates angular speed for passes
    that aren't exactly overhead (some of the true velocity is radial,
    not transverse), which is a conservative bias for a "how hard is this
    to track" warning rather than a precise ephemeris.
    """
    result = propagate(satrec, peak_time)
    speed_km_s = math.sqrt(sum(component**2 for component in result.velocity_km_s))
    angular_rate_rad_s = speed_km_s / range_km
    return math.degrees(angular_rate_rad_s)


def _trackability_score(angular_velocity_deg_per_sec: float) -> float:
    if angular_velocity_deg_per_sec <= TRACKABILITY_EASY_DEG_PER_SEC:
        return 100.0
    if angular_velocity_deg_per_sec >= TRACKABILITY_HARD_DEG_PER_SEC:
        return TRACKABILITY_HARD_FLOOR_SCORE
    span = TRACKABILITY_HARD_DEG_PER_SEC - TRACKABILITY_EASY_DEG_PER_SEC
    raw = (
        100.0
        - (100.0 - TRACKABILITY_HARD_FLOOR_SCORE)
        * (angular_velocity_deg_per_sec - TRACKABILITY_EASY_DEG_PER_SEC)
        / span
    )
    return _clamp(raw)


def illumination_status_for_pass(
    satrec: Satrec, pass_event: PassEvent
) -> SatelliteIlluminationStatus:
    """Sample illumination at rise, peak, and set to catch a satellite
    entering or leaving Earth's shadow mid-pass, without fully re-sampling
    the whole pass at high resolution."""
    statuses = []
    for t in (pass_event.rise_time, pass_event.peak_time, pass_event.set_time):
        try:
            result = propagate(satrec, t)
        except PropagationError:
            continue
        statuses.append(is_satellite_illuminated(result))

    if not statuses:
        return SatelliteIlluminationStatus.ECLIPSED
    if all(statuses):
        return SatelliteIlluminationStatus.ILLUMINATED
    if not any(statuses):
        return SatelliteIlluminationStatus.ECLIPSED
    return SatelliteIlluminationStatus.PARTIAL


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s"


def _sky_label(darkness: SkyDarkness) -> str:
    return {
        SkyDarkness.NIGHT: "Astronomically dark",
        SkyDarkness.ASTRONOMICAL_TWILIGHT: "Astronomical twilight",
        SkyDarkness.NAUTICAL_TWILIGHT: "Nautical twilight",
        SkyDarkness.CIVIL_TWILIGHT: "Civil twilight",
        SkyDarkness.DAYLIGHT: "Daylight",
    }[darkness]


def _illumination_label(status: SatelliteIlluminationStatus) -> str:
    return {
        SatelliteIlluminationStatus.ILLUMINATED: "Favorable - sunlit throughout the pass",
        SatelliteIlluminationStatus.PARTIAL: "Mixed - enters or exits Earth's shadow mid-pass",
        SatelliteIlluminationStatus.ECLIPSED: "Unfavorable - in Earth's shadow",
    }[status]


_BASE_LIMITATION = (
    "Actual visibility depends on local sky conditions, obstructions, "
    "atmospheric conditions, and satellite orientation, which this score "
    "cannot fully capture. Estimated brightness is not modeled precisely."
)


def _score_method(
    method: ObservationMethod,
    pass_event: PassEvent,
    sky: SkyConditions,
    illumination: SatelliteIlluminationStatus,
    satrec: Satrec,
) -> MethodVisibility:
    weights = _GEOMETRY_WEIGHTS[method]
    full_km, zero_km = _RANGE_CURVE_KM[method]

    elevation_score = _elevation_score(pass_event)
    duration_score = _duration_score(pass_event)
    range_score = _range_score(pass_event.max_range_km, full_km, zero_km)

    geometry_score = weights["elevation"] * elevation_score + weights["duration"] * duration_score
    geometry_score += weights["range"] * range_score

    trackability_score: Optional[float] = None
    if method is ObservationMethod.TELESCOPE:
        angular_velocity = _angular_velocity_deg_per_sec(
            satrec, pass_event.peak_time, pass_event.max_range_km
        )
        trackability_score = _trackability_score(angular_velocity)
        geometry_score += weights["trackability"] * trackability_score

    darkness_multiplier = _DARKNESS_MULTIPLIER[method][sky.sky_darkness]
    illumination_multiplier = _ILLUMINATION_MULTIPLIER[illumination]

    final_score = _clamp(geometry_score * darkness_multiplier * illumination_multiplier)
    classification = classify_score(final_score)

    confidence = ConfidenceLevel.MEDIUM
    civil_twilight_marginal = sky.sky_darkness is SkyDarkness.CIVIL_TWILIGHT and final_score < 60
    hard_to_track = trackability_score is not None and trackability_score < 30
    is_uncertain = (
        illumination is SatelliteIlluminationStatus.PARTIAL
        or civil_twilight_marginal
        or hard_to_track
    )
    if is_uncertain:
        confidence = ConfidenceLevel.LOW

    factors = [
        VisibilityFactor(label="Maximum elevation", detail=f"{pass_event.max_elevation_deg:.0f}°"),
        VisibilityFactor(label="Duration", detail=_format_duration(pass_event.duration_seconds)),
        VisibilityFactor(label="Sky", detail=_sky_label(sky.sky_darkness)),
        VisibilityFactor(label="Satellite illumination", detail=_illumination_label(illumination)),
        VisibilityFactor(label="Closest range", detail=f"{pass_event.max_range_km:.0f} km"),
    ]
    if trackability_score is not None:
        difficulty_label = (
            "Low"
            if trackability_score >= 70
            else "Moderate" if trackability_score >= 40 else "High"
        )
        factors.append(VisibilityFactor(label="Tracking difficulty", detail=difficulty_label))

    limitations = [_BASE_LIMITATION]
    if illumination is SatelliteIlluminationStatus.PARTIAL:
        limitations.append(
            "The satellite enters or exits Earth's shadow during this pass and may "
            "fade in or out partway through."
        )
    if sky.sky_darkness is SkyDarkness.CIVIL_TWILIGHT:
        limitations.append(
            "Civil twilight means some sky glow is still present, which can make "
            "fainter objects harder to see than this score alone suggests."
        )
    if trackability_score is not None and trackability_score < 50:
        limitations.append(
            "This pass's apparent angular speed is fast enough that manual "
            "telescope tracking may be difficult, especially at higher magnification."
        )

    return MethodVisibility(
        method=method,
        score=round(final_score),
        classification=classification,
        confidence=confidence,
        factors=factors,
        limitations=limitations,
    )


def assess_pass_visibility(
    satrec: Satrec, observer: ObserverLocation, pass_event: PassEvent
) -> PassVisibilityAssessment:
    """Score a pass for all three observation methods.

    Sky darkness is evaluated once, at the pass's peak - a reasonable
    simplification given passes are typically a few minutes long and the
    Sun's altitude changes slowly on that timescale. Satellite illumination
    is checked separately at rise, peak, and set, since a satellite can
    genuinely enter or leave Earth's shadow mid-pass.
    """
    sky = sky_conditions_at(observer, pass_event.peak_time)
    illumination = illumination_status_for_pass(satrec, pass_event)

    methods = [
        _score_method(method, pass_event, sky, illumination, satrec) for method in ObservationMethod
    ]

    return PassVisibilityAssessment(
        pass_event=pass_event,
        sky_conditions=sky,
        satellite_illumination=illumination,
        methods=methods,
    )
