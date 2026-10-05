"""
SQLAlchemy model for the `visibility_predictions` table.

Deliberate deviation from the project plan's suggested column list
(section 19 lists separate darkness_score/illumination_score/
elevation_score/duration_score/range_score/tracking_difficulty/
estimated_brightness columns): `app/core/scoring.py` computes those as
internal intermediate values but does not currently expose them as a
structured result - only the combined score, classification, confidence,
and a human-readable factors/limitations explanation are part of the
`MethodVisibility` schema (Phase 4). Adding DB columns for values the
domain model doesn't produce would mean storing nulls or fabricated data,
which is worse than not having the columns. `estimated_brightness` is
omitted entirely - brightness is not modeled at all (see Phase 4/project
plan section 13 limitations). If per-factor subscores prove useful later
(e.g. for the Phase 15 research component), the right fix is to have
scoring.py return them as structured data first, then add the columns.

`factors` and `limitations` are stored as JSON, mirroring the
`VisibilityFactor` list and limitation strings from the Pydantic schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.pass_record import PassRecord


class VisibilityPrediction(Base):
    __tablename__ = "visibility_predictions"
    __table_args__ = (
        UniqueConstraint("pass_id", "method", name="uq_visibility_predictions_pass_id_method"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pass_id: Mapped[int] = mapped_column(
        ForeignKey("passes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    method: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)

    factors: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pass_record: Mapped[PassRecord] = relationship(back_populates="visibility_predictions")
