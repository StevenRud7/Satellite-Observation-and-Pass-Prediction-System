"""
Observer location.

The MVP takes manually entered coordinates (per the project plan - browser
geolocation is optional future work, not a requirement of the core
system).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Loose sanity bounds, not a hard physical limit: Dead Sea shore (~-430 m)
# to comfortably above any plausible ground-based human observation site.
MIN_ALTITUDE_M = -500.0
MAX_ALTITUDE_M = 9000.0


class ObserverLocation(BaseModel):
    name: Optional[str] = Field(
        default=None, description="Optional label, e.g. 'Home' or 'Tel Aviv'"
    )
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    altitude_m: float = Field(
        default=0.0, description="Height above the WGS84 ellipsoid, in meters"
    )

    @field_validator("altitude_m")
    @classmethod
    def altitude_must_be_plausible(cls, value: float) -> float:
        if not (MIN_ALTITUDE_M <= value <= MAX_ALTITUDE_M):
            raise ValueError(
                f"altitude_m must be between {MIN_ALTITUDE_M} and {MAX_ALTITUDE_M} meters"
            )
        return value
