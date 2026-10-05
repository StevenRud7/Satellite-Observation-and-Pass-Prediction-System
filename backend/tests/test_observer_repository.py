from app.db.repositories.observer_repository import ObserverRepository
from app.schemas.observer import ObserverLocation


def test_create_then_get_round_trips(db_session) -> None:
    repo = ObserverRepository(db_session)
    observer = ObserverLocation(
        name="Home", latitude_deg=32.08, longitude_deg=34.78, altitude_m=5.0
    )

    observer_id = repo.create(observer)
    fetched = repo.get(observer_id)

    assert fetched is not None
    assert fetched.name == "Home"
    assert fetched.latitude_deg == 32.08
    assert fetched.longitude_deg == 34.78
    assert fetched.altitude_m == 5.0


def test_get_returns_none_for_unknown_id(db_session) -> None:
    repo = ObserverRepository(db_session)
    assert repo.get(999999) is None


def test_list_all_returns_every_saved_observer(db_session) -> None:
    repo = ObserverRepository(db_session)
    repo.create(ObserverLocation(name="Home", latitude_deg=32.08, longitude_deg=34.78))
    repo.create(ObserverLocation(name="Cabin", latitude_deg=45.0, longitude_deg=-70.0))

    all_observers = repo.list_all()

    assert len(all_observers) == 2
    names = {o.name for _, o in all_observers}
    assert names == {"Home", "Cabin"}


def test_delete_removes_observer(db_session) -> None:
    repo = ObserverRepository(db_session)
    observer_id = repo.create(ObserverLocation(latitude_deg=0.0, longitude_deg=0.0))

    deleted = repo.delete(observer_id)

    assert deleted is True
    assert repo.get(observer_id) is None


def test_delete_returns_false_for_unknown_id(db_session) -> None:
    repo = ObserverRepository(db_session)
    assert repo.delete(999999) is False


def test_observer_without_name_round_trips_as_none(db_session) -> None:
    repo = ObserverRepository(db_session)
    observer_id = repo.create(ObserverLocation(latitude_deg=10.0, longitude_deg=20.0))

    fetched = repo.get(observer_id)

    assert fetched is not None
    assert fetched.name is None
