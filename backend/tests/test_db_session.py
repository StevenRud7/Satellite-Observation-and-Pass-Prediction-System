import pytest

from app.core.config import Settings
from app.db import session as db_session_module
from app.models.satellite import Satellite


def test_get_engine_raises_when_database_url_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(db_session_module, "get_settings", lambda: Settings(database_url=None))
    db_session_module.reset_engine_cache()
    try:
        with pytest.raises(db_session_module.DatabaseNotConfiguredError):
            db_session_module.get_engine()
    finally:
        db_session_module.reset_engine_cache()


def test_session_scope_commits_on_success(clean_database) -> None:
    with db_session_module.session_scope() as session:
        session.add(Satellite(norad_id=42, name="Test Satellite"))

    with db_session_module.session_scope() as session:
        found = session.query(Satellite).filter_by(norad_id=42).one_or_none()

    assert found is not None
    assert found.name == "Test Satellite"


def test_session_scope_rolls_back_on_exception(clean_database) -> None:
    with pytest.raises(RuntimeError), db_session_module.session_scope() as session:
        session.add(Satellite(norad_id=43, name="Should not persist"))
        session.flush()
        raise RuntimeError("boom")

    with db_session_module.session_scope() as session:
        count = session.query(Satellite).filter_by(norad_id=43).count()

    assert count == 0
