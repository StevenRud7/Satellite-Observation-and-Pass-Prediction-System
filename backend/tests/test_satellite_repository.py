from datetime import datetime, timezone
from typing import Optional

from app.db.repositories.satellite_repository import SatelliteRepository
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.satellite import SatelliteRecord


def _make_record(
    norad_id: int = 25544, name: str = "ISS (ZARYA)", epoch: Optional[datetime] = None
) -> SatelliteRecord:
    epoch = epoch or datetime.now(timezone.utc)
    return SatelliteRecord(
        norad_id=norad_id,
        name=name,
        international_designator="1998-067A",
        orbital_elements=OrbitalElementSet(
            epoch=epoch,
            line1="1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9990",
            line2="2 25544  51.6400 000.0000 0000000 000.0000 000.0000 15.50000000000010",
            mean_motion=15.5,
            eccentricity=0.0001,
            inclination_deg=51.64,
            raan_deg=0.0,
            arg_perigee_deg=0.0,
            mean_anomaly_deg=0.0,
            bstar=0.0001,
            element_set_number=999,
            revolution_number=1,
            source="celestrak",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )


def test_get_latest_by_norad_id_returns_none_when_unknown(db_session) -> None:
    repo = SatelliteRepository(db_session)
    assert repo.get_latest_by_norad_id(99999) is None


def test_upsert_then_get_round_trips_correctly(db_session) -> None:
    repo = SatelliteRepository(db_session)
    record = _make_record()

    repo.upsert(record)
    fetched = repo.get_latest_by_norad_id(25544)

    assert fetched is not None
    assert fetched.norad_id == 25544
    assert fetched.name == "ISS (ZARYA)"
    assert fetched.international_designator == "1998-067A"
    assert fetched.orbital_elements.line1 == record.orbital_elements.line1
    assert fetched.orbital_elements.mean_motion == record.orbital_elements.mean_motion


def test_upsert_twice_updates_metadata_without_duplicating_satellite(db_session) -> None:
    repo = SatelliteRepository(db_session)
    repo.upsert(_make_record(name="ISS (ZARYA)"))
    repo.upsert(_make_record(name="ISS (ZARYA) - renamed"))

    from app.models.satellite import Satellite

    satellites = db_session.query(Satellite).filter_by(norad_id=25544).all()
    assert len(satellites) == 1
    assert satellites[0].name == "ISS (ZARYA) - renamed"


def test_upsert_twice_keeps_both_orbital_elements_rows(db_session) -> None:
    repo = SatelliteRepository(db_session)
    first_epoch = datetime(2024, 1, 1, tzinfo=timezone.utc)
    second_epoch = datetime(2024, 6, 1, tzinfo=timezone.utc)

    repo.upsert(_make_record(epoch=first_epoch))
    repo.upsert(_make_record(epoch=second_epoch))

    from app.models.orbital_elements import OrbitalElements
    from app.models.satellite import Satellite

    satellite = db_session.query(Satellite).filter_by(norad_id=25544).one()
    rows = db_session.query(OrbitalElements).filter_by(satellite_id=satellite.id).all()
    assert len(rows) == 2


def test_get_latest_returns_most_recent_epoch_regardless_of_insert_order(db_session) -> None:
    repo = SatelliteRepository(db_session)
    newer_epoch = datetime(2024, 6, 1, tzinfo=timezone.utc)
    older_epoch = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # Insert the newer epoch first, then the older one, to make sure
    # "latest" is determined by epoch, not insertion order.
    repo.upsert(_make_record(epoch=newer_epoch))
    repo.upsert(_make_record(epoch=older_epoch))

    fetched = repo.get_latest_by_norad_id(25544)

    assert fetched is not None
    assert fetched.orbital_elements.epoch == newer_epoch


def test_different_satellites_are_independent(db_session) -> None:
    repo = SatelliteRepository(db_session)
    repo.upsert(_make_record(norad_id=25544, name="ISS (ZARYA)"))
    repo.upsert(_make_record(norad_id=20580, name="HST"))

    iss = repo.get_latest_by_norad_id(25544)
    hst = repo.get_latest_by_norad_id(20580)

    assert iss is not None and iss.name == "ISS (ZARYA)"
    assert hst is not None and hst.name == "HST"
