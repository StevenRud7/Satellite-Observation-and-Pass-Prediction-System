"""
Observer endpoints: save, list, retrieve, and delete observer locations
(project plan section 7 / section 22).

All require a database - there's nowhere else to save a location. A
missing database surfaces as a 503 via the centralized handler in
app/api/error_handlers.py, not a raw connection error.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.repositories.observer_repository import ObserverRepository
from app.db.session import get_db_session
from app.schemas.observer import ObserverLocation
from app.schemas.observer_api import ObserverResponse

router = APIRouter(prefix="/api/observers", tags=["observers"])

_DbSessionDep = Depends(get_db_session)


@router.post("", response_model=ObserverResponse, status_code=status.HTTP_201_CREATED)
def create_observer(
    observer: ObserverLocation, session: Session = _DbSessionDep
) -> ObserverResponse:
    observer_id = ObserverRepository(session).create(observer)
    return ObserverResponse(id=observer_id, **observer.model_dump())


@router.get("", response_model=List[ObserverResponse])
def list_observers(session: Session = _DbSessionDep) -> List[ObserverResponse]:
    return [
        ObserverResponse(id=observer_id, **location.model_dump())
        for observer_id, location in ObserverRepository(session).list_all()
    ]


@router.get("/{observer_id}", response_model=ObserverResponse)
def get_observer(observer_id: int, session: Session = _DbSessionDep) -> ObserverResponse:
    location = ObserverRepository(session).get(observer_id)
    if location is None:
        raise HTTPException(status_code=404, detail=f"Observer {observer_id} not found")
    return ObserverResponse(id=observer_id, **location.model_dump())


@router.delete("/{observer_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_observer(observer_id: int, session: Session = _DbSessionDep) -> None:
    deleted = ObserverRepository(session).delete(observer_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Observer {observer_id} not found")
