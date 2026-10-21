"""Regression test to guarantee golden schema_version 1.0 receipts remain valid."""

import json
from pathlib import Path

from veritas.evidence.verify import verify_offline


def test_golden_v1_0_receipt_verifies() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "golden_receipt_v1_0.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    receipt = data["receipt"]
    registry = data["trust_registry"]

    result = verify_offline(receipt, registry)
    assert result["status"] == "SIGNATURE_VALID_OFFLINE"
    assert result["digest_hex"] == receipt["digest_hex"]

    tampered = {**receipt, "payload": {**receipt["payload"], "risk_score": 99}}
    tampered_result = verify_offline(tampered, registry)
    assert tampered_result["status"] == "TAMPERED"
