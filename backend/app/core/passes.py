"""
Pass detection.

Turns a series of point-in-time observer-relative positions into complete
"pass" objects: intervals during which a satellite is above a minimum
elevation threshold, with rise/peak/set details.

Algorithm (matches the project plan's "Pass Search Algorithm"):

1. Sample elevation at a coarse, regular interval across the search window.
2. Walk the samples looking for threshold crossings: below-to-above starts
   a candidate pass, above-to-below ends it.
3. Refine each crossing time with bisection, so rise/set times are accurate
   to `time_tolerance_seconds` rather than only to the sampling interval.
4. Within each pass, refine the time of maximum elevation with a ternary
   search seeded from the coarse sample that had the highest elevation.
5. Build a PassEvent from the refined rise/peak/set positions.

This prioritizes correctness and readability over performance, per the
project plan ("prioritize correctness before optimization... do not
prematurely over-engineer the pass-search algorithm").

Known simplifications (documented rather than silently assumed):
- Elevation is assumed to cross the threshold at most once between two
  consecutive coarse samples. With the default 30-second sampling
  interval this holds for essentially all real passes; an unusually fast,
  low-altitude satellite skimming exactly at the threshold could in
  principle violate it. Shrinking `sample_interval_seconds` reduces this
  risk further, at the cost of more SGP4 calls.
- The peak-finding ternary search assumes a single elevation maximum per
  pass (unimodal), which is true for the vast majority of passes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from sgp4.api import Satrec, jday

from app.core.coordinates import (
    FastObserverGeometry,
    TopocentricPosition,
    teme_to_topocentric_many,
)
from app.core.propagation import propagate_many
from app.schemas.observer import ObserverLocation
from app.schemas.pass_event import PassEvent

DEFAULT_MIN_ELEVATION_DEG = 10.0
DEFAULT_SAMPLE_INTERVAL_SECONDS = 30.0
# 1 second. This was loosened to 5s earlier (Phase 10) because every
# refinement step was a full Astropy transform; refinement is now done with
# the fast NumPy geometry (see _make_fast_position_fn), so the tighter
# tolerance costs almost nothing and rise/set/peak times are located
# about 5x more precisely than before.
DEFAULT_TIME_TOLERANCE_SECONDS = 1.0

# A position provider is anything that maps a UTC time to a topocentric
# position, or None if no position is available at that time (e.g. SGP4
# considers the orbit decayed there). The pass-search algorithm below is
# written entirely against this interface rather than against SGP4 or
# Astropy directly, which means it can be tested with fast, deterministic
# synthetic elevation curves - see tests/test_passes.py - independently of
# whether the real orbital mechanics pipeline is correct (that pipeline is
# tested separately in test_propagation.py and test_coordinates.py against
# official reference vectors).
PositionFn = Callable[[datetime], "TopocentricPosition | None"]


def _jd_fr(when_utc: datetime) -> Tuple[float, float]:
    return jday(
        when_utc.year,
        when_utc.month,
        when_utc.day,
        when_utc.hour,
        when_utc.minute,
        when_utc.second + when_utc.microsecond / 1e6,
    )


def _make_fast_position_fn(
    satrec: Satrec, observer: ObserverLocation, grid_times: List[datetime]
) -> PositionFn:
    """A position function used only to *locate* rise/peak/set times.

    Backed by one vectorized SGP4 call for the coarse grid plus a cheap
    NumPy geometry (see `FastObserverGeometry` in coordinates.py) for every
    lookup - including the many single-time lookups bisection and
    ternary-search refinement make between grid points. Those used to each
    be a full Astropy frame transform (~50-100 ms apiece, ~80% of total
    search time); here each is tens of microseconds. Positions returned
    differ from the Astropy path by well under 0.05 degrees, which only
    nudges *where* a crossing/peak is located by a fraction of a second -
    the values actually reported for each pass are recomputed with Astropy
    afterwards in `_polish_with_reference_transform`.
    """
    geometry = FastObserverGeometry(observer)

    times_utc = [t.astimezone(timezone.utc) for t in grid_times]
    jds = np.empty(len(times_utc))
    frs = np.empty(len(times_utc))
    for i, t in enumerate(times_utc):
        jds[i], frs[i] = _jd_fr(t)

    error_codes, positions, _ = satrec.sgp4_array(jds, frs)
    ok = np.asarray(error_codes) == 0

    grid_positions: Dict[datetime, TopocentricPosition] = {}
    if ok.any():
        az, el, rng = geometry.azimuth_elevation_range(jds[ok], frs[ok], positions[ok])
        valid_times = [t for t, good in zip(times_utc, ok) if good]
        for t, a, e, r in zip(valid_times, az, el, rng):
            grid_positions[t] = TopocentricPosition(
                time=t, azimuth_deg=float(a), elevation_deg=float(e), range_km=float(r)
            )

    def _position_at(when: datetime) -> Optional[TopocentricPosition]:
        when_utc = when.astimezone(timezone.utc)
        cached = grid_positions.get(when_utc)
        if cached is not None:
            return cached
        jd, fr = _jd_fr(when_utc)
        error_code, position, _ = satrec.sgp4(jd, fr)
        if error_code != 0:
            return None
        az1, el1, rng1 = geometry.azimuth_elevation_range(
            np.array([jd]), np.array([fr]), np.array([position], dtype=float)
        )
        return TopocentricPosition(
            time=when_utc,
            azimuth_deg=float(az1[0]),
            elevation_deg=float(el1[0]),
            range_km=float(rng1[0]),
        )

    return _position_at


def _polish_with_reference_transform(
    satrec: Satrec, observer: ObserverLocation, passes: List[PassEvent]
) -> List[PassEvent]:
    """Recompute every reported az/el/range with the reference Astropy
    transform, in ONE vectorized call for all passes (rise/peak/set of each).

    The times were located with the fast geometry above; this makes the
    numbers shown to the user come from exactly the same Astropy pipeline as
    before. If SGP4 fails at any of those instants (essentially never, since
    the fast search already propagated there), the pass keeps its
    search-time values rather than being dropped.
    """
    if not passes:
        return passes

    instants: List[datetime] = []
    for p in passes:
        instants.extend((p.rise_time, p.peak_time, p.set_time))

    results = propagate_many(satrec, instants)
    if any(r is None for r in results):
        return passes
    topo = teme_to_topocentric_many([r for r in results if r is not None], observer)

    polished: List[PassEvent] = []
    for i, p in enumerate(passes):
        rise, peak, set_ = topo[3 * i], topo[3 * i + 1], topo[3 * i + 2]
        polished.append(
            p.model_copy(
                update={
                    "rise_azimuth_deg": rise.azimuth_deg,
                    "peak_azimuth_deg": peak.azimuth_deg,
                    "set_azimuth_deg": set_.azimuth_deg,
                    "max_elevation_deg": peak.elevation_deg,
                    "rise_range_km": rise.range_km,
                    "max_range_km": peak.range_km,
                    "set_range_km": set_.range_km,
                }
            )
        )
    return polished


def _generate_sample_times(
    start: datetime, end: datetime, interval_seconds: float
) -> List[datetime]:
    step = timedelta(seconds=interval_seconds)
    times = []
    t = start
    while t < end:
        times.append(t)
        t += step
    times.append(end)
    return times


def _bisect_crossing(
    position_at: PositionFn,
    t_lo: datetime,
    t_hi: datetime,
    threshold_deg: float,
    tolerance_seconds: float,
) -> datetime:
    """Find the time in (t_lo, t_hi) where elevation crosses `threshold_deg`.

    Assumes elevation(t_lo) and elevation(t_hi) are on opposite sides of the
    threshold (one at-or-above, one below) and that there is exactly one
    crossing in between.
    """
    pos_lo = position_at(t_lo)
    if pos_lo is None:
        return t_lo
    sign_lo = pos_lo.elevation_deg >= threshold_deg

    while (t_hi - t_lo).total_seconds() > tolerance_seconds:
        t_mid = t_lo + (t_hi - t_lo) / 2
        pos_mid = position_at(t_mid)
        if pos_mid is None:
            # Propagation failed exactly at the midpoint; nudge and retry
            # rather than getting stuck.
            t_mid = t_mid + timedelta(seconds=tolerance_seconds / 2)
            pos_mid = position_at(t_mid)
            if pos_mid is None:
                break

        sign_mid = pos_mid.elevation_deg >= threshold_deg
        if sign_mid == sign_lo:
            t_lo = t_mid
        else:
            t_hi = t_mid

    return t_lo + (t_hi - t_lo) / 2


def _refine_peak(
    position_at: PositionFn,
    seed_time: datetime,
    window_seconds: float,
    rise_time: datetime,
    set_time: datetime,
    tolerance_seconds: float,
) -> Tuple[datetime, TopocentricPosition]:
    """Ternary-search for the elevation maximum near `seed_time`, within [rise, set]."""
    lo = max(rise_time, seed_time - timedelta(seconds=window_seconds))
    hi = min(set_time, seed_time + timedelta(seconds=window_seconds))
    if lo >= hi:
        lo, hi = rise_time, set_time

    while (hi - lo).total_seconds() > tolerance_seconds:
        third = (hi - lo) / 3
        m1 = lo + third
        m2 = hi - third

        pos1 = position_at(m1)
        pos2 = position_at(m2)
        if pos1 is None or pos2 is None:
            break

        if pos1.elevation_deg < pos2.elevation_deg:
            lo = m1
        else:
            hi = m2

    peak_time = lo + (hi - lo) / 2
    peak_pos = position_at(peak_time)
    if peak_pos is None:
        # Fall back to whichever bound still propagates rather than raising -
        # this is a rare edge case (propagation failure right at the peak).
        peak_pos = position_at(lo) or position_at(hi)
    assert peak_pos is not None
    return peak_time, peak_pos


def find_passes(
    satrec: Satrec,
    observer: ObserverLocation,
    start: datetime,
    end: datetime,
    *,
    min_elevation_deg: float = DEFAULT_MIN_ELEVATION_DEG,
    sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    time_tolerance_seconds: float = DEFAULT_TIME_TOLERANCE_SECONDS,
) -> List[PassEvent]:
    """Find all passes of a real satellite above `min_elevation_deg`, for one observer.

    Thin wrapper around `find_passes_from_position_fn`: crossing/peak times
    are located with a fast NumPy position function (see
    `_make_fast_position_fn`), then the reported rise/peak/set values are
    recomputed with the reference Astropy transform in a single batch (see
    `_polish_with_reference_transform`). Searching used to run an Astropy
    transform per refinement step, which dominated total time - this keeps
    the same results at a small fraction of the cost.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start >= end:
        raise ValueError("start must be before end")

    grid_times = _generate_sample_times(start, end, sample_interval_seconds)
    position_at = _make_fast_position_fn(satrec, observer, grid_times)
    found = find_passes_from_position_fn(
        position_at,
        start,
        end,
        min_elevation_deg=min_elevation_deg,
        sample_interval_seconds=sample_interval_seconds,
        time_tolerance_seconds=time_tolerance_seconds,
    )
    return _polish_with_reference_transform(satrec, observer, found)


