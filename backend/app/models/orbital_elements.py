"""
SQLAlchemy model for the `orbital_elements` table.

Deliberate deviation from the project plan's suggested column list
(section 19 lists just id/satellite_id/epoch/line1/line2/source/
retrieved_at): this also stores the individually-parsed orbital
parameters (mean_motion, eccentricity, etc.). These are not derived or
intermediate calculations - they come directly from CelesTrak's GP JSON
response alongside the raw TLE lines - so storing them avoids having to
re-parse the fixed-column TLE format just to redisplay a value we already
had, and they map 1:1 onto the existing `OrbitalElementSet` schema
(Phase 1) with no lossy round-trip. This does NOT store per-second
positions or anything computed by SGP4 - see project plan section 20.

Each successful CelesTrak fetch is inserted as a new row rather than
overwritten in place, so "the latest elements" is always well-defined
(most recent epoch) without destroying history. This is a deliberate
choice, not an oversight: it happens to be exactly the historical data
the optional Phase 15 research question ("how does orbital-element age
affect prediction accuracy?") would need. It does mean this table grows
over time for actively-tracked satellites - worth a retention/pruning
policy in Phase 10 if it becomes large in practice.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.satellite import Satellite


class OrbitalElements(Base):
    __tablename__ = "orbital_elements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        ForeignKey("satellites.id", ondelete="CASCADE"), nullable=False, index=True
    )

    epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    line1: Mapped[str] = mapped_column(String(80), nullable=False)
    line2: Mapped[str] = mapped_column(String(80), nullable=False)

    mean_motion: Mapped[float] = mapped_column(Float, nullable=False)
    eccentricity: Mapped[float] = mapped_column(Float, nullable=False)
    inclination_deg: Mapped[float] = mapped_column(Float, nullable=False)
    raan_deg: Mapped[float] = mapped_column(Float, nullable=False)
    arg_perigee_deg: Mapped[float] = mapped_column(Float, nullable=False)
    mean_anomaly_deg: Mapped[float] = mapped_column(Float, nullable=False)
    bstar: Mapped[float] = mapped_column(Float, nullable=False)
    element_set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revolution_number: Mapped[int] = mapped_column(Integer, nullable=False)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    satellite: Mapped[Satellite] = relationship(back_populates="orbital_elements")
