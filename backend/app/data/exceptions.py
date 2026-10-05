"""
Exceptions for the orbital data ingestion pipeline.

Kept separate from FastAPI so the ingestion/validation code has no
dependency on the web framework and can be tested (or reused) in isolation.
Routes are responsible for translating these into HTTP responses.
"""


class CelestrakClientError(Exception):
    """Raised when CelesTrak can't be reached or returns an unusable response."""


class SatelliteNotFoundError(CelestrakClientError):
    """Raised when CelesTrak has no data for the requested identifier."""


class OrbitalDataValidationError(Exception):
    """Raised when retrieved orbital element data fails validation checks."""


class GeocodingError(Exception):
    """Raised when the place-search (geocoding) provider can't be reached or fails."""
