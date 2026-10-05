"""
Validation for orbital element data retrieved from CelesTrak.

CelesTrak's GP data comes from this project as two separate pieces (see
app/data/celestrak.py for why): the JSON/OMM metadata record, and the raw
TLE line pair SGP4 actually propagates. Each gets its own validation:

1. `validate_gp_record` - the JSON record has the fields we depend on, and
   its values are physically plausible for an Earth-orbiting object (this
   catches corrupted data; it is not a claim that the orbit is accurate).
2. `validate_tle_lines` - the TLE lines are well-formed (correct
   line-number prefixes, length, checksum) before they're ever handed to
   SGP4.
"""

from __future__ import annotations

from typing import Any, Dict

from app.data.exceptions import OrbitalDataValidationError
from app.data.tle import validate_tle_checksum

REQUIRED_GP_FIELDS = (
    "OBJECT_NAME",
    "NORAD_CAT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "BSTAR",
    "ELEMENT_SET_NO",
    "REV_AT_EPOCH",
)


def validate_gp_record(record: Dict[str, Any], expected_norad_id: int) -> None:
    """Raise OrbitalDataValidationError if `record` is missing data or implausible.

    `record` is one entry from CelesTrak's GP JSON response
    (https://celestrak.org/NORAD/elements/gp.php?...&FORMAT=JSON) - the
    OMM-keyword metadata record, not the raw TLE lines (see
    `validate_tle_lines` for those).
    """
    missing = [field for field in REQUIRED_GP_FIELDS if record.get(field) is None]
    if missing:
        raise OrbitalDataValidationError(f"CelesTrak record is missing fields: {missing}")

    actual_norad_id = int(record["NORAD_CAT_ID"])
    if actual_norad_id != expected_norad_id:
        raise OrbitalDataValidationError(
            f"Requested NORAD ID {expected_norad_id} but CelesTrak returned {actual_norad_id}"
        )

    eccentricity = float(record["ECCENTRICITY"])
    if not (0.0 <= eccentricity < 1.0):
        raise OrbitalDataValidationError(f"Eccentricity {eccentricity} is out of physical range")

    inclination = float(record["INCLINATION"])
    if not (0.0 <= inclination <= 180.0):
        raise OrbitalDataValidationError(f"Inclination {inclination} is out of physical range")

    mean_motion = float(record["MEAN_MOTION"])
    if mean_motion <= 0.0:
        raise OrbitalDataValidationError(f"Mean motion {mean_motion} must be positive")


def validate_tle_lines(line1: str, line2: str) -> None:
    """Raise OrbitalDataValidationError if the raw TLE line pair is malformed.

    `line1`/`line2` come from CelesTrak's `FORMAT=TLE` response - plain
    fixed-width TLE text, not JSON.
    """
    if not (isinstance(line1, str) and isinstance(line2, str)):
        raise OrbitalDataValidationError("TLE lines must be strings")

    if not (line1.startswith("1 ") and line2.startswith("2 ")):
        raise OrbitalDataValidationError("TLE lines do not have the expected line-number prefix")

    if not validate_tle_checksum(line1):
        raise OrbitalDataValidationError("TLE line 1 failed checksum validation")

    if not validate_tle_checksum(line2):
        raise OrbitalDataValidationError("TLE line 2 failed checksum validation")
