"""
A single entry in a ranked list of observation opportunities: one
satellite's pass, scored for one observation method.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.pass_event import PassEvent
from app.schemas.visibility import MethodVisibility


class RankedOpportunity(BaseModel):
    norad_id: int
    satellite_name: str
    pass_event: PassEvent
    visibility: MethodVisibility
