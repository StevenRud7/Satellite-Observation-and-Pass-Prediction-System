"""
Pass repository: persistence for computed passes and their visibility
predictions ("useful pass results where appropriate" - project plan
section 20).

Used by `PassService` (app/services/pass_service.py), which is what the
`/api/passes/*` routes call - this repository itself has no FastAPI
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pass_record import PassRecord as PassRecordORM
from app.models.satellite import Satellite as SatelliteORM
from app.models.visibility_prediction import VisibilityPrediction as VisibilityPredictionORM
from app.schemas.pass_event import PassEvent
from app.schemas.visibility import (
    ConfidenceLevel,
    MethodVisibility,
    ObservationMethod,
    VisibilityClassification,
    VisibilityFactor,
)


@dataclass(frozen=True)
class StoredPass:
    """A persisted pass plus enough satellite/observer context to display
    it without a second lookup."""

    id: int
    norad_id: int
    satellite_name: str
    observer_id: int
    pass_event: PassEvent


class PassRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_pass_with_visibility(
        self,
        satellite_id: int,
        observer_id: int,
        pass_event: PassEvent,
        visibility_results: List[MethodVisibility],
    ) -> int:
        """Persist one pass and its scored visibility results (one row per
        observation method). Returns the new pass's database id."""
        pass_row = PassRecordORM(
            satellite_id=satellite_id,
            observer_id=observer_id,
            rise_time=pass_event.rise_time,
            peak_time=pass_event.peak_time,
            set_time=pass_event.set_time,
            rise_azimuth=pass_event.rise_azimuth_deg,
            peak_azimuth=pass_event.peak_azimuth_deg,
            set_azimuth=pass_event.set_azimuth_deg,
            max_elevation=pass_event.max_elevation_deg,
            duration_seconds=pass_event.duration_seconds,
            min_elevation_threshold=pass_event.min_elevation_threshold_deg,
            rise_range=pass_event.rise_range_km,
            max_range=pass_event.max_range_km,
            set_range=pass_event.set_range_km,
        )
        self._session.add(pass_row)
        self._session.flush()  # assigns pass_row.id

        for result in visibility_results:
            self._session.add(
                VisibilityPredictionORM(
                    pass_id=pass_row.id,
                    method=result.method.value,
                    score=result.score,
                    classification=result.classification.value,
                    confidence=result.confidence.value,
                    factors=[factor.model_dump() for factor in result.factors],
                    limitations=result.limitations,
                )
            )
        self._session.flush()

        return pass_row.id

    def get_by_id(self, pass_id: int) -> Optional[StoredPass]:
        row = self._session.get(PassRecordORM, pass_id)
        if row is None:
            return None
        return _to_stored_pass(row)

    def get_visibility_predictions(self, pass_id: int) -> List[MethodVisibility]:
        """Every scored observation method for a stored pass. Returns an
        empty list both when the pass doesn't exist and when it exists
        but has no predictions - callers that need to distinguish those
        should check `get_by_id` first."""
        rows = self._session.scalars(
            select(VisibilityPredictionORM).where(VisibilityPredictionORM.pass_id == pass_id)
        ).all()
        return [_to_method_visibility(row) for row in rows]

    def search(
        self,
        *,
        norad_id: Optional[int] = None,
        observer_id: Optional[int] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[StoredPass]:
        """Search previously stored passes. This is read-only over
        already-computed data - it does not compute new passes (that's
        POST /api/passes/predict)."""
        query = select(PassRecordORM)
        if norad_id is not None:
            query = query.join(SatelliteORM).where(SatelliteORM.norad_id == norad_id)
        if observer_id is not None:
            query = query.where(PassRecordORM.observer_id == observer_id)
        if start is not None:
            query = query.where(PassRecordORM.rise_time >= start)
        if end is not None:
            query = query.where(PassRecordORM.set_time <= end)
        query = query.order_by(PassRecordORM.rise_time).limit(limit)

        rows = self._session.scalars(query).all()
        return [_to_stored_pass(row) for row in rows]


def _to_stored_pass(row: PassRecordORM) -> StoredPass:
    pass_event = PassEvent(
        rise_time=row.rise_time,
        peak_time=row.peak_time,
        set_time=row.set_time,
        rise_azimuth_deg=row.rise_azimuth,
        peak_azimuth_deg=row.peak_azimuth,
        set_azimuth_deg=row.set_azimuth,
        max_elevation_deg=row.max_elevation,
        duration_seconds=row.duration_seconds,
        rise_range_km=row.rise_range,
        max_range_km=row.max_range,
        set_range_km=row.set_range,
        min_elevation_threshold_deg=row.min_elevation_threshold,
    )
    return StoredPass(
        id=row.id,
        norad_id=row.satellite.norad_id,
        satellite_name=row.satellite.name,
        observer_id=row.observer_id,
        pass_event=pass_event,
    )


def _to_method_visibility(row: VisibilityPredictionORM) -> MethodVisibility:
    factors: List[Dict[str, Any]] = row.factors
    return MethodVisibility(
        method=ObservationMethod(row.method),
        score=row.score,
        classification=VisibilityClassification(row.classification),
        confidence=ConfidenceLevel(row.confidence),
        factors=[VisibilityFactor(**factor) for factor in factors],
        limitations=row.limitations,
    )
