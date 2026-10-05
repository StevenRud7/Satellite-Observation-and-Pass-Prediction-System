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

from sgp4.api import Satrec

from app.core.coordinates import TopocentricPosition, teme_to_topocentric, teme_to_topocentric_many
from app.core.propagation import PropagationError, propagate, propagate_many
from app.schemas.observer import ObserverLocation
from app.schemas.pass_event import PassEvent

DEFAULT_MIN_ELEVATION_DEG = 10.0
DEFAULT_SAMPLE_INTERVAL_SECONDS = 30.0
# 5 seconds, not 1: profiling (Phase 10) showed each refinement step
# (bisection/ternary search) costs real time - each one is a real
# Astropy coordinate transform - and tighter tolerance buys precision
# nobody needs here. A rise/set time accurate to 5 seconds, or a peak
# elevation accurate to a similarly small fraction of a degree, is far
# more precision than a human going outside to look at the sky (or a
# telescope being manually pointed) can use. Loosening this from 1.0 to
# 5.0 cut 24-hour search time by roughly 25% with no meaningful loss of
# usefulness.
DEFAULT_TIME_TOLERANCE_SECONDS = 5.0

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


def _make_position_fn(satrec: Satrec, observer: ObserverLocation) -> PositionFn:
    def _position_at(when: datetime) -> Optional[TopocentricPosition]:
        try:
            result = propagate(satrec, when)
        except PropagationError:
            return None
        return teme_to_topocentric(result, observer)

    return _position_at


def _make_batch_position_fn(
    satrec: Satrec, observer: ObserverLocation, grid_times: List[datetime]
) -> PositionFn:
    """A position function backed by one vectorized batch propagation of
    `grid_times` (see coordinates.py's `teme_to_topocentric_many` for the
    measured performance reason this exists), falling back to the plain
    single-call path for any time not exactly on that grid - used by
    bisection/peak refinement, which query arbitrary times between grid
    points. Those refinement calls are few per pass (a handful of
    bisection steps), so batching them isn't worth the complexity; the
    coarse grid is where the sample count (and thus the payoff) is large.
    """
    propagation_results = propagate_many(satrec, grid_times)
    valid_results = [r for r in propagation_results if r is not None]
    topocentric_results = teme_to_topocentric_many(valid_results, observer)

    # zip(strict=True) would express this invariant but needs Python 3.10+,
    # so it is checked explicitly to keep Python 3.8 support.
    if len(valid_results) != len(topocentric_results):
        raise RuntimeError("Coordinate transform returned a different number of results")
    grid_positions: Dict[datetime, TopocentricPosition] = dict(
        zip((r.time for r in valid_results), topocentric_results)
    )

    single_position_fn = _make_position_fn(satrec, observer)

    def _position_at(when: datetime) -> Optional[TopocentricPosition]:
        cached = grid_positions.get(when.astimezone(timezone.utc))
        if cached is not None:
            return cached
        return single_position_fn(when)

    return _position_at


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

    Thin wrapper around `find_passes_from_position_fn` that supplies a
    position function backed by one batched SGP4 + coordinate-transform
    call for the coarse sampling grid (see `_make_batch_position_fn`) -
    measured at roughly 60x faster than calling the single-time path once
    per sample for a 24-hour search window (Phase 10 profiling notes).
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start >= end:
        raise ValueError("start must be before end")

    grid_times = _generate_sample_times(start, end, sample_interval_seconds)
    position_at = _make_batch_position_fn(satrec, observer, grid_times)
    return find_passes_from_position_fn(
        position_at,
        start,
        end,
        min_elevation_deg=min_elevation_deg,
        sample_interval_seconds=sample_interval_seconds,
        time_tolerance_seconds=time_tolerance_seconds,
    )


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
