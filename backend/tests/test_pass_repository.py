from datetime import datetime, timezone
from typing import List, Tuple

from app.db.repositories.observer_repository import ObserverRepository
from app.db.repositories.pass_repository import PassRepository
from app.db.repositories.satellite_repository import SatelliteRepository
from app.models.pass_record import PassRecord
from app.models.visibility_prediction import VisibilityPrediction
from app.schemas.observer import ObserverLocation
from app.schemas.orbital_elements import OrbitalElementSet
from app.schemas.pass_event import PassEvent
from app.schemas.satellite import SatelliteRecord
from app.schemas.visibility import (
    ConfidenceLevel,
    MethodVisibility,
    ObservationMethod,
    VisibilityClassification,
    VisibilityFactor,
)


def _seed_satellite_and_observer(db_session) -> Tuple[int, int]:
    sat_repo = SatelliteRepository(db_session)
    sat_repo.upsert(
        SatelliteRecord(
            norad_id=25544,
            name="ISS (ZARYA)",
            orbital_elements=OrbitalElementSet(
                epoch=datetime.now(timezone.utc),
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
    )
    from app.models.satellite import Satellite

    satellite_id = db_session.query(Satellite).filter_by(norad_id=25544).one().id

    observer_repo = ObserverRepository(db_session)
    observer_id = observer_repo.create(
        ObserverLocation(name="Home", latitude_deg=32.08, longitude_deg=34.78, altitude_m=5.0)
    )
    return satellite_id, observer_id


def _make_pass_event() -> PassEvent:
    now = datetime.now(timezone.utc)
    return PassEvent(
        rise_time=now,
        peak_time=now,
        set_time=now,
        rise_azimuth_deg=10.0,
        peak_azimuth_deg=90.0,
        set_azimuth_deg=170.0,
        max_elevation_deg=80.0,
        duration_seconds=300.0,
        rise_range_km=1500.0,
        max_range_km=500.0,
        set_range_km=1500.0,
        min_elevation_threshold_deg=10.0,
    )


def _make_visibility_results() -> List[MethodVisibility]:
    return [
        MethodVisibility(
            method=ObservationMethod.NAKED_EYE,
            score=90,
            classification=VisibilityClassification.EXCELLENT,
            confidence=ConfidenceLevel.MEDIUM,
            factors=[VisibilityFactor(label="Maximum elevation", detail="80°")],
            limitations=["Actual visibility depends on local conditions."],
        ),
        MethodVisibility(
            method=ObservationMethod.TELESCOPE,
            score=70,
            classification=VisibilityClassification.POSSIBLE,
            confidence=ConfidenceLevel.LOW,
            factors=[VisibilityFactor(label="Tracking difficulty", detail="Moderate")],
            limitations=[],
        ),
    ]


def test_save_pass_with_visibility_creates_pass_and_predictions(db_session) -> None:
    satellite_id, observer_id = _seed_satellite_and_observer(db_session)
    repo = PassRepository(db_session)

    pass_id = repo.save_pass_with_visibility(
        satellite_id, observer_id, _make_pass_event(), _make_visibility_results()
    )

    pass_row = db_session.get(PassRecord, pass_id)
    assert pass_row is not None
    assert pass_row.max_elevation == 80.0
    assert pass_row.satellite_id == satellite_id
    assert pass_row.observer_id == observer_id

    predictions = (
        db_session.query(VisibilityPrediction).filter_by(pass_id=pass_id).order_by("method").all()
    )
    assert len(predictions) == 2
    methods = {p.method for p in predictions}
    assert methods == {"naked_eye", "telescope"}


def test_saved_visibility_prediction_preserves_factors_as_json(db_session) -> None:
    satellite_id, observer_id = _seed_satellite_and_observer(db_session)
    repo = PassRepository(db_session)

    pass_id = repo.save_pass_with_visibility(
        satellite_id, observer_id, _make_pass_event(), _make_visibility_results()
    )

    naked_eye = (
        db_session.query(VisibilityPrediction).filter_by(pass_id=pass_id, method="naked_eye").one()
    )
    assert naked_eye.factors == [{"label": "Maximum elevation", "detail": "80°"}]
    assert naked_eye.limitations == ["Actual visibility depends on local conditions."]


def test_deleting_pass_removes_visibility_predictions(db_session) -> None:
    satellite_id, observer_id = _seed_satellite_and_observer(db_session)
    repo = PassRepository(db_session)
    pass_id = repo.save_pass_with_visibility(
        satellite_id, observer_id, _make_pass_event(), _make_visibility_results()
    )

    pass_row = db_session.get(PassRecord, pass_id)
    db_session.delete(pass_row)
    db_session.flush()

    remaining = db_session.query(VisibilityPrediction).filter_by(pass_id=pass_id).all()
    assert remaining == []
