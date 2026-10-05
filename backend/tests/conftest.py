"""
Shared test fixtures.

VALID_GP_RECORD is a realistic CelesTrak GP JSON record for Vanguard 1
(NORAD 00005). CelesTrak's JSON format carries the individually-parsed
OMM (Orbit Mean-Elements Message) fields but, contrary to an earlier
assumption in this codebase, does NOT include the raw TLE_LINE1/TLE_LINE2
strings - those come from a separate `FORMAT=TLE` request (see
app/data/celestrak.py). SAMPLE_TLE_LINE1/2 are that satellite's real,
well-known reference TLE lines (used in the sgp4 library's own test
suite) with verified-correct checksums, so tests exercise real
validation and parsing logic rather than synthetic data.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - populates Base.metadata with every table
from app.core.config import get_settings
from app.db.base import Base

SAMPLE_TLE_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
SAMPLE_TLE_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"

VALID_GP_RECORD = {
    "OBJECT_NAME": "VANGUARD 1",
    "OBJECT_ID": "1958-002B",
    "EPOCH": "2000-06-27T18:50:19.733568",
    "MEAN_MOTION": 10.82419157,
    "ECCENTRICITY": 0.1859667,
    "INCLINATION": 34.2682,
    "RA_OF_ASC_NODE": 348.7242,
    "ARG_OF_PERICENTER": 331.7664,
    "MEAN_ANOMALY": 19.3264,
    "EPHEMERIS_TYPE": 0,
    "CLASSIFICATION_TYPE": "U",
    "NORAD_CAT_ID": 5,
    "ELEMENT_SET_NO": 475,
    "REV_AT_EPOCH": 13667,
    "BSTAR": 2.8098e-05,
    "MEAN_MOTION_DOT": 0.00000023,
    "MEAN_MOTION_DDOT": 0,
}


@pytest.fixture
def valid_gp_record() -> dict:
    return dict(VALID_GP_RECORD)


@pytest.fixture
def valid_tle_lines() -> tuple:
    return (SAMPLE_TLE_LINE1, SAMPLE_TLE_LINE2)


# --- Database fixtures -----------------------------------------------------
#
# These tests require a real, reachable PostgreSQL database (DATABASE_URL).
# They are skipped - not failed - when one isn't available, so `pytest`
# still passes on a machine or CI job with no database configured (see
# backend/.env.example and the README for how to set one up locally).
# This project deliberately does not fall back to SQLite for these tests:
# the point of Phase 6 is PostgreSQL specifically, and SQLite differs from
# it in ways (constraint enforcement, JSON handling) that could hide real
# bugs.


def _try_connect(url: str) -> bool:
    try:
        engine = create_engine(url)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def database_url() -> str:
    settings = get_settings()
    if not settings.database_url or not _try_connect(settings.database_url):
        pytest.skip(
            "PostgreSQL not available for database tests - set DATABASE_URL to a "
            "reachable Postgres instance to run these (see backend/.env.example)."
        )
    return settings.database_url


@pytest.fixture(scope="session")
def db_engine(database_url: str):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def clean_database(db_engine):
    """Truncate every table before a test runs, so tests don't see each
    other's rows. Used directly by tests that go through
    `app.db.session.session_scope()` (which manages its own Session bound
    to the global engine) rather than the `db_session` fixture below."""
    with db_engine.connect() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE visibility_predictions, passes, orbital_elements, "
                "satellites, observers RESTART IDENTITY CASCADE"
            )
        )
        connection.commit()


@pytest.fixture
def db_session(db_engine, clean_database):
    """A real, isolated SQLAlchemy Session against the test database."""
    session_factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
