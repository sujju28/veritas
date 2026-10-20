"""Liveness ignores the chain and the database. Readiness checks SQLite only."""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from veritas.api.schemas import DependencyCheck, HealthResponse, ReadyResponse
from veritas.api.settings import Settings
from veritas.storage import check_sqlite

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="veritas")


@router.get("/ready", response_model=ReadyResponse)
def ready(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    checks: list[DependencyCheck] = []
    try:
        check_sqlite(settings.db_path)
    except OSError, sqlite3.Error:
        checks.append(
            DependencyCheck(
                name="sqlite",
                status="failed",
                detail="Local SQLite database is unavailable",
            )
        )
    else:
        checks.append(
            DependencyCheck(
                name="sqlite",
                status="ok",
                detail="Local SQLite database opened",
            )
        )
    checks.append(
        DependencyCheck(
            name="chain",
            status="warning",
            detail="Chain RPC is not consulted. A missing local chain does not affect liveness.",
        )
    )
    status: Literal["ready", "degraded", "not_ready"]
    if any(item.status == "failed" for item in checks):
        status = "not_ready"
        status_code = 503
    elif any(item.status == "warning" for item in checks):
        status = "degraded"
        status_code = 200
    else:
        status = "ready"
        status_code = 200
    payload = ReadyResponse(status=status, checks=checks)
    return JSONResponse(status_code=status_code, content=payload.model_dump())
