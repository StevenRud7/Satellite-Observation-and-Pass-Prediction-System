"""
Schemas for place/city/district search ("geocoding").

This lets a user type a place name (a city, a district/neighbourhood, a
landmark) instead of typing raw latitude/longitude - see
`app/data/geocoding.py` for the client that resolves these against
OpenStreetMap/Nominatim.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GeocodeResult(BaseModel):
    display_name: str = Field(description="Full human-readable place name, for display")
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    place_type: Optional[str] = Field(
        default=None,
        description=(
            "Broad kind of place, e.g. 'city', 'suburb', 'neighbourhood', 'town'. "
            "Comes directly from the data source and isn't a fixed enum."
        ),
    )
    country: Optional[str] = Field(default=None)
