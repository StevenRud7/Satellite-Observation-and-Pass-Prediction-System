"""
Place-search ("geocoding") endpoint.

Lets the frontend's location form accept a typed place name - a city, a
district/neighbourhood, or a landmark - instead of requiring raw
latitude/longitude. See app/data/geocoding.py for the underlying client
(OpenStreetMap/Nominatim) and app/services/geocoding_service.py for the
caching wrapper used here.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_geocoding_service
from app.schemas.geocoding import GeocodeResult
from app.services.geocoding_service import GeocodingService

router = APIRouter(prefix="/api/geocode", tags=["geocoding"])

_GeocodingServiceDep = Depends(get_geocoding_service)


@router.get("", response_model=List[GeocodeResult])
def geocode(
    q: str = Query(min_length=2, max_length=128, description="Place name, e.g. 'Camden, London'"),
    limit: int = Query(default=6, ge=1, le=10),
    service: GeocodingService = _GeocodingServiceDep,
) -> List[GeocodeResult]:
    return service.search(q, limit=limit)
