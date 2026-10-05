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

    def create(self, observer: ObserverLocation) -> int:
        row = ObserverORM(
            name=observer.name,
            latitude=observer.latitude_deg,
            longitude=observer.longitude_deg,
            altitude=observer.altitude_m,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def get(self, observer_id: int) -> Optional[ObserverLocation]:
        row = self._session.get(ObserverORM, observer_id)
        return _to_schema(row) if row is not None else None

    def list_all(self) -> List[Tuple[int, ObserverLocation]]:
        rows = self._session.scalars(select(ObserverORM).order_by(ObserverORM.id)).all()
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
