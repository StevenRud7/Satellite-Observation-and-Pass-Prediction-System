"""
Ranking: sorting and filtering already-scored observation opportunities.

Deliberately has no knowledge of CelesTrak, SGP4, or how the opportunities
were produced - it just orders and filters a list of RankedOpportunity
objects, so it can be tested with plain fixtures instead of real orbital
data. Gathering the opportunities in the first place (fetching satellites,
finding their passes, scoring each one) is `ranking_service.py`'s job.
"""

from __future__ import annotations

from typing import List, Optional

from app.schemas.ranking import RankedOpportunity


def rank_opportunities(
    opportunities: List[RankedOpportunity],
    *,
    min_score: int = 0,
    min_elevation_deg: Optional[float] = None,
    max_elevation_deg: Optional[float] = None,
    limit: Optional[int] = None,
) -> List[RankedOpportunity]:
    """Filter and sort opportunities by score, descending.

    Note on scope: filtering by satellite type/category (project plan
    section 18) isn't available yet - satellite object_type isn't
    populated until a SATCAT lookup is added (see Phase 1 limitations),
    and there's no persistent satellite catalog to filter over yet
    (Phase 6). Only score and elevation filters are implemented here.
    """
    filtered = [
        o
        for o in opportunities
        if o.visibility.score >= min_score
        and (min_elevation_deg is None or o.pass_event.max_elevation_deg >= min_elevation_deg)
        and (max_elevation_deg is None or o.pass_event.max_elevation_deg <= max_elevation_deg)
    ]

    ranked = sorted(filtered, key=lambda o: o.visibility.score, reverse=True)

    if limit is not None:
        ranked = ranked[:limit]

    return ranked
