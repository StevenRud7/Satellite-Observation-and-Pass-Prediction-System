"""
Pass service: resolves an observer and satellite, computes passes and
their visibility, and persists both.

This is what POST /api/passes/predict calls. It requires a configured
database, since it creates persisted Pass/VisibilityPrediction rows with
real ids - unlike GET /api/passes/next, which computes live without
persisting and works without a database at all (see routes_passes.py for
that distinction and why it's deliberate).
"""

from __future__ import annotations

from typing import List, Tuple

from app.core.passes import find_passes
from app.core.propagation import build_satrec
from app.core.scoring import assess_pass_visibility
from app.db.repositories.observer_repository import ObserverRepository
from app.db.repositories.pass_repository import PassRepository
from app.db.repositories.satellite_repository import SatelliteRepository
from app.db.session import session_scope
from app.schemas.observer import ObserverLocation
from app.schemas.pass_api import PassPredictRequest, PassWithVisibility
from app.services.satellite_service import SatelliteService


class ObserverNotFoundError(Exception):
    """Raised when a request references an observer_id that doesn't exist."""


class SatelliteNotCachedError(Exception):
    """Raised when a satellite has been fetched (so we have a SatelliteRecord)
    but somehow has no database row - should not normally happen when a
    database is configured, since fetching always caches through it."""


class PassService:
    def __init__(self, satellite_service: SatelliteService) -> None:
        self._satellite_service = satellite_service

    def predict_and_persist(self, request: PassPredictRequest) -> List[PassWithVisibility]:
        satellite_record = self._satellite_service.get_satellite(request.norad_id)
        satrec = build_satrec(satellite_record.orbital_elements)

        with session_scope() as session:
            observer_repo = ObserverRepository(session)
            satellite_repo = SatelliteRepository(session)
            pass_repo = PassRepository(session)

            observer_id, observer_location = self._resolve_observer(observer_repo, request)

            satellite_id = satellite_repo.get_id_by_norad_id(request.norad_id)
            if satellite_id is None:
                raise SatelliteNotCachedError(
                    f"Satellite {request.norad_id} was fetched but has no database row - "
                    "is a database configured?"
                )

            passes = find_passes(
                satrec,
                observer_location,
                request.start,
                request.end,
                min_elevation_deg=request.min_elevation_deg,
            )

            results = []
            for pass_event in passes:
                assessment = assess_pass_visibility(satrec, observer_location, pass_event)
                pass_id = pass_repo.save_pass_with_visibility(
                    satellite_id, observer_id, pass_event, assessment.methods
                )
                results.append(
                    PassWithVisibility(
                        id=pass_id,
                        norad_id=satellite_record.norad_id,
                        satellite_name=satellite_record.name,
                        observer_id=observer_id,
                        pass_event=pass_event,
                        visibility=assessment.methods,
                    )
                )
            return results

    @staticmethod
    def _resolve_observer(
        observer_repo: ObserverRepository, request: PassPredictRequest
    ) -> Tuple[int, ObserverLocation]:
        if request.observer_id is not None:
            location = observer_repo.get(request.observer_id)
            if location is None:
                raise ObserverNotFoundError(f"Observer {request.observer_id} not found")
            return request.observer_id, location

        assert request.latitude_deg is not None and request.longitude_deg is not None
        location = ObserverLocation(
            name=request.observer_name,
            latitude_deg=request.latitude_deg,
            longitude_deg=request.longitude_deg,
            altitude_m=request.altitude_m,
        )
        new_id = observer_repo.create(location)
        return new_id, location
