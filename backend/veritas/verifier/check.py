"""Independent on-chain check. This module does not import the scoring API."""

from __future__ import annotations

from typing import Any

from veritas.evidence.verify import SIGNATURE_VALID_OFFLINE, verify_offline
from veritas.ledger.client import (
    ChainConfigError,
    ChainIdentityError,
    ChainResetError,
    ChainRpcError,
    LedgerClient,
    LedgerConfig,
)
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256, decision_key


def verify_on_chain(
    receipt: dict[str, Any],
    trusted_key_registry: dict[str, Any],
    *,
    rpc_url: str,
    chain_id: int,
    contract_address: str,
    runtime_code_sha256: str = PINNED_RUNTIME_SHA256,
) -> dict[str, Any]:
    offline = verify_offline(receipt, trusted_key_registry)
    decision_id = _decision_id(receipt)
    base = {
        "digest_hex": offline.get("digest_hex"),
        "signing_key_id": offline.get("signing_key_id"),
        "decision_id": decision_id,
        "decision_key": None if decision_id is None else "0x" + decision_key(decision_id).hex(),
        "chain_id": chain_id,
        "contract_address": contract_address,
    }
    if offline["status"] != SIGNATURE_VALID_OFFLINE:
        return {"status": offline["status"], **base}
    try:
        client = LedgerClient(
            LedgerConfig(
                rpc_url=rpc_url,
                chain_id=chain_id,
                contract_address=contract_address,
                runtime_code_sha256=runtime_code_sha256,
            )
        )
        client.validate()
        current = client.get_decision(decision_key(decision_id or ""))
    except ChainRpcError:
        return {"status": "VERIFICATION_UNAVAILABLE", **base}
    except ChainConfigError, ChainResetError, ChainIdentityError:
        return {"status": "CONFIG_MISMATCH", **base}
    if not current.exists:
        return {"status": "PENDING_ANCHOR", **base}
    if current.evidence_digest.hex() != offline["digest_hex"]:
        return {"status": "ONCHAIN_MISMATCH", **base}
    return {"status": "VERIFIED_ONCHAIN", **base}


def _decision_id(receipt: dict[str, Any]) -> str | None:
    payload = receipt.get("payload")
    if not isinstance(payload, dict):
        return None
    value = payload.get("decision_id")
    if not isinstance(value, str) or not value:
        return None
    return value
