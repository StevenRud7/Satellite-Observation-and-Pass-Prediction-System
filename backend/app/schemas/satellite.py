"""
Satellite metadata plus its current orbital elements.

This is the API-facing (and, until Phase 6, the only) representation of a
satellite. It intentionally does not include a database primary key -
until there is a database, NORAD ID is the natural identifier.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.orbital_elements import OrbitalElementSet


class SatelliteRecord(BaseModel):
    norad_id: int = Field(description="NORAD catalog ID, e.g. 25544 for the ISS")
    name: str = Field(description="Satellite name as published by the data source")
    international_designator: Optional[str] = Field(
        default=None, description="COSPAR/international designator, e.g. '1998-067A'"
    )
    object_type: Optional[str] = Field(
        default=None,
        description=(
            "Payload/rocket body/debris/etc. Not populated in Phase 1 - CelesTrak's "
            "GP endpoint doesn't return it; would require a separate SATCAT lookup."
        ),
    )

    orbital_elements: OrbitalElementSet


class SatelliteSearchResult(BaseModel):
    """A lightweight name/ID pair, e.g. one hit from `GET /api/satellites/search`
    or one entry of the curated catalog (`GET /api/satellites/catalog`).

    Deliberately doesn't carry orbital elements - a search can return many
    hits, and the caller only needs enough to let a person recognize and
    pick a satellite; the full record is fetched afterwards via
    `GET /api/satellites/{norad_id}` once one is actually selected.
    """

    norad_id: int
    name: str
    category: Optional[str] = Field(
        default=None, description="Only set for curated catalog entries, e.g. 'Space Station'"
    )
