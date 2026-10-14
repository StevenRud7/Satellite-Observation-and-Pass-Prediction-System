#!/usr/bin/env python3
"""
Build a JSON snapshot of current TLEs and write it to --out (format documented
in backend/app/data/snapshot.py).

What goes in the snapshot:
  - CelesTrak's "stations" and "visual" groups (one request each: the space
    stations plus ~100 of the brightest objects - the ones people actually go
    outside to look at),
  - every NORAD ID in backend/app/data/satellite_catalog.py,
  - every ID listed in scripts/extra_norad_ids.txt.

Sources, in order: CelesTrak (groups, then single-ID requests for anything the
groups didn't cover), and for any ID still missing, the public TLE API
(https://tle.ivanstanojevic.me). So the snapshot still gets built if one of
the two is unreachable from the machine running this script.

Standard library only, so the scheduled GitHub Actions job needs no
`pip install`. Polite to CelesTrak: a handful of requests per run with pauses,
meant to run only a few times a day. Every TLE is checksum-validated before it
is written; invalid ones are skipped.

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
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = REPO_ROOT / "backend" / "app" / "data" / "satellite_catalog.py"
EXTRA_IDS_FILE = Path(__file__).resolve().parent / "extra_norad_ids.txt"
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"
TLE_API_URL = "https://tle.ivanstanojevic.me/api/tle"
GROUPS = ("stations", "visual")
HEADERS = {"User-Agent": "satellite-pass-predictor-snapshot/1.0"}

Snapshot = Dict[str, Dict[str, str]]


def checksum_ok(line: str) -> bool:
    if len(line) != 69 or not line[68].isdigit():
        return False
    total = sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68])
    return total % 10 == int(line[68])


def _http_get(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_3le(text: str) -> Snapshot:
    """Parse CelesTrak's 3-line format: name line, then TLE line 1 and 2."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    found: Snapshot = {}
    for i in range(len(lines) - 2):
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 ") and not name.startswith(("1 ", "2 ")):
            if checksum_ok(l1) and checksum_ok(l2) and l1[2:7] == l2[2:7]:
                found[str(int(l1[2:7]))] = {"name": name.strip(), "line1": l1, "line2": l2}
    return found


def catalog_ids() -> List[int]:
    # Read the IDs straight out of the catalog source so this script stays
    # dependency-free and can't drift from the app's own list.
    text = CATALOG_FILE.read_text(encoding="utf-8")
    return [int(m) for m in re.findall(r"CatalogEntry\(\s*(\d+)\s*,", text)]


def extra_ids() -> List[int]:
    if not EXTRA_IDS_FILE.exists():
        return []
    ids = []
    for raw in EXTRA_IDS_FILE.read_text(encoding="utf-8").splitlines():
        raw = raw.split("#", 1)[0].strip()
        if raw.isdigit():
            ids.append(int(raw))
    return ids


def from_celestrak_group(group: str) -> Snapshot:
    query = urllib.parse.urlencode({"GROUP": group, "FORMAT": "TLE"})
    return parse_3le(_http_get(f"{CELESTRAK_URL}?{query}"))


def from_celestrak_single(norad_id: int) -> Optional[Dict[str, str]]:
    query = urllib.parse.urlencode({"CATNR": norad_id, "FORMAT": "TLE"})
    return parse_3le(_http_get(f"{CELESTRAK_URL}?{query}")).get(str(norad_id))


def from_tle_api(norad_id: int) -> Optional[Dict[str, str]]:
    data = json.loads(_http_get(f"{TLE_API_URL}/{norad_id}"))
    l1, l2 = str(data.get("line1", "")).rstrip(), str(data.get("line2", "")).rstrip()
    if checksum_ok(l1) and checksum_ok(l2) and int(l1[2:7]) == norad_id:
        return {"name": str(data.get("name", f"NORAD {norad_id}")), "line1": l1, "line2": l2}
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    satellites: Snapshot = {}

    for group in GROUPS:
        try:
            got = from_celestrak_group(group)
            satellites.update(got)
            print(f"ok   CelesTrak group {group}: {len(got)} satellites")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"FAIL CelesTrak group {group}: {exc}", file=sys.stderr)
        time.sleep(2.0)

    wanted = sorted(set(catalog_ids()) | set(extra_ids()))
    for norad_id in wanted:
        if str(norad_id) in satellites:
            continue
        entry = None
        try:
            entry = from_celestrak_single(norad_id)
            time.sleep(1.5)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"FAIL CelesTrak {norad_id}: {exc}", file=sys.stderr)
        source = "CelesTrak"
        if entry is None:
            try:
                entry = from_tle_api(norad_id)
                source = "TLE API"
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                print(f"FAIL TLE API {norad_id}: {exc}", file=sys.stderr)
        if entry is not None:
            satellites[str(norad_id)] = entry
            print(f"ok   {norad_id} via {source}")
        else:
            print(f"MISS {norad_id}: no source returned a valid TLE", file=sys.stderr)

    if not satellites:
        print("No satellites fetched - leaving the existing snapshot untouched.", file=sys.stderr)
        return 1

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "satellites": satellites}
    Path(args.out).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(satellites)} satellites to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