def find_passes_from_position_fn(
    position_at: PositionFn,
    start: datetime,
    end: datetime,
    *,
    min_elevation_deg: float = DEFAULT_MIN_ELEVATION_DEG,
    sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    time_tolerance_seconds: float = DEFAULT_TIME_TOLERANCE_SECONDS,
) -> List[PassEvent]:
    """Find all passes above `min_elevation_deg` between `start` and `end`.

    A pass that is already in progress at `start`, or still in progress at
    `end`, is not reported - only complete rise-to-set passes fully
    contained in the window are returned. This keeps every returned pass
    fully described (a real rise time and a real set time) rather than
    silently substituting the search window's boundary.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start >= end:
        raise ValueError("start must be before end")

    sample_times = _generate_sample_times(start, end, sample_interval_seconds)
    samples: List[Tuple[datetime, TopocentricPosition]] = []
    for t in sample_times:
        pos = position_at(t)
        if pos is not None:
            samples.append((t, pos))

    passes: List[PassEvent] = []
    in_pass = False
    rise_bracket: Optional[Tuple[datetime, datetime]] = None
    peak_candidate: Optional[Tuple[datetime, TopocentricPosition]] = None

    for (t1, pos1), (t2, pos2) in zip(samples, samples[1:]):
        e1, e2 = pos1.elevation_deg, pos2.elevation_deg

        if not in_pass:
            if e1 < min_elevation_deg <= e2:
                in_pass = True
                rise_bracket = (t1, t2)
                peak_candidate = (t2, pos2)
            continue

        # We're inside a candidate pass: track the best sample seen so far.
        #
        # Only e2 (the newer sample) needs checking here, not e1 too: e1 of
        # this iteration is the exact same sample as e2 of the previous
        # iteration (samples slide one at a time), which was already
        # compared against peak_candidate then. Checking it again here can
        # never find a new maximum - it would either have already updated
        # peak_candidate last time, or already be <= it. (An earlier version
        # of this code checked both; a coverage-gap review in Phase 11
        # confirmed the e1 check was unreachable and removed it.)
        assert peak_candidate is not None
        if e2 >= min_elevation_deg and e2 > peak_candidate[1].elevation_deg:
            peak_candidate = (t2, pos2)

        if e1 >= min_elevation_deg > e2:
            # Set crossing found - finalize this pass.
            assert rise_bracket is not None
            rise_time = _bisect_crossing(
                position_at, *rise_bracket, min_elevation_deg, time_tolerance_seconds
            )
            set_time = _bisect_crossing(
                position_at, t1, t2, min_elevation_deg, time_tolerance_seconds
            )

            peak_time, peak_pos = _refine_peak(
                position_at,
                peak_candidate[0],
                sample_interval_seconds,
                rise_time,
                set_time,
                time_tolerance_seconds,
            )

            rise_pos = position_at(rise_time)
            set_pos = position_at(set_time)

            if rise_pos is not None and set_pos is not None:
                passes.append(
                    PassEvent(
                        rise_time=rise_time,
                        peak_time=peak_time,
                        set_time=set_time,
                        rise_azimuth_deg=rise_pos.azimuth_deg,
                        peak_azimuth_deg=peak_pos.azimuth_deg,
                        set_azimuth_deg=set_pos.azimuth_deg,
                        max_elevation_deg=peak_pos.elevation_deg,
                        duration_seconds=(set_time - rise_time).total_seconds(),
                        rise_range_km=rise_pos.range_km,
                        max_range_km=peak_pos.range_km,
                        set_range_km=set_pos.range_km,
                        min_elevation_threshold_deg=min_elevation_deg,
                    )
                )

            in_pass = False
            rise_bracket = None
            peak_candidate = None

    return passes
