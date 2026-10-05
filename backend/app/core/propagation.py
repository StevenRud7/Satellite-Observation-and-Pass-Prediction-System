"""
SGP4 orbital propagation.

This module wraps the `sgp4` library and knows nothing about observers,
coordinate transforms, or the API - it only turns a set of orbital
elements plus a UTC time into a satellite's position and velocity in the
TEME (True Equator, Mean Equinox) inertial frame, which is what SGP4
natively produces. Coordinate transformation into an observer-relative
view lives in `coordinates.py`; keeping the two separate matches the
project's module boundaries (propagation / coordinates / passes /
visibility, each independently testable).

We do not implement SGP4 itself - only a mature, widely-used
implementation is used here (https://pypi.org/project/sgp4/), per the
project plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from sgp4.api import Satrec, jday

from app.schemas.orbital_elements import OrbitalElementSet

# SGP4 error codes as returned by Satrec.sgp4(); see
# https://pypi.org/project/sgp4/ for the authoritative list.
SGP4_ERROR_MESSAGES: Dict[int, str] = {
    1: "mean eccentricity is outside the range 0 <= e < 1",
    2: "mean motion has gone negative",
    3: "perturbed eccentricity is outside the range 0 <= e < 1",
    4: "semi-latus rectum became negative",
    5: "epoch elements are unstable (orbital decay)",
    6: "satellite has decayed",
}


class PropagationError(Exception):
    """Raised when SGP4 cannot compute a valid position for the requested time."""


@dataclass(frozen=True)
class PropagationResult:
    time: datetime  # UTC
    position_km: Tuple[float, float, float]  # TEME x, y, z
    velocity_km_s: Tuple[float, float, float]  # TEME vx, vy, vz


def build_satrec(elements: OrbitalElementSet) -> Satrec:
    """Build an SGP4 `Satrec` propagator from a set of orbital elements."""
    return Satrec.twoline2rv(elements.line1, elements.line2)


def propagate(satrec: Satrec, when: datetime) -> PropagationResult:
    """Propagate `satrec` to `when`, returning its TEME position and velocity.

    `when` must be timezone-aware; it is converted to UTC before use.

    Raises:
        PropagationError: if SGP4 reports it cannot compute a valid position
            for this time (e.g. numerically unstable elements, or an orbit
            SGP4 considers decayed).
    """
    if when.tzinfo is None:
        raise ValueError("`when` must be timezone-aware")

    when_utc = when.astimezone(timezone.utc)
    jd, fr = jday(
        when_utc.year,
        when_utc.month,
        when_utc.day,
        when_utc.hour,
        when_utc.minute,
        when_utc.second + when_utc.microsecond / 1e6,
    )

    error_code, position, velocity = satrec.sgp4(jd, fr)

    if error_code != 0:
        message = SGP4_ERROR_MESSAGES.get(error_code, f"unknown SGP4 error code {error_code}")
        raise PropagationError(f"SGP4 propagation failed: {message}")

    return PropagationResult(time=when_utc, position_km=position, velocity_km_s=velocity)


def propagate_many(satrec: Satrec, times: List[datetime]) -> List[Optional[PropagationResult]]:
    """Propagate `satrec` to many times at once, using SGP4's own
    vectorized (array) API instead of one Python-level call per time.

    Returns one entry per input time, in the same order; a time SGP4
    can't propagate becomes `None` in that position rather than raising,
    so one bad sample in a large batch doesn't take down the rest (the
    same tolerance `propagate()` callers already build in via
    PropagationError handling - this just does it per-element instead).

    This exists purely for performance on large batches (e.g. the coarse
    sampling grid in `passes.py`) - see coordinates.py's
    `teme_to_topocentric_many` docstring for the measured numbers behind
    why this matters. For a handful of times, plain `propagate()` in a
    loop is simpler and the difference is not worth the complexity.
    """
    if not times:
        return []

    for when in times:
        if when.tzinfo is None:
            raise ValueError("all times must be timezone-aware")

    times_utc = [when.astimezone(timezone.utc) for when in times]
    jds = np.empty(len(times_utc))
    frs = np.empty(len(times_utc))
    for i, when_utc in enumerate(times_utc):
        jd, fr = jday(
            when_utc.year,
            when_utc.month,
            when_utc.day,
            when_utc.hour,
            when_utc.minute,
            when_utc.second + when_utc.microsecond / 1e6,
        )
        jds[i] = jd
        frs[i] = fr

    error_codes, positions, velocities = satrec.sgp4_array(jds, frs)

    results: List[Optional[PropagationResult]] = []
    for i, when_utc in enumerate(times_utc):
        if error_codes[i] != 0:
            results.append(None)
            continue
        results.append(
            PropagationResult(
                time=when_utc,
                position_km=tuple(positions[i]),
                velocity_km_s=tuple(velocities[i]),
            )
        )
    return results
