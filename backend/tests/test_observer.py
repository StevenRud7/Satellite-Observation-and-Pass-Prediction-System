import pytest
from pydantic import ValidationError

from app.schemas.observer import ObserverLocation


def test_valid_observer_is_accepted() -> None:
    observer = ObserverLocation(latitude_deg=32.08, longitude_deg=34.78, altitude_m=5.0)
    assert observer.latitude_deg == 32.08


def test_default_altitude_is_zero() -> None:
    observer = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0)
    assert observer.altitude_m == 0.0


@pytest.mark.parametrize("latitude", [-90.0, 90.0, 0.0])
def test_latitude_boundary_values_are_accepted(latitude: float) -> None:
    ObserverLocation(latitude_deg=latitude, longitude_deg=0.0)


@pytest.mark.parametrize("latitude", [90.1, -90.1, 1000.0])
def test_latitude_out_of_range_is_rejected(latitude: float) -> None:
    with pytest.raises(ValidationError):
        ObserverLocation(latitude_deg=latitude, longitude_deg=0.0)


@pytest.mark.parametrize("longitude", [180.1, -180.1])
def test_longitude_out_of_range_is_rejected(longitude: float) -> None:
    with pytest.raises(ValidationError):
        ObserverLocation(latitude_deg=0.0, longitude_deg=longitude)


def test_altitude_far_below_sea_level_is_rejected() -> None:
    with pytest.raises(ValidationError, match="altitude_m"):
        ObserverLocation(latitude_deg=0.0, longitude_deg=0.0, altitude_m=-10000.0)


def test_altitude_far_above_typical_ground_sites_is_rejected() -> None:
    with pytest.raises(ValidationError, match="altitude_m"):
        ObserverLocation(latitude_deg=0.0, longitude_deg=0.0, altitude_m=50000.0)
