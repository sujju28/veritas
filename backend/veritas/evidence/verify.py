"""Offline receipt check. This module does not import the API or a chain client.

A passing result is SIGNATURE_VALID_OFFLINE. It is not an on-chain verification.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.exceptions import InvalidSignature
from pydantic import ValidationError

from veritas.evidence.canonical import CanonicalError, canonical_bytes
from veritas.evidence.keys import SigningKeyError, TrustRegistry, public_key_from_b64
from veritas.evidence.models import EvidenceReceipt

SIGNATURE_VALID_OFFLINE = "SIGNATURE_VALID_OFFLINE"


def verify_offline(receipt: dict[str, Any], trusted_key_registry: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = EvidenceReceipt.model_validate(receipt)
        registry = TrustRegistry.model_validate(trusted_key_registry)
        raw = canonical_bytes(parsed.payload.model_dump(exclude_none=True))
    except ValidationError, CanonicalError, SigningKeyError:
        return _result("MALFORMED", None, None)
    digest_hex = hashlib.sha256(raw).hexdigest()
    if digest_hex != parsed.digest_hex:
        return _result(
            "TAMPERED",
            digest_hex,
            parsed.signing_key_id,
            schema_version=parsed.payload.schema_version,
            ruleset_sha256=parsed.payload.ruleset_sha256,
        )
    pinned = next((item for item in registry.keys if item.key_id == parsed.signing_key_id), None)
    if pinned is None or pinned.algorithm != parsed.signature_algorithm:
        return _result(
            "UNKNOWN_ISSUER",
            digest_hex,
            parsed.signing_key_id,
            schema_version=parsed.payload.schema_version,
            ruleset_sha256=parsed.payload.ruleset_sha256,
        )
    try:
        signature = base64.b64decode(parsed.signature_b64, validate=True)
        public_key_from_b64(pinned.public_key_b64).verify(signature, raw)
    except InvalidSignature, SigningKeyError, ValueError:
        return _result(
            "INVALID_SIGNATURE",
            digest_hex,
            parsed.signing_key_id,
            schema_version=parsed.payload.schema_version,
            ruleset_sha256=parsed.payload.ruleset_sha256,
        )
    return _result(
        SIGNATURE_VALID_OFFLINE,
        digest_hex,
        parsed.signing_key_id,
        schema_version=parsed.payload.schema_version,
        ruleset_sha256=parsed.payload.ruleset_sha256,
        source_ref=parsed.payload.source_ref.model_dump() if parsed.payload.source_ref else None,
    )


def _result(
    status: str,
    digest_hex: str | None,
    signing_key_id: str | None,
    *,
    schema_version: str | None = None,
    ruleset_sha256: str | None = None,
    source_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    res: dict[str, Any] = {
        "status": status,
        "digest_hex": digest_hex,
        "signing_key_id": signing_key_id,
    }
    if schema_version is not None:
        res["schema_version"] = schema_version
    if ruleset_sha256 is not None:
        res["ruleset_sha256"] = ruleset_sha256
    if source_ref is not None:
        res["source_ref"] = source_ref
    return res
