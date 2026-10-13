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
from typing import List, Tuple

import erfa
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


# ---------------------------------------------------------------------------
# Fast search-time geometry
#
# `teme_to_topocentric_many` above is the reference-quality transform and is
# what every *reported* azimuth/elevation/range comes from. But Astropy's
# frame machinery costs roughly 50-100 ms per call even for a single point
# (measured: ~250 scalar calls to refine the rise/peak/set of 11 passes was
# ~80% of a 72-hour search), and pass *searching* needs thousands of
# throwaway elevation lookups (the coarse grid, then bisection and
# ternary-search steps). `FastObserverGeometry` does the same TEME -> ITRS
# -> local-horizon rotation chain directly in NumPy - same GMST82 function
# Astropy uses (via pyerfa), same WGS84 ellipsoid - which makes those lookups
# microseconds instead of milliseconds. It deliberately omits polar motion
# and the UT1-UTC offset (both sub-0.01 degree effects), which is fine for
# *locating* a crossing/peak time; `passes.find_passes` then recomputes the
# reported rise/peak/set values with the Astropy path above, so nothing
# user-visible is computed with the approximation.
# ---------------------------------------------------------------------------

_WGS84_A_KM = 6378.137
_WGS84_F = 1.0 / 298.257223563
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)


class FastObserverGeometry:
    """Vectorized TEME -> azimuth/elevation/range for one fixed observer."""

    def __init__(self, observer: ObserverLocation) -> None:
        lat = np.radians(observer.latitude_deg)
        lon = np.radians(observer.longitude_deg)
        height_km = observer.altitude_m / 1000.0

        sin_lat, cos_lat = np.sin(lat), np.cos(lat)
        sin_lon, cos_lon = np.sin(lon), np.cos(lon)

        prime_vertical = _WGS84_A_KM / np.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
        self._observer_ecef = np.array(
            [
                (prime_vertical + height_km) * cos_lat * cos_lon,
                (prime_vertical + height_km) * cos_lat * sin_lon,
                (prime_vertical * (1.0 - _WGS84_E2) + height_km) * sin_lat,
            ]
        )
        # Rows: east, north, up unit vectors in ECEF.
        self._enu = np.array(
            [
                [-sin_lon, cos_lon, 0.0],
                [-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat],
                [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat],
            ]
        )

    def azimuth_elevation_range(
        self, jd: np.ndarray, fr: np.ndarray, teme_positions_km: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Az (deg, 0-360), el (deg), range (km) for N TEME positions at the
        UTC Julian dates given as (`jd`, `fr`) pairs (SGP4's own convention)."""
        gmst = erfa.gmst82(jd, fr)
        cos_g, sin_g = np.cos(gmst), np.sin(gmst)

        x, y, z = teme_positions_km[:, 0], teme_positions_km[:, 1], teme_positions_km[:, 2]
        # TEME -> ECEF is a rotation about z by the Greenwich sidereal angle.
        ecef = np.empty_like(teme_positions_km)
        ecef[:, 0] = cos_g * x + sin_g * y
        ecef[:, 1] = -sin_g * x + cos_g * y
        ecef[:, 2] = z

        rel = ecef - self._observer_ecef
        enu = rel @ self._enu.T
        east, north, up = enu[:, 0], enu[:, 1], enu[:, 2]

        horizontal = np.hypot(east, north)
        rng = np.sqrt(east * east + north * north + up * up)
        elevation = np.degrees(np.arctan2(up, horizontal))
        azimuth = np.degrees(np.arctan2(east, north)) % 360.0
        return azimuth, elevation, rng
