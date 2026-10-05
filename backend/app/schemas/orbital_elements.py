"""
Orbital element data.

This is the shape of a single "current best" set of orbital elements for a
satellite: the raw TLE lines (needed by SGP4 for propagation) plus the
individually-parsed fields (useful for display, filtering, and the future
staleness-vs-accuracy research phase) and retrieval metadata.

This is a plain Pydantic model, not a SQLAlchemy model - Phase 1 has no
database yet. Phase 6 will introduce persistence and can map this schema to
and from an ORM model without changing anything upstream of it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrbitalElementSet(BaseModel):
    epoch: datetime = Field(description="UTC epoch the elements are valid for")

    line1: str = Field(description="Raw TLE line 1, required by SGP4")
    line2: str = Field(description="Raw TLE line 2, required by SGP4")

    mean_motion: float = Field(description="Revolutions per day")
    eccentricity: float
    inclination_deg: float
    raan_deg: float = Field(description="Right ascension of the ascending node, degrees")
    arg_perigee_deg: float = Field(description="Argument of perigee, degrees")
    mean_anomaly_deg: float
    bstar: float = Field(description="Drag term used by SGP4")

    element_set_number: int
    revolution_number: int

    source: str = Field(description="Where these elements came from, e.g. 'celestrak'")
    retrieved_at: datetime = Field(description="When our backend fetched this data, UTC")
