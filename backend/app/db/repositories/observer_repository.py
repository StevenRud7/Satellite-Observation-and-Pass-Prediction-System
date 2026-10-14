"""
Observer repository: persistence for saved observer locations (project
plan section 7: "Users should also be able to save observer locations.").

No API routes use this yet - wiring it up to `/api/observers` endpoints
is Phase 7. This exists now so the persistence layer is built and tested
alongside the rest of Phase 6, and so Phase 7 has something ready to call.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.observer import Observer as ObserverORM
from app.schemas.observer import ObserverLocation


class ObserverRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, observer: ObserverLocation, saved: bool = True) -> int:
        row = ObserverORM(
            name=observer.name,
            latitude=observer.latitude_deg,
            longitude=observer.longitude_deg,
            altitude=observer.altitude_m,
            is_saved=saved,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def _find_matching(self, observer: ObserverLocation) -> Optional[ObserverORM]:
        """An existing row with exactly this name, latitude, longitude and
        altitude (oldest first), saved or not."""
        name_matches = (
            ObserverORM.name.is_(None)
            if observer.name is None
            else ObserverORM.name == observer.name
        )
        return self._session.scalars(
            select(ObserverORM)
            .where(
                name_matches,
                ObserverORM.latitude == observer.latitude_deg,
                ObserverORM.longitude == observer.longitude_deg,
                ObserverORM.altitude == observer.altitude_m,
            )
            .order_by(ObserverORM.id)
            .limit(1)
        ).first()

    def save(self, observer: ObserverLocation) -> int:
        """Add `observer` to the saved-locations list (the "Save this
        location" action) without ever creating a duplicate: if the same
        place is already stored - saved, or as a working record from
        predicting passes - that row is reused (and marked saved)."""
        existing = self._find_matching(observer)
        if existing is None:
            return self.create(observer, saved=True)
        if not existing.is_saved:
            existing.is_saved = True
            self._session.flush()
        return existing.id

    def get_or_create_working(self, observer: ObserverLocation) -> int:
        """An observer row to attach persisted passes to, WITHOUT adding it to
        the saved-locations list. Reuses an existing identical row so
        repeated predictions don't pile up rows either."""
        existing = self._find_matching(observer)
        if existing is not None:
            return existing.id
        return self.create(observer, saved=False)

    def get(self, observer_id: int) -> Optional[ObserverLocation]:
        row = self._session.get(ObserverORM, observer_id)
        return _to_schema(row) if row is not None else None

    def list_all(self, saved_only: bool = False) -> List[Tuple[int, ObserverLocation]]:
        query = select(ObserverORM).order_by(ObserverORM.id)
        if saved_only:
            query = query.where(ObserverORM.is_saved.is_(True))
        rows = self._session.scalars(query).all()
        return [(row.id, _to_schema(row)) for row in rows]

    def delete(self, observer_id: int) -> bool:
        row = self._session.get(ObserverORM, observer_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


def _to_schema(row: ObserverORM) -> ObserverLocation:
    return ObserverLocation(
        name=row.name,
        latitude_deg=row.latitude,
        longitude_deg=row.longitude,
        altitude_m=row.altitude,
    )
