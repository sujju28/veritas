"""Signed receipts: canonical equivalence, tamper rejection, and offline verification."""

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from veritas.api.app import create_app
from veritas.api.settings import Settings
from veritas.evidence.canonical import CanonicalError, canonical_bytes
from veritas.evidence.keys import (
    SigningKeyError,
    ensure_signing_key,
    load_private_key,
    load_trust_registry,
    registry_path_for,
)
from veritas.evidence.models import EvidencePayload
from veritas.evidence.sign import sign_payload
from veritas.evidence.verify import verify_offline
from veritas.simulator.store import seed_database

_DIGEST = "ab" * 32


def _payload(**overrides: object) -> EvidencePayload:
    raw: dict[str, object] = {
        "schema_version": "1.0",
        "decision_id": "dec-001",
        "transaction_id": "txn-001",
        "bank_id": "BANK_A",
        "decision": "REVIEW",
        "risk_score": 68,
        "reason_codes": ["HIGH_VELOCITY", "FAN_OUT"],
        "feature_snapshot_sha256": _DIGEST,
        "model_version": "rule-only",
        "ruleset_version": "rules-v1",
        "decision_timestamp": "2026-10-19T14:00:00Z",
    }
    raw.update(overrides)
    return EvidencePayload.model_validate(raw)


def _signed(
    tmp_path: Path,
    payload: EvidencePayload | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    receipt, _text = sign_payload(
        payload or _payload(),
        load_private_key(key_path),
        "issuer-local-1",
    )
    registry = load_trust_registry(registry_path_for(key_path)).model_dump()
    return receipt.model_dump(), registry


def test_field_order_unicode_and_number_form_share_bytes() -> None:
    body = _payload().model_dump()
    reordered = {key: body[key] for key in reversed(list(body))}
    assert canonical_bytes(body) == canonical_bytes(reordered)
    assert canonical_bytes({"risk_score": 68}) == canonical_bytes({"risk_score": 68.0})
    assert canonical_bytes({"bank_id": "A\u0301"}) == canonical_bytes({"bank_id": "Á"})
    forward = _payload(reason_codes=["FAN_OUT", "HIGH_VELOCITY"])
    backward = _payload(reason_codes=["HIGH_VELOCITY", "FAN_OUT"])
    assert canonical_bytes(forward.model_dump()) == canonical_bytes(backward.model_dump())


def test_non_finite_numbers_are_rejected() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        try:
            canonical_bytes({"risk_score": value})
        except CanonicalError:
            continue
        raise AssertionError(value)


def test_offline_verifier_accepts_original_and_rejects_tampering(tmp_path: Path) -> None:
    receipt, registry = _signed(tmp_path)
    first = verify_offline(receipt, registry)
    second = verify_offline(receipt, registry)
    assert first["status"] == "SIGNATURE_VALID_OFFLINE"
    assert second == first
    assert "VERIFIED_ONCHAIN" not in first["status"]
    altered_score = {**receipt, "payload": {**receipt["payload"], "risk_score": 1}}
    altered_reasons = {
        **receipt,
        "payload": {**receipt["payload"], "reason_codes": ["TAMPER"]},
    }
    altered_time = {
        **receipt,
        "payload": {**receipt["payload"], "decision_timestamp": "2026-10-19T14:00:01Z"},
    }
    altered_id = {**receipt, "payload": {**receipt["payload"], "decision_id": "dec-other"}}
    assert verify_offline(altered_score, registry)["status"] == "TAMPERED"
    assert verify_offline(altered_reasons, registry)["status"] == "TAMPERED"
    assert verify_offline(altered_time, registry)["status"] == "TAMPERED"
    assert verify_offline(altered_id, registry)["status"] == "TAMPERED"
    with_amount = {**receipt, "payload": {**receipt["payload"], "amount_minor": 10}}
    assert verify_offline(with_amount, registry)["status"] == "MALFORMED"


def test_substituted_signature_and_unknown_signer(tmp_path: Path) -> None:
    receipt, registry = _signed(tmp_path)
    other, _other_registry = _signed(tmp_path / "other", _payload(decision_id="dec-002"))
    swapped = {**receipt, "signature_b64": other["signature_b64"]}
    assert verify_offline(swapped, registry)["status"] == "INVALID_SIGNATURE"
    renamed = {**receipt, "signing_key_id": "issuer-other"}
    assert verify_offline(renamed, registry)["status"] == "UNKNOWN_ISSUER"
    foreign = {**other, "signing_key_id": "issuer-local-1"}
    assert verify_offline(foreign, registry)["status"] == "INVALID_SIGNATURE"


def test_equivalent_unicode_still_verifies(tmp_path: Path) -> None:
    receipt, registry = _signed(tmp_path, _payload(bank_id="Á"))
    copied = {**receipt, "payload": {**receipt["payload"], "bank_id": "A\u0301"}}
    assert verify_offline(copied, registry)["status"] == "SIGNATURE_VALID_OFFLINE"
    changed = {**receipt, "payload": {**receipt["payload"], "bank_id": "BANK_B"}}
    assert verify_offline(changed, registry)["status"] == "TAMPERED"


def test_digest_matches_across_processes() -> None:
    body = _payload().model_dump()
    expected = hashlib.sha256(canonical_bytes(body)).hexdigest()
    code = (
        "import hashlib\n"
        "from veritas.evidence.canonical import canonical_bytes\n"
        f"body = {body!r}\n"
        "print(hashlib.sha256(canonical_bytes(body)).hexdigest())\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == expected


def test_private_key_mode_and_public_registry(tmp_path: Path) -> None:
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == 0o600
    registry_text = registry_path_for(key_path).read_text(encoding="utf-8")
    assert "PRIVATE KEY" not in registry_text
    os.chmod(key_path, 0o644)
    try:
        load_private_key(key_path)
    except SigningKeyError:
        return
    raise AssertionError("world-readable key was accepted")


def test_exported_receipt_verifies_and_a_copy_does_not(tmp_path: Path) -> None:
    db_path = tmp_path / "score.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    settings = Settings(
        db_path=db_path,
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "receipt"},
        )
        decision_id = created.json()["decision_id"]
        exported = client.get(f"/api/v1/decisions/{decision_id}/receipt")
        replay = client.get(f"/api/v1/decisions/{decision_id}/receipt")
    assert exported.status_code == 200
    receipt = exported.json()
    assert replay.json()["digest_hex"] == receipt["digest_hex"]
    assert receipt["payload"]["bank_id"] == "BANK_B"
    assert receipt["payload"]["risk_score"] == created.json()["risk_score"]
    assert "PRIVATE KEY" not in exported.text
    assert "public_key" not in receipt
    registry = load_trust_registry(registry_path_for(key_path)).model_dump()
    assert verify_offline(receipt, registry)["status"] == "SIGNATURE_VALID_OFFLINE"
    tampered = {**receipt, "payload": {**receipt["payload"], "risk_score": 0}}
    assert verify_offline(tampered, registry)["status"] == "TAMPERED"
    assert verify_offline(receipt, registry)["status"] == "SIGNATURE_VALID_OFFLINE"


