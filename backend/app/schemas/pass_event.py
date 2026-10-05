"""
A single satellite pass: the interval during which a satellite is above a
configured minimum elevation, as seen from one observer.

Naming note: the project plan's original suggestion was `models/pass.py`.
`pass` is a Python keyword, so a module literally named `pass.py` cannot
be imported with a normal `import` statement. This is named
`pass_event.py` on disk instead; the exported class is still `PassEvent`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PassEvent(BaseModel):
    rise_time: datetime
    peak_time: datetime
    set_time: datetime

    rise_azimuth_deg: float
    peak_azimuth_deg: float
    set_azimuth_deg: float

    max_elevation_deg: float
    duration_seconds: float

    rise_range_km: float
    max_range_km: float
    set_range_km: float

    min_elevation_threshold_deg: float = Field(
        description="The elevation threshold this pass was detected against"
    )
