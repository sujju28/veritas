"""Version 1 evidence payload. The receipt does not carry a trust anchor.

Supports Protocol 1.0 and 1.1 schemas. Protocol 1.1 requires ruleset_sha256
and optionally supports source_ref for on-chain provenance.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SIGNATURE_ALGORITHM = "Ed25519"
_HEX64 = r"^[0-9a-f]{64}$"
_UTC = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chain_id: int = Field(gt=0)
    block_number: int = Field(ge=0)
    tx_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")
    log_index: int = Field(ge=0)


class EvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^1\.[01]$")
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
    ruleset_sha256: str | None = Field(default=None, pattern=_HEX64)
    source_ref: SourceRef | None = None

    @field_validator("reason_codes")
    @classmethod
    def reason_codes_are_sorted_tokens(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("reason codes must be non-empty")
        return sorted(set(cleaned))

    @model_validator(mode="after")
    def validate_protocol_rules(self) -> Self:
        if self.schema_version == "1.0":
            if self.ruleset_sha256 is not None:
                raise ValueError("ruleset_sha256 is forbidden in schema version 1.0")
            if self.source_ref is not None:
                raise ValueError("source_ref is forbidden in schema version 1.0")
        elif self.schema_version == "1.1":
            if self.ruleset_sha256 is None:
                raise ValueError("ruleset_sha256 is required in schema version 1.1")
        return self


class EvidenceReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: EvidencePayload
    digest_hex: str = Field(pattern=_HEX64)
    signature_b64: str = Field(min_length=1, max_length=256)
    signing_key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    signature_algorithm: str = Field(pattern=r"^Ed25519$")
