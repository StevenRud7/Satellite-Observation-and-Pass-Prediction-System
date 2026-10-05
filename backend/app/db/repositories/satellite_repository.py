"""
Satellite repository: persistence for satellite metadata and orbital
elements.

Translates between ORM models (app.models) and domain schemas
(app.schemas) so nothing outside this module needs to know both exist -
callers work entirely in terms of SatelliteRecord/OrbitalElementSet, the
same schemas used throughout the rest of the app (propagation, passes,
scoring). This is what keeps the scientific engine decoupled from
SQLAlchemy, per the project plan.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orbital_elements import OrbitalElements as OrbitalElementsORM
from app.models.satellite import Satellite as SatelliteORM
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord


class SatelliteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_latest_by_norad_id(self, norad_id: int) -> Optional[SatelliteRecord]:
        """The satellite's metadata plus its most recent orbital elements
        (by epoch), or None if we have never stored this satellite."""
        satellite = self._session.scalar(
            select(SatelliteORM).where(SatelliteORM.norad_id == norad_id)
        )
        if satellite is None or not satellite.orbital_elements:
            return None

        # The relationship is ordered by epoch descending (see
        # app/models/satellite.py), so the first entry is the latest.
        latest = satellite.orbital_elements[0]
        return _to_satellite_record(satellite, latest)

    def get_id_by_norad_id(self, norad_id: int) -> Optional[int]:
        """The satellite's database id (not its NORAD id), or None if it
        has never been fetched/cached. Used to resolve the foreign key
        needed when persisting a pass - see PassService."""
        return self._session.scalar(
            select(SatelliteORM.id).where(SatelliteORM.norad_id == norad_id)
        )

    def list_all(self) -> List[SatelliteRecord]:
        """Every satellite we have previously fetched, with its latest
        orbital elements. This is NOT a full catalog browse - it only
        returns satellites this backend has already cached via
        `/api/satellites/{norad_id}`. Real catalog browsing would need
        bulk CelesTrak ingestion, which is out of scope for now (see
        Phase 1 limitations)."""
        satellites = self._session.scalars(select(SatelliteORM)).all()
        return [
            _to_satellite_record(satellite, satellite.orbital_elements[0])
            for satellite in satellites
            if satellite.orbital_elements
        ]

    def upsert(self, record: SatelliteRecord) -> None:
        """Insert or update satellite metadata, and add a new orbital
        elements row.

        Each fetch is inserted as a new orbital_elements row rather than
        overwriting the previous one in place - see app/models/
        orbital_elements.py for why (short version: it's cheap, and it's
        exactly the historical data the Phase 15 research question needs).
        """
        satellite = self._session.scalar(
            select(SatelliteORM).where(SatelliteORM.norad_id == record.norad_id)
        )
        if satellite is None:
            satellite = SatelliteORM(norad_id=record.norad_id, name=record.name)
            self._session.add(satellite)
            self._session.flush()  # assigns satellite.id
        else:
            satellite.name = record.name

        satellite.international_designator = record.international_designator
        satellite.object_type = record.object_type

        elements = record.orbital_elements
        self._session.add(
            OrbitalElementsORM(
                satellite_id=satellite.id,
                epoch=elements.epoch,
                line1=elements.line1,
                line2=elements.line2,
                mean_motion=elements.mean_motion,
                eccentricity=elements.eccentricity,
                inclination_deg=elements.inclination_deg,
                raan_deg=elements.raan_deg,
                arg_perigee_deg=elements.arg_perigee_deg,
                mean_anomaly_deg=elements.mean_anomaly_deg,
                bstar=elements.bstar,
                element_set_number=elements.element_set_number,
                revolution_number=elements.revolution_number,
                source=elements.source,
                retrieved_at=elements.retrieved_at,
            )
        )
        self._session.flush()


def _to_satellite_record(satellite: SatelliteORM, elements: OrbitalElementsORM) -> SatelliteRecord:
    return SatelliteRecord(
        norad_id=satellite.norad_id,
        name=satellite.name,
        international_designator=satellite.international_designator,
        object_type=satellite.object_type,
        orbital_elements=OrbitalElementSet(
            epoch=elements.epoch,
            line1=elements.line1,
            line2=elements.line2,
            mean_motion=elements.mean_motion,
            eccentricity=elements.eccentricity,
            inclination_deg=elements.inclination_deg,
            raan_deg=elements.raan_deg,
            arg_perigee_deg=elements.arg_perigee_deg,
            mean_anomaly_deg=elements.mean_anomaly_deg,
            bstar=elements.bstar,
            element_set_number=elements.element_set_number,
            revolution_number=elements.revolution_number,
            source=elements.source,
            retrieved_at=elements.retrieved_at,
        ),
    )
