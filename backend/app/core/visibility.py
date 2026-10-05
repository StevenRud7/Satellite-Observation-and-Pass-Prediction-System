"""
Astronomy building blocks for the visibility engine: where the Sun is, how
dark the sky is at the observer, and whether the satellite itself is
sunlit at a given moment.

As in coordinates.py, we lean on Astropy (`get_sun`, `AltAz`) rather than
hand-rolling solar position algorithms - same reasoning: an established,
well-tested library beats a bespoke implementation for something this
foundational.

Satellite illumination uses a simplified **cylindrical Earth-shadow
model**: a satellite is considered eclipsed if it is on the night side of
Earth and within one Earth-radius of the Sun-Earth line. This ignores the
penumbra (partial shadow) and Earth's oblateness - a standard, widely used
simplification (the same one many amateur pass-prediction tools use) that
is more than adequate for "is the satellite likely visible", but is not a
precise eclipse calculation. See project plan section 13/32: brightness
and illumination-adjacent predictions are inherently lower-confidence than
orbital position itself.
"""

from __future__ import annotations

import math
from datetime import datetime

from astropy import units as u
from astropy.coordinates import TEME, AltAz, get_sun
from astropy.time import Time

from app.core.coordinates import observer_earth_location
from app.core.propagation import PropagationResult
from app.schemas.observer import ObserverLocation
from app.schemas.visibility import SkyConditions, SkyDarkness

# WGS84 equatorial radius. Using a single spherical radius (rather than
# modeling Earth's actual oblate shape) is the standard simplification for
# a cylindrical shadow model.
EARTH_RADIUS_KM = 6378.137


def classify_sky_darkness(sun_altitude_deg: float) -> SkyDarkness:
    if sun_altitude_deg > 0.0:
        return SkyDarkness.DAYLIGHT
    if sun_altitude_deg > -6.0:
        return SkyDarkness.CIVIL_TWILIGHT
    if sun_altitude_deg > -12.0:
        return SkyDarkness.NAUTICAL_TWILIGHT
    if sun_altitude_deg > -18.0:
        return SkyDarkness.ASTRONOMICAL_TWILIGHT
    return SkyDarkness.NIGHT


def sun_altitude_deg(observer: ObserverLocation, when: datetime) -> float:
    """The Sun's altitude above the observer's horizon, in degrees."""
    astropy_time = Time(when)
    sun = get_sun(astropy_time)
    location = observer_earth_location(observer)
    sun_altaz = sun.transform_to(AltAz(obstime=astropy_time, location=location))
    return float(sun_altaz.alt.degree)


def sky_conditions_at(observer: ObserverLocation, when: datetime) -> SkyConditions:
    altitude = sun_altitude_deg(observer, when)
    return SkyConditions(
        time=when.isoformat(),
        sun_altitude_deg=altitude,
        sky_darkness=classify_sky_darkness(altitude),
    )


def is_satellite_illuminated(result: PropagationResult) -> bool:
    """Whether the satellite is sunlit, per the cylindrical shadow model above."""
    astropy_time = Time(result.time)

    sun_gcrs = get_sun(astropy_time)
    sun_teme = sun_gcrs.transform_to(TEME(obstime=astropy_time))
    sx, sy, sz = sun_teme.cartesian.xyz.to(u.km).value
    sun_distance = math.sqrt(sx * sx + sy * sy + sz * sz)
    sun_unit = (sx / sun_distance, sy / sun_distance, sz / sun_distance)

    px, py, pz = result.position_km
    along_sun = px * sun_unit[0] + py * sun_unit[1] + pz * sun_unit[2]

    if along_sun > 0:
        # Satellite is on the sunward side of Earth - always lit regardless
        # of distance from the shadow axis.
        return True

    perp_x = px - along_sun * sun_unit[0]
    perp_y = py - along_sun * sun_unit[1]
    perp_z = pz - along_sun * sun_unit[2]
    perp_distance = math.sqrt(perp_x * perp_x + perp_y * perp_y + perp_z * perp_z)

    return perp_distance > EARTH_RADIUS_KM
