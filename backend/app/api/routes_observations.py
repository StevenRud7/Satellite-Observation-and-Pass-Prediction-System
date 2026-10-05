"""
Ranking endpoint: "find the best satellites to observe" (project plan
section 18/33).

Computed live, not persisted - same reasoning as GET /api/passes/next:
this is a read-only lookup, so it stays a side-effect-free GET and works
without a database configured (SatelliteService's Postgres caching
happens transparently underneath if a database is configured, but this
endpoint doesn't require one).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_ranking_service
from app.core.passes import DEFAULT_MIN_ELEVATION_DEG
from app.schemas.observer import ObserverLocation
from app.schemas.ranking import RankedOpportunity
from app.schemas.visibility import ObservationMethod
from app.services.ranking_service import DEFAULT_CANDIDATE_NORAD_IDS, RankingService

router = APIRouter(prefix="/api/observations", tags=["observations"])

_RankingServiceDep = Depends(get_ranking_service)


@router.get("/best", response_model=List[RankedOpportunity])
def best_observations(
    latitude_deg: float = Query(ge=-90, le=90),
    longitude_deg: float = Query(ge=-180, le=180),
    altitude_m: float = Query(default=0.0),
    method: ObservationMethod = Query(default=ObservationMethod.NAKED_EYE),
    norad_ids: List[int] = Query(
        default=list(DEFAULT_CANDIDATE_NORAD_IDS),
        description="Satellites to consider - see project limitations: this is not a full catalog",
    ),
    within_hours: float = Query(default=24.0, gt=0, le=24 * 14),
    pass_search_min_elevation_deg: float = Query(default=DEFAULT_MIN_ELEVATION_DEG, ge=0, le=90),
    min_score: int = Query(default=0, ge=0, le=100),
    min_elevation_deg: Optional[float] = Query(default=None, ge=0, le=90),
    max_elevation_deg: Optional[float] = Query(default=None, ge=0, le=90),
    limit: int = Query(default=10, ge=1, le=100),
    service: RankingService = _RankingServiceDep,
) -> List[RankedOpportunity]:
    observer = ObserverLocation(
        latitude_deg=latitude_deg, longitude_deg=longitude_deg, altitude_m=altitude_m
    )
    now = datetime.now(timezone.utc)

    return service.find_best_opportunities(
        observer,
        now,
        now + timedelta(hours=within_hours),
        method=method,
        norad_ids=tuple(norad_ids),
        pass_search_min_elevation_deg=pass_search_min_elevation_deg,
        min_score=min_score,
        min_elevation_deg=min_elevation_deg,
        max_elevation_deg=max_elevation_deg,
        limit=limit,
    )
