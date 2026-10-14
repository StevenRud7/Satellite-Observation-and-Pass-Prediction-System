"""
Ranking service.

Orchestrates the full Phase 5 pipeline: fetch each candidate satellite's
current orbital elements, find its passes in the requested window, score
each pass for the requested observation method, and return a ranked list -
answering "find me the best satellites to observe" (project plan
section 18).

Scope note: there is no persistent satellite catalog yet (Phase 6), so
"which satellites to consider" has to be supplied by the caller rather
than discovered automatically. `DEFAULT_CANDIDATE_NORAD_IDS` below is a
small, convenience-only starting point (just the ISS) - not a stand-in
for real catalog browsing, which needs bulk CelesTrak ingestion and
persistence (Phase 6/7) to do properly.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

from app.core.logging import get_logger
from app.core.passes import DEFAULT_MIN_ELEVATION_DEG, find_passes
from app.core.propagation import PropagationError, build_satrec
from app.core.ranking import rank_opportunities
from app.core.scoring import assess_pass_visibility
from app.data.exceptions import CelestrakClientError, OrbitalDataValidationError
from app.schemas.observer import ObserverLocation
from app.schemas.ranking import RankedOpportunity
from app.schemas.satellite import SatelliteRecord
from app.schemas.visibility import ObservationMethod
from app.services.satellite_service import SatelliteService

logger = get_logger(__name__)

# A small, convenience-only default set of candidates - see module
# docstring. The ISS is used because it is unambiguous and extremely
# well-known; a real "browse satellites" feature is future work.
DEFAULT_CANDIDATE_NORAD_IDS: Tuple[int, ...] = (25544,)  # ISS (ZARYA)

# Satellites' orbital data is fetched concurrently (the fetches are pure
# network/DB waiting), then passes are computed one satellite at a time.
# Capped so a long satellite list can't open an unreasonable number of
# simultaneous connections to CelesTrak/the database.
_MAX_PARALLEL_FETCHES = 6


class RankingService:
    def __init__(self, satellite_service: SatelliteService) -> None:
        self._satellite_service = satellite_service

    def find_best_opportunities(
        self,
        observer: ObserverLocation,
        start: datetime,
        end: datetime,
        *,
        method: ObservationMethod = ObservationMethod.NAKED_EYE,
        norad_ids: Tuple[int, ...] = DEFAULT_CANDIDATE_NORAD_IDS,
        pass_search_min_elevation_deg: float = DEFAULT_MIN_ELEVATION_DEG,
        min_score: int = 0,
        min_elevation_deg: Optional[float] = None,
        max_elevation_deg: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[RankedOpportunity]:
        """Find and rank observation opportunities across `norad_ids`.

        A satellite that can't be fetched or validated (network issue, bad
        data) is skipped with a warning rather than failing the whole
        request - one bad NORAD ID shouldn't take down a ranked list of
        several others.

        However, if *every* requested satellite fails to fetch, that is
        not the same thing as "there happen to be no qualifying passes
        right now" - it means this request couldn't actually determine
        anything. Returning an empty list in that case would be
        indistinguishable, in the UI, from a genuine "no passes found"
        result, which makes a real outage (e.g. CelesTrak being
        unreachable from wherever this backend is hosted) silently look
        like ordinary "nothing happening tonight" - which is exactly what
        happened in practice before this check existed. So: the last
        fetch/validation error is re-raised once no candidate at all
        succeeded, rather than swallowed. It propagates as the same
        CelestrakClientError/OrbitalDataValidationError it always was,
        which app/api/error_handlers.py already turns into a clear 502/422
        response - nothing new to wire up for that part.
        """
        opportunities: List[RankedOpportunity] = []
        successful_fetches = 0
        last_fetch_error: Optional[Exception] = None

        fetched = self._fetch_all(norad_ids)

        # Each distinct satellite is processed once. Without this, a NORAD ID
        # repeated in the request (e.g. ?norad_ids=25544&norad_ids=25544)
        # produced every one of its passes twice in the results.
        for norad_id in dict.fromkeys(norad_ids):
            outcome = fetched[norad_id]
            if isinstance(outcome, Exception):
                logger.warning("Skipping NORAD ID %s in ranking: %s", norad_id, outcome)
                last_fetch_error = outcome
                continue
            record = outcome

            successful_fetches += 1

            satrec = build_satrec(record.orbital_elements)
            passes = find_passes(
                satrec, observer, start, end, min_elevation_deg=pass_search_min_elevation_deg
            )

            for pass_event in passes:
                try:
                    assessment = assess_pass_visibility(satrec, observer, pass_event)
                except PropagationError as exc:
                    logger.warning(
                        "Skipping a pass for NORAD ID %s during scoring: %s", norad_id, exc
                    )
                    continue

                method_result = next(m for m in assessment.methods if m.method == method)
                opportunities.append(
                    RankedOpportunity(
                        norad_id=record.norad_id,
                        satellite_name=record.name,
                        pass_event=pass_event,
                        visibility=method_result,
                    )
                )

        if successful_fetches == 0 and norad_ids and last_fetch_error is not None:
            raise last_fetch_error

        return rank_opportunities(
            opportunities,
            min_score=min_score,
            min_elevation_deg=min_elevation_deg,
            max_elevation_deg=max_elevation_deg,
            limit=limit,
        )

    def _fetch_all(
        self, norad_ids: Tuple[int, ...]
    ) -> Dict[int, Union[SatelliteRecord, Exception]]:
        """Fetch every distinct satellite's record concurrently.

        Returns, per NORAD ID, either the record or the fetch/validation
        error it raised (other exception types propagate, exactly as they
        did when fetching sequentially).
        """

        def _one(norad_id: int) -> Union[SatelliteRecord, Exception]:
            try:
                return self._satellite_service.get_satellite(norad_id)
            except (CelestrakClientError, OrbitalDataValidationError) as exc:
                return exc

        unique_ids = list(dict.fromkeys(norad_ids))
        if len(unique_ids) <= 1:
            return {nid: _one(nid) for nid in unique_ids}

        with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_FETCHES, len(unique_ids))) as pool:
            outcomes = list(pool.map(_one, unique_ids))
        return dict(zip(unique_ids, outcomes))
