"""Sign the canonical payload bytes. The digest is SHA-256 of those same bytes."""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas.evidence.canonical import canonical_bytes
from veritas.evidence.models import SIGNATURE_ALGORITHM, EvidencePayload, EvidenceReceipt


def sign_payload(
    payload: EvidencePayload,
    private_key: Ed25519PrivateKey,
    key_id: str,
) -> tuple[EvidenceReceipt, str]:
    raw = canonical_bytes(payload.model_dump(exclude_none=True))
    digest_hex = hashlib.sha256(raw).hexdigest()
    signature = private_key.sign(raw)
    receipt = EvidenceReceipt(
        payload=payload,
        digest_hex=digest_hex,
        signature_b64=base64.b64encode(signature).decode("ascii"),
        signing_key_id=key_id,
        signature_algorithm=SIGNATURE_ALGORITHM,
    )
    return receipt, raw.decode("utf-8")
