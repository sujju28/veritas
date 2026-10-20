"""Opaque on-chain key. The preimage is the decision id, not account data."""

from __future__ import annotations

import hashlib

PINNED_RUNTIME_SHA256 = "9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db"
DECISION_PREFIX = b"VERITAS:DECISION:"


def decision_key(decision_id: str) -> bytes:
    if not decision_id or len(decision_id) > 80:
        raise ValueError("decision id is missing")
    return hashlib.sha256(DECISION_PREFIX + decision_id.encode("utf-8")).digest()
