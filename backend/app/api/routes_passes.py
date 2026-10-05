"""
Pass endpoints.

Two deliberately different flavors here, both documented at the point of
use below:

- POST /predict computes passes for a satellite+observer+window and
  PERSISTS them (via PassService) - it creates resources with real
  database ids, which is why it's a POST rather than a GET, and why it
  requires a database.
- GET /next computes live and does NOT persist - a safe, idempotent
  lookup with no side effects, matching what a GET should be. It works
  even without a database configured.

GET /search, GET /{pass_id}, and GET /{pass_id}/visibility are pure reads
over already-persisted passes - they never compute anything new.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_pass_service, get_satellite_service
from app.core.passes import DEFAULT_MIN_ELEVATION_DEG, find_passes
from app.core.propagation import build_satrec
from app.core.scoring import assess_pass_visibility
from app.db.repositories.pass_repository import PassRepository
from app.db.session import get_db_session
from app.schemas.observer import ObserverLocation
from app.schemas.pass_api import PassPredictRequest, PassWithVisibility
from app.schemas.visibility import MethodVisibility, ObservationMethod
from app.services.pass_service import PassService
from app.services.satellite_service import SatelliteService

router = APIRouter(prefix="/api/passes", tags=["passes"])

_PassServiceDep = Depends(get_pass_service)
_SatelliteServiceDep = Depends(get_satellite_service)
_DbSessionDep = Depends(get_db_session)


@router.post("/predict", response_model=List[PassWithVisibility])
def predict_passes(
    request: PassPredictRequest, service: PassService = _PassServiceDep
) -> List[PassWithVisibility]:
    return service.predict_and_persist(request)


@router.get("/next", response_model=PassWithVisibility)
def next_pass(
    norad_id: int,
    latitude_deg: float = Query(ge=-90, le=90),
    longitude_deg: float = Query(ge=-180, le=180),
    altitude_m: float = Query(default=0.0),
    min_elevation_deg: float = Query(default=DEFAULT_MIN_ELEVATION_DEG, ge=0, le=90),
    within_hours: float = Query(default=24.0, gt=0, le=24 * 14),
    satellite_service: SatelliteService = _SatelliteServiceDep,
) -> PassWithVisibility:
    """The single soonest pass in the next `within_hours`, computed live.
    Not persisted - see module docstring for why."""
    satellite_record = satellite_service.get_satellite(norad_id)
    satrec = build_satrec(satellite_record.orbital_elements)
    observer = ObserverLocation(
        latitude_deg=latitude_deg, longitude_deg=longitude_deg, altitude_m=altitude_m
    )

    now = datetime.now(timezone.utc)
    passes = find_passes(
        satrec,
        observer,
        now,
        now + timedelta(hours=within_hours),
        min_elevation_deg=min_elevation_deg,
    )

    if not passes:
        raise HTTPException(
            status_code=404,
            detail=f"No pass of satellite {norad_id} found in the next {within_hours} hours",
        )

    soonest = passes[0]
    assessment = assess_pass_visibility(satrec, observer, soonest)

    return PassWithVisibility(
        id=None,
        norad_id=satellite_record.norad_id,
        satellite_name=satellite_record.name,
        observer_id=None,
        pass_event=soonest,
        visibility=assessment.methods,
    )


@router.get("/search", response_model=List[PassWithVisibility])
def search_passes(
    norad_id: Optional[int] = None,
    observer_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = _DbSessionDep,
) -> List[PassWithVisibility]:
    """Search previously predicted (persisted) passes. Does not compute
    anything new - see POST /predict for that."""
    repo = PassRepository(session)
    stored = repo.search(
        norad_id=norad_id, observer_id=observer_id, start=start, end=end, limit=limit
    )
    return [
        PassWithVisibility(
            id=p.id,
            norad_id=p.norad_id,
            satellite_name=p.satellite_name,
            observer_id=p.observer_id,
            pass_event=p.pass_event,
            visibility=repo.get_visibility_predictions(p.id),
        )
        for p in stored
    ]


@router.get("/{pass_id}", response_model=PassWithVisibility)
def get_pass(pass_id: int, session: Session = _DbSessionDep) -> PassWithVisibility:
    repo = PassRepository(session)
    stored = repo.get_by_id(pass_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Pass {pass_id} not found")

    return PassWithVisibility(
        id=stored.id,
        norad_id=stored.norad_id,
        satellite_name=stored.satellite_name,
        observer_id=stored.observer_id,
        pass_event=stored.pass_event,
        visibility=repo.get_visibility_predictions(pass_id),
    )


@router.get("/{pass_id}/visibility", response_model=List[MethodVisibility])
def get_pass_visibility(
    pass_id: int,
    method: Optional[ObservationMethod] = Query(
        default=None, description="Filter to a single observation method"
    ),
    session: Session = _DbSessionDep,
) -> List[MethodVisibility]:
    repo = PassRepository(session)
    if repo.get_by_id(pass_id) is None:
        raise HTTPException(status_code=404, detail=f"Pass {pass_id} not found")

    results = repo.get_visibility_predictions(pass_id)
    if method is not None:
        results = [r for r in results if r.method == method]
    return results
