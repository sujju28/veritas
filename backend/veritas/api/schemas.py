"""Response models for the Phase 01 liveness and readiness routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["veritas"]


class DependencyCheck(BaseModel):
    name: str
    status: Literal["ok", "warning", "failed"]
    detail: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    checks: list[DependencyCheck] = Field(default_factory=list)
