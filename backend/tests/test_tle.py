from app.data.tle import tle_line_checksum, validate_tle_checksum

VALID_LINE_1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
VALID_LINE_2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def test_checksum_of_known_valid_line_matches_trailing_digit() -> None:
    assert tle_line_checksum(VALID_LINE_1) == int(VALID_LINE_1[-1])
    assert tle_line_checksum(VALID_LINE_2) == int(VALID_LINE_2[-1])


def test_validate_tle_checksum_accepts_valid_lines() -> None:
    assert validate_tle_checksum(VALID_LINE_1) is True
    assert validate_tle_checksum(VALID_LINE_2) is True


def test_validate_tle_checksum_rejects_tampered_line() -> None:
    tampered = VALID_LINE_1[:20] + "9" + VALID_LINE_1[21:]
    assert validate_tle_checksum(tampered) is False


def test_validate_tle_checksum_rejects_wrong_length() -> None:
    assert validate_tle_checksum(VALID_LINE_1[:-1]) is False
    assert validate_tle_checksum(VALID_LINE_1 + "1") is False


def test_validate_tle_checksum_rejects_non_digit_checksum_char() -> None:
    malformed = VALID_LINE_1[:-1] + "X"
    assert validate_tle_checksum(malformed) is False


def test_minus_sign_counts_as_one_in_checksum() -> None:
    # '00000-0' and '28098-4' each contain a '-' which counts as 1 for the
    # checksum; this is a defining quirk of the TLE checksum algorithm.
    line_without_minus = VALID_LINE_1.replace("-", "0")
    # Same digits otherwise, so the checksums should differ.
    assert tle_line_checksum(line_without_minus) != tle_line_checksum(VALID_LINE_1)
