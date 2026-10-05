import pytest

from app.data.exceptions import OrbitalDataValidationError
from app.data.validation import validate_gp_record, validate_tle_lines


def test_valid_record_passes(valid_gp_record: dict) -> None:
    validate_gp_record(valid_gp_record, expected_norad_id=5)  # should not raise


def test_missing_field_is_rejected(valid_gp_record: dict) -> None:
    del valid_gp_record["MEAN_MOTION"]
    with pytest.raises(OrbitalDataValidationError, match="missing fields"):
        validate_gp_record(valid_gp_record, expected_norad_id=5)


def test_norad_id_mismatch_is_rejected(valid_gp_record: dict) -> None:
    with pytest.raises(OrbitalDataValidationError, match="Requested NORAD ID"):
        validate_gp_record(valid_gp_record, expected_norad_id=99999)


def test_eccentricity_out_of_range_is_rejected(valid_gp_record: dict) -> None:
    valid_gp_record["ECCENTRICITY"] = 1.5
    with pytest.raises(OrbitalDataValidationError, match="Eccentricity"):
        validate_gp_record(valid_gp_record, expected_norad_id=5)


def test_inclination_out_of_range_is_rejected(valid_gp_record: dict) -> None:
    valid_gp_record["INCLINATION"] = 200.0
    with pytest.raises(OrbitalDataValidationError, match="Inclination"):
        validate_gp_record(valid_gp_record, expected_norad_id=5)


def test_non_positive_mean_motion_is_rejected(valid_gp_record: dict) -> None:
    valid_gp_record["MEAN_MOTION"] = 0.0
    with pytest.raises(OrbitalDataValidationError, match="Mean motion"):
        validate_gp_record(valid_gp_record, expected_norad_id=5)


def test_valid_tle_lines_pass(valid_tle_lines) -> None:
    line1, line2 = valid_tle_lines
    validate_tle_lines(line1, line2)  # should not raise


def test_bad_line_prefix_is_rejected(valid_tle_lines) -> None:
    line1, line2 = valid_tle_lines
    bad_line1 = "X" + line1[1:]
    with pytest.raises(OrbitalDataValidationError, match="line-number prefix"):
        validate_tle_lines(bad_line1, line2)


def test_bad_checksum_is_rejected(valid_tle_lines) -> None:
    line1, line2 = valid_tle_lines
    bad_line1 = line1[:-1] + str((int(line1[-1]) + 1) % 10)
    with pytest.raises(OrbitalDataValidationError, match="checksum"):
        validate_tle_lines(bad_line1, line2)


def test_non_string_lines_are_rejected() -> None:
    with pytest.raises(OrbitalDataValidationError, match="must be strings"):
        validate_tle_lines(None, "2 00005  34.2682")  # type: ignore[arg-type]
