import math
from datetime import datetime, timezone
from typing import Tuple

import pytest

from app.core.propagation import PropagationResult
from app.core.visibility import (
    classify_sky_darkness,
    is_satellite_illuminated,
    sky_conditions_at,
    sun_altitude_deg,
)
from app.schemas.observer import ObserverLocation
from app.schemas.visibility import SkyDarkness


@pytest.mark.parametrize(
    "altitude,expected",
    [
        (10.0, SkyDarkness.DAYLIGHT),
        (0.0001, SkyDarkness.DAYLIGHT),
        (0.0, SkyDarkness.CIVIL_TWILIGHT),
        (-3.0, SkyDarkness.CIVIL_TWILIGHT),
        (-6.0, SkyDarkness.NAUTICAL_TWILIGHT),
        (-9.0, SkyDarkness.NAUTICAL_TWILIGHT),
        (-12.0, SkyDarkness.ASTRONOMICAL_TWILIGHT),
        (-15.0, SkyDarkness.ASTRONOMICAL_TWILIGHT),
        (-18.0, SkyDarkness.NIGHT),
        (-45.0, SkyDarkness.NIGHT),
    ],
)
def test_classify_sky_darkness_boundaries(altitude: float, expected: SkyDarkness) -> None:
    assert classify_sky_darkness(altitude) == expected


def test_sun_altitude_near_zenith_at_equatorial_equinox_noon() -> None:
    # Known astronomical geometry: near the equator, near an equinox, near
    # local solar noon, the Sun should be close to directly overhead.
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0)
    when = datetime(2024, 3, 20, 12, 0, 0, tzinfo=timezone.utc)

    altitude = sun_altitude_deg(observer, when)

    assert altitude == pytest.approx(88.17, abs=0.5)


def test_sun_altitude_near_nadir_at_equatorial_equinox_midnight() -> None:
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0)
    when = datetime(2024, 3, 20, 0, 0, 0, tzinfo=timezone.utc)

    altitude = sun_altitude_deg(observer, when)

    assert altitude == pytest.approx(-88.14, abs=0.5)


def test_sky_conditions_at_wires_altitude_to_classification() -> None:
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0)
    when = datetime(2024, 3, 20, 0, 0, 0, tzinfo=timezone.utc)

    conditions = sky_conditions_at(observer, when)

    assert conditions.sky_darkness == classify_sky_darkness(conditions.sun_altitude_deg)
    assert conditions.time == when.isoformat()


REFERENCE_TIME = datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc)


def _sun_unit_vector_teme() -> Tuple[float, float, float]:
    """Direction toward the Sun in TEME coordinates at REFERENCE_TIME,
    computed independently here (not reusing the module under test) so the
    constructed geometries below are a genuine external check."""
    from astropy import units as u
    from astropy.coordinates import TEME, get_sun
    from astropy.time import Time

    t = Time(REFERENCE_TIME)
    sun_teme = get_sun(t).transform_to(TEME(obstime=t))
    x, y, z = sun_teme.cartesian.xyz.to(u.km).value
    d = math.sqrt(x * x + y * y + z * z)
    return (x / d, y / d, z / d)


def test_satellite_toward_sun_is_illuminated() -> None:
    ux, uy, uz = _sun_unit_vector_teme()
    position = (ux * 7000.0, uy * 7000.0, uz * 7000.0)
    result = PropagationResult(time=REFERENCE_TIME, position_km=position, velocity_km_s=(0, 0, 0))

    assert is_satellite_illuminated(result) is True


def test_satellite_directly_behind_earth_from_sun_is_eclipsed() -> None:
    ux, uy, uz = _sun_unit_vector_teme()
    # Directly opposite the Sun, well within one Earth radius of the shadow axis.
    position = (-ux * 7000.0, -uy * 7000.0, -uz * 7000.0)
    result = PropagationResult(time=REFERENCE_TIME, position_km=position, velocity_km_s=(0, 0, 0))

    assert is_satellite_illuminated(result) is False


def test_satellite_far_off_shadow_axis_on_night_side_is_illuminated() -> None:
    """Even on the 'night side' (along_sun < 0), a satellite far enough from
    the Earth-Sun line (beyond Earth's shadow radius) should still be lit -
    this is what distinguishes a cylindrical shadow from simply checking
    which hemisphere the satellite is in."""
    ux, uy, uz = _sun_unit_vector_teme()

    # Build a vector perpendicular to the sun direction.
    arbitrary = (1.0, 0.0, 0.0) if abs(ux) < 0.9 else (0.0, 1.0, 0.0)
    px = uy * arbitrary[2] - uz * arbitrary[1]
    py = uz * arbitrary[0] - ux * arbitrary[2]
    pz = ux * arbitrary[1] - uy * arbitrary[0]
    norm = math.sqrt(px * px + py * py + pz * pz)
    perp = (px / norm, py / norm, pz / norm)

    # Slightly on the night side, but 20,000 km off-axis - well outside Earth's shadow.
    position = (
        -ux * 500.0 + perp[0] * 20000.0,
        -uy * 500.0 + perp[1] * 20000.0,
        -uz * 500.0 + perp[2] * 20000.0,
    )
    result = PropagationResult(time=REFERENCE_TIME, position_km=position, velocity_km_s=(0, 0, 0))

    assert is_satellite_illuminated(result) is True
