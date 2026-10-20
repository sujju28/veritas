"""Version 1 evidence payload. The receipt does not carry a trust anchor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

SIGNATURE_ALGORITHM = "Ed25519"
_HEX64 = r"^[0-9a-f]{64}$"
_UTC = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


class EvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    decision_id: str = Field(min_length=1, max_length=80)
    transaction_id: str = Field(min_length=1, max_length=80)
    bank_id: str = Field(min_length=1, max_length=32)
    decision: str = Field(pattern=r"^(LOW|REVIEW|HIGH)$")
    risk_score: int = Field(ge=0, le=100)
    reason_codes: list[str] = Field(max_length=16)
    feature_snapshot_sha256: str = Field(pattern=_HEX64)
    model_version: str = Field(min_length=1, max_length=64)
    ruleset_version: str = Field(min_length=1, max_length=64)
    decision_timestamp: str = Field(pattern=_UTC)

    @field_validator("reason_codes")
    @classmethod
    def reason_codes_are_sorted_tokens(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("reason codes must be non-empty")
        return sorted(set(cleaned))


class EvidenceReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: EvidencePayload
    digest_hex: str = Field(pattern=_HEX64)
    signature_b64: str = Field(min_length=1, max_length=256)
    signing_key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    signature_algorithm: str = Field(pattern=r"^Ed25519$")
