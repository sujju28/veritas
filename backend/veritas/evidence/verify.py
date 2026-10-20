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
        raw = canonical_bytes(parsed.payload.model_dump())
    except ValidationError, CanonicalError, SigningKeyError:
        return _result("MALFORMED", None, None)
    digest_hex = hashlib.sha256(raw).hexdigest()
    if digest_hex != parsed.digest_hex:
        return _result("TAMPERED", digest_hex, parsed.signing_key_id)
    pinned = next((item for item in registry.keys if item.key_id == parsed.signing_key_id), None)
    if pinned is None or pinned.algorithm != parsed.signature_algorithm:
        return _result("UNKNOWN_ISSUER", digest_hex, parsed.signing_key_id)
    try:
        signature = base64.b64decode(parsed.signature_b64, validate=True)
        public_key_from_b64(pinned.public_key_b64).verify(signature, raw)
    except InvalidSignature, SigningKeyError, ValueError:
        return _result("INVALID_SIGNATURE", digest_hex, parsed.signing_key_id)
    return _result(SIGNATURE_VALID_OFFLINE, digest_hex, parsed.signing_key_id)


def _result(status: str, digest_hex: str | None, signing_key_id: str | None) -> dict[str, Any]:
    return {
        "status": status,
        "digest_hex": digest_hex,
        "signing_key_id": signing_key_id,
    }
