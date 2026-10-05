"""
SQLAlchemy declarative base.

The naming convention below is applied to every constraint and index
Alembic generates (foreign keys, unique constraints, indexes, etc.),
giving them predictable names like `fk_orbital_elements_satellite_id_satellites`
instead of database-assigned defaults that vary and are awkward to
reference later in a migration (e.g. to drop a constraint by name).
This is a standard SQLAlchemy recommendation, not a project-specific
invention.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
