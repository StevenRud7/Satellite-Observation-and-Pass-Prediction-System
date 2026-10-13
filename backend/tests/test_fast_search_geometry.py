"""
Guards for the fast pass-search path (see coordinates.FastObserverGeometry and
passes._make_fast_position_fn):

1. The fast geometry stays close to the reference Astropy transform.
2. Every az/el/range that `find_passes` *reports* is exactly what the
   reference Astropy transform gives at the reported times - i.e. the fast
   path only decides *when* things happen, never what numbers are shown.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import Satrec, jday

from app.core.coordinates import FastObserverGeometry, teme_to_topocentric_many
from app.core.passes import find_passes
from app.core.propagation import propagate, propagate_many
from app.schemas.observer import ObserverLocation

LINE1 = "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
LINE2 = "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482"
START = datetime(2019, 12, 10, 12, tzinfo=timezone.utc)


def _satrec() -> Satrec:
    return Satrec.twoline2rv(LINE1, LINE2)


def test_fast_geometry_matches_astropy_within_search_tolerance() -> None:
    sat = _satrec()
    for lat, lon, alt in [(32.08, 34.78, 0.0), (-33.9, 151.2, 50.0), (64.1, -21.9, 0.0)]:
        observer = ObserverLocation(latitude_deg=lat, longitude_deg=lon, altitude_m=alt)
        times = [START + timedelta(seconds=30 * i) for i in range(600)]
        results = [r for r in propagate_many(sat, times) if r is not None]
        reference = teme_to_topocentric_many(results, observer)

        jd = np.empty(len(results))
        fr = np.empty(len(results))
        for i, r in enumerate(results):
            t = r.time
            jd[i], fr[i] = jday(
                t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6
            )
        positions = np.array([r.position_km for r in results])
        az, el, rng = FastObserverGeometry(observer).azimuth_elevation_range(jd, fr, positions)

        ref_el = np.array([p.elevation_deg for p in reference])
        ref_rng = np.array([p.range_km for p in reference])
        ref_az = np.array([p.azimuth_deg for p in reference])

        assert np.abs(el - ref_el).max() < 0.1
        assert np.abs(rng - ref_rng).max() < 2.0
        above = ref_el > 0
        az_diff = np.abs((az - ref_az + 180.0) % 360.0 - 180.0)
        assert az_diff[above].max() < 0.2


def test_reported_pass_values_are_exact_astropy_values_at_reported_times() -> None:
    sat = _satrec()
    observer = ObserverLocation(latitude_deg=32.08, longitude_deg=34.78, altitude_m=20.0)

    passes = find_passes(sat, observer, START, START + timedelta(hours=48))
    assert passes, "expected at least one pass in 48 hours"

    for p in passes:
        for when, az, el_or_none, rng in (
            (p.rise_time, p.rise_azimuth_deg, None, p.rise_range_km),
            (p.peak_time, p.peak_azimuth_deg, p.max_elevation_deg, p.max_range_km),
            (p.set_time, p.set_azimuth_deg, None, p.set_range_km),
        ):
            ref = teme_to_topocentric_many([propagate(sat, when)], observer)[0]
            assert abs(ref.azimuth_deg - az) < 1e-9
            assert abs(ref.range_km - rng) < 1e-9
            if el_or_none is not None:
                assert abs(ref.elevation_deg - el_or_none) < 1e-9


def test_passes_are_ordered_and_above_threshold_at_peak() -> None:
    sat = _satrec()
    observer = ObserverLocation(latitude_deg=51.5, longitude_deg=-0.12, altitude_m=0.0)

    passes = find_passes(sat, observer, START, START + timedelta(hours=72), min_elevation_deg=10.0)

    for p in passes:
        assert p.rise_time < p.peak_time < p.set_time
        assert p.max_elevation_deg >= 10.0
        assert p.duration_seconds > 0
