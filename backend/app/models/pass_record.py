"""
SQLAlchemy model for the `passes` table.

Naming note: like `app/schemas/pass_event.py`, this is not named
`pass.py` on disk - `pass` is a Python keyword. The table itself is still
named `passes` in the database.

Stores a computed pass result. This is a deliberate exception to "don't
store every intermediate calculation" (section 20): a specific pass, once
computed, is a discrete, meaningful, cheap-to-store event - not a dense
time series - and matches the project plan's own suggested schema
(section 19) closely, plus rise/set range (we already compute them
alongside max range, at negligible extra storage cost).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.observer import Observer
    from app.models.satellite import Satellite
    from app.models.visibility_prediction import VisibilityPrediction


class PassRecord(Base):
    __tablename__ = "passes"
    __table_args__ = (
        # Supports "passes for this satellite (and observer, and/or time
        # range)" - the composite's leading column is satellite_id, so it
        # also serves satellite_id-only queries.
        Index("ix_passes_satellite_observer_rise", "satellite_id", "observer_id", "rise_time"),
        # Supports "passes for this observer" without a satellite_id filter
        # (GET /api/passes/search?observer_id=... - a real, distinct query
        # shape the composite index above doesn't serve well, since it
        # isn't a leading-column match for that access pattern).
        Index("ix_passes_observer_rise", "observer_id", "rise_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        ForeignKey("satellites.id", ondelete="CASCADE"), nullable=False
    )
    observer_id: Mapped[int] = mapped_column(
        ForeignKey("observers.id", ondelete="CASCADE"), nullable=False
    )

    rise_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    peak_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    set_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rise_azimuth: Mapped[float] = mapped_column(Float, nullable=False)
    peak_azimuth: Mapped[float] = mapped_column(Float, nullable=False)
    set_azimuth: Mapped[float] = mapped_column(Float, nullable=False)

    max_elevation: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    min_elevation_threshold: Mapped[float] = mapped_column(Float, nullable=False)

    rise_range: Mapped[float] = mapped_column(Float, nullable=False)
    max_range: Mapped[float] = mapped_column(Float, nullable=False)
    set_range: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    satellite: Mapped[Satellite] = relationship()
    observer: Mapped[Observer] = relationship()
    visibility_predictions: Mapped[List[VisibilityPrediction]] = relationship(
        back_populates="pass_record", cascade="all, delete-orphan"
    )
