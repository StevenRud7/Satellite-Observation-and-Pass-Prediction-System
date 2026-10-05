"""
Importing this package registers every ORM model with `Base.metadata` -
required both for Alembic's autogenerate to see the full schema and for
`Base.metadata.create_all()` (used in tests) to create every table.
"""

from app.models.observer import Observer
from app.models.orbital_elements import OrbitalElements
from app.models.pass_record import PassRecord
from app.models.satellite import Satellite
from app.models.visibility_prediction import VisibilityPrediction

__all__ = [
    "Observer",
    "OrbitalElements",
    "PassRecord",
    "Satellite",
    "VisibilityPrediction",
]
