"""
Request/response schemas for the /api/passes endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.passes import DEFAULT_MIN_ELEVATION_DEG
from app.schemas.pass_event import PassEvent
from app.schemas.visibility import MethodVisibility


class PassPredictRequest(BaseModel):
    """Predict passes for one satellite from one observer, over a time
    window, and persist the results.

    The observer is specified in exactly one of two ways: an existing
    saved observer's `observer_id`, or an ad-hoc `latitude_deg`/
    `longitude_deg` (optionally `altitude_m`/`observer_name`) - in which
    case a new observer is saved automatically and its id is returned.
    This keeps every predicted pass consistently addressable by id
    (needed for GET /api/passes/{id}) without forcing the caller to save
    a named location first just to try a prediction once.
    """

    norad_id: int = Field(description="NORAD catalog ID of the satellite to search")

    observer_id: Optional[int] = Field(default=None, description="An existing saved observer's id")
    latitude_deg: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude_deg: Optional[float] = Field(default=None, ge=-180, le=180)
    altitude_m: float = Field(default=0.0, description="Only used when creating a new observer")
    observer_name: Optional[str] = Field(
        default=None, description="Optional label, only used when creating a new observer"
    )

    start: datetime
    end: datetime
    min_elevation_deg: float = Field(default=DEFAULT_MIN_ELEVATION_DEG, ge=0, le=90)

    @model_validator(mode="after")
    def _validate_observer_reference_and_window(self) -> PassPredictRequest:
        has_id = self.observer_id is not None
        has_coords = self.latitude_deg is not None and self.longitude_deg is not None
        if has_id == has_coords:  # both provided, or neither
            raise ValueError(
                "Provide exactly one of observer_id, or latitude_deg and longitude_deg together"
            )
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class PassWithVisibility(BaseModel):
    id: Optional[int] = Field(
        default=None, description="Database id if this pass was persisted, else null"
    )
    norad_id: int
    satellite_name: str
    observer_id: Optional[int] = None
    pass_event: PassEvent
    visibility: List[MethodVisibility]
