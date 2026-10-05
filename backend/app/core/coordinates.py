"""
Coordinate transformation: TEME (SGP4's native inertial frame) to
observer-relative topocentric azimuth/elevation/range.

We deliberately do not hand-roll GMST, precession, nutation, or polar
motion here. Astropy's TEME -> ITRS -> AltAz frame transforms already
implement these correctly and are well-tested; reimplementing them would
add risk without adding value for this project (project plan: "Use
established astronomy libraries where appropriate rather than
implementing complicated astronomical transformations manually unless
doing so has educational value.").

IMPORTANT - two Astropy setup fixes are applied at import time, below,
both found by actually profiling this code (Phase 10) rather than
guessed at:

1. IERS auto-download is disabled. Astropy's AltAz/ITRS transforms can,
   by default, try to download updated Earth-orientation data (IERS
   bulletins) from the network on first use - exactly the kind of
   surprise network call we don't want inside a web request handler.
   We rely on the bundled IERS-B table instead, which is more than
   accurate enough for pass prediction (arc-second-level Earth
   orientation corrections are irrelevant when we care about
   degree-level visibility, not sub-arcsecond astrometry).

2. That bundled IERS-B table is loaded and registered as the *global*
   Earth-orientation table once, here, at import time. Without this,
   Astropy still works correctly, but profiling `find_passes` (Phase 10)
   showed each individual coordinate transform re-opening and
   re-parsing the on-disk IERS table from scratch - the dominant cost of
   a ~47ms-per-call transform. Loading it once up front turns that into
   a one-time startup cost instead of a per-call one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

import numpy as np
from astropy import units as u
from astropy.coordinates import (
    ITRS,
    TEME,
    AltAz,
    CartesianDifferential,
    CartesianRepresentation,
    EarthLocation,
)
from astropy.time import Time
from astropy.utils import iers

iers.conf.auto_download = False
iers.earth_orientation_table.set(iers.IERS_B.open())

from app.core.propagation import PropagationResult  # noqa: E402
from app.schemas.observer import ObserverLocation  # noqa: E402


@dataclass(frozen=True)
class TopocentricPosition:
    time: datetime  # UTC
    azimuth_deg: float
    elevation_deg: float
    range_km: float


def observer_earth_location(observer: ObserverLocation) -> EarthLocation:
    return EarthLocation.from_geodetic(
        lon=observer.longitude_deg * u.deg,
        lat=observer.latitude_deg * u.deg,
        height=observer.altitude_m * u.m,
    )


def teme_to_topocentric(
    result: PropagationResult, observer: ObserverLocation
) -> TopocentricPosition:
    """Convert a single TEME position/velocity into topocentric az/el/range.

    For more than a handful of times, prefer `teme_to_topocentric_many` -
    see its docstring for why (short version: ~60x faster at scale,
    measured, not assumed - Phase 10 notes).
    """
    return teme_to_topocentric_many([result], observer)[0]


def teme_to_topocentric_many(
    results: List[PropagationResult], observer: ObserverLocation
) -> List[TopocentricPosition]:
    """Convert many TEME position/velocities (same observer) into
    topocentric az/el/range, in one vectorized Astropy call.

    Why this exists: profiling `find_passes` (Phase 10) showed each
    individual `transform_to` call costs ~1-2ms of fixed Python/Quantity
    object-creation overhead, regardless of how much actual numeric work
    it does - Astropy's coordinate frames are built for correctness and
    for handling *arrays* efficiently, not for being called with scalars
    in a tight loop. Passing an array of N times through one transform
    call pays that fixed overhead once instead of N times: measured at
    ~60x faster for a 24-hour pass search (2880 samples) than calling
    `teme_to_topocentric` in a loop. The math is identical either way -
    this is purely a performance path, not a different calculation.
    """
    if not results:
        return []

    astropy_times = Time([r.time for r in results])

    positions_km = np.array([r.position_km for r in results])
    velocities_km_s = np.array([r.velocity_km_s for r in results])

    teme_position = CartesianRepresentation(
        positions_km[:, 0] * u.km, positions_km[:, 1] * u.km, positions_km[:, 2] * u.km
    )
    teme_velocity = CartesianDifferential(
        velocities_km_s[:, 0] * u.km / u.s,
        velocities_km_s[:, 1] * u.km / u.s,
        velocities_km_s[:, 2] * u.km / u.s,
    )
    teme_coord = TEME(teme_position.with_differentials(teme_velocity), obstime=astropy_times)

    itrs_coord = teme_coord.transform_to(ITRS(obstime=astropy_times))

    location = observer_earth_location(observer)
    topocentric_frame = AltAz(obstime=astropy_times, location=location)
    topocentric = itrs_coord.transform_to(topocentric_frame)

    az_values = topocentric.az.degree
    alt_values = topocentric.alt.degree
    range_values = topocentric.distance.to(u.km).value

    return [
        TopocentricPosition(
            time=results[i].time,
            azimuth_deg=float(az_values[i]),
            elevation_deg=float(alt_values[i]),
            range_km=float(range_values[i]),
        )
        for i in range(len(results))
    ]
