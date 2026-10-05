"""
Utilities for validating raw TLE (Two-Line Element) lines.

We don't hand-parse the individual TLE columns ourselves for the numeric
orbital parameters - CelesTrak's JSON format gives us those pre-parsed and
they're what SGP4 actually consumes via the raw lines anyway. What we do
need to check ourselves is that the lines we were given are well-formed,
since a corrupted or truncated TLE would otherwise fail deep inside SGP4
with a much less helpful error.
"""

from __future__ import annotations

TLE_LINE_LENGTH = 69


def tle_line_checksum(line: str) -> int:
    """Compute the standard TLE checksum for the first 68 characters of a line.

    Every digit contributes its value; every '-' contributes 1; everything
    else (letters, '.', '+', spaces) contributes 0. The result is mod 10.
    """
    total = 0
    for char in line[:68]:
        if char.isdigit():
            total += int(char)
        elif char == "-":
            total += 1
    return total % 10


def validate_tle_checksum(line: str) -> bool:
    """Return True if `line` is 69 characters long and its checksum digit matches."""
    if len(line) != TLE_LINE_LENGTH:
        return False
    if not line[68].isdigit():
        return False
    return tle_line_checksum(line) == int(line[68])
