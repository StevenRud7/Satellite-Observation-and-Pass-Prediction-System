"""
Curated catalog of well-known, easy-to-recognize satellites.

This is deliberately a short, hand-picked list rather than a live query
against CelesTrak's full catalog (tens of thousands of objects) - it exists
so the "satellites to consider" picker has something sensible to show
*before* the user searches or types a NORAD ID, grouped into categories a
newcomer will recognize. Every entry's NORAD ID has been checked against
independent sources; when in doubt about a satellite (e.g. one of the
thousands of individual Starlink satellites, whose IDs turn over
constantly), it was left out rather than guessed - use
`GET /api/satellites/search?q=...` (see routes_satellites.py) for anything
not in this list.

NORAD IDs and names don't change, so this is a plain constant rather than
something fetched over the network. It should still be revisited
occasionally: a satellite can be decommissioned or deorbited (its CelesTrak
GP entry then disappears, or the object simply won't come back above the
horizon), even though its catalog number stays valid.
"""

from __future__ import annotations

from typing import List, NamedTuple


class CatalogEntry(NamedTuple):
    norad_id: int
    name: str
    category: str


SATELLITE_CATALOG: List[CatalogEntry] = [
    # Space stations - the brightest, easiest objects to start with.
    CatalogEntry(25544, "ISS (ZARYA)", "Space Station"),
    CatalogEntry(48274, "CSS (TIANHE)", "Space Station"),
    # Space telescopes.
    CatalogEntry(20580, "HST (Hubble Space Telescope)", "Space Telescope"),
    # Historic / long-lived satellites.
    CatalogEntry(5, "VANGUARD 1", "Historic"),
    # Earth observation.
    CatalogEntry(39084, "LANDSAT 8", "Earth Observation"),
    CatalogEntry(49260, "LANDSAT 9", "Earth Observation"),
    # Weather (geostationary).
    CatalogEntry(41866, "GOES 16", "Weather"),
    # Amateur radio - some of the longest-operating satellites in orbit.
    CatalogEntry(7530, "OSCAR 7 (AMSAT)", "Amateur Radio"),
]
