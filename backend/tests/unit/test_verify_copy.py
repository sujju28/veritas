"""The dashboard verify route checks a copy and leaves the stored receipt alone."""

from pathlib import Path

from fastapi.testclient import TestClient
from veritas.api.app import create_app
from veritas.api.settings import Settings
from veritas.evidence.keys import ensure_signing_key
from veritas.simulator.store import seed_database


def test_tampered_copy_fails_and_stored_receipt_stays(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    settings = Settings(
        db_path=db_path,
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
        contract_address="",
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "dash"},
        )
        decision_id = created.json()["decision_id"]
        original = client.get(f"/api/v1/decisions/{decision_id}/receipt")
        copied = original.json()
        copied["payload"]["risk_score"] = 1
        checked = client.post("/api/v1/verify", json=copied)
        again = client.get(f"/api/v1/decisions/{decision_id}/receipt")
        leaked = client.post("/api/v1/verify", json={**original.json(), "private_key": "secret"})
    assert checked.status_code == 200
    assert checked.json()["status"] == "TAMPERED"
    assert checked.json()["stored"] is False
    assert again.json()["digest_hex"] == original.json()["digest_hex"]
    assert again.json()["payload"]["risk_score"] == original.json()["payload"]["risk_score"]
    assert leaked.status_code == 422
    assert "secret" not in leaked.text
