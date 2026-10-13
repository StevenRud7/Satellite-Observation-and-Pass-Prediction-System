#!/usr/bin/env python3
"""
Fetch current TLEs for the curated satellite catalog from CelesTrak and write
them to a JSON snapshot file (format documented in backend/app/data/snapshot.py).

Standard library only, so the scheduled GitHub Actions job needs no
`pip install`. Deliberately polite to CelesTrak: one request per satellite,
a pause between requests, and it is meant to run only a few times a day.

Usage:  python scripts/update_tle_snapshot.py --out tle_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = REPO_ROOT / "backend" / "app" / "data" / "satellite_catalog.py"
URL = "https://celestrak.org/NORAD/elements/gp.php"
HEADERS = {"User-Agent": "satellite-obs-snapshot/1.0 (+https://github.com/StevenRud7)"}


def catalog_ids() -> list:
    # Read the IDs straight out of the catalog source so this script stays
    # dependency-free and can't drift from the app's own list.
    text = CATALOG_FILE.read_text(encoding="utf-8")
    return sorted({int(m) for m in re.findall(r"CatalogEntry\(\s*(\d+)\s*,", text)})


def fetch_tle(norad_id: int) -> dict:
    query = urllib.parse.urlencode({"CATNR": norad_id, "FORMAT": "TLE"})
    request = urllib.request.Request(f"{URL}?{query}", headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        lines = [ln.rstrip() for ln in response.read().decode("utf-8").splitlines() if ln.strip()]
    line1 = next((ln for ln in lines if ln.startswith("1 ")), None)
    line2 = next((ln for ln in lines if ln.startswith("2 ")), None)
    if line1 is None or line2 is None:
        raise ValueError(f"no TLE lines in response ({len(lines)} lines)")
    name_lines = [ln.strip() for ln in lines if not ln.startswith(("1 ", "2 "))]
    name = name_lines[0] if name_lines else f"NORAD {norad_id}"
    return {"name": name, "line1": line1, "line2": line2}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    satellites = {}
    for norad_id in catalog_ids():
        try:
            satellites[str(norad_id)] = fetch_tle(norad_id)
            print(f"ok   {norad_id}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"FAIL {norad_id}: {exc}", file=sys.stderr)
        time.sleep(1.5)

    if not satellites:
        print("No satellites fetched - leaving the existing snapshot untouched.", file=sys.stderr)
        return 1

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "satellites": satellites}
    Path(args.out).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(satellites)} satellites to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
