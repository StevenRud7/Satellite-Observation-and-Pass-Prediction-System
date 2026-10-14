"""
Deployment diagnostics: "can this host actually reach what it depends on,
and how fast?"

Exists because the failure mode this answers - CelesTrak being slow or
unreachable *from the hosting provider* while working fine on a laptop - is
invisible from the app's own code and tests. Hitting this one URL on the
deployed backend tells you in seconds which dependency is the problem
instead of guessing from a generic "timed out" error.

All checks run concurrently, each with its own short timeout, so the
endpoint can't hang. Read-only; no secrets in the output.

How to read it:
- `celestrak_default` ok, `celestrak_ipv4_only` ok         -> CelesTrak is fine.
- `celestrak_default` fails/slow but `celestrak_ipv4_only` ok -> IPv6 routing
  problem; keep FORCE_IPV4=true (the default).
- both CelesTrak checks fail but `tle_api` ok               -> CelesTrak is
  blocking/unreachable from this host; the TLE API fallback covers it.
- `tle_snapshot` ok                                         -> the GitHub
  snapshot is reachable and `generated_at` shows how fresh it is.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.data.celestrak import CELESTRAK_GP_URL

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

_CHECK_TIMEOUT = httpx.Timeout(15.0, connect=6.0)
_HEADERS = {"User-Agent": "satellite-pass-predictor/1.0 (diagnostics)"}


def _timed_get(
    url: str, params: Optional[Dict[str, str]] = None, ipv4_only: bool = False
) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        transport = httpx.HTTPTransport(local_address="0.0.0.0") if ipv4_only else None
        with httpx.Client(timeout=_CHECK_TIMEOUT, transport=transport, headers=_HEADERS) as client:
            response = client.get(url, params=params)
        result: Dict[str, Any] = {
            "ok": response.status_code == 200,
            "http_status": response.status_code,
            "seconds": round(time.monotonic() - started, 2),
            "bytes": len(response.content),
        }
        if url.endswith(".json") and response.status_code == 200:
            try:
                result["generated_at"] = response.json().get("generated_at")
                result["satellite_count"] = len(response.json().get("satellites", {}))
            except (ValueError, AttributeError):
                pass
        return result
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
            "seconds": round(time.monotonic() - started, 2),
        }


def _database_check() -> Dict[str, Any]:
    started = time.monotonic()
    try:
        from sqlalchemy import text

        from app.db.session import session_scope

        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return {"ok": True, "seconds": round(time.monotonic() - started, 2)}
    except Exception as exc:  # report, never raise: this is a diagnostic
        return {
            "ok": False,
            "error": type(exc).__name__,
            "seconds": round(time.monotonic() - started, 2),
        }


@router.get("/upstream")
def upstream_check() -> Dict[str, Any]:
    settings = get_settings()
    iss = {"CATNR": "25544", "FORMAT": "2LE"}  # the cheapest realistic CelesTrak call

    checks: Dict[str, Callable[[], Dict[str, Any]]] = {
        "celestrak_default": lambda: _timed_get(CELESTRAK_GP_URL, iss),
        "celestrak_ipv4_only": lambda: _timed_get(CELESTRAK_GP_URL, iss, ipv4_only=True),
        "tle_api": lambda: _timed_get(f"{settings.tle_api_base_url.rstrip('/')}/25544"),
    }
    if settings.tle_snapshot_url:
        snapshot_url = settings.tle_snapshot_url
        checks["tle_snapshot"] = lambda: _timed_get(snapshot_url)
    if settings.database_url:
        checks["database"] = _database_check

    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = {name: pool.submit(fn) for name, fn in checks.items()}
        result: Dict[str, Any] = {name: fut.result() for name, fut in futures.items()}

    if not settings.tle_snapshot_url:
        result["tle_snapshot"] = {"ok": None, "note": "TLE_SNAPSHOT_URL not configured"}
    result["settings"] = {
        "force_ipv4": settings.force_ipv4,
        "tle_api_enabled": settings.tle_api_enabled,
        "prewarm_enabled": settings.prewarm_enabled,
        "snapshot_prefer_max_age_seconds": settings.snapshot_prefer_max_age_seconds,
        "database_configured": bool(settings.database_url),
    }
    return result