def test_signing_crash_leaves_no_decision(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "crash.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")

    def _crash(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("crash before commit")

    monkeypatch.setattr("veritas.decisions.service.sign_payload", _crash)
    from veritas.decisions.service import evaluate_transaction
    from veritas.storage.db import connect

    try:
        evaluate_transaction(
            db_path,
            transaction_id="txn-000007",
            idempotency_key="crash",
            scoring_mode="rule_only",
            signing_key_path=key_path,
            signing_key_id="issuer-local-1",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("crash was swallowed")
    with connect(db_path) as connection:
        decisions = connection.execute("SELECT COUNT(*) AS total FROM decisions").fetchone()[
            "total"
        ]
        receipts = connection.execute("SELECT COUNT(*) AS total FROM evidence_receipts").fetchone()[
            "total"
        ]
        jobs = connection.execute("SELECT COUNT(*) AS total FROM anchor_outbox").fetchone()["total"]
    assert decisions == 0
    assert receipts == 0
    assert jobs == 0


def test_verifier_module_does_not_import_the_api() -> None:
    source = Path(__file__).resolve().parents[2] / "veritas" / "evidence" / "verify.py"
    text = source.read_text(encoding="utf-8")
    assert "veritas.api" not in text
    assert "fastapi" not in text
    ignore = Path(__file__).resolve().parents[3] / ".gitignore"
    assert ".local/" in ignore.read_text(encoding="utf-8")
