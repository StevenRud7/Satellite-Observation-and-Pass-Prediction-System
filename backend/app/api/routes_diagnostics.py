"""
Deployment diagnostics: "can this host actually reach what it depends on,
and how fast?"

Exists because the failure mode this answers - CelesTrak being slow or
unreachable *from the hosting provider* while working fine on a laptop - is
invisible from the app's own code and tests. Hitting this one URL on the
deployed backend tells you in seconds which dependency is the problem
instead of guessing from a generic "timed out" error.

Read-only, no secrets in the output, and each check has its own short
timeout so the endpoint itself can't hang.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import httpx
from fastapi import APIRouter

from app.api.deps import get_tle_snapshot_client
from app.core.config import get_settings
from app.data.celestrak import CELESTRAK_GP_URL

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

_CHECK_TIMEOUT = httpx.Timeout(20.0, connect=8.0)


def _timed_get(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        response = httpx.get(url, params=params, timeout=_CHECK_TIMEOUT)
        return {
            "ok": response.status_code == 200,
            "http_status": response.status_code,
            "seconds": round(time.monotonic() - started, 2),
            "bytes": len(response.content),
        }
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
            "seconds": round(time.monotonic() - started, 2),
        }


@router.get("/upstream")
def upstream_check() -> Dict[str, Any]:
    settings = get_settings()
    result: Dict[str, Any] = {
        # A single small TLE request - the cheapest realistic CelesTrak call.
        "celestrak_iss_tle": _timed_get(CELESTRAK_GP_URL, {"CATNR": "25544", "FORMAT": "2LE"}),
    }

    snapshot = get_tle_snapshot_client()
    if snapshot.enabled and settings.tle_snapshot_url:
        result["tle_snapshot"] = _timed_get(settings.tle_snapshot_url, {})
    else:
        result["tle_snapshot"] = {"ok": None, "note": "TLE_SNAPSHOT_URL not configured"}

    result["database_configured"] = bool(settings.database_url)
    if settings.database_url:
        started = time.monotonic()
        try:
            from sqlalchemy import text

            from app.db.session import session_scope

            with session_scope() as session:
                session.execute(text("SELECT 1"))
            result["database"] = {"ok": True, "seconds": round(time.monotonic() - started, 2)}
        except Exception as exc:  # report, never raise: this is a diagnostic
            result["database"] = {
                "ok": False,
                "error": type(exc).__name__,
                "seconds": round(time.monotonic() - started, 2),
            }
    return result
