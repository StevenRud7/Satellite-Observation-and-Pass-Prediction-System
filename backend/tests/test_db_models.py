from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.observer import Observer
from app.models.orbital_elements import OrbitalElements
from app.models.pass_record import PassRecord
from app.models.satellite import Satellite
from app.models.visibility_prediction import VisibilityPrediction


def _make_satellite(norad_id: int = 25544) -> Satellite:
    return Satellite(norad_id=norad_id, name="ISS (ZARYA)")


def _make_orbital_elements(satellite_id: int, epoch: datetime) -> OrbitalElements:
    return OrbitalElements(
        satellite_id=satellite_id,
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
    )


def test_satellite_can_be_created_and_queried(db_session) -> None:
    satellite = _make_satellite()
    db_session.add(satellite)
    db_session.flush()

    assert satellite.id is not None
    assert satellite.created_at is not None
    assert satellite.updated_at is not None


def test_satellite_norad_id_must_be_unique(db_session) -> None:
    db_session.add(_make_satellite(norad_id=25544))
    db_session.flush()

    db_session.add(_make_satellite(norad_id=25544))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_satellite_optional_metadata_fields_default_to_null(db_session) -> None:
    satellite = _make_satellite()
    db_session.add(satellite)
    db_session.flush()

    assert satellite.international_designator is None
    assert satellite.object_type is None
    assert satellite.country is None
    assert satellite.launch_date is None


def test_satellite_accepts_optional_metadata(db_session) -> None:
    satellite = Satellite(
        norad_id=25544,
        name="ISS (ZARYA)",
        international_designator="1998-067A",
        object_type="PAYLOAD",
        country="ISS",
        launch_date=date(1998, 11, 20),
    )
    db_session.add(satellite)
    db_session.flush()

    assert satellite.international_designator == "1998-067A"
    assert satellite.launch_date == date(1998, 11, 20)


def test_orbital_elements_relationship_is_ordered_by_epoch_descending(db_session) -> None:
    satellite = _make_satellite()
    db_session.add(satellite)
    db_session.flush()

    older = _make_orbital_elements(satellite.id, datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _make_orbital_elements(satellite.id, datetime(2024, 6, 1, tzinfo=timezone.utc))
    # Insert out of chronological order to make sure the relationship's
    # ORDER BY, not insertion order, determines the result.
    db_session.add(newer)
    db_session.add(older)
    db_session.flush()
    db_session.refresh(satellite)

    assert len(satellite.orbital_elements) == 2
    assert satellite.orbital_elements[0].epoch == datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_deleting_satellite_cascades_to_orbital_elements(db_session) -> None:
    satellite = _make_satellite()
    db_session.add(satellite)
    db_session.flush()
    db_session.add(_make_orbital_elements(satellite.id, datetime.now(timezone.utc)))
    db_session.flush()

    db_session.delete(satellite)
    db_session.flush()

    remaining = db_session.query(OrbitalElements).filter_by(satellite_id=satellite.id).all()
    assert remaining == []


def test_observer_altitude_defaults_to_zero(db_session) -> None:
    observer = Observer(latitude=32.08, longitude=34.78)
    db_session.add(observer)
    db_session.flush()
    db_session.refresh(observer)

    assert observer.altitude == 0.0


def test_pass_record_and_visibility_prediction_relationship(db_session) -> None:
    satellite = _make_satellite()
    observer = Observer(latitude=32.08, longitude=34.78, altitude=5.0)
    db_session.add_all([satellite, observer])
    db_session.flush()

    now = datetime.now(timezone.utc)
    pass_row = PassRecord(
        satellite_id=satellite.id,
        observer_id=observer.id,
        rise_time=now,
        peak_time=now,
        set_time=now,
        rise_azimuth=10.0,
        peak_azimuth=90.0,
        set_azimuth=170.0,
        max_elevation=80.0,
        duration_seconds=300.0,
        min_elevation_threshold=10.0,
        rise_range=1500.0,
        max_range=500.0,
        set_range=1500.0,
    )
    db_session.add(pass_row)
    db_session.flush()

    prediction = VisibilityPrediction(
        pass_id=pass_row.id,
        method="naked_eye",
        score=90,
        classification="excellent",
        confidence="medium",
        factors=[{"label": "Test", "detail": "ok"}],
        limitations=["none"],
    )
    db_session.add(prediction)
    db_session.flush()
    db_session.refresh(pass_row)

    assert len(pass_row.visibility_predictions) == 1
    assert pass_row.visibility_predictions[0].score == 90


def test_visibility_prediction_unique_per_pass_and_method(db_session) -> None:
    satellite = _make_satellite()
    observer = Observer(latitude=32.08, longitude=34.78, altitude=5.0)
    db_session.add_all([satellite, observer])
    db_session.flush()

    now = datetime.now(timezone.utc)
    pass_row = PassRecord(
        satellite_id=satellite.id,
        observer_id=observer.id,
        rise_time=now,
        peak_time=now,
        set_time=now,
        rise_azimuth=10.0,
        peak_azimuth=90.0,
        set_azimuth=170.0,
        max_elevation=80.0,
        duration_seconds=300.0,
        min_elevation_threshold=10.0,
        rise_range=1500.0,
        max_range=500.0,
        set_range=1500.0,
    )
    db_session.add(pass_row)
    db_session.flush()

    db_session.add(
        VisibilityPrediction(
            pass_id=pass_row.id,
            method="naked_eye",
            score=90,
            classification="excellent",
            confidence="medium",
            factors=[],
            limitations=[],
        )
    )
    db_session.flush()

    db_session.add(
        VisibilityPrediction(
            pass_id=pass_row.id,
            method="naked_eye",
            score=50,
            classification="possible",
            confidence="low",
            factors=[],
            limitations=[],
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_deleting_pass_cascades_to_visibility_predictions(db_session) -> None:
    satellite = _make_satellite()
    observer = Observer(latitude=32.08, longitude=34.78, altitude=5.0)
    db_session.add_all([satellite, observer])
    db_session.flush()

    now = datetime.now(timezone.utc)
    pass_row = PassRecord(
        satellite_id=satellite.id,
        observer_id=observer.id,
        rise_time=now,
        peak_time=now,
        set_time=now,
        rise_azimuth=10.0,
        peak_azimuth=90.0,
        set_azimuth=170.0,
        max_elevation=80.0,
        duration_seconds=300.0,
        min_elevation_threshold=10.0,
        rise_range=1500.0,
        max_range=500.0,
        set_range=1500.0,
    )
    db_session.add(pass_row)
    db_session.flush()
    db_session.add(
        VisibilityPrediction(
            pass_id=pass_row.id,
            method="naked_eye",
            score=90,
            classification="excellent",
            confidence="medium",
            factors=[],
            limitations=[],
        )
    )
    db_session.flush()

    db_session.delete(pass_row)
    db_session.flush()

    remaining = db_session.query(VisibilityPrediction).filter_by(pass_id=pass_row.id).all()
    assert remaining == []
