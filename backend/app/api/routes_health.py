"""
Health check endpoint.

This is intentionally the only endpoint in Phase 0. It exists so we can
verify the backend is deployed and reachable before any real functionality
(orbital data, SGP4, etc.) is built on top of it.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="satellite-observation-api",
        timestamp=datetime.now(timezone.utc),
    )
