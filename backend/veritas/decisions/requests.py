"""Decision request contract. Ground-truth labels are not accepted here."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScoringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
