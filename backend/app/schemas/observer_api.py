"""
API-facing observer schema.

`ObserverLocation` (app/schemas/observer.py) is the domain schema used
throughout the scientific engine and has no id, since until Phase 6 there
was nothing to give it one. `ObserverResponse` adds the database id for
API responses without duplicating the lat/lon/altitude validation.
"""

from __future__ import annotations

from app.schemas.observer import ObserverLocation


class ObserverResponse(ObserverLocation):
    id: int
