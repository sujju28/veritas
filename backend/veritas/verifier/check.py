"""Independent on-chain check. This module does not import the scoring API."""

from __future__ import annotations

import json
from pathlib import Path
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
from veritas.ledger.ruleset import (
    PINNED_RULESET_REGISTRY_RUNTIME_SHA256,
    RulesetClient,
    ruleset_key,
)
from veritas.risk.manifest import ruleset_manifest_sha256


def verify_on_chain(
    receipt: dict[str, Any],
    trusted_key_registry: dict[str, Any],
    *,
    rpc_url: str,
    chain_id: int,
    contract_address: str,
    runtime_code_sha256: str = PINNED_RUNTIME_SHA256,
    ruleset_registry_address: str | None = None,
    ruleset_code_sha256: str = PINNED_RULESET_REGISTRY_RUNTIME_SHA256,
    manifest_path: Path | None = None,
    allow_unchecked_ruleset: bool = False,
) -> dict[str, Any]:
    offline = verify_offline(receipt, trusted_key_registry)
    decision_id = _decision_id(receipt)
    base: dict[str, Any] = {
        "digest_hex": offline.get("digest_hex"),
        "signing_key_id": offline.get("signing_key_id"),
        "decision_id": decision_id,
        "decision_key": None if decision_id is None else "0x" + decision_key(decision_id).hex(),
        "chain_id": chain_id,
        "contract_address": contract_address,
        "ruleset_registry_address": ruleset_registry_address,
        "ruleset_check": "NOT_CHECKED",
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

    schema_version = offline.get("schema_version", "1.0")
    if schema_version == "1.0":
        base["ruleset_check"] = "NOT_CHECKED"
        return {"status": "VERIFIED_ONCHAIN", **base}

    # Protocol 1.1 ruleset checks
    receipt_ruleset_hash = offline.get("ruleset_sha256")
    payload = receipt.get("payload", {})
    ruleset_ver = payload.get("ruleset_version", "")

    if allow_unchecked_ruleset and not ruleset_registry_address:
        base["ruleset_check"] = "NOT_CHECKED"
        return {"status": "VERIFIED_ONCHAIN", **base}

    if not ruleset_registry_address:
        base["ruleset_check"] = "NOT_CHECKED"
        return {"status": "RULESET_UNCHECKED", **base}

    try:
        ruleset_client = RulesetClient(
            LedgerConfig(
                rpc_url=rpc_url,
                chain_id=chain_id,
                contract_address=ruleset_registry_address,
                runtime_code_sha256=ruleset_code_sha256,
            )
        )
        ruleset_client.validate()
        onchain_ruleset = ruleset_client.get_ruleset(ruleset_key(ruleset_ver))
    except ChainRpcError:
        return {"status": "VERIFICATION_UNAVAILABLE", **base}
    except ChainConfigError, ChainResetError, ChainIdentityError:
        return {"status": "CONFIG_MISMATCH", **base}

    if not onchain_ruleset.exists:
        base["ruleset_check"] = "UNREGISTERED"
        return {"status": "RULESET_UNREGISTERED", **base}

    if onchain_ruleset.manifest_sha256.hex() != receipt_ruleset_hash:
        base["ruleset_check"] = "MISMATCH"
        return {"status": "RULESET_MISMATCH", **base}

    target_manifest = manifest_path
    if target_manifest is None:
        candidate = Path("docs/rulesets") / f"{ruleset_ver}.json"
        if candidate.exists():
            target_manifest = candidate

    if target_manifest is not None:
        if not target_manifest.exists():
            base["ruleset_check"] = "MANIFEST_MISMATCH"
            return {"status": "MANIFEST_MISMATCH", **base}
        try:
            manifest_content = json.loads(target_manifest.read_text(encoding="utf-8"))
            if ruleset_manifest_sha256(manifest_content) != receipt_ruleset_hash:
                base["ruleset_check"] = "MANIFEST_MISMATCH"
                return {"status": "MANIFEST_MISMATCH", **base}
        except Exception:
            base["ruleset_check"] = "MANIFEST_MISMATCH"
            return {"status": "MANIFEST_MISMATCH", **base}

    if onchain_ruleset.deprecated:
        base["ruleset_check"] = "DEPRECATED"
        return {"status": "VERIFIED_ONCHAIN", **base}

    base["ruleset_check"] = "MATCH"
    return {"status": "VERIFIED_ONCHAIN", **base}


def _decision_id(receipt: dict[str, Any]) -> str | None:
    payload = receipt.get("payload")
    if not isinstance(payload, dict):
        return None
    value = payload.get("decision_id")
    if not isinstance(value, str) or not value:
        return None
    return value
