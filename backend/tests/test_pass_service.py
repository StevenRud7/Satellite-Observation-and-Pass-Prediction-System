from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.pass_api import PassPredictRequest
from app.services.pass_service import ObserverNotFoundError, PassService


class _FakeSatelliteService:
    def __init__(self, record) -> None:
        self._record = record

    def get_satellite(self, norad_id: int, *, force_refresh: bool = False):
        return self._record


def test_predict_raises_observer_not_found(
    clean_database, valid_gp_record, valid_tle_lines
) -> None:
    from app.db.repositories.satellite_repository import SatelliteRepository
    from app.db.session import session_scope
    from app.schemas.orbital_elements import OrbitalElementSet
    from app.schemas.satellite import SatelliteRecord

    record = SatelliteRecord(
        norad_id=5,
        name="VANGUARD 1",
        orbital_elements=OrbitalElementSet(
            epoch=datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc),
            line1=valid_tle_lines[0],
            line2=valid_tle_lines[1],
            mean_motion=valid_gp_record["MEAN_MOTION"],
            eccentricity=valid_gp_record["ECCENTRICITY"],
            inclination_deg=valid_gp_record["INCLINATION"],
            raan_deg=valid_gp_record["RA_OF_ASC_NODE"],
            arg_perigee_deg=valid_gp_record["ARG_OF_PERICENTER"],
            mean_anomaly_deg=valid_gp_record["MEAN_ANOMALY"],
            bstar=valid_gp_record["BSTAR"],
            element_set_number=valid_gp_record["ELEMENT_SET_NO"],
            revolution_number=valid_gp_record["REV_AT_EPOCH"],
            source="celestrak",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )
    with session_scope() as session:
        SatelliteRepository(session).upsert(record)

    service = PassService(satellite_service=_FakeSatelliteService(record))
    request = PassPredictRequest(
        norad_id=5,
        observer_id=999999,
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with pytest.raises(ObserverNotFoundError):
        service.predict_and_persist(request)


def test_predict_raises_satellite_not_cached_when_never_fetched(
    clean_database, valid_gp_record, valid_tle_lines
) -> None:
    """If a satellite was fetched (so SatelliteService has a record) but
    somehow never persisted - e.g. no database was configured at fetch
    time - predicting a pass for it should fail clearly rather than
    silently using a wrong/missing foreign key. Simulated here simply by
    never upserting the satellite into the DB at all."""
    from app.schemas.orbital_elements import OrbitalElementSet
    from app.schemas.satellite import SatelliteRecord
    from app.services.pass_service import SatelliteNotCachedError

    record = SatelliteRecord(
        norad_id=999,
        name="NOT IN DB",
        orbital_elements=OrbitalElementSet(
            epoch=datetime(2000, 6, 27, 18, 50, 19, 733568, tzinfo=timezone.utc),
            line1=valid_tle_lines[0],
            line2=valid_tle_lines[1],
            mean_motion=valid_gp_record["MEAN_MOTION"],
            eccentricity=valid_gp_record["ECCENTRICITY"],
            inclination_deg=valid_gp_record["INCLINATION"],
            raan_deg=valid_gp_record["RA_OF_ASC_NODE"],
            arg_perigee_deg=valid_gp_record["ARG_OF_PERICENTER"],
            mean_anomaly_deg=valid_gp_record["MEAN_ANOMALY"],
            bstar=valid_gp_record["BSTAR"],
            element_set_number=valid_gp_record["ELEMENT_SET_NO"],
            revolution_number=valid_gp_record["REV_AT_EPOCH"],
            source="celestrak",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )
    # Deliberately not upserted into the database.

    service = PassService(satellite_service=_FakeSatelliteService(record))
    request = PassPredictRequest(
        norad_id=999,
        latitude_deg=0.0,
        longitude_deg=0.0,
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with pytest.raises(SatelliteNotCachedError):
        service.predict_and_persist(request)
