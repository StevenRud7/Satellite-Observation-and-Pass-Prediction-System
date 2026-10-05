"""
SQLAlchemy model for the `satellites` table.

Stores satellite identity/metadata only - never computed positions (those
are always calculated dynamically; see project plan section 20, "what
should NOT be stored").
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.orbital_elements import OrbitalElements


class Satellite(Base):
    __tablename__ = "satellites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    norad_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    international_designator: Mapped[Optional[str]] = mapped_column(String(32))
    # Payload/rocket-body/debris/etc. Not populated by the current
    # ingestion pipeline (see Phase 1 limitations - CelesTrak's GP
    # endpoint doesn't return it) but the column exists so it can be
    # filled in later (e.g. a SATCAT lookup) without a migration.
    object_type: Mapped[Optional[str]] = mapped_column(String(32))
    country: Mapped[Optional[str]] = mapped_column(String(64))
    launch_date: Mapped[Optional[date]] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    orbital_elements: Mapped[List[OrbitalElements]] = relationship(
        back_populates="satellite",
        cascade="all, delete-orphan",
        order_by="OrbitalElements.epoch.desc()",
    )
