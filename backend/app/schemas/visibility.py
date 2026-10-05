"""
Data types shared by the visibility/scoring engine.

Kept separate from the computation code (app/core/visibility.py,
app/core/scoring.py) so the vocabulary (what "illuminated" or "possible"
means) is defined once and reused by both the astronomy calculations and
the API-facing response shapes.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from app.schemas.pass_event import PassEvent


class SkyDarkness(str, Enum):
    """Standard twilight bands, based on the Sun's altitude at the observer.

    Boundaries (0°, -6°, -12°, -18°) are the conventional definitions of
    civil/nautical/astronomical twilight - not something this project
    invented, but also not a claim that satellite visibility switches
    on/off sharply at these exact boundaries in reality.
    """

    DAYLIGHT = "daylight"
    CIVIL_TWILIGHT = "civil_twilight"
    NAUTICAL_TWILIGHT = "nautical_twilight"
    ASTRONOMICAL_TWILIGHT = "astronomical_twilight"
    NIGHT = "night"


class SatelliteIlluminationStatus(str, Enum):
    """Whether the satellite itself is sunlit during a pass.

    PARTIAL means the satellite enters or exits Earth's shadow at some
    point between rise and set - it doesn't stay in one state for the
    whole pass.
    """

    ILLUMINATED = "illuminated"
    PARTIAL = "partial"
    ECLIPSED = "eclipsed"


class ObservationMethod(str, Enum):
    NAKED_EYE = "naked_eye"
    BINOCULARS = "binoculars"
    TELESCOPE = "telescope"


class VisibilityClassification(str, Enum):
    """See project plan section 15. Application-defined heuristic bands,
    not a universally accepted astronomical standard."""

    EXCELLENT = "excellent"
    VERY_GOOD = "very_good"
    POSSIBLE = "possible"
    DIFFICULT = "difficult"
    UNLIKELY = "unlikely"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def classify_score(score: float) -> VisibilityClassification:
    if score >= 90:
        return VisibilityClassification.EXCELLENT
    if score >= 75:
        return VisibilityClassification.VERY_GOOD
    if score >= 55:
        return VisibilityClassification.POSSIBLE
    if score >= 35:
        return VisibilityClassification.DIFFICULT
    return VisibilityClassification.UNLIKELY


class SkyConditions(BaseModel):
    time: str = Field(description="ISO timestamp the conditions were evaluated at (UTC)")
    sun_altitude_deg: float
    sky_darkness: SkyDarkness


class VisibilityFactor(BaseModel):
    """One line of the human-readable explanation (project plan section 17)."""

    label: str
    detail: str


class MethodVisibility(BaseModel):
    method: ObservationMethod
    score: int = Field(ge=0, le=100)
    classification: VisibilityClassification
    confidence: ConfidenceLevel
    factors: List[VisibilityFactor]
    limitations: List[str]


class PassVisibilityAssessment(BaseModel):
    """The full Phase 4 output for one pass: shared sky/illumination context
    plus a separate scored result for each observation method."""

    pass_event: PassEvent
    sky_conditions: SkyConditions
    satellite_illumination: SatelliteIlluminationStatus
    methods: List[MethodVisibility]
