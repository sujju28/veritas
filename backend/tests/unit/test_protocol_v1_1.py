"""Tests for Protocol 1.1 evidence schema, validation rules, and compatibility (RSR-06, RSR-07)."""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from veritas.evidence.models import EvidencePayload, SourceRef
from veritas.evidence.sign import sign_payload
from veritas.evidence.verify import verify_offline
from veritas.risk.manifest import ruleset_manifest_sha256

_KEY_HEX = "11" * 32
_DIGEST = "aa" * 32


def _make_key_and_registry() -> tuple[Ed25519PrivateKey, dict[str, object], str]:
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes_raw()
    import base64

    pub_b64 = base64.b64encode(public_bytes).decode("ascii")
    key_id = "test-issuer-1"
    registry = {
        "keys": [
            {
                "key_id": key_id,
                "algorithm": "Ed25519",
                "public_key_b64": pub_b64,
            }
        ]
    }
    return private_key, registry, key_id


def test_protocol_1_1_valid_receipt() -> None:
    priv, reg, key_id = _make_key_and_registry()
    manifest_hash = ruleset_manifest_sha256()

    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-101",
        transaction_id="txn-101",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256=_DIGEST,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _text = sign_payload(payload, priv, key_id)
    result = verify_offline(receipt.model_dump(), reg)
    assert result["status"] == "SIGNATURE_VALID_OFFLINE"
    assert result["schema_version"] == "1.1"
    assert result["ruleset_sha256"] == manifest_hash


def test_protocol_1_1_with_source_ref() -> None:
    priv, reg, key_id = _make_key_and_registry()
    manifest_hash = ruleset_manifest_sha256()

    source = SourceRef(
        chain_id=31337,
        block_number=42,
        tx_hash="0x" + "bb" * 32,
        log_index=1,
    )
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-102",
        transaction_id="txn-102",
        bank_id="BANK_A",
        decision="HIGH",
        risk_score=85,
        reason_codes=["FAN_OUT"],
        feature_snapshot_sha256=_DIGEST,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
        source_ref=source,
    )
    receipt, _text = sign_payload(payload, priv, key_id)
    result = verify_offline(receipt.model_dump(), reg)
    assert result["status"] == "SIGNATURE_VALID_OFFLINE"
    assert result["source_ref"] == source.model_dump()


def test_protocol_1_1_missing_ruleset_sha256_is_malformed() -> None:
    _, reg, _ = _make_key_and_registry()
    bad_receipt = {
        "payload": {
            "schema_version": "1.1",
            "decision_id": "dec-103",
            "transaction_id": "txn-103",
            "bank_id": "BANK_A",
            "decision": "LOW",
            "risk_score": 10,
            "reason_codes": ["FAN_IN"],
            "feature_snapshot_sha256": _DIGEST,
            "model_version": "rule-only",
            "ruleset_version": "rules-v1",
            "decision_timestamp": "2026-10-20T12:00:00Z",
            # missing ruleset_sha256
        },
        "digest_hex": _DIGEST,
        "signature_b64": "AAAA",
        "signing_key_id": "test-issuer-1",
        "signature_algorithm": "Ed25519",
    }
    result = verify_offline(bad_receipt, reg)
    assert result["status"] == "MALFORMED"


def test_protocol_1_0_with_ruleset_sha256_is_malformed() -> None:
    _, reg, _ = _make_key_and_registry()
    bad_receipt = {
        "payload": {
            "schema_version": "1.0",
            "decision_id": "dec-104",
            "transaction_id": "txn-104",
            "bank_id": "BANK_A",
            "decision": "LOW",
            "risk_score": 10,
            "reason_codes": ["FAN_IN"],
            "feature_snapshot_sha256": _DIGEST,
            "model_version": "rule-only",
            "ruleset_version": "rules-v1",
            "ruleset_sha256": ruleset_manifest_sha256(),  # forbidden in 1.0
            "decision_timestamp": "2026-10-20T12:00:00Z",
        },
        "digest_hex": _DIGEST,
        "signature_b64": "AAAA",
        "signing_key_id": "test-issuer-1",
        "signature_algorithm": "Ed25519",
    }
    result = verify_offline(bad_receipt, reg)
    assert result["status"] == "MALFORMED"


def test_schema_version_1_2_is_malformed_rsr_07() -> None:
    _, reg, _ = _make_key_and_registry()
    bad_receipt = {
        "payload": {
            "schema_version": "1.2",
            "decision_id": "dec-105",
            "transaction_id": "txn-105",
            "bank_id": "BANK_A",
            "decision": "LOW",
            "risk_score": 10,
            "reason_codes": ["FAN_IN"],
            "feature_snapshot_sha256": _DIGEST,
            "model_version": "rule-only",
            "ruleset_version": "rules-v1",
            "ruleset_sha256": ruleset_manifest_sha256(),
            "decision_timestamp": "2026-10-20T12:00:00Z",
        },
        "digest_hex": _DIGEST,
        "signature_b64": "AAAA",
        "signing_key_id": "test-issuer-1",
        "signature_algorithm": "Ed25519",
    }
    result = verify_offline(bad_receipt, reg)
    assert result["status"] == "MALFORMED"


def test_golden_1_0_backwards_compatibility_rsr_06() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "golden_receipt_v1_0.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    receipt = data["receipt"]
    registry = data["trust_registry"]

    result = verify_offline(receipt, registry)
    assert result["status"] == "SIGNATURE_VALID_OFFLINE"
    assert result["schema_version"] == "1.0"
    assert result.get("ruleset_sha256") is None
